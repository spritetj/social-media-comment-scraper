"""
Intelligent Query Builder v2 — Thai-Aware Search Strategy Engine.

Given a user's question/objective (Thai, English, or mixed), intelligently
decompose it into diverse Google search queries that maximize URL discovery
across YouTube, TikTok, Facebook, and Instagram.

Works with or without an LLM key:
  - LLM path:  LLM generates actual per-platform query strings
  - Rule-based: 3-layer generation (dork, natural, broad) per platform

Returns IntelligentQueryResult with per-platform queries + relevance_keywords.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from search.thai_nlp import (
    extract_meaningful_thai_words,
    get_thai_transliterations,
    segment_thai,
)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SearchStrategy:
    brand_entity: str = ""                         # "yoguruto"
    brand_variants: list[str] = field(default_factory=list)  # ["Yoguruto", "YOGURUTO"]
    thai_transliterations: list[str] = field(default_factory=list)  # ["โยกุรุโตะ"]
    intent: str = "general"                        # trend_analysis|review|problem|...
    research_objective: str = ""                   # "Why yoguruto is trending"
    date_filter: str = ""                          # "after:2025-01-01" or ""
    original_input: str = ""


@dataclass
class IntelligentQueryResult:
    queries: dict[str, list[str]] = field(default_factory=dict)
    relevance_keywords: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Intent keywords & angles
# ---------------------------------------------------------------------------

_INTENT_KEYWORDS = {
    "trend_analysis": {
        "th": ["กระแส", "ดัง", "เทรนด์", "ไวรัล", "ฮิต", "ฟีเวอร์",
               "ตื่นเต้น", "ฮือฮา", "พูดถึง", "แห่", "บูม", "ป๊อปปูล่า"],
        "en": ["trend", "trending", "viral", "hype", "popular", "buzz",
               "excited", "excitement", "sensation", "boom"],
    },
    "review": {
        "th": ["รีวิว", "ลอง", "ใช้", "เทียบ", "เปรียบ", "ดีไหม",
               "ประสบการณ์", "ลองกิน", "ลองใช้", "คุ้มไหม"],
        "en": ["review", "honest", "experience", "comparison", "worth",
               "tried", "testing"],
    },
    "problem": {
        "th": ["ปัญหา", "แก้", "เสีย", "พัง", "บัค", "ข้อเสีย",
               "ผิดหวัง", "ระวัง", "ไม่ดี", "แย่"],
        "en": ["problem", "issue", "bug", "fix", "broken", "complaint",
               "disappointed", "warning"],
    },
    "purchase": {
        "th": ["ซื้อ", "ราคา", "ถูก", "แพง", "โปร", "ส่วนลด", "คุ้ม",
               "ขาย", "สินค้า", "น่าซื้อ", "ตลาด", "โอกาส"],
        "en": ["buy", "price", "cheap", "discount", "deal", "worth",
               "sell", "product", "market", "opportunity"],
    },
    "how_to": {
        "th": ["วิธี", "ยังไง", "อย่างไร", "ขั้นตอน", "สอน"],
        "en": ["how", "guide", "tutorial", "setup", "install", "step"],
    },
    "opinion": {
        "th": ["คิดยังไง", "ความเห็น", "ดีไหม", "ชอบ", "แนะนำ"],
        "en": ["opinion", "think", "recommend", "thoughts", "worth it"],
    },
}

# Natural search templates — how Thai people actually search
_NATURAL_TEMPLATES = {
    "trend_analysis": {
        "th": [
            "{brand} กระแส",
            "{brand} ทำไมถึงดัง",
            "{brand} ดัง {year}",
            "{brand} ไวรัล",
            "{brand} ตื่นเต้น",
            "{brand} ฮือฮา",
            "{brand} ฮิต {year}",
        ],
        "en": [
            "{brand} viral",
            "{brand} trending",
            "{brand} hype {year}",
            "{brand} excitement",
        ],
    },
    "review": {
        "th": [
            "{brand} รีวิว",
            "{brand} ดีไหม",
            "{brand} คุ้มไหม",
            "{brand} ข้อดีข้อเสีย",
        ],
        "en": [
            "{brand} review",
            "{brand} honest review",
            "{brand} worth it",
        ],
    },
    "problem": {
        "th": [
            "{brand} ปัญหา",
            "{brand} ข้อเสีย",
            "{brand} ไม่ดี",
        ],
        "en": [
            "{brand} problem",
            "{brand} issue",
            "{brand} complaint",
        ],
    },
    "purchase": {
        "th": [
            "{brand} ราคา",
            "{brand} ซื้อที่ไหน",
            "{brand} คุ้มไหม",
        ],
        "en": [
            "{brand} price",
            "{brand} where to buy",
            "{brand} deal",
        ],
    },
    "how_to": {
        "th": [
            "{brand} วิธีใช้",
            "{brand} สอน",
            "{brand} ขั้นตอน",
        ],
        "en": [
            "{brand} how to",
            "{brand} tutorial",
            "{brand} guide",
        ],
    },
    "opinion": {
        "th": [
            "{brand} ความเห็น",
            "{brand} คิดยังไง",
            "{brand} แนะนำ",
        ],
        "en": [
            "{brand} opinion",
            "{brand} recommend",
        ],
    },
    "general": {
        "th": [
            "{brand} รีวิว",
            "{brand} ประสบการณ์",
        ],
        "en": [
            "{brand} review",
            "{brand} experience",
        ],
    },
}


# Platform URL patterns for dork queries
_PLATFORM_SITES = {
    "youtube": {
        "main": "youtube.com",
        "shorts": "youtube.com/shorts",
    },
    "tiktok": {
        "main": "tiktok.com",
    },
    "facebook": {
        "main": "facebook.com",
    },
    "instagram": {
        "main": "instagram.com",
        "reels": "instagram.com/reel/",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def build_intelligent_queries(
    user_input: str,
    platforms: list[str] | None = None,
    date_range: str = "any",
    max_queries_per_platform: int = 20,
    progress_callback=None,
) -> IntelligentQueryResult:
    """Build intelligent search queries from a user's natural-language input.

    Returns IntelligentQueryResult with:
      - .queries: {"youtube": [q1, q2, ...], "tiktok": [...], ...}
      - .relevance_keywords: ["yoguruto", "โยกุรุโตะ"] for result filtering
    """
    if platforms is None:
        platforms = ["youtube", "tiktok", "facebook", "instagram"]

    text = user_input.strip()

    # Fast path: simple topic without LLM → delegate to original builder
    if _is_simple_topic(text) and not _has_llm_configured():
        from search.query_builder import build_queries

        queries = build_queries(text, platforms, date_range)
        # Extract individual words as relevance keywords (not the full phrase)
        en_words = re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", text)
        en_stop = {"the", "and", "for", "how", "why", "what", "this", "that",
                    "from", "with", "about", "does", "not", "but", "are", "was"}
        brand_variants = [w for w in en_words if w.lower() not in en_stop]
        thai_words = extract_meaningful_thai_words(text)
        return IntelligentQueryResult(
            queries=queries,
            relevance_keywords=_build_relevance_keywords(
                brand_variants[0] if brand_variants else (thai_words[0] if thai_words else text),
                brand_variants,
                thai_words,
            ),
        )

    if progress_callback:
        progress_callback("Analyzing your question...")

    # Try LLM path first, then rule-based fallback
    if _has_llm_configured():
        try:
            result = await _strategize_with_llm(
                text, platforms, date_range, max_queries_per_platform,
            )
            if progress_callback:
                total = sum(len(v) for v in result.queries.values())
                progress_callback(
                    f"Generated {total} search queries across {len(result.queries)} platforms (LLM)"
                )
            return result
        except Exception:
            pass  # Fall through to rule-based

    # Rule-based path
    strategy = _build_search_strategy(text, date_range)

    if progress_callback:
        progress_callback(
            f"Brand: {strategy.brand_entity} | Intent: {strategy.intent}"
            + (f" | Thai: {', '.join(strategy.thai_transliterations[:2])}"
               if strategy.thai_transliterations else "")
        )

    queries = _generate_rule_based_queries(
        strategy, platforms, max_queries_per_platform,
    )
    relevance_keywords = _build_relevance_keywords(
        strategy.brand_entity,
        strategy.brand_variants,
        strategy.thai_transliterations,
    )

    if progress_callback:
        total = sum(len(v) for v in queries.values())
        progress_callback(f"Generated {total} search queries across {len(queries)} platforms")

    return IntelligentQueryResult(
        queries=queries,
        relevance_keywords=relevance_keywords,
    )


# ---------------------------------------------------------------------------
# Simple-topic detection
# ---------------------------------------------------------------------------


def _is_simple_topic(text: str) -> bool:
    """Return True if input looks like a simple topic (not a question).

    Uses pythainlp segmentation to correctly count Thai words —
    a sentence like 'เป็นสินค้าที่น่ามาขายในไทยไหม' is many words,
    not one token.
    """
    if "?" in text or "?" in text:
        return False
    # Segment Thai text to get accurate word count
    tokens = segment_thai(text)
    # Filter out whitespace and single-char particles
    meaningful = [t for t in tokens if len(t.strip()) > 1]
    return len(meaningful) <= 3


# ---------------------------------------------------------------------------
# LLM availability
# ---------------------------------------------------------------------------


def _has_llm_configured() -> bool:
    """Check if an LLM provider and API key are available."""
    # 1. Try Streamlit session state
    try:
        import streamlit as st
        provider = st.session_state.get("active_provider")
        if provider:
            keys = st.session_state.get("api_keys", {})
            if keys.get(provider):
                return True
    except Exception:
        pass
    # 2. Fall back to env vars
    import os
    env_vars = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"]
    return any(os.environ.get(v) for v in env_vars)


# ---------------------------------------------------------------------------
# LLM strategist — generates actual query strings per platform
# ---------------------------------------------------------------------------

_STRATEGIST_PROMPT = """You are a Thai social media research strategist. Given a user's research question (Thai, English, or mixed), you must:

1. UNDERSTAND THE INTENT — What is the user really asking? Not just the brand, but the ANGLE:
   - "คนตื่นเต้นอะไรกับ Sushipop" → intent is EXCITEMENT/HYPE, not just "Sushipop"
   - "Yoguruto ดีไหม" → intent is REVIEW/OPINION
   - "ทำไม XX ถึงดัง" → intent is TREND ANALYSIS
   - "XX เป็นสินค้าที่น่ามาขายในไทยไหม" → intent is MARKET VIABILITY

2. GENERATE ANGLE-SPECIFIC QUERIES — Each query should reflect the intent angle:
   - For excitement/hype: use ตื่นเต้น, ฮือฮา, กระแส, ไวรัล, ฮิต, ฟีเวอร์
   - For reviews: use รีวิว, ดีไหม, คุ้มไหม, ข้อดีข้อเสีย, ประสบการณ์
   - For problems: use ปัญหา, ข้อเสีย, ไม่ดี, ผิดหวัง, ระวัง
   - For market viability: use ขาย, ตลาด, โอกาส, คู่แข่ง, กลุ่มเป้าหมาย

3. THINK LIKE A THAI SOCIAL MEDIA USER — Thai users mix Thai and English freely:
   - "Sushipop ฮิตมาก" (mixed Thai+English)
   - "รีวิว Sushipop ลองกินจริง" (Thai frame + English brand)
   - Use colloquial Thai, not formal

ALL search goes through Google, so every query must use site: to target a specific platform.

Return ONLY a JSON object:
{{
  "brand_entity": "main brand/product/topic name",
  "brand_variants": ["variant1", "variant2"],
  "thai_transliterations": ["Thai-script transliterations of English brand name"],
  "intent": "one of: trend_analysis, review, problem, purchase, how_to, opinion, excitement, market_viability, general",
  "intent_keywords_th": ["Thai keywords that capture the user's angle/intent"],
  "intent_keywords_en": ["English keywords for the same angle"],
  "research_objective": "one-sentence summary of what the user really wants to find",
  "date_filter": "after:YYYY-MM-DD if time-sensitive, otherwise empty string",
  "platform_queries": {{
    "youtube": ["query1", "query2", ...],
    "tiktok": ["query1", "query2", ...],
    "facebook": ["query1", "query2", ...],
    "instagram": ["query1", "query2", ...]
  }}
}}

Rules for generating queries:
1. Every query MUST include site: targeting exactly one platform
2. Generate 3 types per platform:
   - DORK: site:platform.com "brand" intent_keyword — exact brand + angle
   - NATURAL: site:platform.com brand Thai-colloquial-phrase — how people actually search
   - BROAD: "brand" OR "thai_variant" site:platform.com angle — wider net
3. Include Thai transliterations as query variants
4. Use "quotes" around brand names, after: for time-sensitive queries, OR for variants
5. For YouTube, also include site:youtube.com/shorts queries
6. For Instagram, also include site:instagram.com/reel/ queries
7. Generate {max_q} queries per platform
8. CRITICAL: Queries must reflect the USER'S ANGLE, not generic searches. If the user asks about excitement, every query should seek excitement-related content.

Platforms to generate for: {platforms}"""


async def _strategize_with_llm(
    user_input: str,
    platforms: list[str],
    date_range: str,
    max_queries_per_platform: int,
) -> IntelligentQueryResult:
    """Use LLM to generate per-platform query strings."""
    from ai.client import LLMClient

    prompt = _STRATEGIST_PROMPT.format(
        max_q=max_queries_per_platform,
        platforms=", ".join(platforms),
    )

    client = LLMClient()
    result = await client.analyze(
        prompt=prompt,
        data=f"User input: {user_input}",
    )

    if isinstance(result, str):
        match = re.search(r"\{[\s\S]*\}", result)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError("LLM response contained no JSON")
    elif isinstance(result, dict):
        data = result
    else:
        raise ValueError("Unexpected LLM response type")

    # Extract platform queries
    platform_queries = data.get("platform_queries", {})
    queries: dict[str, list[str]] = {}
    for platform in platforms:
        pq = platform_queries.get(platform, [])
        if isinstance(pq, list):
            queries[platform] = pq[:max_queries_per_platform]

    # Build relevance keywords: brand + variants + Thai transliterations
    brand = data.get("brand_entity", user_input)
    brand_variants = data.get("brand_variants", [])
    thai_trans = data.get("thai_transliterations", [])
    relevance_keywords = _build_relevance_keywords(brand, brand_variants, thai_trans)

    # Apply date filter from date_range param if LLM didn't include one
    date_filter = data.get("date_filter", "")
    if not date_filter:
        date_filter = _build_date_filter(date_range, None)
    if date_filter:
        for platform in queries:
            queries[platform] = [
                f"{q} {date_filter}" if date_filter not in q else q
                for q in queries[platform]
            ]

    return IntelligentQueryResult(queries=queries, relevance_keywords=relevance_keywords)


# ---------------------------------------------------------------------------
# Rule-based strategy builder
# ---------------------------------------------------------------------------


def _build_search_strategy(user_input: str, date_range: str) -> SearchStrategy:
    """Build a SearchStrategy from user input without LLM."""
    text = user_input.strip()

    # Extract English words (brand/entity candidates)
    en_words = re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", text)
    en_stopwords = {
        "the", "and", "for", "how", "why", "what", "this", "that",
        "from", "with", "about", "does", "not", "but", "are", "was",
        "can", "will", "has", "have", "had", "been", "being", "would",
        "should", "could", "may", "might", "shall", "its", "their",
    }

    # Brand entity: first meaningful English word, or Thai proper noun
    brand_candidates = [w for w in en_words if w.lower() not in en_stopwords]
    if brand_candidates:
        brand_entity = brand_candidates[0]
    else:
        # Use meaningful Thai words as brand
        thai_words = extract_meaningful_thai_words(text)
        brand_entity = thai_words[0] if thai_words else text

    # Brand variants (case variations)
    brand_variants = list(dict.fromkeys([
        brand_entity,
        brand_entity.lower(),
        brand_entity.upper(),
        brand_entity.capitalize(),
    ]))

    # Thai transliterations of English brand
    thai_trans: list[str] = []
    if brand_entity and re.match(r"[A-Za-z]", brand_entity):
        thai_trans = get_thai_transliterations(brand_entity)

    # Detect intent
    thai_runs = re.findall(r"[\u0E00-\u0E7F]+", text)
    intent = _detect_intent(text, thai_runs, en_words)

    # Date filter
    date_filter = _build_date_filter(date_range, "recent" if intent == "trend_analysis" else None)

    return SearchStrategy(
        brand_entity=brand_entity,
        brand_variants=brand_variants,
        thai_transliterations=thai_trans,
        intent=intent,
        research_objective=text,
        date_filter=date_filter,
        original_input=text,
    )


def _detect_intent(text: str, thai_runs: list[str], en_words: list[str]) -> str:
    """Detect search intent from keywords."""
    combined = text.lower()
    scores: dict[str, int] = {}

    for intent_name, keyword_map in _INTENT_KEYWORDS.items():
        score = 0
        for th_kw in keyword_map["th"]:
            if th_kw in combined:
                score += 2
        for en_kw in keyword_map["en"]:
            if en_kw in combined:
                score += 2
        if score > 0:
            scores[intent_name] = score

    if scores:
        return max(scores, key=scores.get)
    return "general"


# ---------------------------------------------------------------------------
# 3-layer rule-based query generation
# ---------------------------------------------------------------------------


def _generate_rule_based_queries(
    strategy: SearchStrategy,
    platforms: list[str],
    max_per_platform: int,
) -> dict[str, list[str]]:
    """Generate queries using 3 layers per platform.

    Layer 1 — Platform dork queries (exact match with site:)
    Layer 2 — Natural queries (how Thai people actually search)
    Layer 3 — Broad discovery (OR queries, intitle:)
    """
    brand = strategy.brand_entity
    if not brand:
        return {}

    year = str(datetime.now().year)
    queries: dict[str, list[str]] = {}

    for platform in platforms:
        sites = _PLATFORM_SITES.get(platform)
        if not sites:
            continue

        pq: list[str] = []
        main_site = sites["main"]

        # === Layer 1: Platform dork queries ===

        # Brand exact match
        pq.append(f'site:{main_site} "{brand}"')

        # Thai transliteration exact match
        for thai in strategy.thai_transliterations:
            pq.append(f'site:{main_site} "{thai}"')

        # Brand variants (case variants that differ from primary)
        for variant in strategy.brand_variants:
            q = f'site:{main_site} "{variant}"'
            if q not in pq:
                pq.append(q)

        # Brand + intent angle (Thai)
        intent_templates = _NATURAL_TEMPLATES.get(strategy.intent, _NATURAL_TEMPLATES["general"])
        for tmpl in intent_templates.get("th", [])[:2]:
            angle = tmpl.replace("{brand}", "").replace("{year}", year).strip()
            if angle:
                pq.append(f'site:{main_site} "{brand}" {angle}')

        # Brand + intent angle (English)
        for tmpl in intent_templates.get("en", [])[:1]:
            angle = tmpl.replace("{brand}", "").replace("{year}", year).strip()
            if angle:
                pq.append(f'site:{main_site} "{brand}" {angle}')

        # Alt URLs (shorts, reels)
        alt_keys = [k for k in sites if k != "main"]
        for alt in alt_keys:
            pq.append(f'site:{sites[alt]} "{brand}"')

        # === Layer 2: Natural queries (how Thai people search) ===

        for tmpl in intent_templates.get("th", []):
            natural = tmpl.format(brand=brand, year=year)
            pq.append(f"site:{main_site} {natural}")

        for tmpl in intent_templates.get("en", []):
            natural = tmpl.format(brand=brand, year=year)
            pq.append(f"site:{main_site} {natural}")

        # Natural queries with Thai transliterations
        for thai in strategy.thai_transliterations[:1]:
            for tmpl in intent_templates.get("th", [])[:2]:
                natural = tmpl.format(brand=thai, year=year)
                pq.append(f"site:{main_site} {natural}")

        # === Layer 3: Broad discovery ===

        # OR query combining brand + Thai transliteration
        if strategy.thai_transliterations:
            or_parts = f'"{brand}"'
            for thai in strategy.thai_transliterations:
                or_parts += f' OR "{thai}"'
            pq.append(f"{or_parts} site:{main_site}")

        # intitle: for stronger relevance signal
        pq.append(f'intitle:"{brand}" site:{main_site}')

        # Unquoted broad match
        pq.append(f"site:{main_site} {brand}")

        # === Apply date filter & deduplicate ===
        date_filter = strategy.date_filter
        if date_filter:
            pq = [
                f"{q} {date_filter}" if date_filter not in q else q
                for q in pq
            ]

        # Deduplicate preserving order, then cap
        seen: set[str] = set()
        deduped: list[str] = []
        for q in pq:
            if q not in seen:
                seen.add(q)
                deduped.append(q)
        queries[platform] = deduped[:max_per_platform]

    return queries


# ---------------------------------------------------------------------------
# Relevance keywords builder
# ---------------------------------------------------------------------------


def _build_relevance_keywords(
    brand_entity: str,
    brand_variants: list[str],
    thai_transliterations: list[str],
) -> list[str]:
    """Build a list of keywords for result relevance filtering.

    Includes the brand, its variants, and Thai transliterations
    so that results matching any variant are kept.
    """
    keywords: list[str] = []
    seen: set[str] = set()

    for word in [brand_entity] + brand_variants + thai_transliterations:
        if not word:
            continue
        lower = word.lower()
        if lower not in seen:
            seen.add(lower)
            keywords.append(lower)

    return keywords


# ---------------------------------------------------------------------------
# Date filter helper
# ---------------------------------------------------------------------------


def _build_date_filter(date_range: str, date_hint: str | None = None) -> str:
    """Build a Google date filter string."""
    if date_range == "any" and date_hint != "recent":
        return ""

    now = datetime.now()
    if date_range == "week":
        after = now - timedelta(days=7)
    elif date_range == "month":
        after = now - timedelta(days=30)
    elif date_range == "year":
        after = now - timedelta(days=365)
    elif date_hint == "recent":
        after = now - timedelta(days=30)
    else:
        return ""

    return f"after:{after.strftime('%Y-%m-%d')}"
