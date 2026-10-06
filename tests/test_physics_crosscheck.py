"""Independent textbook cross-check of the analytical inductor tool.

These tests re-derive CCM buck/boost, gapped/powder magnetics, Steinmetz,
Dowell, DCR, and the 2-node thermal iteration from first principles and
compare them to package outputs.  They do not copy implementation internals
beyond public APIs.
"""
from __future__ import annotations

import math

import pytest

from inductor_design.converter.buck import BuckSpec, size_buck
from inductor_design.converter.boost import BoostSpec, size_boost
from inductor_design.cores import CORES
from inductor_design.materials import MATERIALS
from inductor_design.wires import solid_wire, litz_wire, skin_depth_m
from inductor_design.sizing import (
    required_turns_gapped,
    achievable_inductance_gapped,
    required_turns_powder,
    achievable_inductance_powder,
    compute_flux,
    fill_factor,
)
from inductor_design.losses import core_loss_w, winding_loss, _dowell_fr
from inductor_design.thermal import thermal_estimate, natural_convection_h
from inductor_design.optimizer.search import design_buck, design_boost

MU0 = 4.0 * math.pi * 1e-7
RHO_CU_20 = 1.724e-8
ALPHA_CU = 3.93e-3


def _rel(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-30)


def test_buck_ccm_matches_textbook_at_eta_1():
    vin_min, vin_max, vout, iout, fsw, r = 9.0, 16.0, 3.3, 5.0, 500e3, 0.3
    op = size_buck(BuckSpec(vin_min, vin_max, vout, iout, fsw, r, efficiency=1.0))
    d_min = vout / vin_max
    d_max = vout / vin_min
    di = r * iout
    l_off = vout * (1.0 - d_min) / (di * fsw)
    l_on = (vin_max - vout) * d_min / (di * fsw)
    assert op.duty_min == pytest.approx(d_min)
    assert op.duty_max == pytest.approx(d_max)
    assert op.l_min == pytest.approx(l_off)
    assert l_on == pytest.approx(l_off)
    assert op.i_peak == pytest.approx(iout + 0.5 * di)
    assert op.i_rms == pytest.approx(math.sqrt(iout**2 + di**2 / 12.0))
    assert op.volt_seconds == pytest.approx((vin_max - vout) * d_min / fsw)


def test_buck_on_off_voltseconds_diverge_when_eta_not_one():
    """Documented limitation: η inflates D, so OFF-interval L ≠ ON-interval L."""
    op = size_buck(BuckSpec(9, 16, 3.3, 5, 500e3, 0.3, efficiency=0.92))
    d_min = 3.3 / (16.0 * 0.92)
    l_off = 3.3 * (1.0 - d_min) / (0.3 * 5.0 * 500e3)
    l_on = (16.0 - 3.3) * d_min / (0.3 * 5.0 * 500e3)
    assert op.l_min == pytest.approx(l_off)
    assert _rel(l_on, l_off) == pytest.approx(0.1008, rel=1e-3)


def test_boost_ccm_and_input_current_includes_efficiency():
    spec = BoostSpec(10, 14, 24, 2, 300e3, 0.3, efficiency=0.92)
    op = size_boost(spec)
    d_max = 1.0 - (10.0 * 0.92) / 24.0
    i_l = 2.0 / (1.0 - d_max)
    assert i_l == pytest.approx(2.0 * 24.0 / (10.0 * 0.92))
    assert op.i_l_avg_worst == pytest.approx(i_l)
    di = 0.3 * i_l
    assert op.l_min == pytest.approx((10.0 * d_max) / (di * 300e3))
    assert op.i_peak == pytest.approx(i_l + 0.5 * di)


def test_gapped_ferrite_l_equals_mu0_n2_ae_over_gap():
    core = CORES["PQ2625"]
    n, gap = required_turns_gapped(core, 10e-6, 0.3, 10.0)
    assert n == math.ceil(10e-6 * 10.0 / (0.3 * core.ae_m2))
    assert gap == pytest.approx(MU0 * core.ae_m2 * n**2 / 10e-6)
    assert achievable_inductance_gapped(core, n, gap) == pytest.approx(10e-6)


def test_powder_l_equals_mu0_mur_n2_ae_over_le():
    core, mat = CORES["T80"], MATERIALS["KoolMu_60"]
    n = required_turns_powder(core, mat, 10e-6)
    al = MU0 * mat.mu_r * core.ae_m2 / core.le_m
    assert n == math.ceil(math.sqrt(10e-6 / al))
    assert achievable_inductance_powder(core, mat, n) == pytest.approx(al * n**2)
    assert achievable_inductance_powder(core, mat, n) >= 10e-6 * 0.999


def test_flux_peak_and_half_swing():
    core = CORES["PQ2625"]
    bpk, bac = compute_flux(30, core.ae_m2, i_peak=10.0, delta_i_pp=2.0, inductance_h=20e-6)
    assert bpk == pytest.approx(20e-6 * 10.0 / (30 * core.ae_m2))
    assert bac == pytest.approx(20e-6 * 2.0 / (2.0 * 30 * core.ae_m2))
    assert bpk / bac == pytest.approx(10.0)


def test_steinmetz_and_skin_depth():
    n87, core = MATERIALS["N87"], CORES["PQ2625"]
    f, bac = 500e3, 0.08
    expected = n87.k * (f**n87.alpha) * (bac**n87.beta) * core.ve_m3
    assert core_loss_w(n87, bac, f, core.ve_m3) == pytest.approx(expected)
    rho = RHO_CU_20 * (1.0 + ALPHA_CU * (70.0 - 20.0))
    delta = math.sqrt(rho / (math.pi * f * MU0))
    assert skin_depth_m(f, 70.0) == pytest.approx(delta)
    assert 0.09e-3 < delta < 0.12e-3  # ~0.10 mm for Cu @ 500 kHz, 70 C


def test_dowell_and_winding_dcr():
    wire = solid_wire(20)
    core = CORES["PQ2625"]
    delta = wire.cu_diameter_m / skin_depth_m(500e3, 70.0)
    x = delta
    sh2, si2 = math.sinh(2 * x), math.sin(2 * x)
    ch2, co2 = math.cosh(2 * x), math.cos(2 * x)
    fr_ref = x * ((sh2 + si2) / (ch2 - co2) + (2.0 / 3.0) * (2**2 - 1) * (sh2 - si2) / (ch2 + co2))
    assert _dowell_fr(delta, 2) == pytest.approx(max(1.0, fr_ref))
    wl = winding_loss(wire, 12, core.mlt_m, i_dc=5.0, delta_i_pp=1.5, f_hz=500e3, layers=2, temp_c=70)
    rho = RHO_CU_20 * (1.0 + ALPHA_CU * 50.0)
    rdc = rho * core.mlt_m * 12 / wire.area_cu_m2
    assert wl.r_dc == pytest.approx(rdc)
    i_ac = 1.5 / (2.0 * math.sqrt(3.0))
    assert wl.p_dc == pytest.approx(5.0**2 * wl.r_dc)
    assert wl.p_ac == pytest.approx(i_ac**2 * wl.r_ac)


def test_thermal_two_node_independent_iteration():
    core = CORES["PQ2625"]
    p_c, p_cu = 0.4, 0.6
    surf, L = core.surface_m2, core.height_mm * 1e-3
    dt = 40.0
    for _ in range(8):
        h = max(5.0, 1.42 * (dt / L) ** 0.25)
        dt_new = (p_c + p_cu) / (h * surf)
        if abs(dt_new - dt) < 0.05:
            dt = dt_new
            break
        dt = dt_new
    th = thermal_estimate(p_c, p_cu, surf, L, 25.0)
    assert th.t_surface_c - 25.0 == pytest.approx(dt, rel=1e-3)
    assert th.t_hotspot_c == pytest.approx(th.t_surface_c + p_cu * 3.0)
    assert natural_convection_h(40.0, 0.02) == pytest.approx(max(5.0, 1.42 * (40 / 0.02) ** 0.25))


def test_litz_window_area_is_bundle_not_strands_times_bundle():
    litz = litz_wire(38, 40)
    bundle = math.pi * (litz.outer_diameter_m / 2.0) ** 2
    assert litz.outer_area_m2 == pytest.approx(bundle)
    core = CORES["PQ2016"]
    ff = fill_factor(core, litz, turns=2)
    assert 0.0 < ff < 0.4  # previously ~1.37 because of *strands


def test_end_to_end_buck_boost_physical_sanity():
    buck = design_buck(BuckSpec(9, 16, 3.3, 5, 500e3, 0.3, 0.92), max_temp_rise=60, max_fill=0.4)
    boost = design_boost(BoostSpec(10, 14, 24, 2, 300e3, 0.3, 0.92), max_temp_rise=60, max_fill=0.4)
    assert buck.best is not None and boost.best is not None
    assert buck.all_candidates_evaluated == 540
    assert buck.feasible_count > 0 and boost.feasible_count > 0
    for result in (buck, boost):
        b = result.best
        assert b.inductance_h >= 0.9 * result.operating_point["target_l"]
        assert b.saturation_margin >= -1e-9
        assert 0 < b.fill <= 0.4 + 1e-9
        assert b.p_total_w == pytest.approx(b.p_core_w + b.p_cu_w)
        assert 0 < b.temperature_rise_c <= 60.0 + 1e-6
    losses = [c.p_total_w for c in buck.pareto]
    assert losses == sorted(losses)
