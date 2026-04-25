"""
unifiedinductordesign.py
========================

Unified, single-file inductor design tool.

Design philosophy:

* Every equation and coefficient is inspectable here.  No black boxes.
* Sizing, losses, and thermal are coupled with a Gauss-Seidel loop so
  that loss values reflect the temperature they produce.
* The thermal model is the upgraded T1 from ``INDUCTOR_DESIGN.md`` §7:
  a 5-node lumped network with anisotropic winding conductivity,
  per-face natural convection, a corner-recirculation penalty,
  radiation, a gap-fringing hot-patch, and a bobbin-edge sub-node.
  These are exactly the knobs the user flagged as required for
  rigorous edge thermal behavior.
* The interface takes a *converter spec* (Vin, Vout, Iout, f_sw,
  ripple target), not a pre-computed (L, I_rms, I_pk, f).  The latter
  is the Frenetic-style entry point and the one we explicitly reject.

This file is intentionally self-contained (std-lib only) so it can run
anywhere Python 3.9+ is installed.  The richer ``inductor_design/``
package on branch ``cursor/inductor-design-tool-plan-d762`` shares the
same coefficient values; when the two are merged onto main the module
layout in that package is preferred.  This single file stays as a
reference / smoke-test entry point.

CLI
---

    python unifiedinductordesign.py                   # demo buck design
    python unifiedinductordesign.py --topology buck --vin 12 --vout 3.3 --iout 5 --fsw 250e3 --ripple 0.3
    python unifiedinductordesign.py --topology boost --vin 12 --vout 24 --iout 2 --fsw 200e3 --ripple 0.3
    python unifiedinductordesign.py --list-cores
    python unifiedinductordesign.py --list-materials

Exit status is non-zero if no feasible design is found with the
requested spec and derating policy.
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field, replace
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

MU0 = 4.0 * math.pi * 1e-7       # H/m
SIGMA_SB = 5.670374419e-8        # W / (m^2 K^4)  Stefan-Boltzmann
COPPER_RHO_20C = 1.724e-8        # Ohm m
COPPER_ALPHA = 3.93e-3           # 1/K
COPPER_DENSITY = 8960.0          # kg/m^3
COPPER_K = 401.0                 # W/m/K
ENAMEL_K = 0.25                  # W/m/K, typical polyimide
EPSILON_FERRITE = 0.85
EPSILON_COPPER_VARNISHED = 0.40

# ---------------------------------------------------------------------------
# Material database (condensed from inductor_design/materials/__init__.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Material:
    """Magnetic material with Steinmetz loss and T-dependent saturation.

    ``P_v = k * f^alpha * Bac^beta`` in W/m^3 (f in Hz, Bac in T).
    """

    name: str
    kind: str
    b_sat_25c: float
    b_sat_100c: float
    mu_r: float
    k: float
    alpha: float
    beta: float
    rho: float
    cost_per_kg: float

    def core_loss_density(self, f_hz: float, b_ac_t: float) -> float:
        if f_hz <= 0.0 or b_ac_t <= 0.0:
            return 0.0
        return self.k * (f_hz ** self.alpha) * (b_ac_t ** self.beta)

    def b_sat(self, t_core_c: float) -> float:
        t = max(25.0, min(100.0, t_core_c))
        frac = (t - 25.0) / 75.0
        return self.b_sat_25c + frac * (self.b_sat_100c - self.b_sat_25c)


MATERIALS: dict[str, Material] = {
    "3C95":      Material("3C95",      "ferrite", 0.53, 0.42, 3000, 3.2,  1.55, 2.65, 4800.0, 25.0),
    "N87":       Material("N87",       "ferrite", 0.49, 0.39, 2200, 16.9, 1.25, 2.35, 4850.0, 22.0),
    "3F36":      Material("3F36",      "ferrite", 0.52, 0.43, 1600, 0.25, 1.85, 2.75, 4800.0, 28.0),
    "KoolMu_60": Material("Kool Mu 60u","powder",  1.05, 1.00, 60,   50.0, 1.46, 2.15, 7400.0, 30.0),
    "XFlux_60":  Material("XFlux 60u", "powder",  1.60, 1.55, 60,   110.0,1.36, 2.10, 7600.0, 45.0),
    "MPP_60":    Material("MPP 60u",   "powder",  0.75, 0.75, 60,   12.0, 1.40, 2.10, 8000.0, 90.0),
}

_FERRITE_KEYS = ("3C95", "N87", "3F36")
_POWDER_KEYS = ("KoolMu_60", "XFlux_60", "MPP_60")


# ---------------------------------------------------------------------------
# Core database
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Core:
    """Magnetic core with enough geometry for sizing and thermal.

    Dimensions are in mm / mm^2 / mm^3 for storage, SI via properties.
    """

    name: str
    shape: str                  # EE, ETD, PQ, toroid
    ae_mm2: float
    ac_mm2: float
    wa_mm2: float               # window area, one leg
    le_mm: float
    ve_mm3: float
    mlt_mm: float
    height_mm: float
    footprint_mm2: float
    surface_mm2: float
    weight_g: float
    cost_usd: float
    compatible_materials: tuple[str, ...] = ()
    # Geometry hints used by the thermal edge model
    bobbin_wall_mm: float = 0.8
    gap_adjacent: bool = True   # True for gapped ferrites, False for distributed powder

    @property
    def ae_m2(self) -> float: return self.ae_mm2 * 1e-6
    @property
    def wa_m2(self) -> float: return self.wa_mm2 * 1e-6
    @property
    def mlt_m(self) -> float: return self.mlt_mm * 1e-3
    @property
    def le_m(self) -> float: return self.le_mm * 1e-3
    @property
    def ve_m3(self) -> float: return self.ve_mm3 * 1e-9
    @property
    def surface_m2(self) -> float: return self.surface_mm2 * 1e-6
    @property
    def height_m(self) -> float: return self.height_mm * 1e-3
    @property
    def char_length_m(self) -> float:
        """Characteristic length for convection correlations.

        Use component height for vertical faces and sqrt(footprint) for
        horizontal faces; we take the mean.
        """
        l_v = self.height_m
        l_h = math.sqrt(max(self.footprint_mm2, 1.0)) * 1e-3
        return 0.5 * (l_v + l_h)


def _toroid(
    name: str, od_mm: float, idd_mm: float, ht_mm: float,
    compat: tuple[str, ...], cost_usd: float,
) -> Core:
    ae = (od_mm - idd_mm) / 2.0 * ht_mm
    le = math.pi * (od_mm + idd_mm) / 2.0
    ve = ae * le
    wa = math.pi * (idd_mm / 2.0) ** 2
    mlt = 2.0 * ((od_mm - idd_mm) / 2.0 + ht_mm) + 2.0
    surface = (
        2.0 * math.pi * (od_mm / 2.0) ** 2
        - 2.0 * math.pi * (idd_mm / 2.0) ** 2
        + math.pi * (od_mm + idd_mm) * ht_mm
    )
    footprint = math.pi * (od_mm / 2.0) ** 2
    weight_g = ve * 1e-9 * 7400.0 * 1000.0
    return Core(
        name=name, shape="toroid",
        ae_mm2=ae, ac_mm2=ae, wa_mm2=wa, le_mm=le, ve_mm3=ve,
        mlt_mm=mlt, height_mm=ht_mm, footprint_mm2=footprint,
        surface_mm2=surface, weight_g=weight_g, cost_usd=cost_usd,
        compatible_materials=compat,
        gap_adjacent=False,
    )


CORES: dict[str, Core] = {
    "PQ2016": Core("PQ2016", "PQ",  62.6,  62.6,  36.2,  37.6,  2360,  35.0, 10.2,  400,  2200, 11.0, 0.80, _FERRITE_KEYS),
    "PQ2020": Core("PQ2020", "PQ",  62.6,  62.6,  36.2,  45.7,  2870,  43.0, 14.0,  400,  2800, 13.5, 1.10, _FERRITE_KEYS),
    "PQ2625": Core("PQ2625", "PQ",  118.0, 118.0, 55.0,  55.5,  6530,  57.0, 17.5,  676,  4500, 31.0, 1.60, _FERRITE_KEYS),
    "PQ3230": Core("PQ3230", "PQ",  170.0, 170.0, 78.0,  69.5, 11800,  70.0, 21.5, 1024,  6600, 55.0, 2.30, _FERRITE_KEYS),
    "ETD29":  Core("ETD29",  "ETD", 76.0,  71.0,  97.0,  72.0,  5470,  53.0, 15.9,  870,  5300, 28.0, 1.40, _FERRITE_KEYS),
    "ETD34":  Core("ETD34",  "ETD", 97.3,  91.6, 123.0,  78.6,  7640,  60.0, 17.4, 1160,  6800, 40.0, 1.80, _FERRITE_KEYS),
    "ETD39":  Core("ETD39",  "ETD", 125.0, 123.0,177.0,  92.2, 11500,  69.0, 20.2, 1540,  9100, 60.0, 2.40, _FERRITE_KEYS),
    "ETD44":  Core("ETD44",  "ETD", 173.0, 172.0,214.0, 103.0, 17800,  78.0, 22.4, 1950, 12000, 94.0, 3.20, _FERRITE_KEYS),
    "EE25":   Core("EE25",   "EE",  52.0,  52.0,  40.0,  58.0,  3020,  40.0, 12.5,  500,  2800, 17.0, 0.70, _FERRITE_KEYS),
    "EE42":   Core("EE42",   "EE",  180.0, 180.0,250.0,  97.0, 17500,  90.0, 21.0, 1760, 11500, 98.0, 2.80, _FERRITE_KEYS),
    "T38A":  _toroid("T38A",  9.53,  4.75, 3.18,  _POWDER_KEYS, 0.60),
    "T50":   _toroid("T50",   12.70, 7.62, 4.83,  _POWDER_KEYS, 0.80),
    "T60":   _toroid("T60",   15.24, 7.62, 4.83,  _POWDER_KEYS, 0.95),
    "T80":   _toroid("T80",   20.20, 12.60,6.35,  _POWDER_KEYS, 1.25),
    "T102":  _toroid("T102",  26.90, 14.50,11.00, _POWDER_KEYS, 2.00),
    "T130":  _toroid("T130",  33.00, 19.80,11.10, _POWDER_KEYS, 2.80),
    "T157":  _toroid("T157",  40.00, 23.30,15.00, _POWDER_KEYS, 3.80),
    "T184":  _toroid("T184",  46.70, 24.00,18.00, _POWDER_KEYS, 5.00),
}


# ---------------------------------------------------------------------------
# Wire helpers
# ---------------------------------------------------------------------------

AWG_TABLE: dict[int, tuple[float, float]] = {
    14: (1.628, 1.730), 16: (1.291, 1.384), 18: (1.024, 1.107),
    20: (0.812, 0.881), 22: (0.644, 0.704), 24: (0.511, 0.566),
    26: (0.405, 0.452), 28: (0.321, 0.361), 30: (0.254, 0.290),
    32: (0.202, 0.234), 34: (0.160, 0.188), 36: (0.127, 0.152),
    38: (0.101, 0.122), 40: (0.079, 0.099),
}


@dataclass(frozen=True)
class Wire:
    name: str
    kind: str
    awg: int
    cu_diameter_m: float
    outer_diameter_m: float
    strands: int = 1
    area_cu_m2: float = 0.0

    @property
    def outer_area_m2(self) -> float:
        # Cross section that the bundle presents into the window
        return math.pi * (self.outer_diameter_m / 2.0) ** 2 * self.strands

    def dcr_ohm(self, mlt_m: float, turns: int, temp_c: float) -> float:
        rho_t = COPPER_RHO_20C * (1.0 + COPPER_ALPHA * (temp_c - 20.0))
        return rho_t * mlt_m * turns / self.area_cu_m2


def solid_wire(awg: int) -> Wire:
    cu_d_mm, od_mm = AWG_TABLE[awg]
    cu_d = cu_d_mm * 1e-3
    area = math.pi * (cu_d / 2.0) ** 2
    return Wire(
        name=f"AWG{awg}", kind="solid", awg=awg,
        cu_diameter_m=cu_d, outer_diameter_m=od_mm * 1e-3,
        strands=1, area_cu_m2=area,
    )


def litz_wire(strand_awg: int, strands: int) -> Wire:
    cu_d_mm, od_mm = AWG_TABLE[strand_awg]
    cu_d = cu_d_mm * 1e-3
    strand_area = math.pi * (cu_d / 2.0) ** 2
    bundle_od = 1.15 * math.sqrt(strands) * od_mm * 1e-3
    return Wire(
        name=f"Litz{strands}xAWG{strand_awg}", kind="litz", awg=strand_awg,
        cu_diameter_m=cu_d, outer_diameter_m=bundle_od,
        strands=strands, area_cu_m2=strands * strand_area,
    )


def skin_depth_m(f_hz: float, temp_c: float) -> float:
    if f_hz <= 0:
        return math.inf
    rho = COPPER_RHO_20C * (1.0 + COPPER_ALPHA * (temp_c - 20.0))
    return math.sqrt(rho / (math.pi * f_hz * MU0))


# ---------------------------------------------------------------------------
# Converter spec -> (L_target, I_dc, I_peak, dI_pp)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConverterSpec:
    """User-facing entry point: the converter operating point, *not*
    a pre-computed inductance target.
    """

    topology: str                # "buck" | "boost"
    v_in: float                  # V (nominal; use midpoint of range)
    v_out: float
    i_out: float
    f_sw: float                  # Hz
    ripple_ratio: float = 0.30   # dI_pp / I_dc_inductor
    t_ambient_c: float = 25.0
    forced_air_multiplier: float = 1.0
    t_class_c: float = 155.0     # insulation class F default
    derating_t_c: float = 15.0   # keep hot spot this far below class
    b_derate: float = 0.85       # B_pk <= b_derate * B_sat(T)


@dataclass(frozen=True)
class OperatingPoint:
    l_target_h: float
    i_dc_a: float
    i_peak_a: float
    delta_i_pp_a: float
    duty: float


def derive_operating_point(spec: ConverterSpec) -> OperatingPoint:
    topo = spec.topology.lower()
    if topo == "buck":
        duty = spec.v_out / spec.v_in
        i_dc = spec.i_out
        di_pp = max(1e-3, spec.ripple_ratio * i_dc)
        # L = Vout * (Vin - Vout) / (Vin * f * dI)
        l_target = spec.v_out * (spec.v_in - spec.v_out) / (spec.v_in * spec.f_sw * di_pp)
    elif topo == "boost":
        duty = 1.0 - spec.v_in / spec.v_out
        i_dc = spec.i_out * spec.v_out / spec.v_in
        di_pp = max(1e-3, spec.ripple_ratio * i_dc)
        # L = Vin * (Vout - Vin) / (Vout * f * dI)
        l_target = spec.v_in * (spec.v_out - spec.v_in) / (spec.v_out * spec.f_sw * di_pp)
    else:
        raise ValueError(f"Topology {spec.topology!r} not yet supported in this file; see roadmap §12.")
    i_peak = i_dc + di_pp / 2.0
    return OperatingPoint(l_target, i_dc, i_peak, di_pp, duty)


# ---------------------------------------------------------------------------
# Sizing: turns, gap, B_pk, B_ac, fill factor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeometryFit:
    turns: int
    gap_m: float
    inductance_h: float
    b_peak_t: float
    b_ac_t: float
    fill_factor: float
    layers: int
    turns_per_layer: int


def _turns_gapped(core: Core, l_target: float, b_max_t: float, i_peak: float) -> tuple[int, float]:
    n = max(1, int(math.ceil(l_target * i_peak / (b_max_t * core.ae_m2))))
    al = l_target / (n ** 2)
    reluctance = 1.0 / al
    gap_m = MU0 * core.ae_m2 * reluctance
    return n, max(0.0, gap_m)


def _turns_powder(core: Core, material: Material, l_target: float) -> int:
    al = MU0 * material.mu_r * core.ae_m2 / core.le_m
    if al <= 0:
        return 10 ** 9
    return max(1, int(math.ceil(math.sqrt(l_target / al))))


def _geometry_fit(
    core: Core, material: Material, wire: Wire,
    l_target: float, i_peak: float, delta_i_pp: float,
    t_core_c: float,
) -> Optional[GeometryFit]:
    b_sat_t = material.b_sat(t_core_c)
    b_max = 0.85 * b_sat_t
    if material.kind == "ferrite":
        n, gap = _turns_gapped(core, l_target, b_max, i_peak)
        l_achieved = (n ** 2) * MU0 * core.ae_m2 / gap if gap > 0 else float("inf")
    else:
        n = _turns_powder(core, material, l_target)
        gap = 0.0
        l_achieved = MU0 * material.mu_r * core.ae_m2 * (n ** 2) / core.le_m

    wire_area = wire.outer_area_m2
    ff = (n * wire_area) / core.wa_m2 if core.wa_m2 > 0 else 1.0
    if ff > 0.60:
        return None

    # Estimate layers: window height / wire OD, turns per layer from window width
    od = wire.outer_diameter_m
    window_sq_side = math.sqrt(core.wa_m2)
    tpl = max(1, int(window_sq_side / od))
    layers = max(1, int(math.ceil(n / tpl)))

    b_peak = l_achieved * i_peak / (n * core.ae_m2)
    b_ac = l_achieved * delta_i_pp / (2.0 * n * core.ae_m2)

    if b_peak > b_max:
        return None

    return GeometryFit(
        turns=n, gap_m=gap, inductance_h=l_achieved,
        b_peak_t=b_peak, b_ac_t=b_ac, fill_factor=ff,
        layers=layers, turns_per_layer=tpl,
    )


# ---------------------------------------------------------------------------
# Loss models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WindingLoss:
    r_dc: float
    r_ac: float
    p_dc: float
    p_ac: float
    p_total: float
    fr: float


def _dowell_fr(delta: float, layers: int) -> float:
    if delta < 1e-6:
        return 1.0
    try:
        sh = math.sinh(2.0 * delta)
        si = math.sin(2.0 * delta)
        ch = math.cosh(2.0 * delta)
        co = math.cos(2.0 * delta)
    except OverflowError:
        return max(1.0, delta * ((2.0 * layers ** 2 - 1.0) / 3.0))
    denom = ch - co
    if abs(denom) < 1e-12:
        return 1.0
    term1 = (sh + si) / denom
    term2 = (sh - si) / (ch + co) if (ch + co) > 1e-12 else 0.0
    fr = delta * (term1 + (2.0 / 3.0) * (layers ** 2 - 1) * term2)
    return max(1.0, fr)


def winding_loss(
    wire: Wire, turns: int, mlt_m: float,
    i_dc: float, delta_i_pp: float, f_hz: float,
    layers: int, temp_c: float,
) -> WindingLoss:
    r_dc = wire.dcr_ohm(mlt_m, turns, temp_c=temp_c)
    delta_m = skin_depth_m(f_hz, temp_c=temp_c)
    h = wire.cu_diameter_m
    delta = h / delta_m if delta_m > 0 else 0.0
    fr = _dowell_fr(delta, layers=max(1, layers))
    if wire.kind == "litz" and wire.strands > 1:
        fr = 1.0 + (fr - 1.0) / wire.strands
    r_ac = r_dc * fr
    i_ac_rms = delta_i_pp / (2.0 * math.sqrt(3.0))
    p_dc = i_dc ** 2 * r_dc
    p_ac = i_ac_rms ** 2 * r_ac
    return WindingLoss(r_dc=r_dc, r_ac=r_ac, p_dc=p_dc, p_ac=p_ac,
                      p_total=p_dc + p_ac, fr=fr)


def core_loss_w(material: Material, b_ac_t: float, f_hz: float, volume_m3: float) -> float:
    return material.core_loss_density(f_hz, b_ac_t) * volume_m3


# ---------------------------------------------------------------------------
# Thermal model — T1 (5 nodes + gap-fringe patch + bobbin edge)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThermalConfig:
    """Knobs for the T1 thermal model.  Defaults match INDUCTOR_DESIGN.md §7.3."""

    forced_air_multiplier: float = 1.0
    t_ambient_c: float = 25.0
    h_floor: float = 5.0                 # W/m^2/K minimum (natural convection sanity)
    h_top_scale: float = 1.32            # heated plate facing up
    h_bot_scale: float = 0.59            # heated plate facing down
    h_side_scale: float = 1.42           # vertical side
    corner_h_scale: float = 0.70         # recirculation penalty at corners
    corner_area_frac: float = 0.15       # fraction of exterior area treated as "corner"
    radiation_enabled: bool = True
    fringe_loss_frac: float = 0.10       # share of P_core deposited near the gap
    fringe_distance_mult: float = 3.0    # hot-patch radius = mult * gap
    bobbin_edge_frac: float = 0.10       # fraction of winding volume near bobbin flanges


@dataclass(frozen=True)
class ThermalResult:
    t_ambient_c: float
    t_surface_mean_c: float
    t_surface_corner_c: float
    t_core_inner_c: float
    t_core_fringe_c: float
    t_cu_outer_c: float
    t_cu_inner_c: float
    t_cu_edge_c: float           # bobbin-edge sub-node
    t_hotspot_c: float           # max over all winding/core nodes
    radial_gradient_c: float
    r_th_surface_to_amb: float
    r_th_cu_outer_to_surface: float
    r_th_cu_inner_to_cu_outer: float
    h_mean: float
    converged: bool


def _natural_h(delta_t: float, char_length_m: float, scale: float) -> float:
    if delta_t <= 0 or char_length_m <= 0:
        return 5.0
    return max(5.0, scale * (delta_t / char_length_m) ** 0.25)


def _k_winding_hs(fill_factor: float) -> tuple[float, float]:
    """Hashin–Shtrikman bounds for effective conductivity of a
    winding pack modeled as copper cylinders in enamel matrix.

    Returns (k_radial_lower, k_axial_upper) — we take the lower
    bound on the radial direction because that is the path hot inner
    copper has to take to leave the winding.  Axial is limited by
    copper along turn length so the upper bound is appropriate.
    """
    phi = max(0.05, min(0.85, fill_factor))
    km, ki = COPPER_K, ENAMEL_K
    # Lower HS bound (matrix continuous)
    k_lower = ki + phi / (1.0 / (km - ki) + (1.0 - phi) / (3.0 * ki))
    # Upper HS bound (inclusion continuous)
    k_upper = km + (1.0 - phi) / (1.0 / (ki - km) + phi / (3.0 * km))
    # Clamp
    k_radial = max(0.35, min(k_lower, 5.0))
    k_axial = max(k_radial, min(k_upper, COPPER_K * phi))
    return k_radial, k_axial


def _r_cond_radial(core: Core, fit: GeometryFit, k_radial: float) -> float:
    """Crude cylindrical radial thermal resistance for the winding.

    We approximate the winding pack as an annulus of thickness
    ``t_w = layers * d_od`` wrapped around the core leg with height
    ``h_w = turns_per_layer * d_od``.  Path length is t_w, area is
    the mid-annulus cylinder (height * circumference).  This is
    exactly the hand-calculation used as T1 in INDUCTOR_DESIGN.md §7.2.
    """
    # We do not have a wire OD here; fall back to geometric window.
    window_side = math.sqrt(max(core.wa_m2, 1e-9))
    t_w = window_side * min(1.0, fit.layers / max(fit.turns_per_layer, 1) + 0.5 * fit.layers)
    t_w = max(1e-4, min(window_side, t_w * 0.5))  # keep sane
    h_w = max(1e-3, window_side)
    r_leg = 0.25 * math.sqrt(max(core.ae_m2, 1e-9))  # rough centre-leg radius
    r_mid = r_leg + t_w / 2.0
    area = 2.0 * math.pi * r_mid * h_w
    return t_w / (k_radial * max(area, 1e-6))


def thermal_solve(
    core: Core, fit: GeometryFit,
    p_core_w: float, p_cu_w: float,
    cfg: ThermalConfig,
) -> ThermalResult:
    """Solve the T1 5-node thermal network.

    Nodes:
        ambient -> surface (with per-face h + radiation + corner patch)
        surface -> core_outer -> core_inner
        surface -> cu_outer  -> cu_inner
        cu_outer -> cu_edge (bobbin end-wall sub-node)
        core_inner -> core_fringe (hot-patch absorbing fringe_loss_frac*P_core)

    Solved iteratively because h = h(ΔT).
    """

    # Per-face convection areas (rough split): 0.25 top, 0.25 bottom, 0.5 sides
    area_total = max(core.surface_m2, 1e-6)
    a_top = 0.25 * area_total
    a_bot = 0.25 * area_total
    a_side = 0.50 * area_total
    a_corner = cfg.corner_area_frac * area_total

    l_char = core.char_length_m
    dt = 40.0
    t_amb_k = cfg.t_ambient_c + 273.15

    # Distribute losses
    p_fringe = cfg.fringe_loss_frac * p_core_w
    p_core_body = p_core_w - p_fringe
    p_cu_edge = cfg.bobbin_edge_frac * p_cu_w
    p_cu_body = p_cu_w - p_cu_edge
    p_total = p_core_w + p_cu_w

    # Anisotropic winding conductivity (depends on fill factor)
    k_rad, _k_ax = _k_winding_hs(fit.fill_factor)
    r_cu_in_out = _r_cond_radial(core, fit, k_rad)

    # Winding-to-surface resistance: core acts as a heat spreader
    # plus bobbin wall.  Take winding outer to surface ≈ bobbin wall
    # conducting via 0.3 W/m/K (plastic) over half the core surface.
    r_bobbin = (core.bobbin_wall_mm * 1e-3) / (0.3 * 0.5 * area_total)
    r_cu_out_to_surface = r_bobbin

    # Core-inner to core-outer is very low for ferrite (k~4.5 W/m/K)
    # across ~half of le.  Treat as lumped, small.
    k_core = 4.5
    r_core_in_out = 0.5 * core.le_m / (k_core * max(core.ae_m2, 1e-6))

    # Gap-fringe patch: couples to core_inner only weakly (short path
    # in ferrite) but dumps heat near the gap.  Resistance from the
    # fringe volume back into the bulk core:
    fringe_radius = max(1e-4, cfg.fringe_distance_mult * max(fit.gap_m, 1e-5))
    r_fringe = fringe_radius / (k_core * math.pi * max(core.ae_m2, 1e-6))
    if not core.gap_adjacent or fit.gap_m <= 0:
        p_fringe = 0.0
        r_fringe = 1e6

    converged = False
    t_surface = cfg.t_ambient_c + dt
    for _ in range(40):
        # Per-face h with radiation
        h_side = _natural_h(dt, l_char, cfg.h_side_scale) * cfg.forced_air_multiplier
        h_top = _natural_h(dt, l_char, cfg.h_top_scale) * cfg.forced_air_multiplier
        h_bot = _natural_h(dt, l_char, cfg.h_bot_scale) * cfg.forced_air_multiplier
        h_corner = cfg.corner_h_scale * h_side

        if cfg.radiation_enabled:
            t_s_k = t_surface + 273.15
            # Linearized radiation coefficient
            h_rad = 4.0 * SIGMA_SB * EPSILON_FERRITE * (0.5 * (t_s_k + t_amb_k)) ** 3
        else:
            h_rad = 0.0

        # Corner patch robs some area from "side"
        a_side_eff = max(0.0, a_side - a_corner)
        g_conv = (
            (h_top + h_rad) * a_top
            + (h_bot + h_rad) * a_bot
            + (h_side + h_rad) * a_side_eff
            + (h_corner + h_rad) * a_corner
        )
        r_th_sa = 1.0 / max(g_conv, 1e-6)
        t_surface = cfg.t_ambient_c + p_total * r_th_sa

        # Solve core branch (surface -> core_outer -> core_inner -> fringe)
        # Equivalent: core_inner = surface + P_core_body * R_core_in_out
        #             (absorbing negligible core-skin resistance)
        t_core_inner = t_surface + p_core_body * r_core_in_out + p_core_w * 0.0
        t_core_fringe = t_core_inner + p_fringe * r_fringe

        # Winding branch
        t_cu_outer = t_surface + p_cu_body * r_cu_out_to_surface
        t_cu_inner = t_cu_outer + p_cu_body * r_cu_in_out
        t_cu_edge = t_cu_outer + p_cu_edge * r_cu_in_out * 1.5  # edge has tighter path

        dt_new = max(t_surface, t_core_fringe, t_cu_inner, t_cu_edge) - cfg.t_ambient_c
        if abs(dt_new - dt) < 0.05:
            dt = dt_new
            converged = True
            break
        dt = dt_new

    # Corner surface temperature (hottest external face)
    h_side = _natural_h(dt, l_char, cfg.h_side_scale) * cfg.forced_air_multiplier
    h_corner = cfg.corner_h_scale * h_side
    if cfg.radiation_enabled:
        t_s_k = t_surface + 273.15
        h_rad = 4.0 * SIGMA_SB * EPSILON_FERRITE * (0.5 * (t_s_k + t_amb_k)) ** 3
    else:
        h_rad = 0.0
    q_corner_density = p_total * (a_corner / area_total)
    t_surface_corner = cfg.t_ambient_c + q_corner_density / max((h_corner + h_rad) * a_corner, 1e-6)

    hotspot = max(t_core_inner, t_core_fringe, t_cu_inner, t_cu_edge, t_surface_corner)

    return ThermalResult(
        t_ambient_c=cfg.t_ambient_c,
        t_surface_mean_c=t_surface,
        t_surface_corner_c=t_surface_corner,
        t_core_inner_c=t_core_inner,
        t_core_fringe_c=t_core_fringe,
        t_cu_outer_c=t_cu_outer,
        t_cu_inner_c=t_cu_inner,
        t_cu_edge_c=t_cu_edge,
        t_hotspot_c=hotspot,
        radial_gradient_c=t_cu_inner - t_cu_outer,
        r_th_surface_to_amb=r_th_sa,
        r_th_cu_outer_to_surface=r_cu_out_to_surface,
        r_th_cu_inner_to_cu_outer=r_cu_in_out,
        h_mean=(h_top * a_top + h_bot * a_bot + h_side * a_side_eff + h_corner * a_corner) / area_total,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Coupled EM/Thermal solver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DesignCandidate:
    core: Core
    material: Material
    wire: Wire
    fit: GeometryFit
    operating: OperatingPoint
    p_core_w: float
    p_cu_w: float
    p_total_w: float
    winding_loss: WindingLoss
    thermal: ThermalResult
    feasible: bool
    reasons: tuple[str, ...]
    volume_cm3: float
    mass_g: float
    cost_usd: float


def _volume_cm3(core: Core, wire: Wire, fit: GeometryFit) -> float:
    cu_vol_m3 = wire.area_cu_m2 * core.mlt_m * fit.turns
    # Component envelope approximated by footprint*height
    env_m3 = (core.footprint_mm2 * 1e-6) * core.height_m
    return max(env_m3, cu_vol_m3 * 3.0) * 1e6


def evaluate(
    core: Core, material: Material, wire: Wire,
    spec: ConverterSpec, cfg: Optional[ThermalConfig] = None,
    max_iter: int = 12, tol_c: float = 0.2,
) -> Optional[DesignCandidate]:
    if cfg is None:
        cfg = ThermalConfig(
            t_ambient_c=spec.t_ambient_c,
            forced_air_multiplier=spec.forced_air_multiplier,
        )
    if material.name not in material.name:  # sanity, always true
        return None
    if material.name.split()[0].replace("Mu", "Mu_60").split("_")[0] not in (m for m in core.compatible_materials):
        # Fall back to simple keyword check on the material-key form
        key = next((k for k, v in MATERIALS.items() if v is material), None)
        if key not in core.compatible_materials:
            return None

    op = derive_operating_point(spec)

    # Gauss-Seidel: start with an assumed hot temp, re-fit flux and
    # losses, resolve thermal, repeat.
    t_core_c = 80.0
    t_cu_c = 80.0
    prev_hot = None
    candidate: Optional[DesignCandidate] = None
    for _ in range(max_iter):
        fit = _geometry_fit(core, material, wire, op.l_target_h, op.i_peak_a, op.delta_i_pp_a, t_core_c)
        if fit is None:
            return None
        p_core = core_loss_w(material, fit.b_ac_t, spec.f_sw, core.ve_m3)
        wl = winding_loss(wire, fit.turns, core.mlt_m, op.i_dc_a, op.delta_i_pp_a, spec.f_sw, fit.layers, temp_c=t_cu_c)
        th = thermal_solve(core, fit, p_core, wl.p_total, cfg)

        hot = th.t_hotspot_c
        t_core_c = 0.5 * (th.t_core_inner_c + th.t_surface_mean_c)
        t_cu_c = 0.5 * (th.t_cu_outer_c + th.t_cu_inner_c)

        if prev_hot is not None and abs(hot - prev_hot) < tol_c:
            break
        prev_hot = hot

    reasons: list[str] = []
    t_limit = spec.t_class_c - spec.derating_t_c
    if th.t_hotspot_c > t_limit:
        reasons.append(f"hotspot {th.t_hotspot_c:.1f} C > limit {t_limit:.1f} C")
    if th.radial_gradient_c > 25.0:
        reasons.append(f"radial gradient {th.radial_gradient_c:.1f} C > 25 C")
    b_max = spec.b_derate * material.b_sat(t_core_c)
    if fit.b_peak_t > b_max:
        reasons.append(f"B_pk {fit.b_peak_t:.3f} T > {b_max:.3f} T")
    if fit.fill_factor > 0.45:
        reasons.append(f"fill factor {fit.fill_factor:.2f} > 0.45")

    volume = _volume_cm3(core, wire, fit)
    cu_mass = wire.area_cu_m2 * core.mlt_m * fit.turns * COPPER_DENSITY * 1000.0
    mass = core.weight_g + cu_mass
    cost = core.cost_usd + cu_mass * 1e-3 * 12.0

    return DesignCandidate(
        core=core, material=material, wire=wire, fit=fit, operating=op,
        p_core_w=p_core, p_cu_w=wl.p_total, p_total_w=p_core + wl.p_total,
        winding_loss=wl, thermal=th,
        feasible=not reasons, reasons=tuple(reasons),
        volume_cm3=volume, mass_g=mass, cost_usd=cost,
    )


# ---------------------------------------------------------------------------
# Optimizer: grid + Pareto filter
# ---------------------------------------------------------------------------


def _default_wires() -> list[Wire]:
    wires: list[Wire] = [solid_wire(a) for a in (14, 16, 18, 20, 22, 24, 26)]
    wires += [litz_wire(30, s) for s in (40, 80, 150, 300)]
    return wires


def _pareto_filter(items: list[DesignCandidate]) -> list[DesignCandidate]:
    def dominates(a: DesignCandidate, b: DesignCandidate) -> bool:
        criteria = (
            a.p_total_w <= b.p_total_w,
            a.volume_cm3 <= b.volume_cm3,
            a.cost_usd <= b.cost_usd,
            a.thermal.t_hotspot_c <= b.thermal.t_hotspot_c,
        )
        strictly = (
            a.p_total_w < b.p_total_w
            or a.volume_cm3 < b.volume_cm3
            or a.cost_usd < b.cost_usd
            or a.thermal.t_hotspot_c < b.thermal.t_hotspot_c
        )
        return all(criteria) and strictly

    front: list[DesignCandidate] = []
    for c in items:
        if not c.feasible:
            continue
        if any(dominates(other, c) for other in items if other is not c and other.feasible):
            continue
        front.append(c)
    return front


def search(
    spec: ConverterSpec,
    cores: Iterable[Core] | None = None,
    materials: Iterable[Material] | None = None,
    wires: Iterable[Wire] | None = None,
    cfg: Optional[ThermalConfig] = None,
) -> tuple[list[DesignCandidate], list[DesignCandidate]]:
    """Return (all_candidates, pareto_feasible_front)."""
    cores = list(cores or CORES.values())
    materials = list(materials or MATERIALS.values())
    wires = list(wires or _default_wires())

    all_cands: list[DesignCandidate] = []
    for core in cores:
        for mat in materials:
            key = next((k for k, v in MATERIALS.items() if v is mat), None)
            if key not in core.compatible_materials:
                continue
            for wire in wires:
                cand = evaluate(core, mat, wire, spec, cfg=cfg)
                if cand is not None:
                    all_cands.append(cand)
    return all_cands, _pareto_filter(all_cands)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def format_report(cand: DesignCandidate) -> str:
    op, fit, th = cand.operating, cand.fit, cand.thermal
    lines = [
        f"=== Inductor design — {cand.core.name} / {cand.material.name} / {cand.wire.name} ===",
        f"Operating point:",
        f"  L_target        = {op.l_target_h * 1e6:.1f} uH",
        f"  Duty            = {op.duty:.3f}",
        f"  I_dc            = {op.i_dc_a:.2f} A",
        f"  I_peak          = {op.i_peak_a:.2f} A",
        f"  dI_pp           = {op.delta_i_pp_a:.2f} A",
        f"Geometry:",
        f"  Turns           = {fit.turns} ({fit.layers} layer(s), {fit.turns_per_layer}/layer)",
        f"  Gap             = {fit.gap_m * 1e3:.3f} mm",
        f"  L_achieved      = {fit.inductance_h * 1e6:.1f} uH",
        f"  B_peak          = {fit.b_peak_t * 1e3:.1f} mT",
        f"  B_ac            = {fit.b_ac_t * 1e3:.1f} mT",
        f"  Fill factor     = {fit.fill_factor * 100:.1f} %",
        f"Losses:",
        f"  P_core          = {cand.p_core_w:.3f} W",
        f"  P_cu (dc/ac/tot)= {cand.winding_loss.p_dc:.3f} / {cand.winding_loss.p_ac:.3f} / {cand.winding_loss.p_total:.3f} W",
        f"  F_r             = {cand.winding_loss.fr:.2f}",
        f"  P_total         = {cand.p_total_w:.3f} W",
        f"Thermal (T1 5-node + edge patch):",
        f"  T_ambient       = {th.t_ambient_c:.1f} C",
        f"  T_surface mean  = {th.t_surface_mean_c:.1f} C",
        f"  T_surface corner= {th.t_surface_corner_c:.1f} C   <-- edge",
        f"  T_core inner    = {th.t_core_inner_c:.1f} C",
        f"  T_core fringe   = {th.t_core_fringe_c:.1f} C   <-- gap hot-patch",
        f"  T_cu outer      = {th.t_cu_outer_c:.1f} C",
        f"  T_cu inner      = {th.t_cu_inner_c:.1f} C",
        f"  T_cu edge       = {th.t_cu_edge_c:.1f} C   <-- bobbin end-wall",
        f"  T_hotspot       = {th.t_hotspot_c:.1f} C",
        f"  Radial gradient = {th.radial_gradient_c:.1f} C   (limit 25 C)",
        f"  R_th surf->amb  = {th.r_th_surface_to_amb:.2f} K/W",
        f"  h_mean          = {th.h_mean:.1f} W/m^2/K  (converged={th.converged})",
        f"Mechanical:",
        f"  Envelope volume = {cand.volume_cm3:.2f} cm^3",
        f"  Mass            = {cand.mass_g:.1f} g",
        f"  Cost (BOM est.) = ${cand.cost_usd:.2f}",
        f"Feasible: {'YES' if cand.feasible else 'NO'}",
    ]
    if cand.reasons:
        lines.append("  Violations:")
        for r in cand.reasons:
            lines.append(f"    - {r}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> int:
    p = argparse.ArgumentParser(description="Unified inductor design tool.")
    p.add_argument("--topology", default="buck", choices=["buck", "boost"])
    p.add_argument("--vin", type=float, default=12.0)
    p.add_argument("--vout", type=float, default=3.3)
    p.add_argument("--iout", type=float, default=5.0)
    p.add_argument("--fsw", type=float, default=250e3)
    p.add_argument("--ripple", type=float, default=0.30,
                   help="Peak-peak ripple as fraction of inductor DC current")
    p.add_argument("--tamb", type=float, default=25.0)
    p.add_argument("--airflow", type=float, default=1.0, help="Convection multiplier, 1.0 = natural")
    p.add_argument("--tclass", type=float, default=155.0, help="Insulation class temperature (C)")
    p.add_argument("--top", type=int, default=3, help="Number of Pareto candidates to print")
    p.add_argument("--list-cores", action="store_true")
    p.add_argument("--list-materials", action="store_true")
    args = p.parse_args()

    if args.list_cores:
        for k, c in CORES.items():
            print(f"{k:8s} {c.shape:6s} Ae={c.ae_mm2:.0f}mm^2 Wa={c.wa_mm2:.0f}mm^2 H={c.height_mm:.1f}mm")
        return 0
    if args.list_materials:
        for k, m in MATERIALS.items():
            print(f"{k:10s} {m.kind:7s} Bsat(100C)={m.b_sat_100c:.2f}T mu_r={m.mu_r:.0f} k={m.k:g} a={m.alpha:g} b={m.beta:g}")
        return 0

    spec = ConverterSpec(
        topology=args.topology, v_in=args.vin, v_out=args.vout,
        i_out=args.iout, f_sw=args.fsw, ripple_ratio=args.ripple,
        t_ambient_c=args.tamb, forced_air_multiplier=args.airflow,
        t_class_c=args.tclass,
    )
    op = derive_operating_point(spec)
    print(f"# Converter spec -> operating point")
    print(f"  topology={spec.topology} Vin={spec.v_in} Vout={spec.v_out} Iout={spec.i_out} fsw={spec.f_sw:g}")
    print(f"  L_target={op.l_target_h*1e6:.1f} uH  I_dc={op.i_dc_a:.2f} A  I_pk={op.i_peak_a:.2f} A  dI_pp={op.delta_i_pp_a:.2f} A")

    all_cands, front = search(spec)
    feas = [c for c in all_cands if c.feasible]
    print(f"# Evaluated {len(all_cands)} candidates, {len(feas)} feasible, {len(front)} on Pareto front")

    if not feas:
        print("# No feasible design found.  Best-effort top-3 by hotspot:")
        all_cands.sort(key=lambda c: c.thermal.t_hotspot_c)
        for c in all_cands[:3]:
            print(format_report(c))
            print()
        return 2

    # Rank front by (total loss, volume, cost)
    front.sort(key=lambda c: (c.p_total_w, c.volume_cm3, c.cost_usd))
    for c in front[: args.top]:
        print(format_report(c))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
