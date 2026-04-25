import math

from inductor_design.cores import CORES
from inductor_design.materials import MATERIALS
from inductor_design.sizing import (
    required_turns_gapped,
    required_turns_powder,
    achievable_inductance_gapped,
    achievable_inductance_powder,
    fill_factor,
    compute_flux,
)
from inductor_design.wires import solid_wire


def test_gapped_turns_then_inductance():
    core = CORES["PQ2625"]
    n, gap = required_turns_gapped(core, target_l=10e-6, max_b_peak_t=0.3,
                                   i_peak=10.0)
    assert n > 0
    assert gap > 0
    l_ach = achievable_inductance_gapped(core, n, gap)
    assert math.isclose(l_ach, 10e-6, rel_tol=1e-3)


def test_powder_turns_inductance_monotonic():
    core = CORES["T80"]
    mat = MATERIALS["KoolMu_60"]
    n1 = required_turns_powder(core, mat, 10e-6)
    n2 = required_turns_powder(core, mat, 40e-6)
    assert n2 > n1
    l1 = achievable_inductance_powder(core, mat, n1)
    l2 = achievable_inductance_powder(core, mat, n2)
    assert l2 > l1


def test_fill_factor_and_flux():
    core = CORES["PQ2625"]
    wire = solid_wire(20)
    ff = fill_factor(core, wire, turns=30)
    assert 0.0 < ff < 1.0
    bpk, bac = compute_flux(30, core.ae_m2, i_peak=10.0, delta_i_pp=2.0,
                            inductance_h=20e-6)
    assert bpk > bac > 0
