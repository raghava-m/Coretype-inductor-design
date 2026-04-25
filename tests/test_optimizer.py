from inductor_design import BuckSpec, BoostSpec, design_buck, design_boost


def test_buck_end_to_end_finds_design():
    spec = BuckSpec(vin_min=9.0, vin_max=16.0, vout=3.3, iout=5.0, fsw=500e3)
    result = design_buck(spec)
    assert result.all_candidates_evaluated > 0
    assert result.feasible_count > 0
    assert result.best is not None
    # Basic physical sanity
    b = result.best
    assert b.turns >= 1
    assert b.inductance_h > 0
    assert 0 < b.fill < 1
    assert b.p_total_w > 0
    assert b.temperature_rise_c > 0


def test_boost_end_to_end_finds_design():
    spec = BoostSpec(vin_min=10.0, vin_max=14.0, vout=24.0, iout=2.0, fsw=300e3)
    result = design_boost(spec)
    assert result.feasible_count > 0
    assert result.best is not None
    assert result.best.saturation_margin >= 0


def test_pareto_monotonic():
    spec = BuckSpec(vin_min=9.0, vin_max=16.0, vout=3.3, iout=5.0, fsw=500e3)
    result = design_buck(spec)
    losses = [c.p_total_w for c in result.pareto]
    assert losses == sorted(losses)
