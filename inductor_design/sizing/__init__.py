"""Turn/gap sizing helpers and feasibility checks."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..cores import Core
from ..materials import Material
from ..wires import Wire

MU0 = 4.0 * math.pi * 1e-7


@dataclass(frozen=True)
class GeometryFit:
    turns: int
    gap_m: float                 # 0.0 for powder (distributed gap)
    inductance_h: float
    b_peak_t: float
    b_ac_t: float
    fill_factor: float           # 0..1, window utilization


def required_turns_gapped(
    core: Core, target_l: float, max_b_peak_t: float, i_peak: float
) -> tuple[int, float]:
    """For a gapped-ferrite core, minimum turns is set by saturation
    (B_pk ≤ max_B) and gap is then chosen to land on target_l.
    """
    n_min = max(1, int(math.ceil(target_l * i_peak / (max_b_peak_t * core.ae_m2))))
    al = target_l / (n_min ** 2)                   # H / turn^2
    reluctance = 1.0 / al                           # A·t / Wb
    gap_m = MU0 * core.ae_m2 * reluctance           # ignore core reluctance vs gap
    return n_min, max(0.0, gap_m)


def required_turns_powder(
    core: Core, material: Material, target_l: float
) -> int:
    """Distributed-gap powder: L = µ0 µr N² Ae / le."""
    al = MU0 * material.mu_r * core.ae_m2 / core.le_m
    if al <= 0:
        return 10**9
    return max(1, int(math.ceil(math.sqrt(target_l / al))))


def fill_factor(core: Core, wire: Wire, turns: int) -> float:
    """Window-area fill (copper + insulation, ignoring bobbin)."""
    wire_area = wire.outer_area_m2       # includes insulation, all strands
    return (turns * wire_area) / core.wa_m2


def compute_flux(
    turns: int, ae_m2: float, i_peak: float, delta_i_pp: float, inductance_h: float
) -> tuple[float, float]:
    """Return (B_peak, B_ac) in tesla."""
    b_peak = inductance_h * i_peak / (turns * ae_m2)
    b_ac = inductance_h * delta_i_pp / (2.0 * turns * ae_m2)
    return b_peak, b_ac


def achievable_inductance_gapped(core: Core, turns: int, gap_m: float) -> float:
    reluctance = gap_m / (MU0 * core.ae_m2)
    if reluctance <= 0:
        return float("inf")
    return turns ** 2 / reluctance


def achievable_inductance_powder(
    core: Core, material: Material, turns: int
) -> float:
    return MU0 * material.mu_r * core.ae_m2 * turns ** 2 / core.le_m
