# Analytical tool validation

Independent cross-check of the v0 inductor design tool (`inductor_design/`)
and a wall-clock speed measurement of its analytical path.  Physics checks
re-derive textbook CCM / magnetics / Steinmetz / Dowell / DCR / 2-node
thermal equations and compare them to package outputs; they do not copy
implementation internals.

Run:

```bash
pytest
python scripts/bench_analytical.py
```

The single-file T1 tool on `cursor/inductor-design-doc-aa1a`
(`unifiedinductordesign.py`) was also timed for comparison.

## Verdict

The analytical tool **works**. Converter sizing, gapped-ferrite and powder
turns/gap, Steinmetz core loss, Dowell AC resistance, DCR, and the 2-node
thermal iteration match independent textbook formulas. End-to-end buck and
boost searches return feasible, physically consistent designs.

It is **fast**: a full 540-candidate buck design plus Pareto filter is
about **11 ms**; the CCM equations themselves are **~1.5 µs**. That is
well under the plan's "under a minute" product thesis — about four orders
of magnitude faster.

## Speed (this cloud CPU, Python 3.12)

| Step | Mean wall time | Rate |
| --- | --- | --- |
| `size_buck` CCM equations | 1.44 µs | ~690,000 / s |
| `size_boost` CCM equations | 1.52 µs | ~660,000 / s |
| One candidate (turns/gap + Steinmetz + Dowell + 2-node thermal) | 9.92 µs | ~101,000 / s |
| Full `design_buck` (540 candidates + Pareto) | 11.0 ms | ~90 designs / s |
| Full `design_boost` (540 candidates + Pareto) | 7.6 ms | ~130 designs / s |
| Mixed sweep of 5 converter specs | 38.8 ms | ~26 sweeps / s |

The T1 5-node Gauss–Seidel tool (`unifiedinductordesign.py`) is slower, as
expected, because each candidate re-evaluates losses vs temperature:

| Step | Mean wall time | Rate |
| --- | --- | --- |
| Unified T1 search, buck 12→3.3 V @ 250 kHz (366 candidates) | 25.5 ms | ~14,000 cand / s |
| Unified T1 search, boost 12→24 V @ 200 kHz (348 candidates) | 27.6 ms | ~13,000 cand / s |

Existing unit tests: **24 passed in 0.11 s** (10 original + independent
cross-checks + wire tests).

## Physics cross-check

All of the following matched independent formulas (relative error < 1e-9
unless noted).

### Converter (CCM)

Buck 9–16 V → 3.3 V / 5 A @ 500 kHz, η = 1:

- D_min = 3.3/16 = 0.20625, D_max = 3.3/9 = 0.36667
- L_min = 3.4925 µH from both the on-interval and off-interval formulas
- I_peak = 5.75 A, I_rms = 5.019 A

Boost 10–14 V → 24 V / 2 A @ 300 kHz, η = 0.92:

- I_L,worst = P_out / (V_in,min · η) = 5.217 A
- L_min = 13.133 µH
- Volt-seconds = V_in,min · D_max / f

### Magnetics

- Gapped ferrite: L = µ0 N² Ae / g reconstructs the target inductance.
  PQ2625, 10 µH, I_pk = 10 A, B_max = 0.3 T → N = 3, g = 0.1335 mm.
- Powder: L = µ0 µr N² Ae / le. T80 Kool Mµ 60µ, 10 µH → N = 17, L = 10.21 µH.
- B_peak = L I_pk / (N Ae), B_ac = L ΔI / (2 N Ae) (half-swing).

### Losses

- Steinmetz P = k f^α B_ac^β Ve matches the material coefficients.
- Copper skin depth at 500 kHz, 70 °C = 0.102 mm (expected ~0.10 mm).
- Dowell Fr matches the package 2x-argument form.
- DCR uses ρ_20 (1 + α (T−20)); P_dc = I_dc² R_dc; P_ac = I_ac² R_ac
  with I_ac,rms = ΔI / (2√3) for triangular ripple.

### Thermal (package 2-node)

Independent h = 1.42 (ΔT/L)^0.25 iteration reproduces package surface ΔT
to ~0.01 K. Hotspot = surface + P_cu · 3 K/W.

### End-to-end (after litz fill fix)

Buck 9–16 V → 3.3 V / 5 A @ 500 kHz, η = 0.92:

- 540 evaluated, 416 feasible, 6 on the Pareto front
- Recommended: PQ2016 / N87 / AWG14 / 2 T / 0.092 mm gap
- L = 3.414 µH, P = 0.08 W, ΔT = 5.4 K, B_pk = 0.157 T (50 % sat margin)

Boost 10–14 V → 24 V / 2 A @ 300 kHz, η = 0.92:

- 540 evaluated, 362 feasible, 5 on the Pareto front
- Recommended: PQ2016 / N87 / AWG14 / 5 T / 0.150 mm gap
- L = 13.133 µH, P = 0.15 W, ΔT = 9.1 K, B_pk = 0.252 T

Five additional specs (including 18–36 V → 12 V / 8 A and 40–60 V → 12 V / 15 A)
all found a feasible design.

The unified T1 tool on the same 12 V → 3.3 V / 5 A @ 250 kHz spec (ideal
duty, no η) produces L_target = 6.380 µH, identical to the package at
Vin = 12 V, η = 1, and a feasible PQ2016 / N87 / AWG14 design with
T_hotspot = 36.0 °C (gap-fringe node), T_corner = 30.3 °C > T_mean = 29.7 °C.

## Bugs found and fixed

**Litz window fill was overstated by the strand count.**
`Wire.outer_area_m2` multiplied the served-bundle area by `strands`.
A 40×AWG38 litz fill was 40× too large, so every litz candidate failed
the 40 % fill gate (2 turns on PQ2016 reported fill 137 % instead of 3.4 %).
Feasible-set size rose 314 → 416 (buck) and 255 → 362 (boost) after the fix.
The loss-optimal pick is still solid AWG14 on these light-ripple examples
because I_ac is small, so P_ac stays tiny even at Fr ≈ 48.

## Known limitations (not treated as failures)

1. **Buck L at η < 1 uses the off-interval formula with inflated duty.**
   D = Vout/(Vin·η). At η = 0.92 this undersizes L by ~10 % versus the
   on-interval (Vin−Vout)·D/(ΔI·f). Volt-seconds in the report use the
   on-interval, so L_min and V·s are slightly inconsistent when η ≠ 1.
   Ripple is set by terminal voltages; a later pass should size L with
   D = Vout/Vin and keep η for current stress only.

2. **Dowell Fr is huge for fat solid wire at hundreds of kHz**
   (Fr ≈ 48 for AWG14 @ 500 kHz, 2 layers). That is the 1-D foil formula
   in deep skin, not a coding error. Round-wire / Ferreira and a real layer
   count would be more accurate. The search currently passes `layers_hint=2`
   for every candidate.

3. **Steinmetz ignores DC bias** (no iGSE). Powder µr is constant (no
   µr(H,T) roll-off). Gap reluctance ignores the ferrite path and fringing
   (no Rogowski factor), so actual L is a few percent higher than predicted.

4. **Package thermal is a 2-node network** with a hard-coded
   R_th,winding-core = 3 K/W. The T1 5-node model on the other branch is
   the higher-fidelity analytical thermal path.

5. **`main` does not contain this tool.** It lives on
   `cursor/inductor-design-tool-plan-d762` (this package) and
   `cursor/inductor-design-doc-aa1a` (unified T1 file).
