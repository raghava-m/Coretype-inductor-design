#!/usr/bin/env python3
"""Size core-type inductor clamp tie rods for a short-duration shock.

A tie rod between top and bottom brackets is primarily an *axial* member.
Bending appears only if the top clamp can sway relative to the bottom clamp
(lateral shock) or if the rod is loaded eccentrically.

This module evaluates:
  * inertial force from mass × shock g (optional +1 g gravity)
  * half-sine impulse / velocity change from the pulse duration
  * axial, shear, and portal-frame bending on each rod
  * friction-lock (preload) check against lateral slip
  * smallest ISO metric rod that passes combined-stress and separation checks

Stdlib only. Run::

    python3 -m mechanical.tie_rod_shock
    python3 mechanical/tie_rod_shock.py --mass 200 --shock-g 5 --duration-ms 20
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Sequence

G = 9.81  # m/s²
E_STEEL = 210e9  # Pa


# ISO 898-1 / ISO 724 coarse-pitch properties (nominal).
# As = tensile stress area. d3 ≈ minor diameter (root), used for bending.
ROD_TABLE: tuple[dict[str, Any], ...] = (
    {"size": "M8", "d_mm": 8.0, "pitch_mm": 1.25, "d2_mm": 7.188, "d3_mm": 6.466, "As_mm2": 36.6},
    {"size": "M10", "d_mm": 10.0, "pitch_mm": 1.5, "d2_mm": 9.026, "d3_mm": 8.160, "As_mm2": 58.0},
    {"size": "M12", "d_mm": 12.0, "pitch_mm": 1.75, "d2_mm": 10.863, "d3_mm": 9.853, "As_mm2": 84.3},
    {"size": "M16", "d_mm": 16.0, "pitch_mm": 2.0, "d2_mm": 14.701, "d3_mm": 13.546, "As_mm2": 157.0},
    {"size": "M20", "d_mm": 20.0, "pitch_mm": 2.5, "d2_mm": 18.376, "d3_mm": 16.933, "As_mm2": 245.0},
    {"size": "M24", "d_mm": 24.0, "pitch_mm": 3.0, "d2_mm": 22.051, "d3_mm": 20.319, "As_mm2": 353.0},
    {"size": "M30", "d_mm": 30.0, "pitch_mm": 3.5, "d2_mm": 27.727, "d3_mm": 25.706, "As_mm2": 561.0},
)

# ISO 898-1 property class / ISO 3506 A2-70.
GRADE_TABLE = {
    "8.8": {"Rp02_MPa": 640.0, "Rm_MPa": 800.0, "name": "ISO 898-1 class 8.8"},
    "10.9": {"Rp02_MPa": 940.0, "Rm_MPa": 1040.0, "name": "ISO 898-1 class 10.9"},
    "A2-70": {"Rp02_MPa": 450.0, "Rm_MPa": 700.0, "name": "ISO 3506 A2-70 stainless"},
    "A4-80": {"Rp02_MPa": 600.0, "Rm_MPa": 800.0, "name": "ISO 3506 A4-80 stainless"},
}


@dataclass
class ShockInputs:
    """User-facing design inputs. Lengths in millimetres, mass in kg."""

    mass_kg: float = 200.0
    shock_g: float = 5.0
    duration_ms: float = 20.0
    n_rods: int = 4
    free_length_mm: float = 400.0
    spacing_x_mm: float = 300.0  # rod-to-rod along core length
    spacing_y_mm: float = 200.0  # rod-to-rod across core width
    h_cg_mm: float = 250.0  # CG height above bottom clamp / mount plane
    cg_ecc_x_mm: float = 20.0  # CG offset from rod-group centroid
    cg_ecc_y_mm: float = 0.0
    rod_ecc_mm: float = 1.0  # load-line offset at the nut face
    preload_N: float | None = None  # None → recommend from shock + clamp
    clamp_pressure_MPa: float = 1.0
    yoke_area_mm2: float = 15000.0  # area the clamps press on the core
    mu_friction: float = 0.20
    grade: str = "8.8"
    daf: float = 1.0  # extra dynamic amplification; 1.0 if fn >> 1/(2τ)
    sf_yield: float = 1.5  # on Rp0.2 for a rare shock event
    sf_separation: float = 1.5
    share_factor: float = 1.25  # unequal axial sharing among rods
    shear_share: float = 1.0  # used only when assume_shear_keys is False
    end_fixity: str = "fixed_fixed"  # or "cantilever"
    rods_resist_overturning: bool = False  # False if bottom bracket is bolted down
    assume_shear_keys: bool = True  # do not put portal bending into the rod
    min_size: str = "M12"  # construction minimum for a ~200 kg clamp
    waveform: str = "half_sine"


@dataclass
class ShockForces:
    weight_N: float
    F_shock_N: float
    F_vertical_down_N: float
    F_vertical_up_N: float
    F_lateral_N: float
    delta_v_m_s: float
    impulse_N_s: float
    pulse_Hz: float


@dataclass
class RodLoads:
    F_axial_vertical_N: float
    F_axial_overturning_N: float
    F_axial_ecc_N: float
    F_axial_design_N: float
    V_shear_N: float
    M_portal_Nm: float
    M_eccentric_Nm: float
    M_design_Nm: float
    F_preload_rec_N: float
    F_friction_N: float
    slip_prevented: bool
    k_lat_N_m: float
    fn_lat_Hz: float
    fn_ax_Hz: float


@dataclass
class RodCandidate:
    size: str
    d_mm: float
    As_mm2: float
    d3_mm: float
    sigma_axial_MPa: float
    sigma_bending_MPa: float
    tau_MPa: float
    sigma_vm_MPa: float
    utilization: float
    passes: bool
    notes: list[str] = field(default_factory=list)


def shock_forces(inp: ShockInputs) -> ShockForces:
    m = inp.mass_kg
    n = inp.shock_g * inp.daf
    F_shock = m * n * G
    weight = m * G
    tau = inp.duration_ms / 1000.0
    if tau <= 0:
        raise ValueError("duration_ms must be positive")
    if inp.waveform == "half_sine":
        delta_v = 2.0 * (n * G) * tau / math.pi
    elif inp.waveform == "rectangular":
        delta_v = (n * G) * tau
    else:
        raise ValueError(f"unknown waveform {inp.waveform!r}")
    return ShockForces(
        weight_N=weight,
        F_shock_N=F_shock,
        F_vertical_down_N=m * (n + 1.0) * G,
        F_vertical_up_N=m * max(n - 1.0, 0.0) * G,
        F_lateral_N=F_shock,
        delta_v_m_s=delta_v,
        impulse_N_s=m * delta_v,
        pulse_Hz=1.0 / (2.0 * tau),
    )


def _rod_positions(inp: ShockInputs) -> list[tuple[float, float]]:
    """Rectangle of n_rods (4, 6, or 8) or a line of 2. Coordinates in metres."""
    ax = inp.spacing_x_mm / 2000.0
    ay = inp.spacing_y_mm / 2000.0
    n = inp.n_rods
    if n < 2:
        return [(0.0, 0.0)]
    if n == 2:
        return [(-ax, 0.0), (ax, 0.0)]
    if n == 4:
        return [(-ax, -ay), (ax, -ay), (-ax, ay), (ax, ay)]
    if n == 6:
        return [
            (-ax, -ay),
            (0.0, -ay),
            (ax, -ay),
            (-ax, ay),
            (0.0, ay),
            (ax, ay),
        ]
    if n == 8:
        return [
            (-ax, -ay),
            (0.0, -ay),
            (ax, -ay),
            (-ax, 0.0),
            (ax, 0.0),
            (-ax, ay),
            (0.0, ay),
            (ax, ay),
        ]
    # Regular polygon fallback in the rod rectangle.
    out = []
    for i in range(n):
        th = 2.0 * math.pi * i / n
        out.append((ax * math.cos(th), ay * math.sin(th)))
    return out


def _max_axial_from_moment(positions: Sequence[tuple[float, float]], Mx: float, My: float) -> float:
    """Max |F_i| from moments about x/y through the rod-group centroid. F_i = My*xi/Σx² + Mx*yi/Σy²."""
    sum_x2 = sum(x * x for x, _ in positions)
    sum_y2 = sum(y * y for _, y in positions)
    peak = 0.0
    for x, y in positions:
        fi = 0.0
        if sum_x2 > 0:
            fi += My * x / sum_x2
        if sum_y2 > 0:
            fi += Mx * y / sum_y2
        peak = max(peak, abs(fi))
    return peak


def rod_loads(inp: ShockInputs, forces: ShockForces, d_shank_m: float | None = None) -> RodLoads:
    n = max(inp.n_rods, 1)
    L = inp.free_length_mm / 1000.0
    # Vertical tensile share (upward shock unloads the bottom clamp).
    F_v = forces.F_vertical_up_N if forces.F_vertical_up_N > 0 else forces.F_shock_N
    # Use the larger of upward (separation) and downward-with-gravity when
    # rods could see extra tension from bracket flexure — design tensile is
    # the upward case; downward goes into the base. Report the governing
    # tensile as max(upward, shock) × share / n.
    F_ax_v = inp.share_factor * max(F_v, forces.F_shock_N) / n

    positions = _rod_positions(inp)
    h = inp.h_cg_mm / 1000.0
    F_ot = 0.0
    if inp.rods_resist_overturning:
        # One-axis shock (IEC 60068-2-27 style): envelope of X and Y, not both at once.
        mot = forces.F_lateral_N * h
        f_ot_x = _max_axial_from_moment(positions, 0.0, mot)  # force in x → My
        f_ot_y = _max_axial_from_moment(positions, mot, 0.0)  # force in y → Mx
        F_ot = max(f_ot_x, f_ot_y)

    # Unequal sharing from CG offset (vertical force * eccentricity).
    F_vert_for_ecc = forces.F_vertical_down_N
    ecc_My = F_vert_for_ecc * (inp.cg_ecc_x_mm / 1000.0)
    ecc_Mx = F_vert_for_ecc * (inp.cg_ecc_y_mm / 1000.0)
    F_ecc = _max_axial_from_moment(positions, ecc_Mx, ecc_My)

    F_axial = F_ax_v + F_ot + F_ecc

    # Portal BM is always the upper bound (rods take all shear). It is reported
    # even when shear keys are assumed, because that is the moment you must
    # *not* put into the rod.
    V_full = forces.F_lateral_N / n
    if inp.end_fixity == "cantilever":
        M_portal = V_full * L
    else:
        M_portal = V_full * L / 2.0
    M_ecc = F_axial * (inp.rod_ecc_mm / 1000.0)
    if inp.assume_shear_keys:
        V = 0.0
        M_design = M_ecc
    else:
        V = inp.shear_share * V_full
        M_design = inp.shear_share * M_portal + M_ecc

    F_clamp = inp.clamp_pressure_MPa * 1e6 * (inp.yoke_area_mm2 * 1e-6)
    F_pre_from_clamp = F_clamp / n
    F_pre_from_sep = inp.sf_separation * F_axial
    F_pre_rec = max(F_pre_from_clamp, F_pre_from_sep)
    if inp.preload_N is not None:
        F_pre_used = inp.preload_N
    else:
        F_pre_used = F_pre_rec

    F_friction = inp.mu_friction * n * F_pre_used
    slip_prevented = F_friction >= forces.F_lateral_N

    # Lateral / axial natural frequency using a trial shank (M16 if unknown).
    d = d_shank_m if d_shank_m is not None else 0.016
    A = math.pi * d * d / 4.0
    I = math.pi * d**4 / 64.0
    k_ax = n * E_STEEL * A / max(L, 1e-6)
    # Sidesway stiffness, fixed-fixed columns: n * 12 EI / L³
    k_lat = n * 12.0 * E_STEEL * I / max(L, 1e-6) ** 3
    fn_ax = math.sqrt(k_ax / inp.mass_kg) / (2.0 * math.pi)
    fn_lat = math.sqrt(k_lat / inp.mass_kg) / (2.0 * math.pi)

    return RodLoads(
        F_axial_vertical_N=F_ax_v,
        F_axial_overturning_N=F_ot,
        F_axial_ecc_N=F_ecc,
        F_axial_design_N=F_axial,
        V_shear_N=V,
        M_portal_Nm=M_portal,
        M_eccentric_Nm=M_ecc,
        M_design_Nm=M_design,
        F_preload_rec_N=F_pre_rec,
        F_friction_N=F_friction,
        slip_prevented=slip_prevented,
        k_lat_N_m=k_lat,
        fn_lat_Hz=fn_lat,
        fn_ax_Hz=fn_ax,
    )


def _stresses(rod: dict[str, Any], loads: RodLoads, preload_N: float) -> tuple[float, float, float, float]:
    As = rod["As_mm2"] * 1e-6
    d3 = rod["d3_mm"] * 1e-3
    I = math.pi * d3**4 / 64.0
    A_root = math.pi * d3 * d3 / 4.0
    F_t = preload_N + loads.F_axial_design_N
    sigma_a = F_t / As
    sigma_b = loads.M_design_Nm * (d3 / 2.0) / I if I > 0 else 0.0
    tau = (4.0 / 3.0) * loads.V_shear_N / A_root if A_root > 0 else 0.0
    sigma_vm = math.sqrt((sigma_a + sigma_b) ** 2 + 3.0 * tau**2)
    return sigma_a / 1e6, sigma_b / 1e6, tau / 1e6, sigma_vm / 1e6


def shank_diameter_for_bending_mm(M_Nm: float, sigma_Pa: float) -> float:
    """Solid round shank that yields at σ under pure bending."""
    if M_Nm <= 0.0 or sigma_Pa <= 0.0:
        return 0.0
    return (32.0 * M_Nm / (math.pi * sigma_Pa)) ** (1.0 / 3.0) * 1000.0


def evaluate_rod(inp: ShockInputs, loads: RodLoads, rod: dict[str, Any]) -> RodCandidate:
    grade = GRADE_TABLE[inp.grade]
    Rp = grade["Rp02_MPa"]
    preload = inp.preload_N if inp.preload_N is not None else loads.F_preload_rec_N
    sa, sb, tau, svm = _stresses(rod, loads, preload)
    allow = Rp / inp.sf_yield
    notes: list[str] = []
    # Proof-ish cap on mean axial (preload + shock) in the stress area.
    axial_cap = 0.70 * Rp
    F_t = preload + loads.F_axial_design_N
    As = rod["As_mm2"] * 1e-6
    if F_t / As / 1e6 > axial_cap:
        notes.append("axial stress > 70% of Rp0.2 (reduce preload or upsize)")
    if svm > allow:
        notes.append(f"von Mises {svm:.0f} MPa > allow {allow:.0f} MPa")
    # Nut / thread: keep tensile below typical 8.8 proof utilisation.
    passes = svm <= allow and (F_t / As / 1e6) <= axial_cap
    return RodCandidate(
        size=rod["size"],
        d_mm=rod["d_mm"],
        As_mm2=rod["As_mm2"],
        d3_mm=rod["d3_mm"],
        sigma_axial_MPa=sa,
        sigma_bending_MPa=sb,
        tau_MPa=tau,
        sigma_vm_MPa=svm,
        utilization=svm / allow if allow else float("inf"),
        passes=passes,
        notes=notes,
    )


def _first_passing(candidates: Sequence[RodCandidate], min_size: str) -> RodCandidate:
    sizes = [r["size"] for r in ROD_TABLE]
    try:
        min_i = sizes.index(min_size)
    except ValueError:
        min_i = 0
    for c in candidates:
        if sizes.index(c.size) < min_i:
            continue
        if c.passes:
            return c
    return candidates[-1]


def size_tie_rods(inp: ShockInputs | None = None) -> dict[str, Any]:
    inp = inp or ShockInputs()
    if inp.grade not in GRADE_TABLE:
        raise ValueError(f"grade must be one of {sorted(GRADE_TABLE)}")
    if inp.n_rods < 1:
        raise ValueError("n_rods must be >= 1")
    forces = shock_forces(inp)
    loads = rod_loads(inp, forces)
    preload = inp.preload_N if inp.preload_N is not None else loads.F_preload_rec_N
    candidates = [evaluate_rod(inp, loads, rod) for rod in ROD_TABLE]
    recommended = _first_passing(candidates, inp.min_size)

    # Parallel "no keys" pass so the report can show how large the rod would
    # have to be if it were used as a beam.
    beam_inp = replace(inp, assume_shear_keys=False, shear_share=1.0)
    beam_loads = rod_loads(beam_inp, forces)
    beam_candidates = [evaluate_rod(beam_inp, beam_loads, rod) for rod in ROD_TABLE]
    beam_size = _first_passing(beam_candidates, inp.min_size)

    allow_Pa = GRADE_TABLE[inp.grade]["Rp02_MPa"] * 1e6 / inp.sf_yield
    d_beam_mm = shank_diameter_for_bending_mm(loads.M_portal_Nm, allow_Pa)

    warnings: list[str] = []
    if inp.n_rods < 4:
        warnings.append(
            "Fewer than 4 rods cannot form a stable clamp couple; "
            "a single tie rod cannot resist overturning."
        )
    if inp.assume_shear_keys:
        warnings.append(
            "Recommendation assumes shear keys / fitted dowels (or an equivalent "
            "core shear path) so the portal bending moment is NOT carried by the "
            f"tie rod. Without keys you would need about {beam_size.size} "
            f"(solid shank ≥ {d_beam_mm:.0f} mm) — the wrong way to carry 5 g."
        )
    elif not loads.slip_prevented:
        warnings.append(
            "Preload friction is less than the lateral shock force and no shear "
            "keys are assumed, so the portal bending moment is applied to the "
            "rods. Add keys; do not rely on a very large rod as a beam."
        )
    if loads.fn_lat_Hz < forces.pulse_Hz:
        warnings.append(
            f"Rod-only lateral fn ({loads.fn_lat_Hz:.1f} Hz) is below the pulse "
            f"frequency (~{forces.pulse_Hz:.0f} Hz). The core and keys raise fn "
            "and take the shear; quasi-static rod bending is only an upper bound."
        )
    torque_Nm = 0.20 * (recommended.d_mm / 1000.0) * preload  # T = K d F, K≈0.20 as-received

    return {
        "inputs": asdict(inp),
        "forces": asdict(forces),
        "loads": asdict(loads),
        "preload_used_N": preload,
        "recommended_size": recommended.size,
        "recommended_grade": inp.grade,
        "beam_size_without_keys": beam_size.size,
        "beam_shank_mm": d_beam_mm,
        "assembly_torque_Nm": torque_Nm,
        "candidates": [asdict(c) for c in candidates],
        "warnings": warnings,
        "grade": GRADE_TABLE[inp.grade],
    }


def _fmt_kN(x: float) -> str:
    return f"{x / 1000.0:.2f} kN"


def format_report(result: dict[str, Any]) -> str:
    f = result["forces"]
    L = result["loads"]
    inp = result["inputs"]
    lines = [
        "Core-type inductor tie-rod shock sizing",
        "=" * 44,
        f"Mass                 {inp['mass_kg']:.0f} kg",
        f"Shock                {inp['shock_g']:.1f} g for {inp['duration_ms']:.0f} ms  ({inp['waveform']})",
        f"Rods                 {inp['n_rods']} × {result['recommended_grade']}",
        f"Free length L        {inp['free_length_mm']:.0f} mm",
        "",
        "Inertial loads (assembly)",
        f"  Self-weight        {_fmt_kN(f['weight_N'])}",
        f"  5 g shock force    {_fmt_kN(f['F_shock_N'])}   (m × n × g × DAF)",
        f"  Vertical down      {_fmt_kN(f['F_vertical_down_N'])}   ((n+1) g)",
        f"  Vertical up        {_fmt_kN(f['F_vertical_up_N'])}   ((n-1) g, tension on rods)",
        f"  Lateral            {_fmt_kN(f['F_lateral_N'])}",
        f"  Half-sine Δv       {f['delta_v_m_s']:.3f} m/s",
        f"  Impulse            {f['impulse_N_s']:.1f} N·s",
        "",
        "Per-rod loads",
        f"  Axial (vertical)   {_fmt_kN(L['F_axial_vertical_N'])}",
        f"  Axial (overturning){_fmt_kN(L['F_axial_overturning_N'])}",
        f"  Axial (CG offset)  {_fmt_kN(L['F_axial_ecc_N'])}",
        f"  Axial design       {_fmt_kN(L['F_axial_design_N'])}",
        f"  Shear V (if no keys) {_fmt_kN(f['F_lateral_N'] / max(inp['n_rods'], 1))}",
        f"  Portal BM (upper bound) {L['M_portal_Nm']:.1f} N·m   (V L / 2, rods as beams — do not use)",
        f"  Eccentricity BM    {L['M_eccentric_Nm']:.2f} N·m",
        f"  BM used for stress {L['M_design_Nm']:.1f} N·m",
        "",
        "Preload / slip",
        f"  Recommended preload { _fmt_kN(L['F_preload_rec_N'])} per rod",
        f"  Friction capacity  {_fmt_kN(L['F_friction_N'])}  (μ = {inp['mu_friction']})",
        f"  Slip prevented     {L['slip_prevented']}",
        f"  fn axial (M16)     {L['fn_ax_Hz']:.0f} Hz",
        f"  fn lateral (M16)   {L['fn_lat_Hz']:.1f} Hz  (rods only; core raises this)",
        "",
        f"Recommended rod      {result['recommended_size']} {result['recommended_grade']}"
        f"{'  (with shear keys)' if inp['assume_shear_keys'] else '  (rods as beams)'}",
        f"Without shear keys   {result['beam_size_without_keys']}  "
        f"(solid shank ≥ {result['beam_shank_mm']:.0f} mm for portal BM)",
        f"Approx. nut torque   {result['assembly_torque_Nm']:.0f} N·m  (K=0.20, as-received)",
        "",
        f"{'Size':<8}{'σ_ax':>8}{'σ_b':>8}{'τ':>8}{'σ_vm':>8}{'util':>8}  pass",
    ]
    for c in result["candidates"]:
        flag = "YES" if c["passes"] else "no"
        lines.append(
            f"{c['size']:<8}{c['sigma_axial_MPa']:8.0f}{c['sigma_bending_MPa']:8.0f}"
            f"{c['tau_MPa']:8.0f}{c['sigma_vm_MPa']:8.0f}{c['utilization']:8.2f}  {flag}"
        )
    if result["warnings"]:
        lines.append("")
        lines.append("Warnings")
        for w in result["warnings"]:
            lines.append(f"  - {w}")
    lines.append("")
    lines.append(
        "Stresses use thread-root diameter d3 for bending/shear and tensile "
        "stress area As for axial. Combined check is von Mises vs Rp0.2 / SF."
    )
    return "\n".join(lines) + "\n"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Size inductor clamp tie rods for shock.")
    p.add_argument("--mass", type=float, default=200.0, help="inductor mass, kg")
    p.add_argument("--shock-g", type=float, default=5.0, help="peak shock in g")
    p.add_argument("--duration-ms", type=float, default=20.0, help="pulse duration, ms")
    p.add_argument("--n-rods", type=int, default=4)
    p.add_argument("--length", type=float, default=400.0, help="free length between clamps, mm")
    p.add_argument("--spacing-x", type=float, default=300.0, help="rod spacing along x, mm")
    p.add_argument("--spacing-y", type=float, default=200.0, help="rod spacing along y, mm")
    p.add_argument("--h-cg", type=float, default=250.0, help="CG height above base, mm")
    p.add_argument("--preload", type=float, default=None, help="preload per rod, N")
    p.add_argument("--grade", default="8.8", choices=sorted(GRADE_TABLE))
    p.add_argument("--daf", type=float, default=1.0, help="dynamic amplification factor")
    p.add_argument("--shear-share", type=float, default=1.0)
    p.add_argument("--end-fixity", default="fixed_fixed", choices=("fixed_fixed", "cantilever"))
    p.add_argument("--rods-resist-overturning", action="store_true")
    p.add_argument(
        "--no-shear-keys",
        action="store_true",
        help="size the rod as a beam for the full portal moment (not recommended)",
    )
    p.add_argument("--min-size", default="M12")
    p.add_argument("--json", action="store_true", help="print JSON instead of text")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    inp = ShockInputs(
        mass_kg=args.mass,
        shock_g=args.shock_g,
        duration_ms=args.duration_ms,
        n_rods=args.n_rods,
        free_length_mm=args.length,
        spacing_x_mm=args.spacing_x,
        spacing_y_mm=args.spacing_y,
        h_cg_mm=args.h_cg,
        preload_N=args.preload,
        grade=args.grade,
        daf=args.daf,
        shear_share=args.shear_share,
        end_fixity=args.end_fixity,
        rods_resist_overturning=args.rods_resist_overturning,
        assume_shear_keys=not args.no_shear_keys,
        min_size=args.min_size,
    )
    result = size_tie_rods(inp)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
