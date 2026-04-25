"""Boost converter inductor sizing (CCM).

The inductor carries the input current; worst case for both saturation
and ripple is at Vin_min (highest duty, largest average inductor current).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BoostSpec:
    vin_min: float
    vin_max: float
    vout: float
    iout: float
    fsw: float
    ripple_ratio: float = 0.3   # ΔI_L / I_L target
    efficiency: float = 0.92

    def __post_init__(self) -> None:
        if not (0 < self.vin_min <= self.vin_max < self.vout):
            raise ValueError("Boost requires Vin_min ≤ Vin_max < Vout.")
        if self.iout <= 0 or self.fsw <= 0:
            raise ValueError("Iout and fsw must be positive.")
        if not 0 < self.ripple_ratio <= 1.5:
            raise ValueError("ripple_ratio should be in (0, 1.5].")
        if not 0 < self.efficiency <= 1:
            raise ValueError("efficiency must be in (0, 1].")


@dataclass(frozen=True)
class BoostOperatingPoint:
    l_min: float
    duty_min: float
    duty_max: float
    i_l_avg_worst: float   # A — input-side inductor average current at Vin_min
    delta_i: float
    i_peak: float
    i_rms: float
    volt_seconds: float
    flux_swing_factor: float


def size_boost(spec: BoostSpec) -> BoostOperatingPoint:
    """Return the worst-case inductor requirements for a boost converter."""
    d_min = 1.0 - (spec.vin_max * spec.efficiency) / spec.vout
    d_max = 1.0 - (spec.vin_min * spec.efficiency) / spec.vout

    i_l_max = spec.iout / (1.0 - d_max)

    l_min = (spec.vin_min * d_max) / (
        spec.ripple_ratio * i_l_max * spec.fsw
    )

    delta_i = spec.ripple_ratio * i_l_max
    i_peak = i_l_max + 0.5 * delta_i
    i_rms = math.sqrt(i_l_max ** 2 + (delta_i ** 2) / 12.0)

    volt_seconds = spec.vin_min * d_max / spec.fsw
    flux_swing_factor = l_min * delta_i

    return BoostOperatingPoint(
        l_min=l_min,
        duty_min=d_min,
        duty_max=d_max,
        i_l_avg_worst=i_l_max,
        delta_i=delta_i,
        i_peak=i_peak,
        i_rms=i_rms,
        volt_seconds=volt_seconds,
        flux_swing_factor=flux_swing_factor,
    )
