"""Token cost configuration and cost calculation utility."""

COST_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "claude-sonnet-4-5":          {"input": 0.003,   "output": 0.015},
    "claude-3-5-sonnet-20241022": {"input": 0.003,   "output": 0.015},
    "gpt-4o-mini":                {"input": 0.00015, "output": 0.0006},
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = COST_PER_1K_TOKENS.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1000
