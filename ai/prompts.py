"""
Market Research Prompt Templates
=================================
Six analysis types, each producing structured JSON output.
Designed for social-media comment analysis in market research,
competitive intelligence, and customer insight workflows.
"""

import json

# ---------------------------------------------------------------------------
# Analysis type registry
# ---------------------------------------------------------------------------

ANALYSIS_TYPES = {
    "pain_points": "Identify user pain points, frustrations, and complaints",
    "feature_requests": "Extract feature requests and product improvement suggestions",
    "competitive_intel": "Analyze competitor mentions, comparisons, and switching intent",
    "purchase_intent": "Detect buying signals, satisfaction levels, and purchase intent",
    "customer_personas": "Identify distinct customer segments and user personas",
    "full_market_research": "Comprehensive market research report combining all analyses",
    "customer_insight_report": "Customer insight report with audience profile, themes, and recommendations",
}


# ---------------------------------------------------------------------------
# Individual prompt templates
# ---------------------------------------------------------------------------

PAIN_POINTS = """You are a market research analyst specializing in customer pain point analysis.

Analyze the following {comment_count} social media comments about "{topic}" and identify user pain points.

Return ONLY valid JSON matching this exact schema:
{{
  "pain_points": [
    {{
      "issue": "Brief description of the pain point",
      "severity": "high" | "medium" | "low",
      "frequency": <number of comments mentioning this>,
      "category": "usability" | "performance" | "pricing" | "support" | "reliability" | "missing_feature" | "other",
      "example_quotes": ["direct quote 1", "direct quote 2"],
      "impact_summary": "How this affects users"
    }}
  ],
  "summary": "2-3 sentence executive summary of top pain points",
  "total_comments_analyzed": {comment_count},
  "comments_with_pain_points": <number>
}}

Sort pain points by severity (high first), then by frequency (most frequent first).
Only include genuine pain points, not neutral observations.

COMMENTS:
{comments}"""

FEATURE_REQUESTS = """You are a product manager analyzing customer feedback for feature requests.

Analyze the following {comment_count} social media comments about "{topic}" and extract feature requests.

Return ONLY valid JSON matching this exact schema:
{{
  "feature_requests": [
    {{
      "feature": "Description of the requested feature",
      "urgency": "critical" | "high" | "medium" | "low",
      "request_count": <number of comments requesting this>,
      "user_segments": ["segment1", "segment2"],
      "example_quotes": ["direct quote 1", "direct quote 2"],
      "existing_alternatives": "What users currently do instead (if mentioned)",
      "potential_impact": "Expected benefit if implemented"
    }}
  ],
  "summary": "2-3 sentence executive summary of top feature requests",
  "total_comments_analyzed": {comment_count},
  "comments_with_requests": <number>
}}

Sort by urgency (critical first), then by request_count (most requested first).
Only include genuine requests, not general praise or complaints.

COMMENTS:
{comments}"""

COMPETITIVE_INTEL = """You are a competitive intelligence analyst studying market dynamics.

Analyze the following {comment_count} social media comments about "{topic}" for competitive insights.

Return ONLY valid JSON matching this exact schema:
{{
  "competitors": [
    {{
      "name": "Competitor name",
      "mention_count": <number of mentions>,
      "sentiment": "positive" | "negative" | "neutral" | "mixed",
      "switching_reasons": ["reason1", "reason2"],
      "advantages_cited": ["advantage1", "advantage2"],
      "disadvantages_cited": ["disadvantage1", "disadvantage2"],
      "example_quotes": ["direct quote 1", "direct quote 2"]
    }}
  ],
  "positioning_gaps": [
    {{
      "gap": "Description of a positioning or capability gap",
      "opportunity": "How this gap could be exploited"
    }}
  ],
  "market_trends": ["trend1", "trend2"],
  "summary": "2-3 sentence executive summary of competitive landscape",
  "total_comments_analyzed": {comment_count}
}}

Focus on explicit competitor mentions, brand comparisons, and switching behavior.

COMMENTS:
{comments}"""

PURCHASE_INTENT = """You are a sales intelligence analyst detecting purchase signals in customer conversations.

Analyze the following {comment_count} social media comments about "{topic}" for purchase intent signals.

Return ONLY valid JSON matching this exact schema:
{{
  "intent_signals": {{
    "actively_buying": {{
      "count": <number>,
      "examples": ["quote1", "quote2"],
      "details": "Summary of active buyers"
    }},
    "considering": {{
      "count": <number>,
      "examples": ["quote1", "quote2"],
      "details": "Summary of those considering"
    }},
    "satisfied_customers": {{
      "count": <number>,
      "examples": ["quote1", "quote2"],
      "details": "Summary of satisfied users"
    }},
    "dissatisfied_customers": {{
      "count": <number>,
      "examples": ["quote1", "quote2"],
      "details": "Summary of dissatisfied users"
    }},
    "churning": {{
      "count": <number>,
      "examples": ["quote1", "quote2"],
      "details": "Summary of those leaving or threatening to leave"
    }}
  }},
  "funnel_summary": {{
    "total_with_intent": <number>,
    "strongest_signal": "Which intent category is most prevalent",
    "key_drivers": ["driver1", "driver2"],
    "key_blockers": ["blocker1", "blocker2"]
  }},
  "summary": "2-3 sentence executive summary of purchase intent landscape",
  "total_comments_analyzed": {comment_count}
}}

Look for phrases indicating buying intent, satisfaction, dissatisfaction, comparison shopping, and churn risk.

COMMENTS:
{comments}"""

CUSTOMER_PERSONAS = """You are a UX researcher creating data-driven customer personas from real user feedback.

Analyze the following {comment_count} social media comments about "{topic}" to identify distinct customer personas.

Return ONLY valid JSON matching this exact schema:
{{
  "personas": [
    {{
      "name": "Descriptive persona name (e.g., 'Power User Pete', 'Budget-Conscious Beth')",
      "description": "1-2 sentence description of this persona",
      "estimated_percentage": <percentage of comments fitting this persona>,
      "behaviors": ["behavior1", "behavior2", "behavior3"],
      "needs": ["need1", "need2", "need3"],
      "pain_points": ["pain1", "pain2"],
      "goals": ["goal1", "goal2"],
      "typical_quotes": ["quote1", "quote2"],
      "recommended_approach": "How to serve this persona best"
    }}
  ],
  "segment_distribution": {{
    "persona_name_1": <percentage>,
    "persona_name_2": <percentage>
  }},
  "summary": "2-3 sentence executive summary of the customer base composition",
  "total_comments_analyzed": {comment_count}
}}

Identify 3-6 distinct personas. Base them on actual comment patterns, not assumptions.
Percentages should sum to approximately 100.

COMMENTS:
{comments}"""

CUSTOMER_INSIGHT_REPORT = """You are a senior customer insight strategist who transforms raw social media conversations into actionable business intelligence.

Given {comment_count} social media comments about "{topic}" collected from {platforms}, produce a Customer Insight Report that a brand manager or marketing director can act on immediately.

Analyze the comments holistically — look for patterns, contradictions, emerging narratives, and unspoken assumptions.

Return ONLY valid JSON matching this exact schema:
{{
  "executive_summary": "3-5 sentence overview of the most important findings and their business implications",
  "key_findings": [
    {{
      "finding": "Clear statement of the finding",
      "evidence": "Supporting data or quote from comments",
      "business_impact": "Why this matters for the business"
    }}
  ],
  "audience_profile": {{
    "primary_demographics": "Who is talking about this topic (inferred from language, concerns, context)",
    "psychographics": "Values, attitudes, and lifestyle indicators",
    "knowledge_level": "How informed/experienced the audience is with this topic",
    "engagement_style": "How they interact (asking questions, sharing experiences, debating, etc.)"
  }},
  "sentiment_overview": {{
    "overall": "positive" | "negative" | "neutral" | "mixed",
    "positive_percentage": <number>,
    "negative_percentage": <number>,
    "neutral_percentage": <number>,
    "sentiment_drivers": ["What drives positive sentiment", "What drives negative sentiment"],
    "emotional_themes": ["dominant emotions expressed (excitement, frustration, curiosity, etc.)"]
  }},
  "content_themes": [
    {{
      "theme": "Theme name",
      "frequency": <number of comments>,
      "description": "What people are saying about this theme",
      "notable_quotes": ["quote1", "quote2"]
    }}
  ],
  "actionable_recommendations": [
    {{
      "priority": "high" | "medium" | "low",
      "recommendation": "Specific, actionable recommendation",
      "rationale": "Why this recommendation based on the data",
      "expected_outcome": "What implementing this should achieve"
    }}
  ],
  "opportunities": [
    {{
      "opportunity": "Description of the opportunity",
      "evidence": "What in the data suggests this opportunity",
      "suggested_action": "How to capitalize on it"
    }}
  ],
  "risks": [
    {{
      "risk": "Description of the risk or threat",
      "severity": "high" | "medium" | "low",
      "evidence": "What in the data indicates this risk",
      "mitigation": "Suggested way to address it"
    }}
  ]
}}

Ground every finding in actual comment data. Be specific and actionable, not generic.
Prioritize insights that are surprising or non-obvious over expected findings.

COMMENTS:
{comments}"""

COMMENT_TAGGER = """You are a multilingual social media analyst. Classify each comment below.

For EACH comment (identified by its number), return a JSON object with these fields:
- sentiment: "positive" | "negative" | "neutral" | "mixed"
- emotion: "joy" | "anger" | "sadness" | "surprise" | "fear" | "trust" | "anticipation" | "disgust" | "neutral"
- intent: "question" | "complaint" | "praise" | "suggestion" | "experience" | "comparison" | "purchase_intent" | "spam" | "other"
- aspects: array of {{"aspect": "<topic>", "sentiment": "positive" | "negative" | "neutral"}}
- urgency: "high" | "medium" | "low" | "none"

Rules:
- Analyze comments in their ORIGINAL language (Thai, English, mixed, etc.) — do NOT translate.
- Aspects should be auto-discovered from the content (e.g., "price", "taste", "service", "quality", "packaging", "location", "ambiance"). Use short English labels for aspect names.
- If a comment is too short or unclear, use "neutral" for sentiment/emotion, "other" for intent, empty aspects, "none" for urgency.
- Return ONLY a valid JSON array. No explanation, no markdown fences.

Return format — a JSON array where index matches comment number:
[
  {{"id": 1, "sentiment": "positive", "emotion": "joy", "intent": "experience", "aspects": [{{"aspect": "taste", "sentiment": "positive"}}], "urgency": "none"}},
  {{"id": 2, "sentiment": "negative", "emotion": "anger", "intent": "complaint", "aspects": [{{"aspect": "service", "sentiment": "negative"}}, {{"aspect": "price", "sentiment": "negative"}}], "urgency": "medium"}}
]

COMMENTS:
{comments}"""

FULL_MARKET_RESEARCH = """You are a senior market research analyst producing a comprehensive report.

Analyze the following {comment_count} social media comments about "{topic}" and produce a complete market research report.

Return ONLY valid JSON matching this exact schema:
{{
  "executive_summary": "3-5 sentence high-level overview of findings",
  "pain_points": [
    {{
      "issue": "Pain point description",
      "severity": "high" | "medium" | "low",
      "frequency": <count>,
      "category": "usability" | "performance" | "pricing" | "support" | "reliability" | "missing_feature" | "other",
      "example_quotes": ["quote1"]
    }}
  ],
  "feature_requests": [
    {{
      "feature": "Feature description",
      "urgency": "critical" | "high" | "medium" | "low",
      "request_count": <count>,
      "user_segments": ["segment1"]
    }}
  ],
  "competitive_landscape": {{
    "competitors_mentioned": [
      {{
        "name": "Competitor",
        "mention_count": <count>,
        "sentiment": "positive" | "negative" | "neutral" | "mixed"
      }}
    ],
    "positioning_gaps": ["gap1", "gap2"]
  }},
  "purchase_intent": {{
    "actively_buying": <count>,
    "considering": <count>,
    "satisfied": <count>,
    "dissatisfied": <count>,
    "churning": <count>
  }},
  "customer_segments": [
    {{
      "name": "Segment name",
      "estimated_percentage": <percentage>,
      "key_needs": ["need1", "need2"],
      "key_pain_points": ["pain1"]
    }}
  ],
  "recommendations": [
    {{
      "priority": "high" | "medium" | "low",
      "recommendation": "Actionable recommendation",
      "rationale": "Why this matters"
    }}
  ],
  "total_comments_analyzed": {comment_count}
}}

Be thorough but concise.  Ground every finding in actual comment data.
Prioritize actionable insights over observations.

COMMENTS:
{comments}"""


# ---------------------------------------------------------------------------
# Prompt registry
# ---------------------------------------------------------------------------

_PROMPT_MAP = {
    "pain_points": PAIN_POINTS,
    "feature_requests": FEATURE_REQUESTS,
    "competitive_intel": COMPETITIVE_INTEL,
    "purchase_intent": PURCHASE_INTENT,
    "customer_personas": CUSTOMER_PERSONAS,
    "full_market_research": FULL_MARKET_RESEARCH,
    "customer_insight_report": CUSTOMER_INSIGHT_REPORT,
    "comment_tagger": COMMENT_TAGGER,
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def format_comments_for_prompt(comments: list[dict]) -> str:
    """Format a list of normalised comment dicts into a compact text block
    suitable for inclusion in an LLM prompt.

    Expects dicts with at least a ``text`` key (as produced by
    ``utils.schema.to_clean``).  Username, likes, date, and post/video
    caption (content_title) are included when available for richer context.
    Comments are grouped by content_title so the LLM can see which
    post/video each comment belongs to.
    """
    # Group by content_title for context
    by_content: dict[str, list[dict]] = {}
    for c in comments:
        ct = c.get("content_title", "").strip() or ""
        by_content.setdefault(ct, []).append(c)

    lines: list[str] = []
    i = 0
    for content_title, group in by_content.items():
        if content_title:
            lines.append(f"\n[Post/Video: \"{content_title[:200]}\"]")
        for c in group:
            text = c.get("text", "").strip()
            if not text:
                continue
            i += 1
            username = c.get("username", "Anonymous")
            likes = c.get("likes", 0)
            date = c.get("date", "")
            is_reply = c.get("is_reply", False)
            prefix = "  [reply] " if is_reply else ""
            meta_parts = []
            if likes:
                meta_parts.append(f"{likes} likes")
            if date:
                meta_parts.append(str(date))
            meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
            lines.append(f"{i}. {prefix}@{username}{meta}: {text}")
    return "\n".join(lines)


def get_prompt(analysis_type: str, comments: list[dict], topic: str = "") -> str:
    """Build the full prompt string for a given analysis type.

    Parameters
    ----------
    analysis_type : str
        One of the keys in ``ANALYSIS_TYPES``.
    comments : list[dict]
        Normalised comment dicts (clean schema).
    topic : str, optional
        Product, brand, or topic name for context.

    Returns
    -------
    str
        The fully formatted prompt ready to send to an LLM.
    """
    template = _PROMPT_MAP.get(analysis_type)
    if template is None:
        available = ", ".join(_PROMPT_MAP.keys())
        raise ValueError(
            f"Unknown analysis type '{analysis_type}'. "
            f"Available types: {available}"
        )

    formatted_comments = format_comments_for_prompt(comments)
    comment_count = len(comments)
    topic = topic or "general discussion"

    return template.format(
        comment_count=comment_count,
        topic=topic,
        comments=formatted_comments,
    )
