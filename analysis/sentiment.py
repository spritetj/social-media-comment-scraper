"""
Sentiment analysis using VADER — optimized for social media text.
"""

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


def analyze_sentiment(comments: list[dict]) -> dict:
    """Run VADER sentiment analysis on clean comments.

    Returns:
        {
            "distribution": {"positive": float, "neutral": float, "negative": float},
            "avg_compound": float,
            "per_comment": [{"text": str, "compound": float, "label": str}, ...],
            "top_positive": [top 5 most positive comments],
            "top_negative": [top 5 most negative comments],
        }
    """
    if not comments:
        return {}

    analyzer = SentimentIntensityAnalyzer()
    results = []

    for c in comments:
        text = c.get("text", "")
        if not text.strip():
            continue
        scores = analyzer.polarity_scores(text)
        compound = scores["compound"]

        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"

        results.append({
            "text": text,
            "username": c.get("username", ""),
            "compound": compound,
            "label": label,
            "likes": c.get("likes", 0),
        })

    if not results:
        return {}

    total = len(results)
    pos_count = sum(1 for r in results if r["label"] == "positive")
    neu_count = sum(1 for r in results if r["label"] == "neutral")
    neg_count = sum(1 for r in results if r["label"] == "negative")
    avg_compound = sum(r["compound"] for r in results) / total

    # Sort for top positive/negative
    sorted_by_score = sorted(results, key=lambda r: r["compound"])
    top_negative = sorted_by_score[:5]
    top_positive = sorted_by_score[-5:][::-1]

    return {
        "distribution": {
            "positive": round(pos_count / total * 100, 1),
            "neutral": round(neu_count / total * 100, 1),
            "negative": round(neg_count / total * 100, 1),
        },
        "counts": {
            "positive": pos_count,
            "neutral": neu_count,
            "negative": neg_count,
        },
        "avg_compound": round(avg_compound, 3),
        "total_analyzed": total,
        "per_comment": results,
        "top_positive": top_positive,
        "top_negative": top_negative,
    }
