"""
NotebookLM Response Parser
===========================
Parses NotebookLM's markdown responses into the same dict schemas
that the existing UI renderers (_render_customer_insight(), etc.)
already expect. This is the translation layer between NLM's free-form
markdown and the structured dicts the app uses.
"""

import re
from typing import Any


def parse_sentiment_overview(text: str) -> dict:
    """Parse sentiment overview response into sentiment_overview dict.

    Expected output schema (matches _render_customer_insight):
        {
            "overall": "positive"|"negative"|"neutral"|"mixed",
            "positive_percentage": int,
            "negative_percentage": int,
            "neutral_percentage": int,
            "sentiment_drivers": [str],
            "emotional_themes": [str],
        }
    """
    result = {
        "overall": "mixed",
        "positive_percentage": 0,
        "negative_percentage": 0,
        "neutral_percentage": 0,
        "sentiment_drivers": [],
        "emotional_themes": [],
    }

    # Extract overall sentiment
    overall_match = re.search(
        r"Overall Sentiment\s*\n+\s*\[?\s*(positive|negative|neutral|mixed)",
        text, re.IGNORECASE,
    )
    if overall_match:
        result["overall"] = overall_match.group(1).lower()

    # Extract percentages
    for label, key in [
        ("Positive", "positive_percentage"),
        ("Negative", "negative_percentage"),
        ("Neutral", "neutral_percentage"),
    ]:
        pct_match = re.search(
            rf"{label}\s*:\s*\[?\s*(\d+(?:\.\d+)?)\s*\]?\s*%",
            text, re.IGNORECASE,
        )
        if pct_match:
            result[key] = int(float(pct_match.group(1)))

    # Extract sentiment drivers
    drivers = []
    # Positive drivers
    pos_section = re.search(
        r"Positive Drivers?\s*\n((?:\s*[-*]\s*.+\n?)+)", text, re.IGNORECASE
    )
    if pos_section:
        for line in pos_section.group(1).strip().split("\n"):
            cleaned = re.sub(r"^\s*[-*]\s*", "", line).strip()
            if cleaned:
                drivers.append(f"Positive: {cleaned}")

    # Negative drivers
    neg_section = re.search(
        r"Negative Drivers?\s*\n((?:\s*[-*]\s*.+\n?)+)", text, re.IGNORECASE
    )
    if neg_section:
        for line in neg_section.group(1).strip().split("\n"):
            cleaned = re.sub(r"^\s*[-*]\s*", "", line).strip()
            if cleaned:
                drivers.append(f"Negative: {cleaned}")

    if not drivers:
        # Fallback: look for generic "Sentiment Drivers" section
        drv_section = re.search(
            r"Sentiment Drivers?\s*\n((?:\s*[-*]\s*.+\n?)+)", text, re.IGNORECASE
        )
        if drv_section:
            for line in drv_section.group(1).strip().split("\n"):
                cleaned = re.sub(r"^\s*[-*]\s*", "", line).strip()
                if cleaned:
                    drivers.append(cleaned)
    result["sentiment_drivers"] = drivers

    # Extract emotional themes
    themes_section = re.search(
        r"Emotional Themes?\s*\n((?:\s*[-*]\s*.+\n?)+)", text, re.IGNORECASE
    )
    if themes_section:
        for line in themes_section.group(1).strip().split("\n"):
            cleaned = re.sub(r"^\s*[-*]\s*", "", line).strip()
            if cleaned:
                result["emotional_themes"].append(cleaned)

    return result


def parse_aspects(text: str) -> tuple[dict, list]:
    """Parse aspects analysis response.

    Returns:
        (aspect_sentiment, content_themes)

    aspect_sentiment schema (matches tag_summary["aspect_sentiment"]):
        {"aspect_name": {"positive": N, "neutral": N, "negative": N}}

    content_themes schema (matches customer_insight["content_themes"]):
        [{"theme": str, "frequency": int, "description": str, "notable_quotes": [str]}]
    """
    aspect_sentiment = {}
    content_themes = []

    # Parse aspect blocks: ### N. [Name]
    aspect_blocks = re.findall(
        r"###\s*\d+\.\s*(.+?)(?=\n###\s*\d+\.|\n##\s|\Z)",
        text, re.DOTALL,
    )

    for block in aspect_blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        aspect_name = lines[0].strip().rstrip("*").strip()
        if not aspect_name:
            continue

        counts = {"positive": 0, "neutral": 0, "negative": 0}

        for line in lines[1:]:
            # Parse "Positive: N | Neutral: N | Negative: N"
            multi_match = re.search(
                r"Positive:\s*\[?(\d+)\]?\s*\|\s*Neutral:\s*\[?(\d+)\]?\s*\|\s*Negative:\s*\[?(\d+)\]?",
                line, re.IGNORECASE,
            )
            if multi_match:
                counts["positive"] = int(multi_match.group(1))
                counts["neutral"] = int(multi_match.group(2))
                counts["negative"] = int(multi_match.group(3))
                break

            # Single line: "- Positive: N"
            for sent in ["positive", "neutral", "negative"]:
                single_match = re.search(
                    rf"{sent}\s*:\s*\[?(\d+)\]?", line, re.IGNORECASE
                )
                if single_match:
                    counts[sent] = int(single_match.group(1))

        # Only add if we got some counts
        total = sum(counts.values())
        if total > 0:
            aspect_sentiment[aspect_name.lower()] = counts

    # Parse content themes section
    theme_section = re.search(
        r"Content Themes?\s*\n(.*)", text, re.DOTALL | re.IGNORECASE
    )
    if theme_section:
        theme_text = theme_section.group(1)
        theme_blocks = re.findall(
            r"###\s*Theme:\s*(.+?)(?=\n###\s*Theme:|\Z)",
            theme_text, re.DOTALL,
        )
        for block in theme_blocks:
            lines = block.strip().split("\n")
            if not lines:
                continue
            theme_name = lines[0].strip()
            theme_data: dict[str, Any] = {
                "theme": theme_name,
                "frequency": 0,
                "description": "",
                "notable_quotes": [],
            }
            for line in lines[1:]:
                freq_match = re.search(r"Frequency:\s*\[?(\d+)\]?", line, re.IGNORECASE)
                if freq_match:
                    theme_data["frequency"] = int(freq_match.group(1))
                desc_match = re.search(r"Description:\s*(.+)", line, re.IGNORECASE)
                if desc_match:
                    theme_data["description"] = desc_match.group(1).strip()
                quote_match = re.search(r"Notable quote:\s*[\"'](.+?)[\"']", line, re.IGNORECASE)
                if quote_match:
                    theme_data["notable_quotes"].append(quote_match.group(1))
                # Also catch "- "quoted text""
                inline_quote = re.search(r"^\s*[-*]\s*[\"'](.+?)[\"']", line)
                if inline_quote:
                    theme_data["notable_quotes"].append(inline_quote.group(1))
            content_themes.append(theme_data)

    return aspect_sentiment, content_themes


def parse_key_findings(text: str) -> tuple[list, dict, str]:
    """Parse key findings and audience profile response.

    Returns:
        (key_findings, audience_profile, executive_summary)

    key_findings schema:
        [{"finding": str, "evidence": str, "business_impact": str}]

    audience_profile schema:
        {"primary_demographics": str, "psychographics": str,
         "knowledge_level": str, "engagement_style": str}
    """
    key_findings = []
    audience_profile = {
        "primary_demographics": "",
        "psychographics": "",
        "knowledge_level": "",
        "engagement_style": "",
    }
    executive_summary = ""

    # Parse key findings blocks
    finding_blocks = re.findall(
        r"###\s*Finding\s*\d+:\s*(.+?)(?=\n###\s*Finding|\n##\s|\Z)",
        text, re.DOTALL,
    )
    for block in finding_blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue
        finding = {
            "finding": lines[0].strip(),
            "evidence": "",
            "business_impact": "",
        }
        for line in lines[1:]:
            ev_match = re.search(r"Evidence:\s*(.+)", line, re.IGNORECASE)
            if ev_match:
                finding["evidence"] = ev_match.group(1).strip()
            bi_match = re.search(r"Business Impact:\s*(.+)", line, re.IGNORECASE)
            if bi_match:
                finding["business_impact"] = bi_match.group(1).strip()
        key_findings.append(finding)

    # Parse audience profile
    for field, pattern in [
        ("primary_demographics", r"Primary Demographics?\s*\n\s*(.+?)(?=\n###|\n##|\Z)"),
        ("psychographics", r"Psychographics?\s*\n\s*(.+?)(?=\n###|\n##|\Z)"),
        ("knowledge_level", r"Knowledge Level\s*\n\s*(.+?)(?=\n###|\n##|\Z)"),
        ("engagement_style", r"Engagement Style\s*\n\s*(.+?)(?=\n###|\n##|\Z)"),
    ]:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            # Get first non-empty line or paragraph
            content = match.group(1).strip()
            # Take first paragraph
            first_para = content.split("\n\n")[0].strip()
            # Clean up bullet markers
            first_para = re.sub(r"^\s*[-*]\s*", "", first_para)
            audience_profile[field] = first_para

    # Parse executive summary
    summary_match = re.search(
        r"Executive Summary\s*\n\s*(.+?)(?=\n##|\Z)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if summary_match:
        executive_summary = summary_match.group(1).strip()
        # Clean up markdown formatting
        executive_summary = re.sub(r"\[|\]", "", executive_summary)

    return key_findings, audience_profile, executive_summary


def parse_recommendations(text: str) -> tuple[list, list, list]:
    """Parse recommendations, opportunities, and risks.

    Returns:
        (recommendations, opportunities, risks)

    recommendations schema:
        [{"priority": str, "recommendation": str, "rationale": str, "expected_outcome": str}]

    opportunities schema:
        [{"opportunity": str, "evidence": str, "suggested_action": str}]

    risks schema:
        [{"risk": str, "severity": str, "evidence": str, "mitigation": str}]
    """
    recommendations = []
    opportunities = []
    risks = []

    # Split into sections by ## headers
    # Use a regex that captures the header name for reliable matching
    sections = re.split(r"(?:^|\n)##\s+", text)

    for section in sections:
        # Strip any leftover ## prefix (handles text starting with ##)
        section = re.sub(r"^#+\s*", "", section)
        section_lower = section.strip().lower()

        if section_lower.startswith("actionable recommendation"):
            blocks = re.findall(
                r"###\s*\[(\w+)\]\s*(.+?)(?=\n###|\Z)",
                section, re.DOTALL,
            )
            for priority, block in blocks:
                lines = block.strip().split("\n")
                rec = {
                    "priority": priority.lower(),
                    "recommendation": lines[0].strip() if lines else "",
                    "rationale": "",
                    "expected_outcome": "",
                }
                for line in lines[1:]:
                    rat_match = re.search(r"Rationale:\s*(.+)", line, re.IGNORECASE)
                    if rat_match:
                        rec["rationale"] = rat_match.group(1).strip()
                    exp_match = re.search(r"Expected Outcome:\s*(.+)", line, re.IGNORECASE)
                    if exp_match:
                        rec["expected_outcome"] = exp_match.group(1).strip()
                recommendations.append(rec)

        elif section_lower.startswith("opportunit"):
            opp_blocks = re.findall(
                r"###\s*Opportunity\s*\d*:\s*(.+?)(?=\n###|\Z)",
                section, re.DOTALL,
            )
            for block in opp_blocks:
                lines = block.strip().split("\n")
                opp = {
                    "opportunity": lines[0].strip() if lines else "",
                    "evidence": "",
                    "suggested_action": "",
                }
                for line in lines[1:]:
                    ev_match = re.search(r"Evidence:\s*(.+)", line, re.IGNORECASE)
                    if ev_match:
                        opp["evidence"] = ev_match.group(1).strip()
                    act_match = re.search(r"Suggested Action:\s*(.+)", line, re.IGNORECASE)
                    if act_match:
                        opp["suggested_action"] = act_match.group(1).strip()
                opportunities.append(opp)

        elif section_lower.startswith("risk"):
            risk_blocks = re.findall(
                r"###\s*\[(\w+)\]\s*(?:Risk\s*\d*:\s*)?(.+?)(?=\n###|\Z)",
                section, re.DOTALL,
            )
            for severity, block in risk_blocks:
                lines = block.strip().split("\n")
                risk = {
                    "risk": lines[0].strip() if lines else "",
                    "severity": severity.lower(),
                    "evidence": "",
                    "mitigation": "",
                }
                for line in lines[1:]:
                    ev_match = re.search(r"Evidence:\s*(.+)", line, re.IGNORECASE)
                    if ev_match:
                        risk["evidence"] = ev_match.group(1).strip()
                    mit_match = re.search(r"Mitigation:\s*(.+)", line, re.IGNORECASE)
                    if mit_match:
                        risk["mitigation"] = mit_match.group(1).strip()
                risks.append(risk)

    return recommendations, opportunities, risks


def compose_customer_insight(parsed_results: dict) -> dict:
    """Compose all parsed results into a single customer_insight dict
    matching the schema expected by _render_customer_insight().

    Args:
        parsed_results: Dict with keys matching query IDs, each containing
                        the parsed response data.

    Returns:
        Full customer_insight dict ready for rendering.
    """
    insight: dict[str, Any] = {}

    # From sentiment_overview query
    sentiment_data = parsed_results.get("sentiment_overview")
    if sentiment_data:
        sentiment = parse_sentiment_overview(sentiment_data)
        insight["sentiment_overview"] = sentiment

    # From aspects_analysis query
    aspects_data = parsed_results.get("aspects_analysis")
    if aspects_data:
        aspect_sentiment, content_themes = parse_aspects(aspects_data)
        insight["content_themes"] = content_themes
        # Store aspect_sentiment for heatmap reconstruction
        insight["_aspect_sentiment"] = aspect_sentiment

    # From key_findings_audience query
    findings_data = parsed_results.get("key_findings_audience")
    if findings_data:
        findings, audience, summary = parse_key_findings(findings_data)
        insight["key_findings"] = findings
        insight["audience_profile"] = audience
        insight["executive_summary"] = summary

    # From recommendations_risks query
    recs_data = parsed_results.get("recommendations_risks")
    if recs_data:
        recs, opps, risks = parse_recommendations(recs_data)
        insight["actionable_recommendations"] = recs
        insight["opportunities"] = opps
        insight["risks"] = risks

    return insight


def insight_to_tag_summary(insight: dict) -> dict | None:
    """Extract a tag_summary-compatible dict from NLM insight data.

    This allows the aspect heatmap to work with NLM data.
    Returns a dict matching the schema of aggregate_tags() output.
    """
    aspect_sentiment = insight.get("_aspect_sentiment", {})
    if not aspect_sentiment:
        return None

    # Build sentiment distribution from sentiment_overview
    sentiment_overview = insight.get("sentiment_overview", {})
    pos_pct = sentiment_overview.get("positive_percentage", 0)
    neg_pct = sentiment_overview.get("negative_percentage", 0)
    neu_pct = sentiment_overview.get("neutral_percentage", 0)

    return {
        "sentiment_distribution": {
            "positive": pos_pct,
            "negative": neg_pct,
            "neutral": neu_pct,
        },
        "aspect_sentiment": aspect_sentiment,
        # These are not available from NLM (no per-comment tagging)
        "emotion_distribution": {},
        "intent_distribution": {},
        "urgency_distribution": {},
    }
