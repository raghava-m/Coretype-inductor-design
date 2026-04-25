"""Magnetic material database.

Each material has Steinmetz coefficients (k, α, β) in SI units such that
``P_v = k * f^α * Bac^β`` is in W/m^3 with f in Hz and Bac in T.  Values
are representative of public datasheet extractions and are intended for
first-pass design; always refit against the vendor's curves before
production.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    name: str
    kind: str          # "ferrite" or "powder"
    b_sat_25c: float   # T, at 25 °C
    b_sat_100c: float  # T, at 100 °C
    mu_r: float        # relative permeability (effective for powder)
    # Steinmetz: P_v [W/m^3] = k * f^alpha * Bac^beta, f in Hz, Bac in T
    k: float
    alpha: float
    beta: float
    rho: float         # density kg/m^3 (for weight / cost)
    cost_per_kg: float # USD / kg (rough)

    def core_loss_density(self, f_hz: float, b_ac_t: float) -> float:
        """Return volumetric core loss in W/m^3 (Steinmetz, DC-bias ignored)."""
        if f_hz <= 0 or b_ac_t <= 0:
            return 0.0
        return self.k * (f_hz ** self.alpha) * (b_ac_t ** self.beta)

    def b_sat(self, t_core_c: float) -> float:
        """Linearly interpolate B_sat between 25 °C and 100 °C, clamp outside."""
        t = max(25.0, min(100.0, t_core_c))
        frac = (t - 25.0) / 75.0
        return self.b_sat_25c + frac * (self.b_sat_100c - self.b_sat_25c)


MATERIALS: dict[str, Material] = {
    # Power ferrites (gapped E/PQ/ETD usage).  Steinmetz @ ~100 °C.
    "3C95": Material(
        name="3C95", kind="ferrite",
        b_sat_25c=0.53, b_sat_100c=0.42, mu_r=3000,
        k=3.2, alpha=1.55, beta=2.65,
        rho=4800.0, cost_per_kg=25.0,
    ),
    "N87": Material(
        name="N87", kind="ferrite",
        b_sat_25c=0.49, b_sat_100c=0.39, mu_r=2200,
        k=16.9, alpha=1.25, beta=2.35,
        rho=4850.0, cost_per_kg=22.0,
    ),
    "3F36": Material(
        name="3F36", kind="ferrite",
        b_sat_25c=0.52, b_sat_100c=0.43, mu_r=1600,
        k=0.25, alpha=1.85, beta=2.75,
        rho=4800.0, cost_per_kg=28.0,
    ),
    # Powder cores (distributed gap).
    "KoolMu_60": Material(
        name="Kool Mµ 60µ", kind="powder",
        b_sat_25c=1.05, b_sat_100c=1.00, mu_r=60,
        k=50.0, alpha=1.46, beta=2.15,
        rho=7400.0, cost_per_kg=30.0,
    ),
    "XFlux_60": Material(
        name="XFlux 60µ", kind="powder",
        b_sat_25c=1.60, b_sat_100c=1.55, mu_r=60,
        k=110.0, alpha=1.36, beta=2.10,
        rho=7600.0, cost_per_kg=45.0,
    ),
    "MPP_60": Material(
        name="MPP 60µ", kind="powder",
        b_sat_25c=0.75, b_sat_100c=0.75, mu_r=60,
        k=12.0, alpha=1.40, beta=2.10,
        rho=8000.0, cost_per_kg=90.0,
    ),
}


def list_materials() -> list[str]:
    return list(MATERIALS.keys())
