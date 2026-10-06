"""
Three-phase inductor sizing engine.

This module mirrors the workbook's first-pass sizing flow:
- turns from L, Ipk, B_allow, Ae
- flux checks (peak/continuous/ripple)
- airgap estimation
- copper and core loss estimation
- simple thermal dissipation check
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List, Tuple


MU0 = 4e-7 * math.pi
RHO_CU_20C = 1.724e-8
ALPHA_CU = 0.00393


@dataclass
class ThreePhaseInput:
    inductance_h: float
    i_rms_a: float
    i_peak_a: float
    i_continuous_a: float
    i_ripple_pp_a: float
    freq_hz: float
    ae_m2: float
    core_volume_m3: float
    conductor_area_m2: float
    conductor_length_per_phase_m: float
    max_flux_density_t: float
    airgap_locations_per_limb: int = 1
    stack_count: int = 1
    ambient_temp_c: float = 55.0
    max_surface_temp_c: float = 145.0
    cooling_method: str = "forced"  # natural | forced
    airflow_m_s: float = 0.0
    steinmetz_k: float = 6.5
    steinmetz_a: float = 1.51
    steinmetz_b: float = 1.74
    # Optional thermal geometry for workbook-style convection calculations.
    exposed_surface_area_m2: float = 0.0
    characteristic_length_m: float = 0.0
    # Workbook thermal sheet defaults at film temperature (~100 C).
    air_kinematic_viscosity_m2_s: float = 23.0597e-6
    air_thermal_diffusivity_m2_s: float = 32.92e-6
    air_thermal_conductivity_w_mk: float = 0.03163493
    air_prandtl: float = 0.700504
    emissivity: float = 0.8
    # Workbook-style mounting/orientation selectors:
    # airflow_direction_code in {"D1","D2","D3","D4"}
    # mounting in {"Vertical","Horizontal"}
    airflow_direction_code: str = "D2"
    mounting: str = "Vertical"
    # Geometry references used to reconstruct characteristic dimensions
    # similar to Design!O26..O29 in the workbook.
    flat_width_surface_mm: float = 23.8
    flat_depth_surface_mm: float = 38.0
    corner_dimension_mm: float = 11.31
    coil_height_mm: float = 31.5
    # Optional split thermal areas/lengths to closely match workbook cells:
    # D7 (natural plate), D30 (radiation plate), D44 (forced/combined plate),
    # D5, D48, D42 respectively.
    natural_area_m2: float = 0.0
    radiation_area_m2: float = 0.0
    forced_area_m2: float = 0.0
    natural_length_m: float = 0.0
    natural_mix_length_m: float = 0.0
    forced_length_m: float = 0.0
    thermal_loss_reference_w: float = 0.0


@dataclass
class ThreePhaseResult:
    turns: int
    b_peak_t: float
    b_continuous_t: float
    delta_b_t: float
    airgap_total_per_limb_mm: float
    airgap_each_location_mm: float
    rdc_per_phase_ohm: float
    copper_loss_total_w: float
    core_loss_total_w: float
    total_loss_w: float
    thermal_dissipation_capability_w: float
    thermal_dissipation_natural_w: float
    thermal_dissipation_forced_w: float
    thermal_dissipation_radiation_w: float
    required_airflow_m_s: float
    required_airflow_d87_m_s: float
    required_airflow_e87_m_s: float
    warnings: List[str]
    debug_thermal: Dict[str, float | str]


def _calc_turns(inductance_h: float, i_peak_a: float, max_flux_density_t: float, ae_m2: float) -> int:
    n = math.ceil((inductance_h * i_peak_a) / (max_flux_density_t * ae_m2))
    return max(1, int(n))


def _calc_flux(inductance_h: float, current_a: float, turns: int, ae_m2: float) -> float:
    return (inductance_h * current_a) / (turns * ae_m2)


def _calc_airgap_mm(inductance_h: float, turns: int, ae_m2: float) -> float:
    # From magnetic-circuit approximation used in workbook-style sizing.
    return ((turns**2) * MU0 * ae_m2 / inductance_h) * 1000.0


def _calc_rdc_ohm(length_m: float, area_m2: float, temp_c: float) -> float:
    rho_t = RHO_CU_20C * (1 + ALPHA_CU * (temp_c - 20.0))
    return rho_t * length_m / area_m2


def _calc_core_loss_w(volume_m3: float, freq_hz: float, b_peak_t: float, k: float, a: float, b: float) -> float:
    # Pv = k * f^a * B^b (W/m^3)
    return volume_m3 * k * (freq_hz**a) * (b_peak_t**b)


def _natural_h_w_m2k(
    area_m2: float,
    lc_m: float,
    dtemp_k: float,
    k_air: float,
    nu_air: float,
    alpha_air: float,
    pr_air: float,
) -> float:
    if area_m2 <= 0 or lc_m <= 0 or dtemp_k <= 0:
        return 0.0
    g = 9.81
    beta = 1.0 / 300.0
    ra = g * beta * dtemp_k * (lc_m**3) / (nu_air * alpha_air)
    # Vertical plate (close to workbook engineering approximation).
    nu = 0.68 + (0.67 * (ra**0.25)) / ((1.0 + (0.492 / pr_air) ** (9.0 / 16.0)) ** (4.0 / 9.0))
    return nu * k_air / lc_m


def _forced_h_w_m2k(velocity_m_s: float, lc_m: float, nu_air: float, k_air: float, pr_air: float) -> float:
    if velocity_m_s <= 0 or lc_m <= 0:
        return 0.0
    re = velocity_m_s * lc_m / nu_air
    if re < 5e5:
        nu = 0.664 * (re**0.5) * (pr_air ** (1.0 / 3.0))
    else:
        nu = (0.037 * (re**0.8) - 871.0) * (pr_air ** (1.0 / 3.0))
    return max(0.0, nu * k_air / lc_m)


def _radiation_h_w_m2k(ts_k: float, tamb_k: float, emissivity: float) -> float:
    sigma = 5.670374419e-8
    return emissivity * sigma * (ts_k + tamb_k) * (ts_k * ts_k + tamb_k * tamb_k)


def _directional_dimensions_m(inp: ThreePhaseInput) -> tuple[float, float]:
    """
    Reconstruct characteristic length/width from workbook D1..D4 mapping.
    Returns (length_m, width_m).
    """
    fw = inp.flat_width_surface_mm
    fd = inp.flat_depth_surface_mm
    cd = inp.corner_dimension_mm
    ch = inp.coil_height_mm
    code = (inp.airflow_direction_code or "D2").upper()
    mount = (inp.mounting or "Vertical").lower()

    table_mm = {
        "D1_VERTICAL": (ch, 2.0 * fd),
        "D1_HORIZONTAL": (fd, 2.0 * ch),
        "D2_VERTICAL": (ch, 2.0 * fd),
        "D2_HORIZONTAL": (fd, 2.0 * ch),
        "D3_VERTICAL": (ch, fw),
        "D3_HORIZONTAL": ((fw * ch) / max(2.0 * fw + 2.0 * ch, 1e-9), 2.0 * fw + 2.0 * ch),
        "D4_VERTICAL": (ch, 2.0 * fd),
        "D4_HORIZONTAL": (fd, 2.0 * ch),
    }
    key = f"{code}_{'VERTICAL' if mount.startswith('v') else 'HORIZONTAL'}"
    length_mm, width_mm = table_mm.get(key, table_mm["D2_VERTICAL"])
    return length_mm * 1e-3, width_mm * 1e-3


def _thermal_capability_w(
    inp: ThreePhaseInput, thermal_loss_w: float
) -> Tuple[float, float, float, float, float, float, Dict[str, float | str]]:
    dtemp = max(0.0, inp.max_surface_temp_c - inp.ambient_temp_c)
    if dtemp <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {"regime": "none", "dtemp": 0.0}

    d_len_m, d_wid_m = _directional_dimensions_m(inp)

    area = inp.exposed_surface_area_m2
    if area <= 0:
        # Prefer workbook-style directional area when available.
        area = d_len_m * d_wid_m
        if area <= 0:
            # Fallback from volume if directional estimate is not valid.
            side_m = inp.core_volume_m3 ** (1.0 / 3.0)
            area = 6.0 * side_m * side_m

    area_nat = inp.natural_area_m2 if inp.natural_area_m2 > 0 else area
    area_rad = inp.radiation_area_m2 if inp.radiation_area_m2 > 0 else area
    area_forced = inp.forced_area_m2 if inp.forced_area_m2 > 0 else area

    lc = inp.characteristic_length_m
    if lc <= 0:
        # Workbook uses directional characteristic lengths; approximate with
        # its mapped length if explicit value is not provided.
        lc = d_len_m if d_len_m > 0 else max(1e-4, math.sqrt(max(area, 1e-12)))

    # Workbook-style separation:
    # - natural branch uses lc_nat
    # - forced branch uses lc_forced
    lc_forced = inp.forced_length_m if inp.forced_length_m > 0 else lc
    lc_nat = inp.natural_length_m if inp.natural_length_m > 0 else max(1e-6, d_len_m if d_len_m > 0 else lc_forced)
    lc_nat_mix = inp.natural_mix_length_m if inp.natural_mix_length_m > 0 else lc_nat

    # Radiation contribution (sheet D37-style linearization)
    ts_k = inp.max_surface_temp_c + 273.15
    ta_k = inp.ambient_temp_c + 273.15
    h_rad = _radiation_h_w_m2k(ts_k, ta_k, inp.emissivity)
    q_rad = h_rad * area_rad * dtemp

    # Natural convection (D64 -> D65 style)
    gr_nat = 9.81 * (1.0 / max(((ts_k + ta_k) * 0.5), 1e-6)) * dtemp * (lc_nat**3) / (
        inp.air_kinematic_viscosity_m2_s**2
    )
    ra_nat = gr_nat * inp.air_prandtl
    nu_nat = (0.825 + (0.387 * (ra_nat ** (1.0 / 6.0))) / ((1 + (0.492 / inp.air_prandtl) ** (9.0 / 16.0)) ** (8.0 / 27.0))) ** 2
    h_nat = 0.0 if inp.air_thermal_conductivity_w_mk == 0 else nu_nat * inp.air_thermal_conductivity_w_mk / lc_nat
    q_nat = h_nat * area_nat * dtemp

    # Forced convection (D53 -> D59 -> D46 style)
    re_forced = 0.0 if inp.airflow_m_s <= 0 else inp.airflow_m_s * lc_forced / inp.air_kinematic_viscosity_m2_s
    if inp.airflow_m_s <= 0 or lc_forced <= 0:
        nu_forced = 0.0
    elif re_forced < 5e5:
        nu_forced = 0.664 * (re_forced**0.5) * (inp.air_prandtl ** (1.0 / 3.0))
    else:
        nu_forced = 0.037 * (re_forced**0.8) * (inp.air_prandtl ** (1.0 / 3.0))
    h_forced = 0.0 if inp.air_thermal_conductivity_w_mk == 0 else nu_forced * inp.air_thermal_conductivity_w_mk / lc_forced
    q_forced = h_forced * area_forced * dtemp

    # Mixed convection regime selector based on Gr/Re^2 (sheet D56,D57 behavior)
    if re_forced <= 0:
        ratio = 1e100
    else:
        gr_forced_len = 9.81 * (1.0 / max(((ts_k + ta_k) * 0.5), 1e-6)) * dtemp * (lc_forced**3) / (
            inp.air_kinematic_viscosity_m2_s**2
        )
        ratio = gr_forced_len / (re_forced**2)

    if ratio < 0.1:
        regime = "forced"
    elif ratio > 10:
        regime = "natural"
    else:
        regime = "mixed"

    # Workbook-like combination exponent (vertical=3, horizontal=4)
    n_exp = 3.0 if inp.mounting.lower().startswith("v") else 4.0

    # D1 and D3 rows in workbook use subtractive combination; others additive.
    subtractive_codes = {"D1", "D3"}
    # D60 and D66 sheet behavior: scaled only in mixed-transition conditions.
    if regime == "mixed" and h_forced < h_nat:
        h_forced_mix = h_forced * lc_forced / max(lc_nat_mix, 1e-12)
    else:
        h_forced_mix = h_forced
    if regime == "mixed" and h_forced > h_nat:
        h_nat_mix = h_nat * lc_forced / max(lc_nat_mix, 1e-12)
    else:
        h_nat_mix = h_nat

    if inp.airflow_direction_code.upper() in subtractive_codes:
        h_combined = abs((h_forced_mix**n_exp) - (h_nat_mix**n_exp)) ** (1.0 / n_exp)
    else:
        h_combined = ((h_forced_mix**n_exp) + (h_nat_mix**n_exp)) ** (1.0 / n_exp)

    if inp.cooling_method.lower() == "natural":
        q_conv_combined = q_nat
    elif regime == "forced":
        q_conv_combined = h_forced * area_forced * dtemp
    elif regime == "natural":
        q_conv_combined = h_nat * area_forced * dtemp
    else:
        q_conv_combined = h_combined * area_forced * dtemp

    q_total = q_conv_combined + q_rad + q_nat

    # Required airflow from required forced heat transfer (D81..D87 style).
    # D81 removes known natural + radiation components.
    q_required_forced_conv = max(0.0, thermal_loss_w - (q_nat + q_rad))
    h_req_combined = q_required_forced_conv / max(area_forced * dtemp, 1e-12)
    nu_req_combined = h_req_combined * lc_forced / max(inp.air_thermal_conductivity_w_mk, 1e-12)

    # Inverse of D84 logic simplified to forced branch target.
    nu_nat_mix = nu_nat * lc_forced / max(lc_nat_mix, 1e-12)
    if inp.airflow_direction_code.upper() in subtractive_codes:
        nu_req_forced = ((nu_req_combined**n_exp) + (nu_nat_mix**n_exp)) ** (1.0 / n_exp)
    else:
        nu_req_forced = abs((nu_req_combined**n_exp) - (nu_nat_mix**n_exp)) ** (1.0 / n_exp)

    if nu_req_forced <= 0:
        re_req = 0.0
    else:
        re_lam = (nu_req_forced / (0.664 * (inp.air_prandtl ** (1.0 / 3.0)))) ** 2
        if re_lam < 5e5:
            re_req = re_lam
        else:
            re_req = (nu_req_forced / (0.037 * (inp.air_prandtl ** (1.0 / 3.0)))) ** (1.0 / 0.8)
    req_v_d87 = re_req * inp.air_kinematic_viscosity_m2_s / max(lc_forced, 1e-12)

    # Workbook E87 empirical relation.
    h_req = nu_req_forced * inp.air_thermal_conductivity_w_mk / max(lc_forced, 1e-12)
    term = h_req * (lc_forced**0.288)
    if h_req <= 0 or term < 3.33:
        req_v_e87 = 0.0
    else:
        req_v_e87 = ((term - 3.33) / 4.8) ** 1.25

    debug = {
        "regime": regime,
        "dtemp_c": dtemp,
        "area_nat_m2": area_nat,
        "area_rad_m2": area_rad,
        "area_forced_m2": area_forced,
        "lc_nat_m": lc_nat,
        "lc_nat_mix_m": lc_nat_mix,
        "lc_forced_m": lc_forced,
        "gr_nat": gr_nat,
        "ra_nat": ra_nat,
        "nu_nat": nu_nat,
        "h_nat_w_m2k": h_nat,
        "re_forced": re_forced,
        "nu_forced": nu_forced,
        "h_forced_w_m2k": h_forced,
        "gr_re2_ratio": ratio,
        "mix_exponent_n": n_exp,
        "h_combined_w_m2k": h_combined,
        "h_rad_w_m2k": h_rad,
        "q_required_forced_conv_w": q_required_forced_conv,
        "h_req_combined_w_m2k": h_req_combined,
        "nu_req_combined": nu_req_combined,
        "nu_req_forced": nu_req_forced,
        "re_req": re_req,
        "req_v_d87_m_s": req_v_d87,
        "req_v_e87_m_s": req_v_e87,
    }
    return q_total, q_nat, q_forced, q_rad, max(0.0, req_v_d87), max(0.0, req_v_e87), debug


def calculate_three_phase_inductor(inp: ThreePhaseInput) -> ThreePhaseResult:
    warnings: List[str] = []

    turns = _calc_turns(inp.inductance_h, inp.i_peak_a, inp.max_flux_density_t, inp.ae_m2)
    b_peak = _calc_flux(inp.inductance_h, inp.i_peak_a, turns, inp.ae_m2)
    b_cont = _calc_flux(inp.inductance_h, inp.i_continuous_a, turns, inp.ae_m2)
    d_b = _calc_flux(inp.inductance_h, inp.i_ripple_pp_a, turns, inp.ae_m2)

    airgap_total_mm = _calc_airgap_mm(inp.inductance_h, turns, inp.ae_m2)
    gap_count = max(1, int(inp.airgap_locations_per_limb))
    airgap_each_mm = airgap_total_mm / gap_count

    rdc_phase = _calc_rdc_ohm(inp.conductor_length_per_phase_m, inp.conductor_area_m2, 150.0)
    p_cu_total = 3.0 * (inp.i_rms_a**2) * rdc_phase

    p_core_total = _calc_core_loss_w(
        inp.core_volume_m3, inp.freq_hz, b_peak, inp.steinmetz_k, inp.steinmetz_a, inp.steinmetz_b
    )

    p_total = p_cu_total + p_core_total

    thermal_ref_loss = inp.thermal_loss_reference_w if inp.thermal_loss_reference_w > 0 else (p_cu_total / 3.0 + p_core_total / 3.0)
    thermal_cap, q_nat, q_forced, q_rad, req_airflow_d87, req_airflow_e87, debug_thermal = _thermal_capability_w(
        inp, thermal_ref_loss
    )

    if b_peak > inp.max_flux_density_t:
        warnings.append(f"Peak flux exceeds limit: {b_peak:.3f} T > {inp.max_flux_density_t:.3f} T")
    if thermal_cap < thermal_ref_loss:
        warnings.append(
            "Thermal dissipation below thermal reference loss. Increase airflow/surface area or reduce losses."
        )
    if inp.conductor_area_m2 <= 0:
        warnings.append("Conductor area must be positive.")

    return ThreePhaseResult(
        turns=turns,
        b_peak_t=b_peak,
        b_continuous_t=b_cont,
        delta_b_t=d_b,
        airgap_total_per_limb_mm=airgap_total_mm,
        airgap_each_location_mm=airgap_each_mm,
        rdc_per_phase_ohm=rdc_phase,
        copper_loss_total_w=p_cu_total,
        core_loss_total_w=p_core_total,
        total_loss_w=p_total,
        thermal_dissipation_capability_w=thermal_cap,
        thermal_dissipation_natural_w=q_nat,
        thermal_dissipation_forced_w=q_forced,
        thermal_dissipation_radiation_w=q_rad,
        required_airflow_m_s=req_airflow_d87,
        required_airflow_d87_m_s=req_airflow_d87,
        required_airflow_e87_m_s=req_airflow_e87,
        warnings=warnings,
        debug_thermal=debug_thermal,
    )
