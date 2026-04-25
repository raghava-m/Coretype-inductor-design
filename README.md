# inductor-design

An open, physics-grounded inductor design tool for switching power
converters. The goal is to match and beat Frenetic AI on capability while
being fully open source and reproducible. See `INDUCTOR_TOOL_PLAN.md` for
the strategy and `INDUCTOR_DESIGN_PLAN.md` for the methodology.

## Run in GitHub Codespaces (no local install)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/raghava-m/Coretype-inductor-design?quickstart=1&ref=cursor/inductor-design-tool-plan-d762)

1. Click the badge above (or on GitHub: **Code → Codespaces → Create codespace on this branch**).
2. Wait ~60 s for the devcontainer to build. The postCreate script installs
   the package and runs the tests automatically.
3. In the Codespaces terminal, try:

   ```bash
   inductor-design buck --vin-min 9 --vin-max 16 --vout 3.3 --iout 5 --fsw 500e3
   inductor-design boost --vin-min 10 --vin-max 14 --vout 24 --iout 2 --fsw 300e3
   ```

4. Stop the codespace from the GitHub UI when you're done so it doesn't
   consume free-tier hours.

v0 supports **buck** and **boost** converters end-to-end:

- Converter spec → minimum L, I_rms, I_peak, ripple, duty range.
- Multi-objective search over cores, materials, wires, turns, and gap.
- Loss model: Steinmetz core loss + Dowell-style AC winding resistance.
- Two-node thermal model with natural convection.
- Markdown / JSON design report, Pareto front of alternatives.

## Install

```bash
pip install -e .
```

## CLI

```bash
inductor-design buck \
    --vin-min 9 --vin-max 16 --vout 3.3 --iout 5 --fsw 500e3

inductor-design boost \
    --vin-min 10 --vin-max 14 --vout 24 --iout 2 --fsw 300e3
```

Add `--json` to get machine-readable output.

## Python API

```python
from inductor_design import BuckSpec, design_buck
from inductor_design.report import render_markdown

spec = BuckSpec(vin_min=9, vin_max=16, vout=3.3, iout=5, fsw=500e3)
result = design_buck(spec)
print(render_markdown(result))
```

## Worked examples

- `examples/buck_12v_to_3v3.py` — 12 V → 3.3 V / 5 A @ 500 kHz
- `examples/boost_12v_to_24v.py` — 12 V → 24 V / 2 A @ 300 kHz

## Tests

```bash
pytest
```

## Status and roadmap

See `INDUCTOR_TOOL_PLAN.md` for the full plan. v0 is the MVP; v1 adds
buck-boost/SEPIC/flyback, NSGA-II optimization, SPICE export, and an
HTML report; v2 adds planar, coupled inductors, CM chokes, and FEMM
verification; v3 adds an LLM copilot grounded in the physics engine.
