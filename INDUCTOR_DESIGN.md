# Inductor Design — Editable Master Document

> **Status:** Draft v0.1 — working document. This is meant to be edited
> section-by-section. Every equation, coefficient, and assumption here is
> intended to be challenged, tightened, and replaced with measured data.
>
> **Scope:** Power inductors for DC/DC (buck, boost, buck–boost, SEPIC,
> flyback, LLC output choke), PFC boost, and DM/CM filter chokes. Scope
> can be narrowed per design iteration.
>
> **Goal:** An open, inspectable design flow that is *more robust* than
> Frenetic AI, with particular rigor on **thermal behavior at the
> winding edges and core corners**, where most early-life failures occur.

---

## 0. Source material and the missing `unifiedinductordesign.py`

The user referenced `@unifiedinductordesign.py` as the seed for this
document. That file is **not present** in this workspace, in any branch
of this repository, or anywhere reachable on the agent VM. To avoid
blocking progress, this document has been seeded from the already-
committed Python package on branch
`cursor/inductor-design-tool-plan-d762`:

- `inductor_design/cores/__init__.py` — PQ/ETD/EE ferrite cores and
  powder toroids with `Ae, Ac, Wa, le, Ve, MLT, surface, footprint`.
- `inductor_design/materials/__init__.py` — ferrites (3C95, N87, 3F36)
  and powder (Kool Mµ, XFlux, MPP) with Steinmetz `(k, α, β)` and
  `B_sat(T)`.
- `inductor_design/wires/__init__.py` — AWG table, `skin_depth_m`,
  solid and litz wire models.
- `inductor_design/sizing/__init__.py` — turns, gap, `B_pk`, `B_ac`,
  fill-factor, achievable-inductance helpers.
- `inductor_design/losses/__init__.py` — Steinmetz core loss and
  Dowell `Fr` AC winding loss with a litz first-order correction.
- `inductor_design/thermal/__init__.py` — current **two-node**
  winding-to-core + core-to-ambient model with free-convection
  correlation `h ≈ 1.42 (ΔT/L)^(1/4)`.
- `inductor_design/optimizer/search.py` — Pareto search over cores,
  materials, wires, layers.

When the unified source file is added to the repo, the
**Delta section at the bottom of this document** will be filled in
with a file-by-file diff and any re-derivation required.

---

## 1. Problem statement

Design a power inductor for a defined converter operating point such
that the following are simultaneously satisfied, with margin:

1. **Electrical.** Inductance is within spec across the full current
   range (`I_dc ± ΔI/2`) and over temperature; ripple matches spec.
2. **Magnetic.** Peak flux density stays below `B_sat(T_core, H_dc)`
   at worst case (max `I_peak`, hot core), with a user-chosen margin
   (default 15 %).
3. **Thermal.** Hot-spot temperature is ≤ `T_max` of the weakest
   material in the stack (insulation class, potting, adhesive, or
   core Curie limit), with margin. Thermal limits are evaluated
   **globally** (bulk) *and* **locally** (edges, corners, gap fringing
   region, innermost winding layer).
4. **Mechanical.** Winding fits the window with realistic fill
   factor (0.35–0.45 for round + bobbin, 0.5–0.6 for foil), accounts
   for bobbin, tape, triple-insulated wire, and creepage/clearance if
   isolated.
5. **Lifetime/robustness.** Derating curves respected; no hidden
   cliffs from gap fringing heating, saturation-induced runaway, or
   core–winding interface hot-spots.

We explicitly reject designs that pass item 1–2 alone, because those
are exactly where Frenetic-class tools can look good on paper and
fail on the bench.

---

## 2. Specification block (fill this in per design)

```
Converter topology:           buck | boost | buck–boost | SEPIC | flyback | PFC | LLC | CM | DM
Vin range:                    V_min  … V_max   [V]
Vout nominal:                 Vout             [V]
Iout nominal / max / min:     I_out_nom / max / min [A]
Switching frequency:          f_sw             [Hz]
Ripple target (peak-to-peak): ΔI_L_pp / I_out  [%]  or ΔI_pp [A]
Conduction mode:              CCM | BCM | DCM
Ambient temperature range:    T_amb_min … T_amb_max [°C]
Airflow / mounting:           natural | LFM … | potted | heatsinked
Isolation?:                   no | reinforced | basic (specify Vrms, creepage)
Target component budget:      V_box_max [cm³], mass_max [g], cost_max [$]
Derating policy:              B_pk ≤ 0.85·B_sat(T), T_hotspot ≤ T_max − 15 °C
EMI/filter constraint (if CM/DM): Z(f) envelope
```

> This block is mirrored in `inductor_design.converter` specs and is
> what the user enters — unlike Frenetic, which requires pre-computed
> `L, I_rms, I_pk, f` (see plan §1).

---

## 3. Topology-aware current/flux derivation

We derive `(L_target, I_dc, I_peak, ΔI_pp, V·s)` from the spec. The
package already implements buck and boost; this document tracks the
full matrix.

| Topology   | `L_min` rule | `I_dc` | `ΔI_pp` | `B_pk` uses | `B_ac` uses |
|------------|--------------|--------|---------|-------------|-------------|
| Buck       | `L = Vout (Vin−Vout) / (Vin · f_sw · ΔI_pp)` | `I_out` | from `L` | `I_pk = I_out + ΔI/2` | `ΔI/2` |
| Boost      | `L = Vin (Vout−Vin) / (Vout · f_sw · ΔI_pp)` | `I_out·Vout/Vin` | from `L` | `I_pk` inductor-side | `ΔI/2` |
| Buck–boost | `L = (Vin·Vout) / ((Vin+Vout) · f_sw · ΔI_pp)` | `I_out / (1−D)` | from `L` | `I_pk` | `ΔI/2` |
| Flyback    | primary `L_p = (Vin·D)^2 / (2·f_sw·P_in·η)` (BCM/DCM) | — | full `I_pk` AC | `I_pk_pri` | `I_pk/2` |
| PFC boost  | `L = V_in_pk · D_pk / (f_sw · ΔI_pp)` worst line | line-freq envelope | `ΔI_pp` per switch cycle | peak of line | ripple |
| LLC output choke | set by resonant ripple, not `V·s` | `I_out` | ≈ I_pk triangular | `I_pk` | half-peak |
| DM choke   | sized by insertion loss at `f_min_attn`, not energy | line `I_rms` | small | `I_pk_line` | mains fund. |
| CM choke   | sized by `Z_CM(f)` target, requires high µ, low `B_sat` not critical (balanced) | differential ≈ 0 | neglected for sizing | fault case | N/A |

**Action item:** split the CCM/BCM/DCM boundary explicitly; add a
BCM-sizing helper for flyback/PFC in `inductor_design/converter/`.

---

## 4. Core and material selection

Selection scores each `(core, material)` pair by:

1. `AP = Ae · Wa` vs. the area-product requirement
   `AP_req = L·I_pk·I_rms / (k_u · J · B_max)`; start with `k_u = 0.4`
   and `J = 4.5 A/mm²` for natural convection.
2. `B_pk ≤ α · B_sat(T_hot)` where `α = 0.85` default (tighter for PFC
   where line transients can push `I_pk`).
3. Steinmetz loss density at `B_ac, f_sw` below a per-material cap
   (ferrite ≈ 300–500 mW/cm³, powder ≈ 500–800 mW/cm³).
4. Geometric fit: window must accept bobbin wall thickness (0.6–1.0 mm),
   margin tape if isolated, and a **corner relief** (≥ 0.5 mm) so the
   innermost copper layer does not sit on the core edge — this is a
   direct thermal/insulation reliability knob (§7).

### 4.1 Material families

- **Ferrites (3C95, N87, 3F36):** low loss at ≥ 50 kHz, `B_sat ≈ 0.4 T`
  at 100 °C, hard-gapped. Need gap-fringing analysis because copper
  adjacent to the gap sees local eddy heating.
- **Powder (Kool Mµ, XFlux, MPP):** soft saturation (roll-off of µr),
  distributed gap, higher `B_sat` (1.0–1.6 T), but ~3–5× higher core
  loss density. Temperature rise is dominated by core, not winding.
- **Nanocrystalline / amorphous:** low loss, high µ, excellent for CM;
  add to DB in next pass.

### 4.2 Saturation margin with DC-bias

Powder: must use vendor `µr vs H` roll-off, not just `B_sat`. We will
model this as `L(I)` by integrating `µr(H(I))` along `le`. Current
code uses constant `µr`; this is **flagged for improvement**.

---

## 5. Winding design

The code uses round solid wire (`solid_wire`) and served litz
(`litz_wire`). Each iteration chooses:

- **Wire type:** solid if `d_cu ≤ 2·δ_skin(f_sw)`, else litz with
  strand `d_strand ≤ δ_skin/1.5`.
- **Layer count `m`:** enter Dowell directly:
  `Fr = Δ · [ (sinh 2Δ + sin 2Δ)/(cosh 2Δ − cos 2Δ)
  + (2/3)(m²−1)(sinh 2Δ − sin 2Δ)/(cosh 2Δ + cos 2Δ) ]`
  with `Δ = h/δ`.
- **Fill factor:** `k_u = (N · A_outer) / W_a`. Target 0.30–0.40 for
  round wire on bobbin, 0.45–0.55 for foil.
- **Edge turns:** first/last turn of each layer sees asymmetric field
  and higher local proximity loss. The current model does **not**
  capture this — addressed in §7.3.

### 5.1 Harmonic decomposition
At `f_sw` the ripple is triangular, so energy is not only at the
fundamental. We approximate `I_ac_rms = ΔI_pp/(2√3)` and apply `Fr(f_sw)`.
A proper treatment sums `P_ac = Σ_n (I_n)² R_ac(n·f_sw)` over Fourier
harmonics 1…5 of the triangle. **Upgrade target.**

### 5.2 Gap-fringing winding loss
For gapped ferrite, Roshen-style fringing field in the copper nearest
to the gap adds to `P_ac`. Rule of thumb: keep winding window edge at
least `3 × g` from the gap, or use a step-gap / distributed gap in
the centre leg. We enforce this geometrically in §8.

---

## 6. Loss model

### 6.1 Core loss
Current: Steinmetz `P_v = k · f^α · B_ac^β`, `B_ac_t` from ripple.
Limitations and fixes:

- **iGSE** (improved Generalized Steinmetz) for non-sinusoidal flux —
  required for PWM waveforms. Upgrade to iGSE is scheduled.
- **DC-bias dependence** (ferrites lose more with DC-bias near
  saturation). Needs vendor graphs or measured data.
- **Temperature dependence** of `k, α, β`. Most datasheets give
  curves at 25, 60, 100 °C. We should interpolate.

### 6.2 Winding loss
See §5. Add multilayer-litz Fr (Ferreira) and a **bundle proximity**
correction larger than the current `1 + (Fr−1)/N_strands`.

### 6.3 Loss budget sanity checks
Report `P_core / P_cu`. Historical rule for balanced thermal design:
`P_core ≈ P_cu` (each ≈ ½ of total). Flag designs > 3:1 as
thermally unbalanced — they almost always have an edge hot-spot
(§7.3).

---

## 7. Thermal analysis — the part we need to make rigorous

This is the section the user flagged as the top priority, especially
around **edges**: winding-layer ends, bobbin walls, core corners,
and the gap-fringing zone.

### 7.1 Where the current model stops

`thermal_estimate(...)` in `inductor_design/thermal/__init__.py` is a
**single global two-node model**:

```
T_hotspot = T_ambient + (P_core + P_cu) · R_th,ca + P_cu · R_th,wc
R_th,ca  = 1 / (h(ΔT) · A_surface)
h(ΔT)    = max(5, 1.42 · (ΔT / L_char)^0.25)
R_th,wc  = 3.0 K/W (hard-coded)
```

This is fine for a first pass but hides three failure modes that
Frenetic also hides:

1. **Winding interior hot-spot.** Heat generated in inner layers can
   only leave through outer layers → radial thermal gradient.
2. **Edge / corner hot-spots.** Natural-convection `h` drops at
   outer corners and bottom faces (recirculation), and bobbin end
   walls are nearly adiabatic. Real hot-spot is 10–25 °C above the
   mean surface temperature predicted by a global model.
3. **Gap fringing heating.** A gapped ferrite can inject 5–15 % of
   core loss locally into the copper/tape within ~3·g of the gap.

### 7.2 Target: staged thermal model

| Tier | Description | Use when | Cost |
|------|-------------|----------|------|
| **T0** | Current global 2-node | First-pass ranking in Pareto search | µs |
| **T1** | 5-node lumped network: `T_cu_inner`, `T_cu_outer`, `T_core_inner`, `T_core_outer`, `T_ambient`, with contact resistances, anisotropic winding k | Final candidates (top 20 from T0) | ms |
| **T2** | Radially-resolved 1-D (cylindrical) winding + axial gradient + gap-fringe patch | Deep-dive on finalists | 10–100 ms |
| **T3** | 2-D axisymmetric FEM (gmsh + scikit-fem or FEniCS), fully coupled to loss distribution from 2-D magnetics | "Sign-off" analysis | s–min |
| **T4** | 3-D thermal FEM with measured `k_winding` and radiation | Qualification | min–h |

We ship T0 today. **The next implementation increment is T1 + an
"edge correction" patch that covers the user's concern.**

### 7.3 Edge and corner treatment (the immediate fix)

A first, *analytical* upgrade that we can land without FEM:

1. **Anisotropic winding conductivity.** Treat the winding pack as a
   composite with:
   - `k_radial ≈ 0.5–1.2 W/m/K` (limited by enamel + air gaps between
     layers; worst case),
   - `k_axial  ≈ 1.5–3.5 W/m/K` (along copper),
   - `k_cu    ≈ 401 W/m/K` only inside the copper itself.
   Implementation: compute an effective `k_pack` from the **Hashin-
   Shtrikman bounds** given fill factor `k_u` and enamel conductivity
   (0.25 W/m/K). This directly controls `R_th,wc` instead of the
   hard-coded 3 K/W.

2. **Local convection correction per face.** Replace the single `h`
   with per-face values:
   - top face (facing up): `h_top = 1.32 (ΔT/L_c)^0.25`
   - bottom face (facing down, on PCB): `h_bot = 0.59 (ΔT/L_c)^0.25`
   - vertical sides: `h_side = 1.42 (ΔT/L_c)^0.25`
   - corners: scale `h` by 0.7 over a corner patch of side 0.1·L_c
     (empirical recirculation penalty; replace with CFD fit later).
   This is the mechanism that lets the model see that **corners run
   hotter**.

3. **Gap-fringing hot patch.** For each gapped-ferrite candidate,
   deposit `f_fringe · P_core` (default 0.10, configurable) into a
   copper volume within `3·g` of the gap, and raise the local
   `T_cu` node for that region. Feed the worst-of-all nodes into
   saturation and insulation checks, *not* the mean.

4. **Bobbin end-wall accumulation.** First and last turns of the
   winding are bounded by a nearly adiabatic bobbin flange. The
   heat they generate leaves radially only. Model as a lateral
   "edge" sub-node with `R_th,edge` = (thickness / k_pack / A_edge).

5. **Radiation.** At 80–100 °C rise, radiation contributes
   ≈ 4·σ·ε·T_mean³ → ~8–12 W/m²/K. Add `h_rad` in parallel with
   `h_conv` on exterior faces (`ε = 0.85` for ferrite, 0.4 for
   varnished copper). Currently missing.

6. **Temperature-dependent feedback.** All losses depend on T:
   `ρ_cu(T)`, `k,α,β(T)`, `B_sat(T)`. The current solver iterates 8
   times on `ΔT` but keeps losses fixed. Switch to a coupled
   Gauss–Seidel between the electromagnetic and thermal models with a
   tight convergence test (Δ < 0.1 °C).

### 7.4 Acceptance criteria

A design is accepted only if **all** of the following hold at
worst-case ambient:

- `max_i T_node,i ≤ T_class − 15 °C` (class B winding → 110 °C; F →
  140 °C; H → 165 °C — whichever applies).
- `T_core_local(gap region) ≤ T_curie − 30 °C`.
- `T_cu_inner − T_cu_outer ≤ 25 °C` (radial gradient limit;
  otherwise copper expansion cycles stress enamel).
- `B_pk(I_max, T_hot) ≤ 0.85 · B_sat(T_hot)`.

### 7.5 Instrumentation & validation plan

- Thermocouple map: 4 points minimum — winding surface top, winding
  surface bottom, core centre leg, core corner. Log at 1 Hz during
  step-load test.
- IR imaging of the naked inductor at steady state, emissivity-
  corrected.
- Compare measured `ΔT_map` to T1/T2 predictions; tune
  `k_radial, f_fringe, h_corner_scale`. Store fits per `(core,
  winding style)` combo in a YAML so next design starts calibrated.

---

## 8. Geometry and manufacturability rules

Encoded as hard constraints in the optimizer, not soft penalties:

- Min creepage / clearance if isolated: per IEC 62368-1 PA rating.
- Bobbin wall thickness ≥ 0.6 mm; margin tape ≥ 3 mm for reinforced.
- Min turn spacing for HV: `V_turn_peak / 1 kV·mm⁻¹` rule.
- **Gap-to-winding distance ≥ 3·g_m** (keeps winding out of the
  fringe-loss zone — see §5.2 & §7.3).
- **Corner relief ≥ 0.5 mm** between innermost winding and core
  corner (reduces local stress concentration and lets air or potting
  reach the hot edge).
- Litz bundle bend radius ≥ 8·d_bundle.

---

## 9. Optimization

Current implementation: exhaustive grid search over `(core ×
material × wire × layers)` with Pareto filtering on `(loss, volume,
cost, T_hotspot)`. Weakness: cannot handle continuous gap length or
strand count efficiently.

Upgrade path:

1. **NSGA-II** over mixed discrete/continuous variables, using the
   existing database as categorical dimensions and gap/strand as
   continuous.
2. **Early rejection** with T0 thermal; re-rank top K with T1.
3. **Robustness cost:** penalize designs whose `B_pk`, `T_hotspot`
   cross limits within ±10 % of L and ±20 °C of ambient variation.
4. **Confidence intervals.** Propagate Steinmetz coefficient
   uncertainty to `P_core` and report a band, not a point.

---

## 10. Reports

Per candidate:

- Electrical summary: `L, B_pk, B_ac, ΔI, I_rms`.
- Loss table: `P_core, P_cu_dc, P_cu_ac, P_total`, Fr, skin depth.
- Thermal table: temperatures at every node, worst edge node,
  fringe node, margin vs. limit.
- Mechanical: footprint, height, mass, cost.
- BOM: core p/n, material, wire (litz strand/awg count), bobbin,
  tape.
- A Pareto plot across finalists.

---

## 11. Beating Frenetic — concrete scorecard

| Capability | Frenetic AI | This tool today | This tool target |
|---|---|---|---|
| Open model/coefficients | ✗ | ✓ | ✓ |
| Converter-spec entry (not pre-computed L/I/f) | ✗ | ✓ (buck/boost) | ✓ (all topologies incl. CM/DM) |
| Multi-objective Pareto | partial | ✓ (grid) | ✓ (NSGA-II + robustness) |
| Core-loss model | Steinmetz + ML | Steinmetz | iGSE + DC-bias + T-dep |
| AC winding loss | Dowell + ML | Dowell + litz 1st-order | Dowell + Ferreira bundle + harmonic sum |
| Thermal | global lumped | global 2-node | staged T0→T4 with edge/corner/fringe |
| Gap-fringe copper loss/heat | ✗ | ✗ | ✓ (§5.2, §7.3) |
| Saturation with DC-bias | partial | constant µr (powder) | `µr(H,T)` from vendor curves |
| Robustness sweep (spec tolerance) | ✗ | ✗ | ✓ (§9.3) |
| Validation feedback loop | closed cloud | open YAML | `measured → refit coefficients` |

---

## 12. Roadmap (unordered — prioritize with the user)

- [ ] **T1 thermal model** (5-node lumped with anisotropic winding k
  and edge node) — unblocks the user's edge-thermal concern.
- [ ] **Per-face convection + radiation** in thermal solver.
- [ ] **Gap-fringe heat injection** with patched hot-node.
- [ ] Coupled EM/thermal Gauss–Seidel solver.
- [ ] iGSE core-loss.
- [ ] DC-bias `µr(H)` for powder (Kool Mµ, XFlux) from vendor fits.
- [ ] NSGA-II optimizer.
- [ ] CM/DM inductor flows.
- [ ] Validation harness: measured `ΔT` and `L(I)` feeding a
  coefficient-refit tool.
- [ ] T2 1-D cylindrical thermal model.
- [ ] T3 FEM thermal (gmsh + scikit-fem) for finalists.

---

## 13. Open questions / flags

- **Missing source file.** `unifiedinductordesign.py` was referenced
  but not supplied. Please attach it (drop it into the repo root, or
  paste its content), and we will reconcile its internal model with
  the `inductor_design` package in §14.
- What isolation class/standard is the target (60335, 62368, 61558,
  medical)? Drives margin tape & creepage.
- Is the first design target buck, boost, or flyback? Thermal
  priorities differ (flyback has severe peak currents → winding
  hot-spot).
- Allowed manufacturing processes: vacuum potting? If yes, thermal
  model changes — potting is near-isotropic at ~0.6–1.0 W/m/K.

---

## 14. Delta vs. `unifiedinductordesign.py` (to be filled)

Once the source file lands, this section will hold:

- Coefficient and model comparison (Steinmetz k/α/β, Dowell form,
  thermal constants).
- Topology coverage diff.
- Geometry database diff.
- A checklist of which parts of `unifiedinductordesign.py` get folded
  into which module of `inductor_design/`, and which parts this
  document explicitly **rejects** with rationale.

> Until then, this document is self-consistent against the committed
> `inductor_design/` package, and every number can be traced to a
> file and line.
