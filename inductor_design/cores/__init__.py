"""Magnetic core geometry database.

Each core has enough geometric data to compute turns, flux density, MLT,
and surface area.  Values are representative of public datasheets
(Ferroxcube, TDK, Magnetics, Micrometals) for first-pass design.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Core:
    name: str           # e.g. "PQ2620", "T38A"
    shape: str          # "EE", "ETD", "PQ", "RM", "toroid", "drum"
    ae_mm2: float       # effective cross-section area
    ac_mm2: float       # minimum cross-section area (sat check)
    wa_mm2: float       # window area for winding
    le_mm: float        # magnetic path length
    ve_mm3: float       # effective volume
    mlt_mm: float       # mean length per turn
    height_mm: float    # finished component height
    footprint_mm2: float
    surface_mm2: float  # exterior surface for convection
    weight_g: float
    cost_usd: float
    compatible_materials: tuple[str, ...] = ()  # keys into materials DB

    @property
    def ae_m2(self) -> float:
        return self.ae_mm2 * 1e-6

    @property
    def wa_m2(self) -> float:
        return self.wa_mm2 * 1e-6

    @property
    def mlt_m(self) -> float:
        return self.mlt_mm * 1e-3

    @property
    def le_m(self) -> float:
        return self.le_mm * 1e-3

    @property
    def ve_m3(self) -> float:
        return self.ve_mm3 * 1e-9

    @property
    def surface_m2(self) -> float:
        return self.surface_mm2 * 1e-6


def _toroid_geometry(
    name: str, od_mm: float, id_mm: float, ht_mm: float,
    mu_r: float, compat: tuple[str, ...], cost_usd: float,
) -> Core:
    """Build a toroid core entry from OD/ID/HT in mm."""
    od, idd, ht = od_mm, id_mm, ht_mm
    ae = (od - idd) / 2.0 * ht        # mm^2
    le = math.pi * (od + idd) / 2.0   # mm
    ve = ae * le                      # mm^3
    wa = math.pi * (idd / 2.0) ** 2   # mm^2, inside window
    mlt = 2.0 * ((od - idd) / 2.0 + ht) + 2.0  # rough
    surface = (
        2.0 * math.pi * (od / 2.0) ** 2
        - 2.0 * math.pi * (idd / 2.0) ** 2
        + math.pi * (od + idd) * ht
    )
    footprint = math.pi * (od / 2.0) ** 2
    weight = ve * 1e-9 * 7400.0 * 1000.0  # approximate g (powder ρ)
    return Core(
        name=name, shape="toroid",
        ae_mm2=ae, ac_mm2=ae, wa_mm2=wa, le_mm=le, ve_mm3=ve,
        mlt_mm=mlt, height_mm=ht, footprint_mm2=footprint,
        surface_mm2=surface, weight_g=weight, cost_usd=cost_usd,
        compatible_materials=compat,
    )


_FERRITE = ("3C95", "N87", "3F36")
_POWDER = ("KoolMu_60", "XFlux_60", "MPP_60")

CORES: dict[str, Core] = {
    # Gapped ferrite E / PQ cores (Ferroxcube / TDK style)
    "PQ2016": Core("PQ2016", "PQ", 62.6, 62.6, 36.2, 37.6, 2360,
                   35.0, 10.2, 400, 2200, 11.0, 0.80, _FERRITE),
    "PQ2020": Core("PQ2020", "PQ", 62.6, 62.6, 36.2, 45.7, 2870,
                   43.0, 14.0, 400, 2800, 13.5, 1.10, _FERRITE),
    "PQ2625": Core("PQ2625", "PQ", 118.0, 118.0, 55.0, 55.5, 6530,
                   57.0, 17.5, 676, 4500, 31.0, 1.60, _FERRITE),
    "PQ3230": Core("PQ3230", "PQ", 170.0, 170.0, 78.0, 69.5, 11800,
                   70.0, 21.5, 1024, 6600, 55.0, 2.30, _FERRITE),
    "ETD29":  Core("ETD29",  "ETD", 76.0, 71.0, 97.0, 72.0, 5470,
                   53.0, 15.9, 870,  5300, 28.0, 1.40, _FERRITE),
    "ETD34":  Core("ETD34",  "ETD", 97.3, 91.6, 123.0, 78.6, 7640,
                   60.0, 17.4, 1160, 6800, 40.0, 1.80, _FERRITE),
    "ETD39":  Core("ETD39",  "ETD", 125.0, 123.0, 177.0, 92.2, 11500,
                   69.0, 20.2, 1540, 9100, 60.0, 2.40, _FERRITE),
    "ETD44":  Core("ETD44",  "ETD", 173.0, 172.0, 214.0, 103.0, 17800,
                   78.0, 22.4, 1950, 12000, 94.0, 3.20, _FERRITE),
    "EE25":   Core("EE25",   "EE",  52.0, 52.0, 40.0, 58.0, 3020,
                   40.0, 12.5, 500, 2800, 17.0, 0.70, _FERRITE),
    "EE42":   Core("EE42",   "EE",  180.0, 180.0, 250.0, 97.0, 17500,
                   90.0, 21.0, 1760, 11500, 98.0, 2.80, _FERRITE),

    # Powder toroids (Magnetics / Micrometals sizes)
    "T38A":  _toroid_geometry("T38A",  9.53,  4.75, 3.18, 60, _POWDER, 0.60),
    "T50":   _toroid_geometry("T50",   12.70, 7.62, 4.83, 60, _POWDER, 0.80),
    "T60":   _toroid_geometry("T60",   15.24, 7.62, 4.83, 60, _POWDER, 0.95),
    "T80":   _toroid_geometry("T80",   20.20, 12.60, 6.35, 60, _POWDER, 1.25),
    "T102":  _toroid_geometry("T102",  26.90, 14.50, 11.00, 60, _POWDER, 2.00),
    "T130":  _toroid_geometry("T130",  33.00, 19.80, 11.10, 60, _POWDER, 2.80),
    "T157":  _toroid_geometry("T157",  40.00, 23.30, 15.00, 60, _POWDER, 3.80),
    "T184":  _toroid_geometry("T184",  46.70, 24.00, 18.00, 60, _POWDER, 5.00),
}


def list_cores() -> list[str]:
    return list(CORES.keys())
