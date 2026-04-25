#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing inductor-design (editable) and pytest"
pip install --upgrade pip >/dev/null
pip install -e . pytest

echo "==> Running test suite"
pytest -q || true

cat <<'EOF'

========================================================================
  inductor-design is ready.

  Try one of these in the terminal:

    # Buck: 12 V -> 3.3 V / 5 A @ 500 kHz
    inductor-design buck --vin-min 9 --vin-max 16 --vout 3.3 --iout 5 --fsw 500e3

    # Boost: 12 V -> 24 V / 2 A @ 300 kHz
    inductor-design boost --vin-min 10 --vin-max 14 --vout 24 --iout 2 --fsw 300e3

    # Machine-readable JSON
    inductor-design buck --vin-min 9 --vin-max 16 --vout 3.3 --iout 5 --fsw 500e3 --json

    # Worked examples
    python examples/buck_12v_to_3v3.py
    python examples/boost_12v_to_24v.py

  See README.md for the Python API and INDUCTOR_TOOL_PLAN.md for the plan.
========================================================================
EOF
