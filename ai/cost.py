"""
AI Cost Estimation
===================
Estimate token usage and API cost before running an analysis,
so users can make an informed decision.
"""

# Average characters per token (rough estimate across providers)
CHARS_PER_TOKEN = 4

# Pricing per 1 million tokens (input, output) in USD
PRICE_TABLE = {
    "claude": {"input": 3.00, "output": 15.00, "model": "Claude Sonnet"},
    "openai": {"input": 2.50, "output": 10.00, "model": "GPT-4o"},
    "gemini": {"input": 1.25, "output": 5.00, "model": "Gemini 1.5 Pro"},
}

# Estimated output tokens per analysis type
_OUTPUT_TOKENS = {
    "pain_points": 1500,
    "feature_requests": 1500,
    "competitive_intel": 1500,
    "purchase_intent": 1200,
    "customer_personas": 1800,
    "full_market_research": 3000,
}


def estimate_cost(
    comments: list[dict],
    provider: str,
    analysis_type: str,
) -> dict:
    """Estimate token count and cost for an AI analysis run.

    Returns a dict with:
        - estimated_input_tokens
        - estimated_output_tokens
        - estimated_total_tokens
        - estimated_cost  (float, USD)
        - formatted        (human-readable string)
    """
    import json as _json

    # Estimate input tokens from serialised comment text
    text_chars = sum(
        len(_json.dumps(c, ensure_ascii=False, default=str)) for c in comments
    )
    # Add ~500 tokens for the prompt template itself
    input_tokens = (text_chars // CHARS_PER_TOKEN) + 500
    output_tokens = _OUTPUT_TOKENS.get(analysis_type, 1500)

    pricing = PRICE_TABLE.get(provider, PRICE_TABLE["openai"])
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost

    return {
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_total_tokens": input_tokens + output_tokens,
        "estimated_cost": round(total_cost, 4),
        "formatted": (
            f"~{input_tokens + output_tokens:,} tokens "
            f"(~${total_cost:.4f} on {pricing['model']})"
        ),
    }
