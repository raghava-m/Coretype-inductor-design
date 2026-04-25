import math

import pytest

from inductor_design.converter.buck import BuckSpec, size_buck
from inductor_design.converter.boost import BoostSpec, size_boost


def test_buck_duty_and_ripple():
    spec = BuckSpec(vin_min=9.0, vin_max=16.0, vout=3.3, iout=5.0,
                    fsw=500e3, ripple_ratio=0.3, efficiency=1.0)
    op = size_buck(spec)
    assert op.duty_min == pytest.approx(3.3 / 16.0, rel=1e-6)
    assert op.duty_max == pytest.approx(3.3 / 9.0, rel=1e-6)
    # L_min = Vout*(1-Dmin)/(r*Iout*fsw)
    expected_l = 3.3 * (1 - 3.3/16.0) / (0.3 * 5.0 * 500e3)
    assert op.l_min == pytest.approx(expected_l, rel=1e-6)
    assert op.delta_i == pytest.approx(1.5, rel=1e-6)
    assert op.i_peak == pytest.approx(5.75, rel=1e-6)


def test_boost_duty_and_current():
    spec = BoostSpec(vin_min=10.0, vin_max=14.0, vout=24.0, iout=2.0,
                     fsw=300e3, ripple_ratio=0.3, efficiency=1.0)
    op = size_boost(spec)
    assert op.duty_max == pytest.approx(1 - 10.0/24.0, rel=1e-6)
    assert op.duty_min == pytest.approx(1 - 14.0/24.0, rel=1e-6)
    # Input avg at Vin_min
    expected_il = 2.0 / (1 - op.duty_max)
    assert op.i_l_avg_worst == pytest.approx(expected_il, rel=1e-6)


def test_buck_spec_validates():
    with pytest.raises(ValueError):
        BuckSpec(vin_min=3.3, vin_max=5.0, vout=5.0, iout=1.0, fsw=100e3)


def test_boost_spec_validates():
    with pytest.raises(ValueError):
        BoostSpec(vin_min=12.0, vin_max=12.0, vout=10.0, iout=1.0, fsw=100e3)
