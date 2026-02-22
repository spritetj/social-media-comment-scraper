"""
Analysis pipeline orchestrator — runs all analysis modules and handles errors gracefully.
"""

from analysis.sentiment import analyze_sentiment
from analysis.keywords import analyze_keywords
from analysis.topics import analyze_topics
from analysis.engagement import analyze_engagement
from analysis.temporal import analyze_temporal


def run_full_analysis(clean_comments: list[dict]) -> dict:
    """Run all analysis modules on clean (normalized) comments.

    Each module runs independently — if one fails, others still produce results.

    Returns:
        {
            "sentiment": {...} or None,
            "keywords": {...} or None,
            "topics": {...} or None,
            "engagement": {...} or None,
            "temporal": {...} or None,
            "comment_count": int,
            "errors": [str, ...],
        }
    """
    results = {
        "sentiment": None,
        "keywords": None,
        "topics": None,
        "engagement": None,
        "temporal": None,
        "comment_count": len(clean_comments),
        "errors": [],
    }

    if not clean_comments or len(clean_comments) < 10:
        results["errors"].append("Need at least 10 comments for analysis")
        return results

    # Sentiment
    try:
        results["sentiment"] = analyze_sentiment(clean_comments)
    except Exception as e:
        results["errors"].append(f"Sentiment analysis failed: {e}")

    # Keywords
    try:
        results["keywords"] = analyze_keywords(clean_comments)
    except Exception as e:
        results["errors"].append(f"Keyword analysis failed: {e}")

    # Topics (needs more comments)
    try:
        results["topics"] = analyze_topics(clean_comments)
    except Exception as e:
        results["errors"].append(f"Topic analysis failed: {e}")

    # Engagement
    try:
        results["engagement"] = analyze_engagement(clean_comments)
    except Exception as e:
        results["errors"].append(f"Engagement analysis failed: {e}")

    # Temporal
    try:
        results["temporal"] = analyze_temporal(clean_comments)
    except Exception as e:
        results["errors"].append(f"Temporal analysis failed: {e}")

    return results
