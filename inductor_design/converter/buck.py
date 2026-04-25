"""Buck converter inductor sizing (CCM).

Given a converter spec (Vin range, Vout, Iout, fsw, ripple target) this
module produces the worst-case electrical requirements for the inductor:
minimum inductance, peak and RMS currents, ripple, and applied
volt-seconds.  All outputs are deterministic and derived from the
standard CCM buck equations.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BuckSpec:
    vin_min: float          # V
    vin_max: float          # V
    vout: float             # V
    iout: float             # A (max DC load)
    fsw: float              # Hz
    ripple_ratio: float = 0.3   # ΔI_L / Iout target
    efficiency: float = 0.92

    def __post_init__(self) -> None:
        if not (0 < self.vout < self.vin_min <= self.vin_max):
            raise ValueError("Buck requires 0 < Vout < Vin_min ≤ Vin_max.")
        if self.iout <= 0 or self.fsw <= 0:
            raise ValueError("Iout and fsw must be positive.")
        if not 0 < self.ripple_ratio <= 1.5:
            raise ValueError("ripple_ratio should be in (0, 1.5].")
        if not 0 < self.efficiency <= 1:
            raise ValueError("efficiency must be in (0, 1].")


@dataclass(frozen=True)
class BuckOperatingPoint:
    """Worst-case operating point used to size the inductor."""
    l_min: float            # H  — minimum L to meet ripple target
    duty_min: float
    duty_max: float
    delta_i: float          # A pk-pk ripple at worst case
    i_peak: float           # A
    i_rms: float            # A
    volt_seconds: float     # V·s applied during on-time (worst case)
    flux_swing_factor: float  # = L · ΔI (used for B_ac given N, Ae)


def size_buck(spec: BuckSpec) -> BuckOperatingPoint:
    """Return the worst-case inductor requirements for a buck converter.

    Ripple is maximum at Vin_max (lowest duty).  L_min is sized to hold
    ripple ≤ spec.ripple_ratio · Iout at that corner.
    """
    d_min = spec.vout / (spec.vin_max * spec.efficiency)
    d_max = spec.vout / (spec.vin_min * spec.efficiency)

    l_min = (spec.vout * (1.0 - d_min)) / (
        spec.ripple_ratio * spec.iout * spec.fsw
    )

    delta_i = spec.ripple_ratio * spec.iout
    i_peak = spec.iout + 0.5 * delta_i
    i_rms = math.sqrt(spec.iout ** 2 + (delta_i ** 2) / 12.0)

    volt_seconds = (spec.vin_max - spec.vout) * d_min / spec.fsw
    flux_swing_factor = l_min * delta_i

    return BuckOperatingPoint(
        l_min=l_min,
        duty_min=d_min,
        duty_max=d_max,
        delta_i=delta_i,
        i_peak=i_peak,
        i_rms=i_rms,
        volt_seconds=volt_seconds,
        flux_swing_factor=flux_swing_factor,
    )
