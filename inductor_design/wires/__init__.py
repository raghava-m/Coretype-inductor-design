"""Magnet wire (solid and litz) helpers."""
from __future__ import annotations

import math
from dataclasses import dataclass


# Round solid magnet wire (heavy build, "grade 2"). Outer diameter includes
# insulation.  AWG -> (copper diameter mm, outer diameter mm).
AWG_TABLE: dict[int, tuple[float, float]] = {
    14: (1.628, 1.730),
    16: (1.291, 1.384),
    18: (1.024, 1.107),
    20: (0.812, 0.881),
    22: (0.644, 0.704),
    24: (0.511, 0.566),
    26: (0.405, 0.452),
    28: (0.321, 0.361),
    30: (0.254, 0.290),
    32: (0.202, 0.234),
    34: (0.160, 0.188),
    36: (0.127, 0.152),
    38: (0.101, 0.122),
    40: (0.079, 0.099),
}

COPPER_RHO_20C = 1.724e-8       # Ω·m
COPPER_ALPHA = 3.93e-3          # 1/°C
COPPER_DENSITY = 8960.0         # kg/m^3
COPPER_COST_PER_KG = 12.0       # USD


@dataclass(frozen=True)
class Wire:
    name: str
    kind: str               # "solid" or "litz"
    awg: int
    cu_diameter_m: float    # copper only
    outer_diameter_m: float # copper + insulation
    strands: int = 1
    area_cu_m2: float = 0.0

    @property
    def outer_area_m2(self) -> float:
        return math.pi * (self.outer_diameter_m / 2.0) ** 2 * self.strands

    def dcr_ohm(self, mlt_m: float, turns: int, temp_c: float = 70.0) -> float:
        rho_t = COPPER_RHO_20C * (1.0 + COPPER_ALPHA * (temp_c - 20.0))
        length = mlt_m * turns
        return rho_t * length / (self.area_cu_m2)

    def weight_kg(self, mlt_m: float, turns: int) -> float:
        length = mlt_m * turns
        return length * self.area_cu_m2 * COPPER_DENSITY


def solid_wire(awg: int) -> Wire:
    cu_d_mm, od_mm = AWG_TABLE[awg]
    cu_d = cu_d_mm * 1e-3
    area = math.pi * (cu_d / 2.0) ** 2
    return Wire(
        name=f"AWG{awg}",
        kind="solid",
        awg=awg,
        cu_diameter_m=cu_d,
        outer_diameter_m=od_mm * 1e-3,
        strands=1,
        area_cu_m2=area,
    )


def litz_wire(strand_awg: int, strands: int) -> Wire:
    cu_d_mm, od_mm = AWG_TABLE[strand_awg]
    cu_d = cu_d_mm * 1e-3
    strand_area = math.pi * (cu_d / 2.0) ** 2
    # Loose approximation for served litz bundle outer diameter
    bundle_od = 1.15 * math.sqrt(strands) * od_mm * 1e-3
    return Wire(
        name=f"Litz {strands}x AWG{strand_awg}",
        kind="litz",
        awg=strand_awg,
        cu_diameter_m=cu_d,
        outer_diameter_m=bundle_od,
        strands=strands,
        area_cu_m2=strands * strand_area,
    )


def skin_depth_m(f_hz: float, temp_c: float = 70.0) -> float:
    rho = COPPER_RHO_20C * (1.0 + COPPER_ALPHA * (temp_c - 20.0))
    mu0 = 4.0 * math.pi * 1e-7
    return math.sqrt(rho / (math.pi * f_hz * mu0))
