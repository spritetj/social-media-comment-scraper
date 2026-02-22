"""
NotebookLM Query Templates
============================
Structured queries for corpus-level analysis via NotebookLM.
Each query includes strict format instructions for reliable parsing.

Typical analysis run: 5-7 queries (vs 25+ API calls for per-comment tagging).
Uses session continuity — same session_id for all queries in one run.
"""


def get_analysis_queries(
    topic: str,
    comment_count: int,
    platforms: list[str],
) -> list[dict]:
    """Build the ordered list of queries for a full analysis run.

    Returns a list of dicts:
        {
            "id": str,          # unique query identifier
            "question": str,    # the actual question to send
            "required": bool,   # always run vs conditional
            "min_comments": int # minimum comments to justify this query
        }
    """
    platforms_str = ", ".join(p.title() for p in platforms)

    queries = [
        {
            "id": "sentiment_overview",
            "required": True,
            "min_comments": 0,
            "question": f"""Analyze all the comments in this notebook about "{topic}" and provide a sentiment overview.

Structure your response EXACTLY like this:

## Overall Sentiment
[State: positive, negative, neutral, or mixed]

## Sentiment Distribution
- Positive: [X]%
- Negative: [Y]%
- Neutral: [Z]%

## Sentiment Drivers
### Positive Drivers
- [What makes people feel positive — be specific]

### Negative Drivers
- [What makes people feel negative — be specific]

## Emotional Themes
- [List the dominant emotions: excitement, frustration, curiosity, hope, anger, etc.]

Be precise with percentages based on actual comment analysis. Use specific examples from comments.""",
        },
        {
            "id": "aspects_analysis",
            "required": True,
            "min_comments": 0,
            "question": f"""From all comments about "{topic}", identify the top 15 specific aspects/topics that people discuss.

Structure your response EXACTLY like this:

## Aspects Analysis

### 1. [Aspect Name]
- Total mentions: [N]
- Positive: [N] | Neutral: [N] | Negative: [N]
- Key insight: [One sentence summary]
- Sample quote: "[direct quote]"

### 2. [Aspect Name]
- Total mentions: [N]
- Positive: [N] | Neutral: [N] | Negative: [N]
- Key insight: [One sentence summary]
- Sample quote: "[direct quote]"

[Continue for all 15 aspects, ranked by total mentions]

## Content Themes
List 5-8 major content themes:
### Theme: [Name]
- Frequency: [N] comments
- Description: [What people say about this]
- Notable quote: "[quote]"

Use short English labels for aspect names (e.g., "price", "quality", "customer service", "design").""",
        },
        {
            "id": "key_findings_audience",
            "required": True,
            "min_comments": 0,
            "question": f"""Based on the {comment_count} comments about "{topic}" from {platforms_str}, provide key findings and audience profile.

Structure your response EXACTLY like this:

## Key Findings

### Finding 1: [Clear statement]
- Evidence: [Supporting data or quote]
- Business Impact: [Why this matters]

### Finding 2: [Clear statement]
- Evidence: [Supporting data or quote]
- Business Impact: [Why this matters]

[List 5-8 key findings, prioritize surprising or non-obvious insights]

## Audience Profile
### Primary Demographics
[Who is talking — inferred from language, concerns, context]

### Psychographics
[Values, attitudes, lifestyle indicators]

### Knowledge Level
[How informed/experienced the audience is]

### Engagement Style
[How they interact: asking questions, sharing experiences, debating, etc.]

## Executive Summary
[3-5 sentence overview of the most important findings and their business implications]""",
        },
        {
            "id": "recommendations_risks",
            "required": True,
            "min_comments": 0,
            "question": f"""Based on all comments about "{topic}", provide actionable recommendations, opportunities, and risks.

Structure your response EXACTLY like this:

## Actionable Recommendations

### [HIGH] [Recommendation 1]
- Rationale: [Why, based on data]
- Expected Outcome: [What implementing this achieves]

### [MEDIUM] [Recommendation 2]
- Rationale: [Why]
- Expected Outcome: [What it achieves]

[List 5-7 recommendations with priority HIGH/MEDIUM/LOW]

## Opportunities

### Opportunity 1: [Description]
- Evidence: [What in data suggests this]
- Suggested Action: [How to capitalize]

[List 3-5 opportunities]

## Risks

### [HIGH] Risk 1: [Description]
- Evidence: [What indicates this risk]
- Mitigation: [How to address it]

### [MEDIUM] Risk 2: [Description]
- Evidence: [What indicates this]
- Mitigation: [Suggestion]

[List 3-5 risks with severity HIGH/MEDIUM/LOW]""",
        },
        {
            "id": "pain_points",
            "required": False,
            "min_comments": 50,
            "question": f"""Identify the top pain points and frustrations expressed in comments about "{topic}".

Structure your response EXACTLY like this:

## Pain Points Analysis

### 1. [Pain Point] (Severity: HIGH/MEDIUM/LOW)
- Frequency: [N] comments mention this
- Category: [usability/performance/pricing/support/reliability/missing_feature]
- Impact: [How this affects users]
- Example quotes:
  - "[quote 1]"
  - "[quote 2]"

### 2. [Pain Point] (Severity: HIGH/MEDIUM/LOW)
[Same structure]

[List 8-12 pain points, sorted by severity then frequency]

## Summary
[2-3 sentence summary of top pain points]""",
        },
        {
            "id": "competitive_intel",
            "required": False,
            "min_comments": 30,
            "question": f"""Analyze comments about "{topic}" for any competitor mentions, brand comparisons, or switching behavior.

Structure your response EXACTLY like this:

## Competitor Mentions

### [Competitor Name]
- Mentions: [N]
- Sentiment: [positive/negative/neutral/mixed]
- Advantages cited: [what people say is better about this competitor]
- Disadvantages cited: [what people say is worse]
- Switching reasons: [why people switch to/from]
- Example quote: "[quote]"

[Repeat for each competitor mentioned]

## Market Positioning Gaps
- [Gap 1: description and how it could be exploited]
- [Gap 2: description]

## Market Trends
- [Trend 1 observed in discussions]
- [Trend 2]

If no competitors are mentioned, say so clearly.""",
        },
        {
            "id": "customer_personas",
            "required": False,
            "min_comments": 100,
            "question": f"""Based on the commenting patterns about "{topic}", identify 3-5 distinct customer personas.

Structure your response EXACTLY like this:

## Customer Personas

### Persona 1: [Descriptive Name] (~[X]% of commenters)
- Description: [1-2 sentences]
- Behaviors: [What they do]
- Needs: [What they want]
- Pain Points: [What frustrates them]
- Goals: [What they're trying to achieve]
- Typical quote: "[quote]"
- How to serve them: [Recommendation]

### Persona 2: [Name] (~[X]% of commenters)
[Same structure]

[Continue for all personas]

## Segment Distribution Summary
[Brief overview of how the audience breaks down]

Base personas on actual comment patterns, not assumptions. Percentages should sum to ~100%.""",
        },
    ]

    # Filter by comment count
    return [
        q for q in queries
        if q["required"] or comment_count >= q["min_comments"]
    ]


def get_query_count(comment_count: int) -> int:
    """Estimate how many queries will be used for a given comment count."""
    queries = get_analysis_queries("", comment_count, [])
    return len(queries)
