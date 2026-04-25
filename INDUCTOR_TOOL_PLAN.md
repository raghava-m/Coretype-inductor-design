# Plan: An Open Inductor Design Tool (Buck & Boost first)

This document lays out a plan to build an inductor-design tool that is more
capable and more open than Frenetic AI, starting with buck and boost
converters. It is paired with a working Python MVP in this repo
(`inductor_design/`) that already performs buck/boost sizing, loss and thermal
estimation, and multi-objective optimization over a component database.

---

## 1. What Frenetic does well, and where we can beat it

Frenetic AI is strong at:

- Large curated core/material database with vendor curves.
- ML-assisted core-loss and AC-winding-loss prediction (Steinmetz+ extensions,
  proximity-effect modeling).
- Fast "give me an L, I, f and I'll rank parts" workflow.
- Cloud UI with vendor part pointers.

Gaps we can exploit to build something better:

1. **Closed model, closed data.** Users cannot inspect the loss/thermal models
   or extend them. We make every equation, coefficient, and dataset open and
   versioned.
2. **Converter-unaware sizing.** Frenetic's flow is "enter L, I_rms, I_pk,
   f"; the user has to pre-compute those. We let the user enter the
   *converter spec* (Vin range, Vout, Iout, fsw, ripple target, mode) and
   derive L, I_rms, I_pk, dI, volt-seconds, duty extremes automatically for
   buck, boost, buck-boost, SEPIC, flyback, LLC, PFC boost, coupled
   inductors, etc.
3. **No true multi-objective optimization.** We run NSGA-II / scalarized
   sweeps over (core, material, turns, gap, wire type, layer count, litz
   strand count) with Pareto fronts on (loss, volume, cost, temperature,
   saturation margin).
4. **No integrated EMI/DM-CM inductor design.** We add CM-choke and
   differential-mode filter inductor flows with impedance-vs-frequency
   targets.
5. **Weak thermal fidelity.** We include a layered thermal-network model
   (winding-to-core, core-to-ambient, natural vs forced convection) and
   optional FEM/FEMM export for verification.
6. **No hardware-in-the-loop path.** We generate a SPICE/PLECS subcircuit,
   a KiCad footprint/3D for drum/toroid/E-core, a build traveler, and an
   automated bench-test script (LCR sweep, DCR, saturation curve capture
   via a pulse tester, thermal profile via IR).
7. **No design reproducibility.** Every design is a YAML + a lockfile of the
   material/vendor data version used, so two engineers get bit-identical
   results.
8. **No AI copilot grounded in physics.** We add an LLM layer that *only*
   proposes candidate designs and explains trade-offs; the numbers always
   come from the deterministic physics engine, never from the LLM.

### Product thesis
> "Enter a converter spec, get a Pareto-optimal, manufacturable, vendor-sourced
> inductor design with a full loss/thermal report, SPICE model, drawings, and
> a bench validation script — in under a minute, fully open source, fully
> reproducible."

---

## 2. Scope for v1 (this plan)

Target converters for v1:

- **Synchronous / non-synchronous buck** (CCM and boundary).
- **Boost** (CCM and boundary).

Everything else (buck-boost, SEPIC, flyback, PFC, CM chokes, coupled
inductors, planar magnetics) follows the same skeleton and is planned for
v2/v3 below.

Outputs for v1:

1. Recommended core (family + part number from the DB).
2. Winding recipe: N turns, wire gauge / litz config, layer arrangement,
   fill factor, DCR.
3. Gap (for gapped ferrite) or effective permeability (for powder).
4. Predicted: L(I), I_sat margin, ΔI ripple, B_pk, B_ac, P_core, P_cu_dc,
   P_cu_ac, P_total, ΔT.
5. Cost / volume / height estimate.
6. Pareto list of top N alternatives.
7. Exportable artifacts: YAML spec, JSON report, SPICE subckt, build sheet.

---

## 3. Architecture

```
+------------------+    +------------------------+    +---------------------+
|  Converter spec  | -> |  Electrical sizing     | -> |  Candidate generator|
|  (YAML/CLI/API)  |    |  (L, Irms, Ipk, dI, Vs)|    |  (cores x wires x N)|
+------------------+    +------------------------+    +----------+----------+
                                                                 |
                      +------------------+    +----------+-------v---------+
                      |  Thermal model   | <- |  Loss    |   Evaluator     |
                      | (Rth network)    |    |  models  | (per candidate) |
                      +---------+--------+    +----------+--------+--------+
                                |                                 |
                                v                                 v
                       +-------------------+          +------------------------+
                       |  Multi-objective  |  <-----  |  Constraints:          |
                       |  optimizer        |          |  Bsat, ΔT, fill, size, |
                       |  (NSGA-II/sweep)  |          |  cost, availability    |
                       +---------+---------+          +------------------------+
                                 |
                                 v
                     +-----------------------+
                     |  Reporter / exporters |
                     |  (MD, HTML, SPICE,    |
                     |   KiCad, build sheet) |
                     +-----------------------+
```

### Key modules

- `converter/` — volt-second, duty, ripple, RMS/peak current models per topology.
- `materials/` — ferrite (3C95, N87, 3F36, ML91S), powder (Kool Mµ, XFlux,
  MPP, High Flux, Sendust), amorphous, nanocrystalline. Each has Steinmetz
  `(k, α, β)` over temp, B_sat(T), μ_r(H, T), cost/kg.
- `cores/` — geometry DB: Ae, Ac, Ve, lm, window area Wa, MLT, outline,
  weight, height, vendor P/Ns. EE/ETD/PQ/RM/EFD/drum/toroid.
- `wires/` — solid magnet wire AWG table, insulation build; litz (N×d)
  helpers; foil.
- `losses/` — core loss (iGSE/Steinmetz with DC-bias and temperature
  corrections), Dowell 1-D AC resistance, proximity-effect for litz, DCR
  with temperature coefficient.
- `thermal/` — two-node and multi-node Rth, natural convection h(A, ΔT),
  forced-convection de-rating, hot-spot winding temp.
- `sizing/` — first-pass turns/gap, fill-factor feasibility, saturation
  margin.
- `optimizer/` — grid sweep + Pareto front; plug-in point for NSGA-II
  (DEAP/pymoo) in v2.
- `report/` — Markdown/HTML/JSON; SPICE `.subckt` with L(I) table; KiCad
  footprint stubs.
- `cli/` and `api/` — Typer CLI and FastAPI endpoint.

### Stack choices

- Python 3.11, NumPy, SciPy, Pydantic v2, Typer, Rich, Matplotlib.
- Optional: pymoo (NSGA-II), FEMM or `magpylib`/`pyFEMM` for verification,
  PySpice for SPICE sim, KiCad Python API for export.

---

## 4. Physics the tool uses (v1)

### Buck (CCM)
- Duty `D = Vout / (Vin · η)`; bound with `D_min`, `D_max` across Vin range.
- Ripple `ΔI_L = (Vout · (1 − D)) / (L · fsw)`.
- Required L for target ripple `r = ΔI/Iout`:
  `L_min = Vout · (1 − D_min) / (r · Iout · fsw)`.
- Peak `I_pk = Iout + ΔI_L/2`, RMS `I_rms ≈ sqrt(Iout² + ΔI_L²/12)`.
- Volt-seconds on-time `Vs = (Vin − Vout) · D / fsw`.

### Boost (CCM)
- Duty `D = 1 − Vin · η / Vout`.
- Input/inductor avg `I_L = Iout / (1 − D)`.
- Ripple `ΔI_L = Vin · D / (L · fsw)`.
- `L_min = Vin_min · D_max / (r · I_L_max · fsw)`.
- `I_pk = I_L + ΔI_L/2`, `I_rms ≈ sqrt(I_L² + ΔI_L²/12)`.
- `Vs = Vin · D / fsw`.

### Flux and saturation
- `B_pk = L · I_pk / (N · Ae)` ≤ `B_sat(T_core) · margin`.
- `B_ac = L · ΔI_L / (2 · N · Ae)`.

### Core loss (Steinmetz / iGSE)
- `P_v = k · f^α · B_ac^β  [W/m³]`, corrected for temperature via material table.
- For non-sinusoidal triangular current, iGSE with duty D.

### Copper loss
- DCR `R_dc = ρ(T) · N · MLT / A_wire`.
- AC resistance via Dowell for layered windings, or proximity factor for litz
  `R_ac/R_dc = 1 + (π²·N_l²·d⁴·f²·µ₀²·σ²)/192 · ...` (tool uses the standard
  closed form, with guard for deep-skin regime).
- `P_cu = I_rms² · R_dc · F_r(f)`.

### Thermal
- Two-node: `T_core = T_amb + (P_core + P_cu) · R_th_ca`, hot-spot
  `T_hs = T_core + P_cu · R_th_wc`.
- `R_th_ca ≈ 1 / (h · A_surface)` with `h` from a correlation for natural
  convection (`h ≈ 1.42 · (ΔT/L)^0.25`), de-rated for forced air by user
  input.

Every equation lives in a single, auditable module; no black boxes.

---

## 5. Optimization strategy

Decision variables per candidate:
- Core (family + size + material).
- Number of turns N.
- Wire: solid AWG *or* litz (strands, strand AWG), *or* foil.
- Layer count / winding arrangement.
- Gap (for gapped ferrite).

Constraints:
- `B_pk ≤ α · B_sat(T)` (α ≈ 0.8).
- Fill factor ≤ user max (default 0.4 for round wire, 0.7 for foil).
- `T_hs ≤ T_max` (default 120 °C).
- L within ±tol across current/temperature.
- Core, wire in vendor inventory (optional).

Objectives (Pareto):
- Minimize total loss.
- Minimize volume (or height).
- Minimize cost.
- Maximize saturation margin.

v1: exhaustive grid + Pareto filter (fast, deterministic, < 1 s for 10k
candidates). v2: NSGA-II via `pymoo` for continuous gap/litz knobs.

---

## 6. Roadmap

**v0 (this PR):** MVP — buck & boost sizing, small core+material DB,
Steinmetz core loss, Dowell-lite AC resistance, 2-node thermal, grid-Pareto
optimizer, CLI, Markdown report, two worked examples, unit tests.

**v1 (next):**
- Add buck-boost, SEPIC, flyback, PFC boost.
- Add litz optimization (strand count vs frequency) and foil windings.
- Add iGSE with DC-bias and temperature-corrected Steinmetz.
- Add pymoo NSGA-II backend.
- SPICE `.subckt` export with L(I) table; PLECS XML.
- HTML report with plots (B-H, L-vs-I, loss pie, thermal bar).
- FastAPI service + simple web UI.

**v2:**
- Planar magnetics and PCB-embedded windings.
- Coupled inductors and transformers (primary, secondary, leakage, magnetizing).
- CM choke design with impedance targets for EMI filters.
- FEMM / `pyFEMM` verification loop (optional).
- Vendor-API integrations for live pricing and stock.

**v3:**
- LLM copilot (grounded): natural-language converter specs, explanation of
  trade-offs, "why did you pick this core?" — all numerical claims come
  from the physics engine.
- Closed-loop bench validation: auto-generate an LCR/saturation/thermal
  test script, ingest results, refit material coefficients for the
  specific lot.

---

## 7. Validation plan

- **Golden tests:** reproduce 3 reference designs from app notes (TI
  SLVA057, ON Semi AND9135, Wurth buck app note) within ±10% on L,
  ripple, losses, and ΔT.
- **Cross-check vs Frenetic & Magnetics Inc. Inductor Designer** on 10
  canonical cases; capture diffs and iterate.
- **Bench:** build three prototypes per topology, measure L(I), DCR(T),
  ΔT at nominal/peak; compare to prediction.

---

## 8. Deliverables

- Open-source Python package (Apache-2.0).
- CLI: `inductor-design buck --vin 9..16 --vout 3.3 --iout 5 --fsw 500e3`.
- REST API with the same inputs.
- Machine-readable report (JSON) and human report (Markdown/HTML).
- SPICE subckt + KiCad footprint (v1).
- Sample library of validated designs.

---

## 9. Next actions

1. Merge this plan + MVP code.
2. Expand core DB (add 10 common ferrite E-cores and 8 powder toroids).
3. Add buck-boost and flyback topologies.
4. Wire up `pymoo` NSGA-II.
5. Build the HTML report and SPICE exporter.
