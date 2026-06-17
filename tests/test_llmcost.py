from vibe_tools.llmcost import estimate_costs
from vibe_tools._common import estimate_tokens


def test_heuristic_token_estimate():
    # ~4 chars per token
    assert estimate_tokens("", "heuristic") == 0
    assert estimate_tokens("a" * 400, "heuristic") == 100


def test_estimate_costs_orders_cheapest_first():
    pricing = {
        "cheap": {"input": 1.0, "output": 2.0},
        "pricey": {"input": 15.0, "output": 75.0},
    }
    rows = estimate_costs(1_000_000, 1_000_000, pricing)
    assert rows[0]["model"] == "cheap"
    assert rows[-1]["model"] == "pricey"
    # 1M in @ $15 + 1M out @ $75 = $90
    assert abs(rows[-1]["total"] - 90.0) < 1e-9


def test_zero_output_tokens():
    pricing = {"m": {"input": 10.0, "output": 30.0}}
    rows = estimate_costs(2_000_000, 0, pricing)
    assert abs(rows[0]["total"] - 20.0) < 1e-9
