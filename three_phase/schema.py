"""JSON spec <-> analytical design inputs for the cloud web app."""
from __future__ import annotations

from typing import Any

from .analytical_design import (
    ThreePhaseCornerData,
    ThreePhaseDesignInputs,
    ThreePhaseElectricalInputs,
    ThreePhaseInsulationCoordination,
    ThreePhaseStripData,
    ThreePhaseVariableCalculations,
    ThreePhaseVariableInputs,
    run_three_phase_design,
)
from .material_library import core_properties

DEFAULT_SPEC: dict[str, Any] = {
    "electrical": {
        "inductance_uh": 180.0,
        "irms_a": 180.0,
        "short_term_peak_current_a": 340.0,
        "rated_peak_current_a": 254.6,
        "frequency_hz": 50.0,
        "ripple_current_a": 59.0,
        "turn_to_turn_gap_mm": 0.23,
        "gap_bet_layer_to_layer_mm": 0.3,
        "strand_to_strand_gap_mm": 0.2,
        "gap_between_bobbin_core_depth_side_mm": 15.0,
        "gap_between_bobbin_core_width_side_mm": 15.0,
        "isolation_test_voltage_kv": 3.3,
        "femm_total_airgap_limb_mm": 0.0,
        "airgap_locations_limb": 2,
        "extra_turns_for_window_height": 1.0,
    },
    "variable": {
        "core_type": "Core type",
        "series_parallel": "series",
        "cond_in_parallel_t": 1,
        "cond_in_parallel_w": 1,
        "no_of_layers": 1,
        "conductor_material": "copper",
        "core_material": "CRGO M4 (0.27 mm)",
        "significance_turns": 1,
    },
    "insulation": {"clearance_mm": 0.0},
    "variable_calc": {
        "allowed_max_flux_density_t": 0.6,
        "core_width_for_area_mm": 70.0,
        "no_of_cores_in_stack": 1.0,
        "stacking_factor": 0.95,
        "core_stack_mm": 140.0,
        "overall_core_width_mm": 320.0,
        "window_height_mm": 160.0,
        "window_width_mm": 60.0,
        "core_length_mm": 130.25,
        "a_mm": 70.0,
        "b_mm": 60.0,
        "c_mm": 160.0,
        "d_mm": 140.0,
        "e_mm": 120.0,
    },
    "strip": {
        "nom_area_mm2": 99.0,
        "overall_max_width_mm": 11.0,
        "overall_max_thickness_mm": 9.0,
    },
    "corner": {"d_mm": 1.0, "r1_mm": 6.0, "c_mm": 1.0},
    "terminal_lug_length_mm": 0.0,
    "limits": {
        "max_current_density_a_mm2": 4.0,
        "max_window_util_pct": 100.0,
        "max_hotspot_c": 145.0,
        "ambient_c": 55.0,
    },
}


def _f(d: dict, key: str, default: float) -> float:
    if key not in d or d[key] in (None, ""):
        return default
    return float(d[key])


def _i(d: dict, key: str, default: int) -> int:
    if key not in d or d[key] in (None, ""):
        return default
    return int(d[key])


def spec_from_dict(raw: dict[str, Any] | None) -> ThreePhaseDesignInputs:
    src = DEFAULT_SPEC
    if raw:
        merged = {
            "electrical": {**src["electrical"], **(raw.get("electrical") or {})},
            "variable": {**src["variable"], **(raw.get("variable") or {})},
            "insulation": {**src["insulation"], **(raw.get("insulation") or {})},
            "variable_calc": {**src["variable_calc"], **(raw.get("variable_calc") or {})},
            "strip": {**src["strip"], **(raw.get("strip") or {})},
            "corner": {**src["corner"], **(raw.get("corner") or {})},
            "terminal_lug_length_mm": raw.get("terminal_lug_length_mm", src["terminal_lug_length_mm"]),
            "limits": {**src["limits"], **(raw.get("limits") or {})},
        }
    else:
        merged = src
    el, va, ins, vc, st, co = (
        merged["electrical"],
        merged["variable"],
        merged["insulation"],
        merged["variable_calc"],
        merged["strip"],
        merged["corner"],
    )
    rated = el.get("rated_peak_current_a")
    return ThreePhaseDesignInputs(
        electrical=ThreePhaseElectricalInputs(
            inductance_uh=_f(el, "inductance_uh", 180),
            irms_a=_f(el, "irms_a", 180),
            short_term_peak_current_a=_f(el, "short_term_peak_current_a", 340),
            rated_peak_current_a=float(rated) if rated not in (None, "") else None,
            frequency_hz=_f(el, "frequency_hz", 50),
            turn_to_turn_gap_mm=_f(el, "turn_to_turn_gap_mm", 0.23),
            gap_bet_layer_to_layer_mm=_f(el, "gap_bet_layer_to_layer_mm", 0.3),
            strand_to_strand_gap_mm=_f(el, "strand_to_strand_gap_mm", 0.2),
            isolation_test_voltage_kv=_f(el, "isolation_test_voltage_kv", 3.3),
            gap_between_bobbin_core_width_side_mm=_f(el, "gap_between_bobbin_core_width_side_mm", 15),
            gap_between_bobbin_core_depth_side_mm=_f(el, "gap_between_bobbin_core_depth_side_mm", 15),
            femm_total_airgap_limb_mm=_f(el, "femm_total_airgap_limb_mm", 0),
            airgap_locations_limb=_i(el, "airgap_locations_limb", 2),
            extra_turns_for_window_height=_f(el, "extra_turns_for_window_height", 1),
        ),
        variable=ThreePhaseVariableInputs(
            core_type=str(va.get("core_type") or "Core type"),
            series_parallel=str(va.get("series_parallel") or "series"),
            cond_in_parallel_t=_i(va, "cond_in_parallel_t", 1),
            cond_in_parallel_w=_i(va, "cond_in_parallel_w", 1),
            no_of_layers=_i(va, "no_of_layers", 1),
            conductor_material=str(va.get("conductor_material") or "copper"),
            core_material=str(va.get("core_material") or "CRGO M4 (0.27 mm)"),
            significance_turns=_i(va, "significance_turns", 1),
        ),
        insulation=ThreePhaseInsulationCoordination(clearance_mm=_f(ins, "clearance_mm", 0)),
        variable_calc=ThreePhaseVariableCalculations(
            allowed_max_flux_density_t=_f(vc, "allowed_max_flux_density_t", 0.6),
            core_width_for_area_mm=_f(vc, "core_width_for_area_mm", 70),
            no_of_cores_in_stack=_f(vc, "no_of_cores_in_stack", 1),
            stacking_factor=_f(vc, "stacking_factor", 0.95),
            core_stack_mm=_f(vc, "core_stack_mm", 140),
            overall_core_width_mm=_f(vc, "overall_core_width_mm", 320),
            window_height_mm=_f(vc, "window_height_mm", 160),
            window_width_mm=_f(vc, "window_width_mm", 60),
            core_length_mm=_f(vc, "core_length_mm", 130.25),
            a_mm=_f(vc, "a_mm", 70),
            b_mm=_f(vc, "b_mm", 60),
            c_mm=_f(vc, "c_mm", 160),
            d_mm=_f(vc, "d_mm", 140),
            e_mm=_f(vc, "e_mm", 120),
        ),
        strip=ThreePhaseStripData(
            nom_area_mm2=_f(st, "nom_area_mm2", 99),
            overall_max_width_mm=_f(st, "overall_max_width_mm", 11),
            overall_max_thickness_mm=_f(st, "overall_max_thickness_mm", 9),
        ),
        corner=ThreePhaseCornerData(
            d_mm=_f(co, "d_mm", 1),
            r1_mm=_f(co, "r1_mm", 6),
            c_mm=_f(co, "c_mm", 1),
        ),
        terminal_lug_length_mm=float(merged.get("terminal_lug_length_mm") or 0),
    )


def summarize_design(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the analytical design and attach feasibility + envelope volume."""
    spec_dict = {**DEFAULT_SPEC, **(raw or {})}
    if raw:
        spec_dict = {
            **DEFAULT_SPEC,
            **raw,
            "electrical": {**DEFAULT_SPEC["electrical"], **(raw.get("electrical") or {})},
            "variable": {**DEFAULT_SPEC["variable"], **(raw.get("variable") or {})},
            "insulation": {**DEFAULT_SPEC["insulation"], **(raw.get("insulation") or {})},
            "variable_calc": {**DEFAULT_SPEC["variable_calc"], **(raw.get("variable_calc") or {})},
            "strip": {**DEFAULT_SPEC["strip"], **(raw.get("strip") or {})},
            "corner": {**DEFAULT_SPEC["corner"], **(raw.get("corner") or {})},
            "limits": {**DEFAULT_SPEC["limits"], **(raw.get("limits") or {})},
        }
    inp = spec_from_dict(spec_dict)
    out = run_three_phase_design(inp)
    vc = inp.variable_calc
    limb = vc.core_width_for_area_mm if vc.core_width_for_area_mm > 0 else vc.overall_core_width_mm
    envelope_h = vc.window_height_mm + 2.0 * limb
    envelope_mm3 = vc.overall_core_width_mm * envelope_h * vc.core_stack_mm
    p_cu = float(out["dc_coil_loss_150c_w_three_phase_total"])
    p_fe = float(out["core_loss_total_w"])
    p_tot = p_cu + p_fe
    mass = float(out["total_mass_without_clamps_kg"])
    limits = spec_dict["limits"]
    j_lim = float(limits.get("max_current_density_a_mm2", 4.0))
    w_lim = float(limits.get("max_window_util_pct", 100.0))
    reasons = []
    if out["wh_utilization_pct"] > w_lim:
        reasons.append(f"window height {out['wh_utilization_pct']:.1f}% > {w_lim:.0f}%")
    if out["ww_utilization_pct"] > w_lim:
        reasons.append(f"window width {out['ww_utilization_pct']:.1f}% > {w_lim:.0f}%")
    if out["bmax_t"] > out["bmax_allowed_t"] + 1e-6:
        reasons.append(f"Bpk {out['bmax_t']:.3f} T > {out['bmax_allowed_t']:.3f} T")
    if out["current_density_a_per_mm2"] > j_lim:
        reasons.append(f"J {out['current_density_a_per_mm2']:.2f} > {j_lim:.2f} A/mm²")
    core_mat = inp.variable.core_material or "CRGO M4 (0.27 mm)"
    b_lib = core_properties(core_mat).get("bmax_t")
    if b_lib and out["bmax_t"] > float(b_lib) + 1e-6:
        reasons.append(f"Bpk {out['bmax_t']:.3f} T > material Bsat {b_lib:.2f} T")
    return {
        **out,
        "p_total_w": p_tot,
        "envelope_mm3": envelope_mm3,
        "envelope_litre": envelope_mm3 * 1e-6,
        "loss_per_kg": p_tot / mass if mass > 0 else 0.0,
        "feasible": not reasons,
        "reasons": reasons,
        "core_type": inp.variable.core_type,
        "core_material": core_mat,
        "conductor_material": inp.variable.conductor_material,
        "layers": inp.variable.no_of_layers,
        "parallel_t": inp.variable.cond_in_parallel_t,
        "parallel_w": inp.variable.cond_in_parallel_w,
        "core_stack_mm": vc.core_stack_mm,
        "library_bmax_t": b_lib,
        "inductance_uh": inp.electrical.inductance_uh,
        "irms_a": inp.electrical.irms_a,
        "frequency_hz": inp.electrical.frequency_hz,
    }


PUBLIC_KEYS = (
    "id", "feasible", "reasons",
    "core_type", "core_material", "conductor_material",
    "layers", "parallel_t", "parallel_w", "core_stack_mm",
    "turns", "bmax_t", "bmax_rated_t", "bmax_allowed_t", "library_bmax_t",
    "p_total_w", "dc_coil_loss_150c_w_three_phase_total", "core_loss_total_w",
    "total_mass_without_clamps_kg", "total_copper_mass_three_phase_kg",
    "core_mass_used_kg", "envelope_mm3", "envelope_litre", "loss_per_kg",
    "current_density_a_per_mm2", "wh_utilization_pct", "ww_utilization_pct",
    "inductance_uh", "irms_a", "frequency_hz",
    "airgap_total_analytical_mm", "coil_height_mm",
)


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in PUBLIC_KEYS if k in row}
