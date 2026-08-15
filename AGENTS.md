# AGENTS.md

## Cursor Cloud specific instructions

`inductor-design` is a pure-Python (>=3.10) CLI/library tool for designing
inductors for switching power converters. It has **no runtime dependencies**;
the only dev dependency is `pytest`. There is no server or GUI — it is a
terminal application. Standard commands are documented in `README.md`.

Non-obvious notes for this environment:

- The system Python 3.12 on this VM is PEP-668 "externally managed", so
  packages are installed into a virtualenv at `.venv/` (already created during
  environment setup and refreshed by the startup update script). Activate it
  before running anything:

  ```bash
  source .venv/bin/activate
  ```

  After activation the `inductor-design` console script and `pytest` are on
  `PATH`. You can also run tools without activating via `.venv/bin/pytest`,
  `.venv/bin/inductor-design`, etc.

- Test / "lint": this repo has no separate linter; correctness is enforced by
  the test suite. Run `pytest` from the repo root (config lives in
  `pyproject.toml`).

- Run the app (examples):

  ```bash
  inductor-design buck  --vin-min 9  --vin-max 16 --vout 3.3 --iout 5 --fsw 500e3
  inductor-design boost --vin-min 10 --vin-max 14 --vout 24 --iout 2 --fsw 300e3
  # add --json for machine-readable output
  python examples/buck_12v_to_3v3.py
  ```

- The package is installed in **editable** mode (`pip install -e`), so source
  edits under `inductor_design/` take effect immediately without reinstalling.

- Branch note: the full application currently lives on the
  `cursor/inductor-design-tool-plan-d762` line of work. The `main` branch is a
  placeholder with no `pyproject.toml`; the startup update script guards on the
  presence of `pyproject.toml`, so it is safe to run on either branch.
