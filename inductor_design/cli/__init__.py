"""Command-line interface.

Usage::

    python -m inductor_design buck --vin-min 9 --vin-max 16 --vout 3.3 --iout 5 --fsw 500e3
    python -m inductor_design boost --vin-min 10 --vin-max 14 --vout 24 --iout 2 --fsw 300e3
"""
from __future__ import annotations

import argparse
import json
import sys

from ..converter.buck import BuckSpec
from ..converter.boost import BoostSpec
from ..optimizer.search import design_buck, design_boost
from ..report import render_markdown


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--vin-min", type=float, required=True)
    p.add_argument("--vin-max", type=float, required=True)
    p.add_argument("--vout", type=float, required=True)
    p.add_argument("--iout", type=float, required=True)
    p.add_argument("--fsw", type=float, required=True, help="switching freq [Hz]")
    p.add_argument("--ripple", type=float, default=0.3)
    p.add_argument("--efficiency", type=float, default=0.92)
    p.add_argument("--t-ambient", type=float, default=25.0)
    p.add_argument("--max-temp-rise", type=float, default=60.0)
    p.add_argument("--max-fill", type=float, default=0.4)
    p.add_argument("--max-b-fraction", type=float, default=0.8)
    p.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="inductor-design")
    sub = parser.add_subparsers(dest="topology", required=True)
    _add_common_args(sub.add_parser("buck"))
    _add_common_args(sub.add_parser("boost"))
    args = parser.parse_args(argv)

    common = dict(
        t_ambient_c=args.t_ambient,
        max_temp_rise=args.max_temp_rise,
        max_fill=args.max_fill,
        max_b_fraction=args.max_b_fraction,
    )

    if args.topology == "buck":
        spec = BuckSpec(
            vin_min=args.vin_min, vin_max=args.vin_max,
            vout=args.vout, iout=args.iout, fsw=args.fsw,
            ripple_ratio=args.ripple, efficiency=args.efficiency,
        )
        result = design_buck(spec, **common)
    else:
        spec = BoostSpec(
            vin_min=args.vin_min, vin_max=args.vin_max,
            vout=args.vout, iout=args.iout, fsw=args.fsw,
            ripple_ratio=args.ripple, efficiency=args.efficiency,
        )
        result = design_boost(spec, **common)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(render_markdown(result))
    return 0 if result.best is not None else 2


if __name__ == "__main__":
    sys.exit(main())
