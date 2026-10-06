"""Material library for three-phase inductor analytical design.

Centralises the electrical / thermal properties that drive the analytical
sizing so the UI can offer drop-down selection instead of hard-coded copper /
aluminium branches.

Conductor properties
--------------------
- ``sigma_ms_m``            : DC conductivity at 20 C [MS/m] -> R_dc = L / (A * sigma)
- ``density_kg_m3``         : mass density [kg/m^3] -> coil / winding mass
- ``temp_coeff_const``      : inferred-zero temperature T0 [C] used in the
                              resistance temperature correction
                              R(T) = R20 * (T0 + T) / (T0 + 20)

Core properties
---------------
- ``bmax_t``                : recommended design peak flux density [T]
- ``density_kg_m3``         : lamination density [kg/m^3]
- ``steinmetz_k/a/b``       : specific loss coefficients for
                              Pv [W/m^3] = k * f^a * B^b

The Steinmetz coefficients are representative starting values (SI, per m^3);
they are exposed in the UI so the user can override them per data-sheet.
"""

from __future__ import annotations

from typing import Dict, List

# --------------------------------------------------------------------------- #
# Conductor (coil) materials
# --------------------------------------------------------------------------- #
CONDUCTOR_MATERIALS: Dict[str, Dict[str, float]] = {
    "copper": {
        "sigma_ms_m": 58.5,
        "density_kg_m3": 8890.0,
        "temp_coeff_const": 234.45,
    },
    "copper (OFHC)": {
        "sigma_ms_m": 58.0,
        "density_kg_m3": 8940.0,
        "temp_coeff_const": 234.5,
    },
    "aluminium": {
        "sigma_ms_m": 35.85,
        "density_kg_m3": 2703.0,
        "temp_coeff_const": 230.0,
    },
    "aluminium (EC grade)": {
        "sigma_ms_m": 34.0,
        "density_kg_m3": 2700.0,
        "temp_coeff_const": 228.0,
    },
}

# --------------------------------------------------------------------------- #
# Core materials
# --------------------------------------------------------------------------- #
CORE_MATERIALS: Dict[str, Dict[str, float]] = {
    "CRGO M4 (0.27 mm)": {
        "bmax_t": 1.70,
        "density_kg_m3": 7650.0,
        "steinmetz_k": 6.5,
        "steinmetz_a": 1.51,
        "steinmetz_b": 1.74,
    },
    "CRGO M5 (0.30 mm)": {
        "bmax_t": 1.70,
        "density_kg_m3": 7650.0,
        "steinmetz_k": 7.2,
        "steinmetz_a": 1.50,
        "steinmetz_b": 1.75,
    },
    "Amorphous 2605SA1": {
        "bmax_t": 1.35,
        "density_kg_m3": 7180.0,
        "steinmetz_k": 1.9,
        "steinmetz_a": 1.62,
        "steinmetz_b": 1.82,
    },
    "Nanocrystalline (FeSiBNbCu)": {
        "bmax_t": 1.20,
        "density_kg_m3": 7300.0,
        "steinmetz_k": 1.1,
        "steinmetz_a": 1.65,
        "steinmetz_b": 1.90,
    },
    "Silicon steel M19 (NO)": {
        "bmax_t": 1.50,
        "density_kg_m3": 7650.0,
        "steinmetz_k": 12.0,
        "steinmetz_a": 1.55,
        "steinmetz_b": 1.80,
    },
    "Ferrite (MnZn N87)": {
        "bmax_t": 0.35,
        "density_kg_m3": 4850.0,
        "steinmetz_k": 0.9,
        "steinmetz_a": 1.55,
        "steinmetz_b": 2.60,
    },
}

DEFAULT_CONDUCTOR = "copper"
DEFAULT_CORE = "CRGO M4 (0.27 mm)"


def conductor_names() -> List[str]:
    return list(CONDUCTOR_MATERIALS)


def core_names() -> List[str]:
    return list(CORE_MATERIALS)


def _match_key(name: str, table: Dict[str, Dict[str, float]]) -> str | None:
    if not name:
        return None
    n = str(name).strip().lower()
    for key in table:
        if key.lower() == n:
            return key
    # fall back: first word match (e.g. "copper" matches "copper (OFHC)")
    for key in table:
        if key.lower().startswith(n) or n.startswith(key.lower().split(" ")[0]):
            return key
    return None


def conductor_properties(name: str) -> Dict[str, float]:
    """Return conductor properties, defaulting to copper when unknown."""
    key = _match_key(name, CONDUCTOR_MATERIALS) or DEFAULT_CONDUCTOR
    return dict(CONDUCTOR_MATERIALS[key])


def core_properties(name: str) -> Dict[str, float]:
    """Return core properties, defaulting to the reference CRGO when unknown."""
    key = _match_key(name, CORE_MATERIALS) or DEFAULT_CORE
    return dict(CORE_MATERIALS[key])
