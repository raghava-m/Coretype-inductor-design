from three_phase import DEFAULT_SPEC, run_tradeoff, summarize_design
from webapp.server import handle_api


def test_default_spec_is_feasible():
    row = summarize_design(None)
    assert row["turns"] >= 1
    assert row["p_total_w"] > 0
    assert row["total_mass_without_clamps_kg"] > 0
    assert row["feasible"] is True


def test_tradeoff_returns_pareto():
    result = run_tradeoff(DEFAULT_SPEC)
    assert result["evaluated"] > 50
    assert result["feasible"] > 0
    assert result["pareto"]
    assert result["best"] is not None
    losses = [c["p_total_w"] for c in result["pareto"]]
    assert losses == sorted(losses)
    # Pareto points are unique on the compact identity
    ids = [(c["core_material"], c["conductor_material"], c["layers"], c["core_stack_mm"],
            round(c["p_total_w"], 3)) for c in result["pareto"]]
    assert len(ids) == len(set(ids))


def test_api_meta_and_design():
    status, body, ctype = handle_api("GET", "/api/meta", b"")
    assert status == 200
    assert b"core_materials" in body
    status, body, _ = handle_api("POST", "/api/design", b"{}")
    assert status == 200
    assert b"baseline" in body
    status, body, _ = handle_api("POST", "/api/tradeoff", b"{}")
    assert status == 200
    assert b"pareto" in body
