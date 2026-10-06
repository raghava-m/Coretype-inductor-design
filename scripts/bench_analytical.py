#!/usr/bin/env python3
"""Speed benchmark for the analytical inductor design tool.

Reports wall time for CCM sizing, a single candidate evaluation, and the
full core×material×wire grid + Pareto search.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

from inductor_design import BuckSpec, BoostSpec, design_buck, design_boost, size_buck, size_boost
from inductor_design.cores import CORES
from inductor_design.materials import MATERIALS
from inductor_design.optimizer.search import evaluate_candidate
from inductor_design.wires import solid_wire


def _time(fn, n: int, warmup: int = 2) -> list[float]:
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return samples


def _fmt(seconds: float) -> str:
    if seconds < 1e-3:
        return f"{seconds * 1e6:.2f} µs"
    if seconds < 1:
        return f"{seconds * 1e3:.2f} ms"
    return f"{seconds:.3f} s"


def main() -> int:
    spec_b = BuckSpec(9, 16, 3.3, 5, 500e3, 0.3, 0.92)
    spec_g = BoostSpec(10, 14, 24, 2, 300e3, 0.3, 0.92)
    op = size_buck(spec_b)
    core, mat, wire = CORES["PQ2016"], MATERIALS["N87"], solid_wire(14)

    rows = []

    def add(name, samples, extra=""):
        mean = statistics.mean(samples)
        rows.append({
            "name": name,
            "n": len(samples),
            "mean_s": mean,
            "median_s": statistics.median(samples),
            "min_s": min(samples),
            "max_s": max(samples),
            "rate_per_s": (1.0 / mean) if mean else None,
            "note": extra,
        })
        print(
            f"{name:44s}  mean={_fmt(mean):>10s}  "
            f"median={_fmt(statistics.median(samples)):>10s}  "
            f"min={_fmt(min(samples)):>10s}  max={_fmt(max(samples)):>10s}  "
            f"{1.0/mean:,.0f}/s  {extra}"
        )

    add("size_buck CCM equations", _time(lambda: size_buck(spec_b), 5000, 50))
    add("size_boost CCM equations", _time(lambda: size_boost(spec_g), 5000, 50))
    add(
        "evaluate_candidate size+loss+thermal",
        _time(
            lambda: evaluate_candidate(
                core, mat, wire, op.l_min, spec_b.iout, op.i_peak, op.delta_i,
                spec_b.fsw, 25.0, 0.8, 0.4, 60.0, 2,
            ),
            2000, 20,
        ),
    )
    buck_res = design_buck(spec_b)
    add(
        "design_buck full grid+Pareto",
        _time(lambda: design_buck(spec_b), 20, 2),
        extra=f"{buck_res.all_candidates_evaluated} candidates, {buck_res.feasible_count} feasible",
    )
    boost_res = design_boost(spec_g)
    add(
        "design_boost full grid+Pareto",
        _time(lambda: design_boost(spec_g), 20, 2),
        extra=f"{boost_res.all_candidates_evaluated} candidates, {boost_res.feasible_count} feasible",
    )

    specs = [
        BuckSpec(9, 16, 3.3, 5, 500e3),
        BuckSpec(18, 36, 12, 8, 250e3),
        BuckSpec(40, 60, 12, 15, 150e3),
        BoostSpec(10, 14, 24, 2, 300e3),
        BoostSpec(9, 16, 48, 1, 200e3),
    ]

    def sweep():
        for sp in specs:
            (design_buck if isinstance(sp, BuckSpec) else design_boost)(sp)

    add("5-spec mixed sweep (3 buck + 2 boost)", _time(sweep, 5, 1))

    print()
    print(
        f"buck recommended: {buck_res.best.core_name}/{buck_res.best.material_name}/"
        f"{buck_res.best.wire_name}/{buck_res.best.turns}T  "
        f"L={buck_res.best.inductance_h*1e6:.3f} µH  P={buck_res.best.p_total_w:.3f} W  "
        f"ΔT={buck_res.best.temperature_rise_c:.1f} K"
    )
    print(
        f"boost recommended: {boost_res.best.core_name}/{boost_res.best.material_name}/"
        f"{boost_res.best.wire_name}/{boost_res.best.turns}T  "
        f"L={boost_res.best.inductance_h*1e6:.3f} µH  P={boost_res.best.p_total_w:.3f} W  "
        f"ΔT={boost_res.best.temperature_rise_c:.1f} K"
    )

    out = Path("bench_analytical.json")
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    out.write_text(json.dumps({"rows": rows}, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
