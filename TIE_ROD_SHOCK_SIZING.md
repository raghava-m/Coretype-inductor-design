# Tie-rod shock load and sizing — 200 kg core-type inductor

**Direct answer.** A 200 kg inductor at **5 g for 20 ms** produces an inertial force of **9.81 kN**. That force is **not** a bending moment on the tie rod. A tie rod between the top and bottom clamp brackets is an **axial** member.

Bending on the rod appears only if the top clamp can rack sideways relative to the bottom clamp (lateral shock with no shear path through the core or keys). For four rods and an assumed free length **L = 400 mm**, that upper-bound portal moment is:

\[
V = \frac{9.81\,\text{kN}}{4} = 2.45\,\text{kN},\qquad
M = \frac{V L}{2} = \mathbf{491\,N\cdot m}
\]

**Do not size the tie rod for 491 N·m.** A slender rod is a terrible beam: that moment is ~2000 MPa at an M16 thread root (class 8.8 yields at 640 MPa). Carrying 5 g in rod bending would take about a **23 mm solid shank (M30)**. The correct design is **shear keys (or equivalent core shear) + a modest rod sized for preload and vertical tension**.

| Quantity | Value |
| --- | --- |
| Mass | 200 kg |
| Self-weight | 1.96 kN |
| Peak inertial force \(F = m \cdot 5g\) | **9.81 kN** |
| Vertical down (5 g + 1 g) | 11.77 kN |
| Vertical up (5 g − 1 g), tension trying to unload the bottom clamp | 7.85 kN |
| Half-sine velocity change \(\Delta v = 2 a \tau / \pi\) | **0.625 m/s** |
| Impulse | 125 N·s |
| Pulse frequency \(1/(2\tau)\) | 25 Hz |
| Portal BM per rod (4 rods, \(L = 400\) mm, upper bound) | **491 N·m** |
| Axial shock share per rod (4 rods, 1.25 share factor) | **3.1 kN** |

**Starting hardware**

- **4 × M12 class 8.8** is enough on stress if shear keys take the lateral load (**M16 8.8** is the practical preference for a 200 kg clamp).
- Use **A2-70 / A4-80** one size up if the rod sits in the magnetic window.
- **Shear keys or fitted dowels** at both yoke/clamp faces — this is the load path for 5 g lateral, not the rod.
- Do not use a single tie rod.

Geometry values \(L\), rod spacing, and CG height below are **assumed**. Replace them with the drawing:

```bash
python3 mechanical/tie_rod_shock.py --mass 200 --shock-g 5 --duration-ms 20 \
  --n-rods 4 --length 400 --spacing-x 300 --spacing-y 200 --h-cg 250 --grade 8.8
```

`--no-shear-keys` shows the M30 beam case (for illustration only).

---

## 1. What the tie rod actually does

```
                    5 g shock  (vertical or lateral)
                              │
         ┌──────── top clamp / bracket ────────┐
         │         ●                    ●      │   nuts + washers
         │         │                    │      │
         │      tie rod              tie rod   │   free length L
         │         │     ┌────────┐     │      │
         │         │     │ core + │     │      │   200 kg
         │         │     │ copper │     │      │
         │         │     └────────┘     │      │
         │         ●                    ●      │
         └────── bottom clamp / mount ─────────┘
                              ║
                         foundation bolts
```

Typical core-type construction: channel or plate **yoke clamps** on the top and bottom yokes, pulled together by through-rods. The rods:

1. Provide **clamping pressure** on the lamination stack (this usually governs preload).
2. Carry **tensile shock** when 5 g acts upward and tries to separate the top clamp.
3. Carry **shear / bending** only if the top clamp moves sideways relative to the bottom clamp.

The **bottom-bracket mounting bolts** take assembly shear and overturning into the foundation. Do not put that overturning couple into the tie rods unless the bottom clamp is *not* bolted down.

---

## 2. Shock force (this part does not need geometry)

\[
F = m\, n\, g = 200 \times 5 \times 9.81 = 9810\,\text{N}
\]

Duration 20 ms matters for *whether* that 5 g is a fair static equivalent:

- Half-sine pulse, \(\tau = 20\) ms → \(\Delta v = 0.625\) m/s.
- If the assembly \(f_n \gg 25\) Hz, the structure follows the pulse → use **5 g quasi-static**.
- If \(f_n \approx 25\) Hz, undamped half-sine amplification can reach about **1.5–1.8**. Re-run with `--daf 1.6`.
- If \(f_n \ll 25\) Hz (slender rods, no help from the core), the rods see an **impulse**, not a 5 g hold.

A steel clamp frame with a clamped core is stiff **axially** (the calculator gives ~230 Hz for 4 × M16 × 400 mm). **Rod-only** lateral stiffness is low (~8 Hz), which is why the core and the keys must carry shear. Use **(n+1) g** downward, **(n−1) g** upward, **n g** lateral.

---

## 3. When is there a bending moment on the rod?

### 3.1 Vertical shock — essentially no rod bending

Load is along the rod axis. Per rod, with 4 rods and a 1.25 share factor:

\[
F_\text{rod,tensile} = 1.25 \times \frac{m \cdot 5g}{4} \approx 3.07\,\text{kN}
\]

Bending is only \(M = F \times e\) from nut-face eccentricity (a millimetre or two) → a few N·m. Keep hole clearance small and use a hardened washer.

### 3.2 Lateral shock — portal bending (upper bound)

If the clamps rack like a portal frame and the rods are the only lateral path:

| End condition | Moment at the nut | 4 rods, \(L=400\) mm |
| --- | --- | --- |
| Nuts both ends on stiff plates (double curvature) | \(M = VL/2\) | **491 N·m** |
| Flexible top clamp (cantilever) | \(M = VL\) | **981 N·m** |

Scale linearly with free length: \(M \propto L\). Measure \(L\) between the inner faces of the clamps.

That moment at an M16 root (\(d_3 = 13.55\) mm):

\[
\sigma_b = \frac{32 M}{\pi d_3^3} \approx 2020\,\text{MPa}
\]

which is several times yield. Hence: **prevent this moment**, do not “absorb” it with a bigger stud.

### 3.3 Overturning — extra *axial* load, not extra rod bending

Lateral force at CG height \(h\) produces \(M_\text{ot} = F h\). If the **base bolts** resist that couple, the tie rods do not see it. If the rods *are* the load path (`--rods-resist-overturning`):

\[
F_{i} = \frac{M_\text{ot}\, x_i}{\sum x_i^2}
\]

For a 300 mm × 200 mm four-rod rectangle and \(h = 250\) mm, the **narrow** spacing governs: about **6.1 kN** extra axial on the two rods of that couple.

### 3.4 Friction is not enough — use keys

\[
F_\mu = \mu \, n_\text{rods} \, F_\text{preload}
\]

With \(\mu = 0.20\), 4 rods and a shock-minimum preload of 5 kN, \(F_\mu \approx 4\) kN **< 9.81 kN**. Raising preload until friction locks (about 18 kN per rod, ~5 MPa on a 15 000 mm² yoke) will crush insulation. **Add shear keys / fitted dowels / a spigot.** Then rod bending from shock is not the sizing case.

---

## 4. How to size the tie rod

Work in this order.

### Step A — Count and layout

- Four rods at the clamp corners. Two rods are a mechanism under unsymmetric load; one rod cannot resist a couple.
- Keep the rod-group centroid on the inductor CG (plan view).

### Step B — Preload

Lamination clamp pressure is typically **0.5–2 MPa** on the yoke face. Also keep the joint from unloading under upward 5 g:

\[
F_\text{preload} \ge \max\left(\frac{p A_\text{yoke}}{n},\ 1.5 \times F_\text{rod,tensile}\right)
\]

For the default 200 kg case that is about **5 kN per rod** from shock, often **8–15 kN** from yoke pressure. Do **not** use a catalogue M12 “8.8 full preload” torque (~70–90 N·m, ~50–70 kN) — that is far too high for a varnished stack.

Keep mean axial stress (preload + shock) **≤ 70 % of \(R_{p0.2}\)**. Rods stay in tension through the pulse, so buckling is not the check. A joint that goes slack will hammer; that is the failure to prevent.

### Step C — Stress at the thread root

Use minor diameter \(d_3\) for bending and shear, and ISO tensile stress area \(A_s\) for axial:

\[
\sigma_a = \frac{F_\text{preload}+F_\text{shock,axial}}{A_s},\quad
\sigma_b = \frac{32 M}{\pi d_3^3},\quad
\tau = \frac{4}{3}\frac{V}{\pi d_3^2/4}
\]

\[
\sigma_\text{vm} = \sqrt{(\sigma_a+\sigma_b)^2 + 3\tau^2} \le \frac{R_{p0.2}}{1.5}
\]

(SF = 1.5 on yield for a rare 5 g pulse. Use 2.0 if the shock repeats every trip or every sea state.)

| Size | \(A_s\) (mm²) | \(d_3\) (mm) | 8.8 \(R_{p0.2}\) | A2-70 \(R_{p0.2}\) |
| --- | ---: | ---: | ---: | ---: |
| M12 | 84.3 | 9.85 | 640 MPa | 450 MPa |
| M16 | 157 | 13.55 | 640 MPa | 450 MPa |
| M20 | 245 | 16.93 | 640 MPa | 450 MPa |
| M30 | 561 | 25.71 | 640 MPa | 450 MPa |

Numbers from `mechanical/tie_rod_shock.py` for this 200 kg / 5 g case (preload ≈ 5.2 kN, 4 rods, \(L = 400\) mm):

**With shear keys** (only axial + nut eccentricity):

| Size | \(\sigma_\text{vm}\) | Utilisation vs \(R_{p0.2}/1.5\) |
| --- | ---: | ---: |
| M12 × 8.8 | 139 MPa | **0.33 — pass (minimum)** |
| M16 × 8.8 | 69 MPa | 0.16 — preferred |

**Without keys** (portal BM 491 N·m put into the rod):

| Size | \(\sigma_b\) | \(\sigma_\text{vm}\) | Pass? |
| --- | ---: | ---: | --- |
| M16 | 2024 MPa | 2080 MPa | No |
| M20 | 1036 MPa | 1072 MPa | No |
| M24 | 600 MPa | 625 MPa | No |
| M30 | 296 MPa | 312 MPa | Yes, but the wrong design |

Required smooth-shank diameter for 491 N·m at 427 MPa: **\(d = (32M/\pi\sigma)^{1/3} \approx 23\) mm**.

### Step D — Hardware details that decide whether the calculation is valid

- Fully threaded stud, or a shank through the clamp with threads only for the nuts. If the thread sits in a loaded plane, use \(d_3\) (this script does that).
- Nuts: class **8** (or **10** for 10.9 rods) with a **prevailing-torque** nut or Nord-Lock / double nut. A 5 g / 20 ms pulse will loosen plain nuts.
- Hardened washers under both nuts. Clamp hole clearance ≤ 1 mm on diameter.
- Thread engagement ≥ 1×d in a steel nut; do not thread into a thin aluminium bracket.
- Rod in or beside the magnetic window → **A2-70 / A4-80**, one size up versus 8.8.
- Check the **clamp plate** in bending: the yoke reaction sits between the rods. Plates often yield before the rod does.
- Bottom-bracket **mount bolts**: 9.81 kN shear plus overturning \(F h\). Those are not the tie rods.

### Step E — Torque (assembly)

As-received steel, nut factor \(K \approx 0.20\):

\[
T = K\, d\, F_\text{preload}
\]

M12 at 5.2 kN → about **12 N·m** (shock-minimum preload). M12 at 12 kN yoke clamp → about **29 N·m**. Use a calibrated wrench and a specified lubricant; \(K\) swings 0.12–0.25.

---

## 5. What 20 ms does *not* change

Do not integrate 5 g × 20 ms to get a smaller “equivalent static” force for a stiff clamp. For any mode faster than ~25 Hz, the peak force really is **9.81 kN**. The 20 ms figure is there to:

- compute the impulse / \(\Delta v\) (0.625 m/s) for flexible-mode checks,
- compare to \(f_n\),
- remind you this is a **single pulse** (rod fatigue is not the issue; loosening and joint separation are).

If the specification is IEC 60068-2-27 Ea half-sine, apply the pulse in **each of three axes**, one at a time, and take the governing rod case (usually lateral keys + vertical tension, not both at full value at once unless the spec says so).

---

## 6. Recommended design statement (for the drawing)

For a 200 kg core-type inductor, 5 g / 20 ms, four-rod clamp:

1. **4 × M12 class 8.8** studs minimum; **M16 class 8.8** preferred (or **M16 A2-70** if inside the window).
2. Preload **8–15 kN per rod**, limited by 0.5–2 MPa on the yoke face, always ≥ 1.5 × tensile shock share.
3. **Shear keys or fitted dowels** in both yoke/clamp interfaces. Do not rely on the rod for the 491 N·m portal moment.
4. Prevailing-torque nuts + Nord-Lock or equivalent.
5. Bottom-bracket **mount bolts** sized for 9.81 kN shear and \(F h\) overturning.
6. Re-run `mechanical/tie_rod_shock.py` with measured \(L\), rod spacing, and CG before freezing the size. Portal \(M\) scales with \(L\); a 600 mm free length is 736 N·m upper bound — still a keys problem, not an M12 stress problem.
