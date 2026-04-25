"""Multi-objective search over (core, material, wire, turns, gap).

v1 uses an exhaustive grid plus Pareto filtering on (loss, volume,
temperature rise).  The search is bounded and fast (< 1 s for the
default component library).  A pymoo-based NSGA-II backend is planned.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Iterable, Optional

from ..converter.buck import BuckSpec, size_buck, BuckOperatingPoint
from ..converter.boost import BoostSpec, size_boost, BoostOperatingPoint
from ..materials import MATERIALS, Material
from ..cores import CORES, Core
from ..wires import Wire, solid_wire, litz_wire, AWG_TABLE
from ..losses import core_loss_w, winding_loss, WindingLoss
from ..thermal import thermal_estimate, ThermalResult
from ..sizing import (
    fill_factor,
    compute_flux,
    required_turns_gapped,
    required_turns_powder,
    achievable_inductance_gapped,
    achievable_inductance_powder,
)


@dataclass(frozen=True)
class DesignCandidate:
    core_name: str
    material_name: str
    wire_name: str
    turns: int
    gap_mm: float                # 0 for powder
    inductance_h: float
    b_peak_t: float
    b_ac_t: float
    fill: float
    p_core_w: float
    p_cu_w: float
    p_total_w: float
    winding_fr: float
    temperature_rise_c: float
    hotspot_c: float
    volume_mm3: float
    height_mm: float
    footprint_mm2: float
    cost_usd: float
    saturation_margin: float
    feasible: bool
    reason: str = ""

    def score_vector(self) -> tuple[float, float, float]:
        """Used for Pareto ranking: lower is better on all three."""
        return (self.p_total_w, self.volume_mm3, self.temperature_rise_c)


@dataclass
class DesignResult:
    spec_summary: dict
    operating_point: dict
    best: Optional[DesignCandidate]
    pareto: list[DesignCandidate] = field(default_factory=list)
    all_candidates_evaluated: int = 0
    feasible_count: int = 0

    def to_dict(self) -> dict:
        return {
            "spec_summary": self.spec_summary,
            "operating_point": self.operating_point,
            "best": asdict(self.best) if self.best else None,
            "pareto": [asdict(c) for c in self.pareto],
            "all_candidates_evaluated": self.all_candidates_evaluated,
            "feasible_count": self.feasible_count,
        }


# ------------------------------------------------------------------
# Candidate evaluation
# ------------------------------------------------------------------

def _pick_compatible_materials(core: Core, allow: Iterable[str] | None) -> list[Material]:
    names = allow if allow is not None else core.compatible_materials
    return [MATERIALS[n] for n in names if n in MATERIALS]


def _default_wires() -> list[Wire]:
    wires: list[Wire] = [solid_wire(g) for g in (14, 16, 18, 20, 22, 24, 26)]
    wires += [
        litz_wire(38, 40),
        litz_wire(38, 100),
        litz_wire(36, 60),
    ]
    return wires


def evaluate_candidate(
    core: Core,
    material: Material,
    wire: Wire,
    target_l: float,
    i_dc: float,
    i_peak: float,
    delta_i: float,
    f_hz: float,
    t_ambient_c: float,
    max_b_fraction: float,
    max_fill: float,
    max_temp_rise: float,
    layers_hint: int,
) -> DesignCandidate:
    b_sat_hot = material.b_sat(100.0)
    b_limit = max_b_fraction * b_sat_hot

    if material.kind == "ferrite":
        n, gap_m = required_turns_gapped(core, target_l, b_limit, i_peak)
        l_actual = achievable_inductance_gapped(core, n, gap_m) if gap_m > 0 else target_l
    else:
        n = required_turns_powder(core, material, target_l)
        gap_m = 0.0
        l_actual = achievable_inductance_powder(core, material, n)

    # Cap turns to prevent pathological cases
    if n > 2000:
        return DesignCandidate(
            core.name, material.name, wire.name, n, gap_m * 1000,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0,
            core.ve_mm3, core.height_mm, core.footprint_mm2,
            core.cost_usd, 0.0, False, "turns>2000",
        )

    fill = fill_factor(core, wire, n)
    b_peak, b_ac = compute_flux(n, core.ae_m2, i_peak, delta_i, l_actual)

    mlt_m = core.mlt_m
    wl: WindingLoss = winding_loss(
        wire=wire, turns=n, mlt_m=mlt_m,
        i_dc=i_dc, delta_i_pp=delta_i, f_hz=f_hz,
        layers=max(1, layers_hint),
    )
    p_core = core_loss_w(material, b_ac, f_hz, core.ve_m3)
    p_total = p_core + wl.p_total

    char_length_m = core.height_mm * 1e-3
    th: ThermalResult = thermal_estimate(
        p_core_w=p_core, p_cu_w=wl.p_total,
        surface_m2=core.surface_m2,
        char_length_m=char_length_m,
        t_ambient_c=t_ambient_c,
    )

    cu_weight = wire.weight_kg(mlt_m, n)
    cu_cost = cu_weight * 12.0
    total_cost = core.cost_usd + cu_cost + 0.50  # bobbin/assembly

    sat_margin = (b_limit - b_peak) / b_limit if b_limit > 0 else -1.0

    reasons: list[str] = []
    feasible = True
    if fill > max_fill:
        feasible = False
        reasons.append(f"fill={fill:.2f}>{max_fill:.2f}")
    if b_peak > b_limit:
        feasible = False
        reasons.append(f"Bpk={b_peak:.3f}T>{b_limit:.3f}T")
    if th.delta_t_c > max_temp_rise:
        feasible = False
        reasons.append(f"ΔT={th.delta_t_c:.0f}C>{max_temp_rise:.0f}C")
    if material.kind == "ferrite" and gap_m <= 0:
        feasible = False
        reasons.append("gap<=0")
    if l_actual < 0.9 * target_l:
        feasible = False
        reasons.append("L<0.9·target")

    return DesignCandidate(
        core_name=core.name,
        material_name=material.name,
        wire_name=wire.name,
        turns=n,
        gap_mm=gap_m * 1000.0,
        inductance_h=l_actual,
        b_peak_t=b_peak,
        b_ac_t=b_ac,
        fill=fill,
        p_core_w=p_core,
        p_cu_w=wl.p_total,
        p_total_w=p_total,
        winding_fr=wl.fr,
        temperature_rise_c=th.delta_t_c,
        hotspot_c=th.t_hotspot_c,
        volume_mm3=core.ve_mm3,
        height_mm=core.height_mm,
        footprint_mm2=core.footprint_mm2,
        cost_usd=total_cost,
        saturation_margin=sat_margin,
        feasible=feasible,
        reason="; ".join(reasons),
    )


def _pareto_filter(cands: list[DesignCandidate]) -> list[DesignCandidate]:
    pareto: list[DesignCandidate] = []
    for c in cands:
        dominated = False
        cs = c.score_vector()
        for other in cands:
            if other is c:
                continue
            os_ = other.score_vector()
            if all(o <= s for o, s in zip(os_, cs)) and any(o < s for o, s in zip(os_, cs)):
                dominated = True
                break
        if not dominated:
            pareto.append(c)
    # sort by total loss
    return sorted(pareto, key=lambda x: (x.p_total_w, x.volume_mm3))


# ------------------------------------------------------------------
# Public entry points
# ------------------------------------------------------------------

def _run_optimization(
    target_l: float,
    i_dc: float,
    i_peak: float,
    delta_i: float,
    f_hz: float,
    *,
    t_ambient_c: float,
    max_b_fraction: float,
    max_fill: float,
    max_temp_rise: float,
    material_filter: Optional[Iterable[str]] = None,
    core_filter: Optional[Iterable[str]] = None,
    layers_hint: int = 2,
) -> tuple[list[DesignCandidate], int]:
    candidates: list[DesignCandidate] = []
    wires = _default_wires()
    core_names = list(core_filter) if core_filter is not None else list(CORES.keys())
    for cname in core_names:
        core = CORES[cname]
        mats = _pick_compatible_materials(core, material_filter)
        for mat in mats:
            for wire in wires:
                cand = evaluate_candidate(
                    core=core, material=mat, wire=wire,
                    target_l=target_l, i_dc=i_dc, i_peak=i_peak,
                    delta_i=delta_i, f_hz=f_hz,
                    t_ambient_c=t_ambient_c,
                    max_b_fraction=max_b_fraction,
                    max_fill=max_fill,
                    max_temp_rise=max_temp_rise,
                    layers_hint=layers_hint,
                )
                candidates.append(cand)
    feasible = [c for c in candidates if c.feasible]
    return candidates, len(feasible)


def design_buck(
    spec: BuckSpec,
    *,
    target_l: Optional[float] = None,
    t_ambient_c: float = 25.0,
    max_b_fraction: float = 0.8,
    max_fill: float = 0.4,
    max_temp_rise: float = 60.0,
    material_filter: Optional[Iterable[str]] = None,
    core_filter: Optional[Iterable[str]] = None,
) -> DesignResult:
    op: BuckOperatingPoint = size_buck(spec)
    L = target_l if target_l is not None else op.l_min
    all_cands, feas_count = _run_optimization(
        target_l=L,
        i_dc=spec.iout,
        i_peak=op.i_peak,
        delta_i=op.delta_i,
        f_hz=spec.fsw,
        t_ambient_c=t_ambient_c,
        max_b_fraction=max_b_fraction,
        max_fill=max_fill,
        max_temp_rise=max_temp_rise,
        material_filter=material_filter,
        core_filter=core_filter,
    )
    feas = [c for c in all_cands if c.feasible]
    pareto = _pareto_filter(feas) if feas else []
    best = pareto[0] if pareto else (min(feas, key=lambda c: c.p_total_w) if feas else None)
    return DesignResult(
        spec_summary={
            "topology": "buck",
            "vin": [spec.vin_min, spec.vin_max],
            "vout": spec.vout,
            "iout": spec.iout,
            "fsw": spec.fsw,
            "ripple_ratio": spec.ripple_ratio,
            "efficiency": spec.efficiency,
        },
        operating_point=asdict(op) | {"target_l": L},
        best=best, pareto=pareto,
        all_candidates_evaluated=len(all_cands),
        feasible_count=feas_count,
    )


def design_boost(
    spec: BoostSpec,
    *,
    target_l: Optional[float] = None,
    t_ambient_c: float = 25.0,
    max_b_fraction: float = 0.8,
    max_fill: float = 0.4,
    max_temp_rise: float = 60.0,
    material_filter: Optional[Iterable[str]] = None,
    core_filter: Optional[Iterable[str]] = None,
) -> DesignResult:
    op: BoostOperatingPoint = size_boost(spec)
    L = target_l if target_l is not None else op.l_min
    all_cands, feas_count = _run_optimization(
        target_l=L,
        i_dc=op.i_l_avg_worst,
        i_peak=op.i_peak,
        delta_i=op.delta_i,
        f_hz=spec.fsw,
        t_ambient_c=t_ambient_c,
        max_b_fraction=max_b_fraction,
        max_fill=max_fill,
        max_temp_rise=max_temp_rise,
        material_filter=material_filter,
        core_filter=core_filter,
    )
    feas = [c for c in all_cands if c.feasible]
    pareto = _pareto_filter(feas) if feas else []
    best = pareto[0] if pareto else (min(feas, key=lambda c: c.p_total_w) if feas else None)
    return DesignResult(
        spec_summary={
            "topology": "boost",
            "vin": [spec.vin_min, spec.vin_max],
            "vout": spec.vout,
            "iout": spec.iout,
            "fsw": spec.fsw,
            "ripple_ratio": spec.ripple_ratio,
            "efficiency": spec.efficiency,
        },
        operating_point=asdict(op) | {"target_l": L},
        best=best, pareto=pareto,
        all_candidates_evaluated=len(all_cands),
        feasible_count=feas_count,
    )
