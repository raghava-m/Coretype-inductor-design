"""
Three-phase inductor analytical design (aligned with electrical_design_calculations_service_3ph.py).

This module implements the same physics / formulas as the 3ph service without requiring MySQL:
  - Turns from L, Ipk, Bmax, Ae
  - Per-layer coil length from perimeter model (flat faces + corner arcs)
  - R_dc from copper conductivity 58.5 MS/m (or aluminum 35.85) and NOM area
  - R_150C via Infra–Beta style factor for copper
  - Per-phase DC copper loss: P = I_rms^2 * R_150C
  - Three-phase totals: mass and loss scale ×3 (three identical limb windings)

Assumptions (same as legacy 3ph script):
  - Balanced 3-phase E-core: one winding per outer/center limb (identical geometry per phase).
  - `electrical_inputs['irms']` is **phase RMS** current (A).
  - Total copper loss (all phases) = 3 * P_phase when R and I are equal per phase.
  - Window **height** budget: optional **+extra_turns_for_window_height** (default 1.0) on top of
    electrical turns for half-turn / end-winding allowance (does not change N or L).

Usage:
    from three_phase_inductor_design import ThreePhaseDesignInputs, run_three_phase_design
    inp = ThreePhaseDesignInputs(...)
    out = run_three_phase_design(inp)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# Conductivity used in legacy Himaja scripts (MS/m)
SIGMA_COPPER_MS_M = 58.5
SIGMA_ALUMINUM_MS_M = 35.85


def _conductor_properties(name: str) -> Dict[str, float]:
    """Resolve conductor properties from the material library.

    Falls back to the legacy copper/aluminium constants if the library is
    unavailable so the analytical design stays runnable standalone.
    """
    try:
        from .material_library import conductor_properties
    except ImportError:
        from material_library import conductor_properties  # standalone copy

    try:
        return conductor_properties(name)
    except Exception:  # noqa: BLE001 - keep analytical robust without the library
        if str(name).strip().lower().startswith("alum"):
            return {
                "sigma_ms_m": SIGMA_ALUMINUM_MS_M,
                "density_kg_m3": 2703.0,
                "temp_coeff_const": 230.0,
            }
        return {
            "sigma_ms_m": SIGMA_COPPER_MS_M,
            "density_kg_m3": 8890.0,
            "temp_coeff_const": 234.45,
        }


# Default lamination density [kg/m^3] when no core material / density is given.
DENSITY_CRGO_KG_M3 = 7650.0


def _core_density(name: str) -> float:
    """Resolve core lamination density from the material library (default CRGO)."""
    try:
        from .material_library import core_properties
    except ImportError:
        from material_library import core_properties

    try:
        return float(core_properties(name)["density_kg_m3"])
    except Exception:  # noqa: BLE001 - keep analytical robust without the library
        return DENSITY_CRGO_KG_M3


# Fallback Steinmetz coefficients (SI, per m^3) if the material library is missing.
_DEFAULT_STEINMETZ = {"steinmetz_k": 6.5, "steinmetz_a": 1.51, "steinmetz_b": 1.74}


def _core_steinmetz(name: str) -> dict:
    """Resolve Steinmetz coefficients (k, a, b) from the material library.

    Returns keys ``steinmetz_k``, ``steinmetz_a``, ``steinmetz_b`` and falls
    back to representative CRGO values if the library is unavailable.
    """
    try:
        from .material_library import core_properties
    except ImportError:
        from material_library import core_properties

    try:
        props = core_properties(name)
        return {
            "steinmetz_k": float(props.get("steinmetz_k", _DEFAULT_STEINMETZ["steinmetz_k"])),
            "steinmetz_a": float(props.get("steinmetz_a", _DEFAULT_STEINMETZ["steinmetz_a"])),
            "steinmetz_b": float(props.get("steinmetz_b", _DEFAULT_STEINMETZ["steinmetz_b"])),
        }
    except Exception:  # noqa: BLE001 - keep analytical robust without the library
        return dict(_DEFAULT_STEINMETZ)


@dataclass
class ThreePhaseElectricalInputs:
    """Electrical inputs (same keys as service where possible)."""

    inductance_uh: float
    irms_a: float  # phase RMS
    short_term_peak_current_a: float
    # Rated (continuous) peak current for operating flux / core-loss B.
    # If None or <=0, defaults to irms_a * sqrt(2).
    # Short-term peak is still used for turns / saturation sizing.
    rated_peak_current_a: Optional[float] = None
    frequency_hz: float = 50.0  # operating frequency for Steinmetz core loss
    turn_to_turn_gap_mm: float = 0.23
    gap_bet_layer_to_layer_mm: float = 0.3
    strand_to_strand_gap_mm: float = 0.2
    isolation_test_voltage_kv: float = 3.4
    insulation_type: str = "Enamel"
    lug_type: str = "CCT16-8"
    termination_type: str = "Straight Busbar"
    corner_angle_code: str = "C-ANG-0-0"
    gap_between_bobbin_core_width_side_mm: float = 0.0
    gap_between_bobbin_core_depth_side_mm: float = 0.0
    use_bobbin_end_plate_thickness: bool = True
    # 0 => auto-derive plate thickness from isolation voltage (recommended).
    # Set >0 to define the bobbin end-plate thickness [mm] directly.
    bobbin_plate_thickness_mm: float = 0.0
    femm_total_airgap_limb_mm: float = 0.0
    airgap_locations_limb: int = 1
    # Extra effective turns in the **window height** stack only (start/finish, crossover, “half-turn”
    # end allowance). Does not change electrical N or inductance — only height / fitment budget.
    # Set to 0.0 to disable; use 0.5 if you want a half-turn row equivalent only.
    extra_turns_for_window_height: float = 1.0


@dataclass
class ThreePhaseVariableInputs:
    core_type: str = "shell type"  # 3ph E-core uses shell-type style in legacy
    series_parallel: str = "series"
    core_name: str = "UMCCC-400"
    strip_wire_no: str = "STRIP : 7.00 x 3.00"
    cond_in_parallel_t: int = 1
    cond_in_parallel_w: int = 1
    no_of_layers: int = 1
    conductor_material: str = "copper"
    core_material: str = ""  # optional; drives default Bmax via material library
    flux_density_t: Optional[float] = None
    # NOTE: core_stack_mm lives only on ThreePhaseVariableCalculations (single
    # source of truth). It was previously duplicated here and never set by the UI.
    significance_turns: int = 1
    # Optional material-library overrides. When left as None the values are
    # resolved from `conductor_material` (copper / aluminium) at run time.
    conductor_sigma_ms_m: Optional[float] = None
    conductor_density_kg_m3: Optional[float] = None
    conductor_temp_coeff_const: Optional[float] = None
    # Optional Steinmetz core-loss overrides. When None/<=0 the coefficients are
    # resolved from `core_material` via the material library.
    steinmetz_k_override: Optional[float] = None
    steinmetz_a_override: Optional[float] = None
    steinmetz_b_override: Optional[float] = None


@dataclass
class ThreePhaseInsulationCoordination:
    clearance_mm: float = 0.0
    req_clearance_dist_op: float = 0.0
    req_clearance_dist_iso: float = 0.0
    req_creepage_dist_op: float = 0.0
    req_creepage_dist_iso: float = 0.0
    # Extra safety margins for no-bobbin/open-winding designs.
    min_airflow_clearance_mm: float = 0.0
    core_to_coil_droplet_clearance_mm: float = 0.0
    coil_to_core_droplet_clearance_mm: float = 0.0
    apply_window_height_clearance: bool = True
    allow_clearance_reduction: bool = False
    clearance_reduction_factor: float = 1.0


@dataclass
class ThreePhaseVariableCalculations:
    """Precomputed geometry from core DB row + insulation (normally from upstream services)."""

    allowed_max_flux_density_t: float = 1.4
    # If set (>0), this override is used directly for turns/Bmax/Airgap.
    # If None or <=0, Ae is computed from: core_width_for_area_mm * core_stack_mm
    # * no_of_cores_in_stack * stacking_factor.
    core_area_m2: Optional[float] = None
    # Iron width of a single limb (Ae driver). Distinct from overall_core_width_mm
    # which is the full 3-limb outer width. Falls back to overall_core_width if <=0.
    core_width_for_area_mm: float = 22.0
    no_of_cores_in_stack: float = 2.0
    stacking_factor: float = 0.95
    # Lamination density [kg/m^3] for geometry-based core weight (0/None => material library).
    core_density_kg_m3: Optional[float] = None
    significance: int = 1
    end_plate_thickness_mm: float = 2.0
    # 0 => derive from strip width * cond_in_parallel_w (recommended). Set >0 to override.
    overall_conductor_width_mm: float = 0.0
    # If 0: height fitment % is derived from required_coil_height_mm / window_height_mm.
    # If >0: also reported as declared fitment (e.g. from DB) for comparison.
    window_fitment_height_side_mm: float = 0.0
    window_fitment_width_side_mm: float = 0.0  # set from upstream / DB; 0 = not used in util factor
    window_height_mm: float = 86.25
    window_width_mm: float = 35.5
    # Total core length along limb (mm); UMCCC-400 typical f ≈ 130.25 from amorphous table (adjust per core).
    core_length_mm: float = 130.25
    core_stack_mm: float = 65.0
    # Horizontal extent used in flat_width (legacy `overall_core_width`).
    # Kept at 22 mm here to match the single-phase assumption requested by user.
    overall_core_width_mm: float = 22.0
    # 0 => compute core weight from geometry x lamination density (recommended).
    # Set > 0 to force a manual/datasheet core weight override.
    core_mass_kg: float = 0.0
    core_specific_weight_consideration: float = 1.0
    core_cost_per_kg: float = 10.0
    add_consideration_for_coil_height_mm: float = 0.0
    # If None: use max(layer turns) for coil height (matches legacy turns_for_height from upstream).
    # Do NOT hard-code; a wrong default (e.g. 9) while computed turns=18 made coil_height ~80 mm vs ~130 mm.
    turns_for_height: Optional[int] = None
    e_mm: float = 79.5
    b_mm: float = 35.5
    a_mm: float = 22.0
    c_mm: float = 86.25
    d_mm: float = 130.0


@dataclass
class ThreePhaseStripData:
    nom_area_mm2: float = 20.451
    overall_max_width_mm: float = 7.24
    overall_max_thickness_mm: float = 3.2


@dataclass
class ThreePhaseCornerData:
    d_mm: float = 1.0
    r1_mm: float = 2.0
    c_mm: float = 1.0


@dataclass
class ThreePhaseDesignInputs:
    electrical: ThreePhaseElectricalInputs
    variable: ThreePhaseVariableInputs
    insulation: ThreePhaseInsulationCoordination
    variable_calc: ThreePhaseVariableCalculations
    strip: ThreePhaseStripData = field(default_factory=ThreePhaseStripData)
    corner: ThreePhaseCornerData = field(default_factory=ThreePhaseCornerData)
    terminal_lug_length_mm: float = 0.0


def _layer_turn_splits(total_turns: int, n_layers: int) -> tuple[int, ...]:
    """Match legacy 1ph/3ph layer turn assignment (first layer gets round(turns/n_layers), etc.)."""
    nl = max(1, int(n_layers))
    first = round(total_turns / nl)
    rem = total_turns - first
    if nl == 1:
        return (total_turns,)
    second = first if rem > first else rem
    rem2 = total_turns - first - second
    if nl == 2:
        return (first, second)
    third = second if rem2 > second else rem2
    rem3 = total_turns - first - second - third
    if nl == 3:
        return (first, second, third)
    fourth = third if rem3 > third else rem3
    rem4 = total_turns - first - second - third - fourth
    if nl == 4:
        return (first, second, third, fourth)
    fifth = fourth if rem4 > fourth else rem4
    rem5 = total_turns - first - second - third - fourth - fifth
    if nl == 5:
        return (first, second, third, fourth, fifth)
    sixth = fifth if rem5 > fifth else rem5
    return (first, second, third, fourth, fifth, sixth)


def run_three_phase_design(inp: ThreePhaseDesignInputs) -> Dict[str, Any]:
    """
    Run 3-phase inductor design calculations (pure Python, no DB).

    Mirrors electrical_design_calculations_service_3ph.py structure.
    """
    el = inp.electrical
    va = inp.variable
    ins = inp.insulation
    vc = inp.variable_calc
    st = inp.strip
    co = inp.corner

    bmax_allowed = vc.allowed_max_flux_density_t
    if va.flux_density_t is not None:
        bmax_allowed = float(va.flux_density_t)

    core_width_for_area_mm = (
        vc.core_width_for_area_mm if vc.core_width_for_area_mm > 0 else vc.overall_core_width_mm
    )
    geom_core_area_m2 = (
        core_width_for_area_mm
        * vc.core_stack_mm
        * max(1.0, float(vc.no_of_cores_in_stack))
        * (float(vc.stacking_factor) if vc.stacking_factor > 0 else 1.0)
        * 1e-6
    )
    core_area_m2_eff = (
        float(vc.core_area_m2) if vc.core_area_m2 is not None and float(vc.core_area_m2) > 0 else geom_core_area_m2
    )

    l_h = el.inductance_uh * 1e-6
    # Turns sized against short-term peak so the core does not saturate on overload.
    t_turns = (l_h * el.short_term_peak_current_a) / (bmax_allowed * core_area_m2_eff)
    sig = max(1, int(va.significance_turns))
    turns = math.ceil(t_turns / sig) * sig

    bmax_short_term = round(
        (el.short_term_peak_current_a * l_h) / (core_area_m2_eff * turns),
        2,
    )
    # Operating / core-loss flux at rated peak (not short-term overload).
    if el.rated_peak_current_a is not None and float(el.rated_peak_current_a) > 0:
        i_rated_peak = float(el.rated_peak_current_a)
    else:
        i_rated_peak = float(el.irms_a) * math.sqrt(2.0)
    bmax_rated = round(
        (i_rated_peak * l_h) / (core_area_m2_eff * turns),
        4,
    )
    # Legacy key ``bmax_t`` = short-term (saturation check). Core loss uses rated.
    bmax = bmax_short_term

    d_cond_area = st.nom_area_mm2
    parallels = max(1, va.cond_in_parallel_t * va.cond_in_parallel_w)
    current_density = (
        round(el.irms_a / (d_cond_area * parallels), 2) if d_cond_area > 0 else 0.0
    )

    layer_turns = _layer_turn_splits(turns, int(va.no_of_layers))
    first_layer_turns = layer_turns[0]

    minimum_gap_bw_coils = max(
        4 if el.irms_a < 50 else 6 if el.irms_a < 100 else 8,
        max(ins.req_clearance_dist_op, ins.req_clearance_dist_iso),
    )

    gap_between_bobbin_coil_depth_side = co.d_mm
    if el.bobbin_plate_thickness_mm > 0:
        # User-defined bobbin end-plate thickness (overrides auto-derivation).
        bobbin_plate_thickness_raw = el.bobbin_plate_thickness_mm
    else:
        bobbin_plate_thickness_raw = (
            max((round(el.isolation_test_voltage_kv) - int(gap_between_bobbin_coil_depth_side)), 3)
            if el.isolation_test_voltage_kv > 2
            else 2
        )
    bobbin_plate_thickness = bobbin_plate_thickness_raw if el.use_bobbin_end_plate_thickness else 0.0

    radius = co.r1_mm
    corner_add_dim_due_to_radius_f1 = radius * math.cos(math.pi * 0.25) + gap_between_bobbin_coil_depth_side - radius
    gap_between_bobbin_coil_width_side = co.c_mm
    corner_add_dim_due_to_radius_f2 = radius * math.cos(math.pi * 0.25) + gap_between_bobbin_coil_width_side - radius

    strand_wise_overall_conductor_thickness = st.overall_max_thickness_mm
    strand_wise_overall_conductor_width = st.overall_max_width_mm

    overall_conductor_thickness = strand_wise_overall_conductor_thickness * va.cond_in_parallel_t + (
        va.cond_in_parallel_t - 1
    ) * el.strand_to_strand_gap_mm

    # Width is derived from the strip width and parallel-in-width count (mirrors
    # the thickness formula). vc.overall_conductor_width_mm (>0) overrides it.
    strip_based_conductor_width = strand_wise_overall_conductor_width * va.cond_in_parallel_w + (
        va.cond_in_parallel_w - 1
    ) * el.strand_to_strand_gap_mm
    overall_conductor_width = (
        vc.overall_conductor_width_mm
        if vc.overall_conductor_width_mm and vc.overall_conductor_width_mm > 0
        else strip_based_conductor_width
    )

    length_without_clamps = vc.core_length_mm * (1 if va.core_type == "core type" else 2) + (
        ins.clearance_mm + vc.window_fitment_width_side_mm if va.core_type == "core type" else 0
    )

    breadth_without_clamps = (
        vc.core_stack_mm + (ins.clearance_mm + vc.window_fitment_width_side_mm)
        if va.core_type == "core type"
        else 2 * vc.window_fitment_width_side_mm
    )

    # The coil wraps a SINGLE limb, so the straight side uses the limb iron width
    # (core_width_for_area_mm), NOT overall_core_width_mm (full 3-limb outline).
    flat_width_surface_per_side = round(
        core_width_for_area_mm
        + el.gap_between_bobbin_core_depth_side_mm * 2
        + bobbin_plate_thickness * 2
        + corner_add_dim_due_to_radius_f1 * 2
        - (overall_conductor_thickness if overall_conductor_thickness > radius else radius)
        * 2
        * math.cos(math.pi * 0.25),
        2,
    )

    flat_depth_surface_per_side = round(
        vc.core_stack_mm
        + el.gap_between_bobbin_core_width_side_mm * 2
        + bobbin_plate_thickness * 2
        + corner_add_dim_due_to_radius_f2 * 2
        - (overall_conductor_thickness if overall_conductor_thickness > radius else radius)
        * 2
        * math.cos(math.pi * 0.25),
        2,
    )

    corner_dimension_per_side = round(
        (math.pi / 2)
        * (
            (overall_conductor_thickness if overall_conductor_thickness > radius else radius)
            + overall_conductor_thickness * int(va.no_of_layers)
            + el.gap_bet_layer_to_layer_mm * (int(va.no_of_layers) - 1)
        ),
        2,
    )

    # Coil stack height in window (legacy 3ph): turns_for_height × (width + turn_to_turn_gap).
    # turns_for_height must match the busiest layer — use max(layer turns), or explicit override.
    max_turns_per_layer = max(layer_turns)
    turns_for_height_eff = (
        int(vc.turns_for_height)
        if vc.turns_for_height is not None and int(vc.turns_for_height) > 0
        else max_turns_per_layer
    )
    # Height stack: electrical turns in column + optional extra row(s) for half-turn / end effects.
    turns_for_height_stack = float(turns_for_height_eff) + max(0.0, float(el.extra_turns_for_window_height))
    coil_height = round(
        turns_for_height_stack * overall_conductor_width
        + turns_for_height_stack * el.turn_to_turn_gap_mm,
        2,
    )
    # Same as legacy: required vertical build for one column of turns (verify vs window c_mm).
    required_coil_height_mm = coil_height

    # Perimeter layer 1 (same as 3ph service)
    if overall_conductor_thickness > radius:
        coil_perimeter_layer1 = round(
            2 * (flat_width_surface_per_side + flat_depth_surface_per_side)
            + 2 * math.pi * (overall_conductor_thickness + overall_conductor_thickness * 0.5),
            2,
        )
    else:
        coil_perimeter_layer1 = round(2 * math.pi * (radius + overall_conductor_thickness * 0.5), 2)

    def _perim_next(prev: float) -> float:
        return round(
            prev + 2 * math.pi * (overall_conductor_thickness + el.gap_bet_layer_to_layer_mm),
            2,
        )

    p1 = coil_perimeter_layer1
    p2 = _perim_next(p1)
    p3 = _perim_next(p2)
    p4 = _perim_next(p3)
    p5 = _perim_next(p4)
    p6 = _perim_next(p5)

    nl = int(va.no_of_layers)
    lt = list(layer_turns) + [0] * (6 - len(layer_turns))
    first, second, third, fourth, fifth, sixth = lt[:6]

    # Per-layer sizing breakdown (mean turn perimeter × turns in that layer).
    all_perims = [p1, p2, p3, p4, p5, p6]
    perimeters_by_layer = [round(all_perims[i], 2) for i in range(nl)]
    layer_length_contrib = [
        round(all_perims[i] * lt[i], 2) for i in range(nl)
    ]

    each_coil_length = round(
        p1 * first
        + (p2 if nl > 1 else 0) * second
        + (p3 if nl > 2 else 0) * third
        + (p4 if nl > 3 else 0) * fourth
        + (p5 if nl > 4 else 0) * fifth
        + (p6 if nl > 5 else 0) * sixth,
        2,
    )

    total_lead_length = round(
        24
        - 3 * overall_conductor_thickness
        + 3 * math.pi * overall_conductor_thickness
        + inp.terminal_lug_length_mm * 2,
        2,
    )

    typical_cond_area = st.nom_area_mm2
    overall_typical_cond_area = typical_cond_area * va.cond_in_parallel_w * va.cond_in_parallel_t

    # Resolve conductor properties from the material library, allowing explicit
    # per-field overrides (set by the UI material dropdown) to take precedence.
    cond_props = _conductor_properties(va.conductor_material)
    sigma = (
        va.conductor_sigma_ms_m
        if va.conductor_sigma_ms_m is not None
        else cond_props["sigma_ms_m"]
    )
    cond_density = (
        va.conductor_density_kg_m3
        if va.conductor_density_kg_m3 is not None
        else cond_props["density_kg_m3"]
    )
    temp_const = (
        va.conductor_temp_coeff_const
        if va.conductor_temp_coeff_const is not None
        else cond_props["temp_coeff_const"]
    )

    lead_resistance = (
        (total_lead_length * 0.001) / (overall_typical_cond_area * sigma)
        if overall_typical_cond_area > 0
        else 0.0
    )

    rdc_20c = (
        (each_coil_length * 0.001) / (overall_typical_cond_area * sigma) + lead_resistance
        if overall_typical_cond_area > 0
        else 0.0
    )

    rdc_150c = rdc_20c * (temp_const + 150) / (temp_const + 20)

    # Legacy 3ph: length_coil_femm = core_stack * 2 * turns
    length_coil_femm = vc.core_stack_mm * 2 * turns

    dc_coil_loss_150c_per_phase = el.irms_a**2 * rdc_150c
    dc_coil_loss_150c_three_phase = 3.0 * dc_coil_loss_150c_per_phase

    each_coil_mass_kg = (
        overall_typical_cond_area * (each_coil_length + total_lead_length) * 1e-9 * cond_density
    )

    total_airgap_mm = ((4 * math.pi * 1e-7 * (turns**2) * core_area_m2_eff) / (el.inductance_uh * 1e-6)) * 1000
    airgap_limb_location = (
        el.femm_total_airgap_limb_mm if el.femm_total_airgap_limb_mm > 0 else total_airgap_mm
    ) / max(1, el.airgap_locations_limb)

    height_without_clamps = vc.add_consideration_for_coil_height_mm + airgap_limb_location

    # ------------------------------------------------------------------ #
    # Core weight (geometry x lamination density).
    #
    # Front-view iron area of a 3-limb (E / shell) core:
    #   limbs  = core_width * window_height * 3
    #   yokes  = (core_width * 3 + window_width * 2) * core_width * 2  (top + bottom)
    #   volume = (limbs + yokes) * core_stack
    #   mass   = volume * density
    # ------------------------------------------------------------------ #
    limb_width_mm = core_width_for_area_mm  # resolved above (falls back to overall_core_width)
    core_face_limbs_mm2 = limb_width_mm * vc.window_height_mm * 3.0
    core_face_yoke_mm2 = (limb_width_mm * 3.0 + vc.window_width_mm * 2.0) * limb_width_mm * 2.0
    core_face_area_mm2 = core_face_limbs_mm2 + core_face_yoke_mm2
    core_density_used = (
        float(vc.core_density_kg_m3)
        if vc.core_density_kg_m3 is not None and float(vc.core_density_kg_m3) > 0
        else _core_density(va.core_material)
    )
    core_volume_m3 = core_face_area_mm2 * vc.core_stack_mm * 1e-9
    core_mass_geometry_kg = core_volume_m3 * core_density_used

    # Prefer geometry-based weight; allow an explicit manual override via core_mass_kg (>0).
    core_mass_used_kg = (
        vc.core_mass_kg if (vc.core_mass_kg is not None and vc.core_mass_kg > 0)
        else core_mass_geometry_kg
    )
    mass_without_clamps_kg = core_mass_used_kg + each_coil_mass_kg * 3

    # ------------------------------------------------------------------ #
    # Core loss (Steinmetz):  Pv = k * f^a * B^b   [W/m^3]
    #   B  = rated-peak flux density (not short-term overload B)
    #   f  = operating frequency
    #   k,a,b resolved from the selected core material (material library)
    # Losses are reported for the central limb (fed to the thermal stage)
    # and for the whole 3-limb core (limbs + yokes).
    # ------------------------------------------------------------------ #
    stein = _core_steinmetz(va.core_material)

    def _stein_val(override: Optional[float], lib_val: float) -> float:
        return float(override) if (override is not None and float(override) > 0) else lib_val

    stein_k = _stein_val(va.steinmetz_k_override, stein["steinmetz_k"])
    stein_a = _stein_val(va.steinmetz_a_override, stein["steinmetz_a"])
    stein_b = _stein_val(va.steinmetz_b_override, stein["steinmetz_b"])
    core_freq_hz = float(el.frequency_hz) if el.frequency_hz and el.frequency_hz > 0 else 0.0
    core_loss_pv_w_m3 = (
        stein_k * (core_freq_hz ** stein_a) * (float(bmax_rated) ** stein_b)
        if core_freq_hz > 0 and bmax_rated > 0
        else 0.0
    )
    sf_core = float(vc.stacking_factor) if vc.stacking_factor and vc.stacking_factor > 0 else 1.0
    # Iron volumes (gross geometry x stacking factor).
    central_limb_iron_volume_m3 = (
        limb_width_mm * vc.window_height_mm * vc.core_stack_mm * 1e-9 * sf_core
    )
    total_core_iron_volume_m3 = core_volume_m3 * sf_core
    core_loss_central_limb_w = round(core_loss_pv_w_m3 * central_limb_iron_volume_m3, 3)
    core_loss_total_w = round(core_loss_pv_w_m3 * total_core_iron_volume_m3, 3)

    # Clearance/creepage reserve for open-winding or no-bobbin cases.
    base_clearance_req_mm = max(
        ins.clearance_mm,
        ins.req_clearance_dist_op,
        ins.req_clearance_dist_iso,
        ins.req_creepage_dist_op,
        ins.req_creepage_dist_iso,
        ins.min_airflow_clearance_mm,
    )
    droplet_clearance_req_mm = max(
        ins.core_to_coil_droplet_clearance_mm,
        ins.coil_to_core_droplet_clearance_mm,
    )
    per_side_window_height_clearance_mm = max(base_clearance_req_mm, droplet_clearance_req_mm)
    if ins.allow_clearance_reduction:
        per_side_window_height_clearance_mm *= min(max(ins.clearance_reduction_factor, 0.0), 1.0)

    total_window_height_reserved_mm = (
        2.0 * per_side_window_height_clearance_mm if ins.apply_window_height_clearance else 0.0
    )
    available_window_height_mm = max(0.0, vc.window_height_mm - total_window_height_reserved_mm)

    # Height fitment against effective available window height.
    wh_util = (
        round((required_coil_height_mm / available_window_height_mm) * 100, 2)
        if available_window_height_mm > 0
        else 0.0
    )
    wh_util_declared_pct: Optional[float] = None
    if vc.window_fitment_height_side_mm > 0:
        wh_util_declared_pct = round(
            (vc.window_fitment_height_side_mm / vc.window_height_mm) * 100, 2
        )

    h_fit_for_factor = (
        vc.window_fitment_height_side_mm
        if vc.window_fitment_height_side_mm > 0
        else required_coil_height_mm
    )
    w_fit_for_factor = (
        vc.window_fitment_width_side_mm
        if vc.window_fitment_width_side_mm > 0
        else (
            overall_conductor_thickness * max(1, int(va.no_of_layers))
            + el.gap_bet_layer_to_layer_mm * max(0, int(va.no_of_layers) - 1)
        )
    )

    # Window-width utilization (3-limb core): each window is shared by TWO coils
    # (one from each bounding limb). The width consumed per coil is the radial
    # copper build + coil-core clearance (window side) + bobbin end-plate.
    per_coil_window_build_mm = (
        w_fit_for_factor + el.gap_between_bobbin_core_depth_side_mm + bobbin_plate_thickness
    )
    occupied_window_width_mm = round(2.0 * per_coil_window_build_mm, 2)
    ww_util = (
        round((occupied_window_width_mm / vc.window_width_mm) * 100, 2)
        if vc.window_width_mm > 0 else 0.0
    )

    window_utilization_factor = (
        (h_fit_for_factor * (w_fit_for_factor - ins.clearance_mm))
        / (available_window_height_mm * (vc.window_width_mm - ins.clearance_mm))
        if (available_window_height_mm * (vc.window_width_mm - ins.clearance_mm)) > 0
        else 0.0
    )

    return {
        "turns": turns,
        "core_area_m2_effective": core_area_m2_eff,
        "core_area_m2_geometry_based": geom_core_area_m2,
        "bmax_t": bmax,
        "bmax_short_term_t": bmax_short_term,
        "bmax_rated_t": bmax_rated,
        "rated_peak_current_a": i_rated_peak,
        "bmax_allowed_t": bmax_allowed,
        "current_density_a_per_mm2": current_density,
        "each_coil_length_mm": each_coil_length,
        "length_coil_femm_mm": length_coil_femm,
        "core_stack_mm": vc.core_stack_mm,
        "total_lead_length_mm": total_lead_length,
        "rdc_20c_ohm": rdc_20c,
        "rdc_150c_ohm": rdc_150c,
        "dc_coil_loss_150c_w_per_phase": dc_coil_loss_150c_per_phase,
        "dc_coil_loss_150c_w_three_phase_total": dc_coil_loss_150c_three_phase,
        "each_coil_mass_kg": each_coil_mass_kg,
        "total_copper_mass_three_phase_kg": each_coil_mass_kg * 3,
        "core_face_area_mm2": core_face_area_mm2,
        "core_volume_m3": core_volume_m3,
        "core_density_kg_m3_used": core_density_used,
        "core_mass_geometry_kg": core_mass_geometry_kg,
        "core_mass_used_kg": core_mass_used_kg,
        "total_mass_without_clamps_kg": mass_without_clamps_kg,
        "core_loss_frequency_hz": core_freq_hz,
        "core_loss_steinmetz_k": stein_k,
        "core_loss_steinmetz_a": stein_a,
        "core_loss_steinmetz_b": stein_b,
        "core_loss_bpeak_t": float(bmax_rated),
        "core_loss_pv_w_m3": round(core_loss_pv_w_m3, 3),
        "core_loss_central_limb_w": core_loss_central_limb_w,
        "core_loss_total_w": core_loss_total_w,
        "coil_height_mm": coil_height,
        "max_turns_per_layer": max_turns_per_layer,
        "turns_for_height_effective": turns_for_height_eff,
        "extra_turns_for_window_height": el.extra_turns_for_window_height,
        "turns_for_height_stack": turns_for_height_stack,
        "required_coil_height_mm": required_coil_height_mm,
        "wh_utilization_declared_pct": wh_util_declared_pct,
        "bobbin_plate_thickness_raw_mm": bobbin_plate_thickness_raw,
        "bobbin_plate_thickness_used_mm": bobbin_plate_thickness,
        "per_side_window_height_clearance_mm": per_side_window_height_clearance_mm,
        "total_window_height_reserved_mm": total_window_height_reserved_mm,
        "available_window_height_mm": available_window_height_mm,
        "flat_width_surface_per_side_mm": flat_width_surface_per_side,
        "flat_depth_surface_per_side_mm": flat_depth_surface_per_side,
        "coil_perimeter_layer1_mm": coil_perimeter_layer1,
        "coil_perimeters_by_layer_mm": perimeters_by_layer,
        "coil_length_by_layer_mm": layer_length_contrib,
        "overall_conductor_thickness_mm": round(overall_conductor_thickness, 3),
        "overall_conductor_width_mm": round(overall_conductor_width, 3),
        "overall_conductor_area_mm2": round(overall_typical_cond_area, 3),
        "wh_utilization_pct": wh_util,  # required_coil_height / window_height
        "ww_utilization_pct": ww_util,
        "occupied_window_width_mm": occupied_window_width_mm,
        "window_utilization_factor": window_utilization_factor,
        "airgap_total_analytical_mm": total_airgap_mm,
        "airgap_limb_location_mm": airgap_limb_location,
        "minimum_gap_bw_coils_mm": minimum_gap_bw_coils,
        "layer_turns": layer_turns,
        "first_layer_turns": first_layer_turns,
    }


def demo() -> None:
    """Example run with placeholder variable_calculations (replace with DB-backed values)."""
    inp = ThreePhaseDesignInputs(
        electrical=ThreePhaseElectricalInputs(
            inductance_uh=300.0,
            irms_a=150.0,
            short_term_peak_current_a=230.0,
        ),
        variable=ThreePhaseVariableInputs(
            core_type="shell type",
            no_of_layers=1,
            significance_turns=1,
        ),
        insulation=ThreePhaseInsulationCoordination(),
        variable_calc=ThreePhaseVariableCalculations(),
        strip=ThreePhaseStripData(),
        corner=ThreePhaseCornerData(),
        terminal_lug_length_mm=0.0,
    )
    out = run_three_phase_design(inp)
    for k, v in out.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    demo()
