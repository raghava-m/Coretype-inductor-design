import math

import pytest

from inductor_design.wires import solid_wire, litz_wire, skin_depth_m


def test_solid_wire_area_matches_copper_diameter():
    w = solid_wire(20)
    assert w.area_cu_m2 == pytest.approx(math.pi * (w.cu_diameter_m / 2.0) ** 2)
    assert w.outer_area_m2 == pytest.approx(math.pi * (w.outer_diameter_m / 2.0) ** 2)
    assert w.outer_diameter_m > w.cu_diameter_m


def test_litz_outer_area_is_served_bundle():
    w = litz_wire(38, 40)
    bundle = math.pi * (w.outer_diameter_m / 2.0) ** 2
    assert w.strands == 40
    assert w.area_cu_m2 == pytest.approx(40 * math.pi * (w.cu_diameter_m / 2.0) ** 2)
    assert w.outer_area_m2 == pytest.approx(bundle)
    # Bundle envelope is far smaller than 40 × bundle (the previous bug).
    assert w.outer_area_m2 < 2.0 * bundle


def test_skin_depth_scales_as_one_over_sqrt_f():
    d1 = skin_depth_m(100e3, 70.0)
    d4 = skin_depth_m(400e3, 70.0)
    assert d1 / d4 == pytest.approx(2.0)
