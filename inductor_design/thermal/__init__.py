"""Two-node thermal model for the inductor.

Node 1: winding hot-spot.  Node 2: core surface.  Convective path from
the core surface to ambient.  The goal is to give a fast, conservative
estimate of steady-state temperature rise; detailed multi-node or FEM
solutions come later in the roadmap.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThermalResult:
    t_ambient_c: float
    t_surface_c: float
    t_hotspot_c: float
    delta_t_c: float
    r_th_ca: float   # K/W, core to ambient
    r_th_wc: float   # K/W, winding to core


def natural_convection_h(delta_t: float, char_length_m: float) -> float:
    """Very simple correlation for free convection from a vertical-ish
    surface: h ≈ 1.42 * (ΔT / L)^0.25 (W/m²/K).  Clamped for robustness.
    """
    if delta_t <= 0 or char_length_m <= 0:
        return 5.0
    return max(5.0, 1.42 * (delta_t / char_length_m) ** 0.25)


def thermal_estimate(
    p_core_w: float, p_cu_w: float,
    surface_m2: float, char_length_m: float,
    t_ambient_c: float = 25.0,
    forced_air_multiplier: float = 1.0,
    r_th_wc_kpw: float = 3.0,
) -> ThermalResult:
    """Iterate once to estimate ΔT.  forced_air_multiplier scales h
    above the natural-convection baseline."""
    p_total = p_core_w + p_cu_w
    # Initial guess ΔT = 40 K, then update h(ΔT)
    dt = 40.0
    for _ in range(8):
        h = natural_convection_h(dt, char_length_m) * forced_air_multiplier
        r_th_ca = 1.0 / max(h * surface_m2, 1e-6)
        dt_new = p_total * r_th_ca
        if abs(dt_new - dt) < 0.05:
            dt = dt_new
            break
        dt = dt_new
    h = natural_convection_h(dt, char_length_m) * forced_air_multiplier
    r_th_ca = 1.0 / max(h * surface_m2, 1e-6)
    t_surface = t_ambient_c + p_total * r_th_ca
    t_hotspot = t_surface + p_cu_w * r_th_wc_kpw
    return ThermalResult(
        t_ambient_c=t_ambient_c,
        t_surface_c=t_surface,
        t_hotspot_c=t_hotspot,
        delta_t_c=t_hotspot - t_ambient_c,
        r_th_ca=r_th_ca,
        r_th_wc=r_th_wc_kpw,
    )
