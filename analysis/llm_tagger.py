"""
LLM Comment Tagger — batch-classify comments using an LLM.

Tags each comment with sentiment, emotion, intent, aspects, and urgency.
Works with Thai, English, and mixed-language content.
"""

import json
import logging

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


def _format_batch(comments: list[dict]) -> str:
    """Format a batch of comments for the tagger prompt."""
    lines = []
    for i, c in enumerate(comments, 1):
        text = c.get("text", "").strip()
        if not text:
            text = "(empty)"
        lines.append(f"{i}. {text}")
    return "\n".join(lines)


def _parse_tags(raw: dict | str, batch_size: int) -> list[dict]:
    """Parse the LLM response into a list of tag dicts.

    Handles both parsed JSON (list) and raw text responses.
    Returns a list of tag dicts matching the batch size.
    """
    default_tag = {
        "sentiment": "neutral",
        "emotion": "neutral",
        "intent": "other",
        "aspects": [],
        "urgency": "none",
    }

    tags = []

    # If already parsed as a list
    if isinstance(raw, list):
        tags = raw
    elif isinstance(raw, dict):
        # Might be wrapped in a key
        for key in ("tags", "comments", "results", "data"):
            if key in raw and isinstance(raw[key], list):
                tags = raw[key]
                break
        if not tags:
            tags = [raw]
    elif isinstance(raw, str):
        # Try to extract JSON array from text
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [ln for ln in lines[1:] if ln.strip() != "```"]
            text = "\n".join(lines).strip()
        start = text.find("[")
        end = text.rfind("]") + 1
        if start != -1 and end > start:
            try:
                tags = json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    # Build result list, filling in defaults for missing entries
    result = []
    for i in range(batch_size):
        tag = dict(default_tag)
        if i < len(tags) and isinstance(tags[i], dict):
            t = tags[i]
            if t.get("sentiment") in ("positive", "negative", "neutral", "mixed"):
                tag["sentiment"] = t["sentiment"]
            if t.get("emotion"):
                tag["emotion"] = t["emotion"]
            if t.get("intent"):
                tag["intent"] = t["intent"]
            if isinstance(t.get("aspects"), list):
                tag["aspects"] = [
                    a for a in t["aspects"]
                    if isinstance(a, dict) and "aspect" in a
                ]
            if t.get("urgency") in ("high", "medium", "low", "none"):
                tag["urgency"] = t["urgency"]
        result.append(tag)

    return result


async def tag_comments(
    comments: list[dict],
    progress_callback=None,
) -> list[dict]:
    """Tag all comments using the LLM in batches.

    Args:
        comments: List of normalized comment dicts (must have "text" key).
        progress_callback: Optional callback for progress updates.

    Returns:
        List of tag dicts, one per comment. Each tag has:
        sentiment, emotion, intent, aspects, urgency.
    """
    from ai.client import LLMClient
    from ai.prompts import COMMENT_TAGGER

    client = LLMClient()
    all_tags: list[dict] = []
    total = len(comments)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(num_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch = comments[start:end]

        if progress_callback:
            progress_callback(
                f"AI tagging comments {start + 1}-{end} of {total}..."
            )

        try:
            formatted = _format_batch(batch)
            prompt = COMMENT_TAGGER.format(comments=formatted)
            raw = await client.analyze(prompt=prompt)
            batch_tags = _parse_tags(raw, len(batch))
        except Exception as e:
            logger.warning("LLM tagger batch %d failed: %s", batch_idx, e)
            # Fall back to neutral defaults for this batch
            batch_tags = [
                {
                    "sentiment": "neutral",
                    "emotion": "neutral",
                    "intent": "other",
                    "aspects": [],
                    "urgency": "none",
                }
                for _ in batch
            ]

        all_tags.extend(batch_tags)

    return all_tags


def merge_tags_into_comments(
    comments: list[dict], tags: list[dict]
) -> list[dict]:
    """Merge tag data into comment dicts (in-place and return).

    Each comment gets new keys: ai_sentiment, ai_emotion, ai_intent,
    ai_aspects, ai_urgency.
    """
    for i, comment in enumerate(comments):
        if i < len(tags):
            tag = tags[i]
            comment["ai_sentiment"] = tag.get("sentiment", "neutral")
            comment["ai_emotion"] = tag.get("emotion", "neutral")
            comment["ai_intent"] = tag.get("intent", "other")
            comment["ai_aspects"] = tag.get("aspects", [])
            comment["ai_urgency"] = tag.get("urgency", "none")
        else:
            comment["ai_sentiment"] = "neutral"
            comment["ai_emotion"] = "neutral"
            comment["ai_intent"] = "other"
            comment["ai_aspects"] = []
            comment["ai_urgency"] = "none"
    return comments


def aggregate_tags(comments: list[dict]) -> dict:
    """Compute aggregate statistics from tagged comments.

    Returns dict with distribution counts for downstream use
    (e.g., enriching the AI insight report prompt).
    """
    from collections import Counter

    sentiment_counts = Counter()
    emotion_counts = Counter()
    intent_counts = Counter()
    aspect_sentiment: dict[str, Counter] = {}
    urgency_counts = Counter()

    for c in comments:
        sentiment_counts[c.get("ai_sentiment", "neutral")] += 1
        emotion_counts[c.get("ai_emotion", "neutral")] += 1
        intent_counts[c.get("ai_intent", "other")] += 1
        urgency_counts[c.get("ai_urgency", "none")] += 1

        for asp in c.get("ai_aspects", []):
            name = asp.get("aspect", "").lower().strip()
            sent = asp.get("sentiment", "neutral")
            if name:
                if name not in aspect_sentiment:
                    aspect_sentiment[name] = Counter()
                aspect_sentiment[name][sent] += 1

    total = len(comments) or 1

    return {
        "sentiment_distribution": {
            k: round(v / total * 100, 1) for k, v in sentiment_counts.most_common()
        },
        "emotion_distribution": {
            k: round(v / total * 100, 1) for k, v in emotion_counts.most_common()
        },
        "intent_distribution": {
            k: round(v / total * 100, 1) for k, v in intent_counts.most_common()
        },
        "urgency_distribution": {
            k: round(v / total * 100, 1) for k, v in urgency_counts.most_common()
        },
        "aspect_sentiment": {
            aspect: dict(counts) for aspect, counts in sorted(
                aspect_sentiment.items(),
                key=lambda x: sum(x[1].values()),
                reverse=True,
            )
        },
        "total_tagged": len(comments),
    }
