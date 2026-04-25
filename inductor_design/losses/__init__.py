"""Loss models: core loss (Steinmetz) and winding AC/DC loss.

The AC winding resistance uses a 1-D proximity-effect approximation valid
for round wire with multiple layers in a window (the standard "Dowell"
low-frequency expansion), plus a simple strand correction for litz.  For
deep skin-effect regimes the tool falls back to the full Dowell Fr, Fl
expressions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..materials import Material
from ..wires import Wire, skin_depth_m


@dataclass(frozen=True)
class WindingLoss:
    r_dc: float
    r_ac: float
    p_dc: float
    p_ac: float
    p_total: float
    fr: float   # R_ac / R_dc


def core_loss_w(material: Material, b_ac_t: float, f_hz: float,
                volume_m3: float) -> float:
    return material.core_loss_density(f_hz, b_ac_t) * volume_m3


def _dowell_fr(delta: float, layers: int) -> float:
    """Dowell AC-to-DC resistance ratio for a single-winding arrangement.

    delta = h/δ_skin where h is the copper diameter (or equivalent foil
    thickness) and δ_skin is the skin depth at the analysis frequency.
    """
    if delta < 1e-6:
        return 1.0
    # sinh/sin based exact form
    try:
        sh = math.sinh(2.0 * delta)
        si = math.sin(2.0 * delta)
        ch = math.cosh(2.0 * delta)
        co = math.cos(2.0 * delta)
    except OverflowError:
        # Deep skin: Fr ~ delta * (2m^2 - 1) / 3 grows linearly
        return max(1.0, delta * ((2.0 * layers ** 2 - 1.0) / 3.0))
    denom = ch - co
    if abs(denom) < 1e-12:
        return 1.0
    term1 = (sh + si) / denom
    term2 = (sh - si) / (ch + co) if (ch + co) > 1e-12 else 0.0
    fr = delta * (term1 + (2.0 / 3.0) * (layers ** 2 - 1) * term2)
    return max(1.0, fr)


def winding_loss(
    wire: Wire, turns: int, mlt_m: float,
    i_dc: float, delta_i_pp: float, f_hz: float,
    layers: int = 2, temp_c: float = 70.0,
) -> WindingLoss:
    """Compute winding DC + AC loss.

    i_dc is the DC component of the inductor current; delta_i_pp is the
    fundamental triangular ripple, used as the AC RMS surrogate
    ``I_ac_rms = delta_i_pp / (2*sqrt(3))``.
    """
    r_dc = wire.dcr_ohm(mlt_m, turns, temp_c=temp_c)

    # Skin-based delta uses copper diameter for solid, strand diameter for litz
    delta_m = skin_depth_m(f_hz, temp_c=temp_c)
    h = wire.cu_diameter_m
    delta = h / delta_m if delta_m > 0 else 0.0

    fr = _dowell_fr(delta, layers=max(1, layers))
    # For litz, each strand sees the same skin delta, and the bundle-level
    # proximity effect is reduced by 1/strands^(0.5-ish); we use the common
    # first-order correction.
    if wire.kind == "litz" and wire.strands > 1:
        fr = 1.0 + (fr - 1.0) / wire.strands

    r_ac = r_dc * fr

    i_ac_rms = delta_i_pp / (2.0 * math.sqrt(3.0))
    i_rms_total = math.sqrt(i_dc ** 2 + i_ac_rms ** 2)

    p_dc = i_dc ** 2 * r_dc
    p_ac = i_ac_rms ** 2 * r_ac
    p_total = p_dc + p_ac

    return WindingLoss(
        r_dc=r_dc, r_ac=r_ac, p_dc=p_dc, p_ac=p_ac,
        p_total=p_total, fr=fr,
    )
