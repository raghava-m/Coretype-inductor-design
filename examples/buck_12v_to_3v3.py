"""Worked example: 12 V → 3.3 V / 5 A buck at 500 kHz."""
from __future__ import annotations

from inductor_design import BuckSpec, design_buck
from inductor_design.report import render_markdown


def main() -> None:
    spec = BuckSpec(
        vin_min=9.0, vin_max=16.0,
        vout=3.3, iout=5.0,
        fsw=500e3, ripple_ratio=0.3, efficiency=0.92,
    )
    result = design_buck(spec, max_temp_rise=60.0, max_fill=0.4)
    print(render_markdown(result, max_alternatives=3))


if __name__ == "__main__":
    main()
