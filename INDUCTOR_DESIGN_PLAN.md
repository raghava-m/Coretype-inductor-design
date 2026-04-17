# Inductor Design Plan

## 1. Objective
- Design a practical, manufacturable inductor that meets electrical, thermal, and cost targets for the intended power stage.
- Produce a design package that can move from concept to prototype and validation.

## 2. Requirements Definition
Define and lock these inputs before sizing:
- **Inductance target (L):** nominal value and tolerance over temperature/current.
- **Current profile:** RMS current, peak current, ripple current, transient peaks.
- **Switching frequency range:** minimum/nominal/maximum operating frequency.
- **Voltage conditions:** applied volt-seconds during on/off intervals.
- **Thermal constraints:** ambient, airflow, max winding/core temperature rise.
- **Mechanical limits:** max footprint, height, mounting style, creepage/clearance.
- **Compliance constraints:** insulation class, safety, EMI limits.
- **Commercial constraints:** target cost, preferred vendors, lead-time risk.

## 3. Topology and Core Selection
Evaluate inductor style against requirements:
- Shielded drum core
- Toroidal
- Gapped ferrite E/ETD/PQ
- Powdered iron composite

Selection criteria:
- Core loss behavior at operating frequency/flux swing.
- Saturation current margin at peak load and temperature.
- Window area for required copper fill.
- Fringing and EMI behavior.
- Mechanical robustness and assembly complexity.

Deliverable:
- Shortlist of 2 candidate core families with rationale and vendor part options.

## 4. First-Pass Electrical Sizing
Perform analytical sizing with conservative margins:
1. Use converter volt-second relation to estimate minimum turns.
2. Choose air-gap/effective permeability to hit target L.
3. Calculate copper current density and wire selection (solid, litz, foil).
4. Estimate DC resistance (DCR) and copper loss at operating temperature.
5. Estimate AC copper loss (skin/proximity effects where relevant).
6. Estimate core loss using vendor material curves.
7. Confirm saturation margin at worst-case peak current and temperature.

Initial pass/fail gates:
- L within tolerance across current and temperature.
- Total loss within thermal budget.
- Saturation margin >= 20% at worst case.

## 5. Thermal and Mechanical Design
- Build a thermal resistance stack (winding-to-core, core-to-ambient).
- Estimate temperature rise at steady-state worst case.
- Refine winding layout for lower hot-spot temperatures.
- Validate bobbin, insulation tape, and wire insulation class.
- Define drawings: body size, pin pitch, polarity marking, and assembly notes.

Deliverables:
- Thermal estimate sheet.
- Mechanical outline and fabrication notes.

## 6. Simulation and Modeling
- Create a SPICE/PLECS equivalent model with:
  - Nonlinear inductance curve (L vs I).
  - DCR temperature coefficient.
  - Core loss representation (if model supports it).
- Run scenarios:
  - Nominal load
  - Peak load
  - Startup and transient events
  - Frequency spread
- Compare predicted current ripple, loss, and temperature to requirements.

## 7. Prototype Build Plan
- Order 2 to 3 variants around nominal design (e.g., turns/gap sweep).
- Create a build matrix:
  - Variant ID
  - Turns/gap
  - Wire type
  - Expected L, Isat, DCR
- Define incoming checks:
  - Visual/mechanical inspection
  - Inductance at low current
  - DCR at 25 C

## 8. Validation Test Plan
Bench measurements:
- L vs current (to identify roll-off and saturation knee).
- DCR vs temperature.
- Temperature rise at nominal and worst-case loads.
- Efficiency impact at system level.
- EMI scan comparison among variants.

Acceptance criteria:
- Meets inductance/current/thermal limits.
- No thermal runaway or insulation stress.
- Acceptable EMI impact versus baseline.

## 9. Risk Register and Mitigations
- **Saturation risk at high temp:** increase gap/turns or move to larger core.
- **High copper loss:** larger conductor area or litz optimization.
- **Core heating:** lower flux swing or switch material/frequency trade-off.
- **Supply risk:** dual-source core and magnet wire options.
- **EMI risk:** use shielded geometry and optimized winding orientation.

## 10. Project Milestones
1. Requirements freeze
2. Core shortlist and preliminary calculations
3. Prototype release
4. Bench validation complete
5. Design freeze for production

## 11. Deliverables Checklist
- [ ] Requirements specification
- [ ] Core and winding selection rationale
- [ ] Electrical sizing calculations
- [ ] Thermal/mechanical design package
- [ ] Simulation files and summary
- [ ] Prototype build matrix
- [ ] Validation report with pass/fail against criteria
- [ ] Final release document (BOM + drawings + test evidence)

## 12. Recommended Next Actions
1. Finalize numeric requirements (L, I, f, thermal, size).
2. Select two core candidates and run first-pass calculations.
3. Build three prototype variants and execute validation plan.
