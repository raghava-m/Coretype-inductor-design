"""Worked example: 12 V → 24 V / 2 A boost at 300 kHz."""
from __future__ import annotations

from inductor_design import BoostSpec, design_boost
from inductor_design.report import render_markdown


def main() -> None:
    spec = BoostSpec(
        vin_min=10.0, vin_max=14.0,
        vout=24.0, iout=2.0,
        fsw=300e3, ripple_ratio=0.3, efficiency=0.92,
    )
    result = design_boost(spec, max_temp_rise=60.0, max_fill=0.4)
    print(render_markdown(result, max_alternatives=3))


if __name__ == "__main__":
    main()
