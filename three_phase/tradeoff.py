"""Analytical trade-off sweep and Pareto filter for three-phase inductors."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .schema import DEFAULT_SPEC, compact_row, summarize_design
from .material_library import core_properties


def _pareto(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Non-dominated set on (loss, mass, envelope). Lower is better."""
    front: list[dict[str, Any]] = []
    for c in rows:
        cs = (c["p_total_w"], c["total_mass_without_clamps_kg"], c["envelope_mm3"])
        dominated = False
        for o in rows:
            if o is c:
                continue
            os_ = (o["p_total_w"], o["total_mass_without_clamps_kg"], o["envelope_mm3"])
            if all(a <= b for a, b in zip(os_, cs)) and any(a < b for a, b in zip(os_, cs)):
                dominated = True
                break
        if not dominated:
            front.append(c)
    return sorted(front, key=lambda r: (r["p_total_w"], r["total_mass_without_clamps_kg"]))


def _as_list(value: Any, fallback: Iterable[Any]) -> list[Any]:
    if value is None:
        return list(fallback)
    if isinstance(value, (list, tuple)):
        return list(value) if value else list(fallback)
    return [value]


def run_tradeoff(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sweep geometry / material knobs around a user spec and rank Pareto designs."""
    spec = deepcopy(DEFAULT_SPEC)
    if raw:
        for key in ("electrical", "variable", "insulation", "variable_calc", "strip", "corner", "limits"):
            spec[key] = {**spec[key], **(raw.get(key) or {})}
        if "terminal_lug_length_mm" in raw:
            spec["terminal_lug_length_mm"] = raw["terminal_lug_length_mm"]
        if "sweep" in raw and raw["sweep"]:
            spec["sweep"] = raw["sweep"]

    base_stack = float(spec["variable_calc"]["core_stack_mm"])
    sweep = spec.get("sweep") or {}
    stacks = _as_list(sweep.get("core_stack_mm"), [round(base_stack * s, 1) for s in (0.75, 1.0, 1.25)])
    layers = [int(x) for x in _as_list(sweep.get("no_of_layers"), [1, 2, 3])]
    bmaxs = [float(x) for x in _as_list(
        sweep.get("allowed_max_flux_density_t"),
        [0.4, 0.5, 0.6, 0.8, 1.0],
    )]
    cores = _as_list(
        sweep.get("core_material"),
        [spec["variable"]["core_material"], "Amorphous 2605SA1", "CRGO M5 (0.30 mm)"],
    )
    conductors = _as_list(
        sweep.get("conductor_material"),
        [spec["variable"]["conductor_material"], "aluminium"],
    )
    parallels = sweep.get("parallels") or [{"t": 1, "w": 1}, {"t": 1, "w": 2}, {"t": 2, "w": 1}]
    core_types = _as_list(sweep.get("core_type"), [spec["variable"]["core_type"]])
    # Drop Bmax points above a material's recommended Bsat unless the user forced the list.
    forced_bmax = sweep.get("allowed_max_flux_density_t") is not None

    candidates: list[dict[str, Any]] = []
    for stack in stacks:
        for nl in layers:
            for bmax in bmaxs:
                for cmat in cores:
                    for cond in conductors:
                        for par in parallels:
                            for ctype in core_types:
                                trial = deepcopy(spec)
                                trial["variable_calc"]["core_stack_mm"] = float(stack)
                                trial["variable_calc"]["allowed_max_flux_density_t"] = float(bmax)
                                trial["variable"]["no_of_layers"] = int(nl)
                                trial["variable"]["core_material"] = str(cmat)
                                trial["variable"]["conductor_material"] = str(cond)
                                trial["variable"]["cond_in_parallel_t"] = int(par.get("t", 1))
                                trial["variable"]["cond_in_parallel_w"] = int(par.get("w", 1))
                                trial["variable"]["core_type"] = str(ctype)
                                if not forced_bmax:
                                    bsat = float(core_properties(str(cmat)).get("bmax_t") or 1.7)
                                    if float(bmax) > bsat + 1e-9:
                                        continue
                                try:
                                    row = summarize_design(trial)
                                except (ZeroDivisionError, ValueError, OverflowError):
                                    continue
                                row["id"] = len(candidates)
                                candidates.append(row)

    feasible = [c for c in candidates if c["feasible"]]
    pool = feasible or candidates
    seen: set[tuple] = set()
    unique: list[dict[str, Any]] = []
    for c in pool:
        key = (
            round(c["p_total_w"], 4),
            round(c["total_mass_without_clamps_kg"], 4),
            round(c["envelope_mm3"], 1),
            c["core_material"],
            c["conductor_material"],
            c["layers"],
            round(c["core_stack_mm"], 2),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    pareto = _pareto(unique)
    baseline = summarize_design(spec)
    best = pareto[0] if pareto else None
    compact = True if raw is None else bool(raw.get("compact", True))
    pack = compact_row if compact else (lambda r: r)
    return {
        "baseline": pack(baseline),
        "evaluated": len(candidates),
        "feasible": len(feasible),
        "pareto": [pack(c) for c in pareto],
        "candidates": [pack(c) for c in unique],
        "best": pack(best) if best else None,
    }
