"""Tests for NotebookLM integration components."""

import pytest


# ═══════════════════════════════════════════════════════════════════
# Tests for ai/notebooklm_parser.py
# ═══════════════════════════════════════════════════════════════════


class TestParseSentimentOverview:
    def test_basic_parse(self):
        from ai.notebooklm_parser import parse_sentiment_overview

        text = """## Overall Sentiment
mixed

## Sentiment Distribution
- Positive: 45%
- Negative: 30%
- Neutral: 25%

## Sentiment Drivers
### Positive Drivers
- Great product quality
- Excellent customer service

### Negative Drivers
- High pricing
- Slow shipping

## Emotional Themes
- excitement
- frustration
- curiosity
"""
        result = parse_sentiment_overview(text)
        assert result["overall"] == "mixed"
        assert result["positive_percentage"] == 45
        assert result["negative_percentage"] == 30
        assert result["neutral_percentage"] == 25
        assert len(result["sentiment_drivers"]) == 4
        assert any("Great product quality" in d for d in result["sentiment_drivers"])
        assert any("High pricing" in d for d in result["sentiment_drivers"])
        assert len(result["emotional_themes"]) == 3

    def test_bracket_format(self):
        from ai.notebooklm_parser import parse_sentiment_overview

        text = """## Overall Sentiment
[positive]

## Sentiment Distribution
- Positive: [60]%
- Negative: [15]%
- Neutral: [25]%
"""
        result = parse_sentiment_overview(text)
        assert result["overall"] == "positive"
        assert result["positive_percentage"] == 60
        assert result["negative_percentage"] == 15
        assert result["neutral_percentage"] == 25

    def test_empty_text(self):
        from ai.notebooklm_parser import parse_sentiment_overview

        result = parse_sentiment_overview("")
        assert result["overall"] == "mixed"
        assert result["positive_percentage"] == 0

    def test_decimal_percentages(self):
        from ai.notebooklm_parser import parse_sentiment_overview

        text = """## Sentiment Distribution
- Positive: 45.7%
- Negative: 30.3%
- Neutral: 24.0%
"""
        result = parse_sentiment_overview(text)
        assert result["positive_percentage"] == 45
        assert result["negative_percentage"] == 30
        assert result["neutral_percentage"] == 24


class TestParseAspects:
    def test_basic_aspects(self):
        from ai.notebooklm_parser import parse_aspects

        text = """## Aspects Analysis

### 1. Price
- Total mentions: 50
- Positive: 10 | Neutral: 15 | Negative: 25
- Key insight: Most people find it expensive
- Sample quote: "Too expensive for what you get"

### 2. Quality
- Total mentions: 40
- Positive: 30 | Neutral: 5 | Negative: 5
- Key insight: Generally praised
- Sample quote: "Great quality material"

## Content Themes
### Theme: Value for Money
- Frequency: 35 comments
- Description: People debate whether the price matches quality
- Notable quote: "worth every penny"
"""
        aspect_sentiment, content_themes = parse_aspects(text)

        assert "price" in aspect_sentiment
        assert aspect_sentiment["price"]["positive"] == 10
        assert aspect_sentiment["price"]["negative"] == 25
        assert "quality" in aspect_sentiment
        assert aspect_sentiment["quality"]["positive"] == 30

        assert len(content_themes) >= 1
        assert content_themes[0]["theme"] == "Value for Money"
        assert content_themes[0]["frequency"] == 35

    def test_empty_text(self):
        from ai.notebooklm_parser import parse_aspects

        aspect_sentiment, content_themes = parse_aspects("")
        assert aspect_sentiment == {}
        assert content_themes == []


class TestParseKeyFindings:
    def test_basic_findings(self):
        from ai.notebooklm_parser import parse_key_findings

        text = """## Key Findings

### Finding 1: Users love the design
- Evidence: 30+ comments praising the look
- Business Impact: Design is a key differentiator

### Finding 2: Price is a barrier
- Evidence: Many compare with cheaper alternatives
- Business Impact: May lose price-sensitive customers

## Audience Profile
### Primary Demographics
Tech-savvy millennials aged 25-35

### Psychographics
Value quality over quantity, brand-conscious

### Knowledge Level
Highly informed about competitors

### Engagement Style
Active debaters who share detailed opinions

## Executive Summary
The product is well-received for its design but faces price resistance. The audience is tech-savvy and brand-conscious.
"""
        findings, audience, summary = parse_key_findings(text)

        assert len(findings) == 2
        assert findings[0]["finding"] == "Users love the design"
        assert "30+" in findings[0]["evidence"]
        assert findings[1]["finding"] == "Price is a barrier"

        assert "millennials" in audience["primary_demographics"].lower() or "25-35" in audience["primary_demographics"]
        assert audience["psychographics"] != ""
        assert audience["knowledge_level"] != ""
        assert audience["engagement_style"] != ""

        assert "design" in summary.lower() or "well-received" in summary.lower()


class TestParseRecommendations:
    def test_basic_recs(self):
        from ai.notebooklm_parser import parse_recommendations

        text = """## Actionable Recommendations

### [HIGH] Launch a mid-tier pricing option
- Rationale: 40% of comments mention price as barrier
- Expected Outcome: Capture price-sensitive segment

### [MEDIUM] Improve mobile experience
- Rationale: Several complaints about mobile UX
- Expected Outcome: Better mobile engagement

## Opportunities

### Opportunity 1: Partner with influencers
- Evidence: Many commenters follow tech influencers
- Suggested Action: Launch influencer campaign

## Risks

### [HIGH] Risk 1: Competitor launching cheaper alternative
- Evidence: Multiple mentions of competitor X's upcoming product
- Mitigation: Highlight unique features in marketing
"""
        recs, opps, risks = parse_recommendations(text)

        assert len(recs) == 2
        assert recs[0]["priority"] == "high"
        assert "pricing" in recs[0]["recommendation"].lower()
        assert recs[1]["priority"] == "medium"

        assert len(opps) >= 1
        assert "influencer" in opps[0]["opportunity"].lower()

        assert len(risks) >= 1
        assert risks[0]["severity"] == "high"


class TestComposeCustomerInsight:
    def test_full_compose(self):
        from ai.notebooklm_parser import compose_customer_insight

        parsed_results = {
            "sentiment_overview": """## Overall Sentiment
positive

## Sentiment Distribution
- Positive: 60%
- Negative: 20%
- Neutral: 20%

## Sentiment Drivers
### Positive Drivers
- Great quality

### Negative Drivers
- High price

## Emotional Themes
- excitement
""",
            "aspects_analysis": """## Aspects Analysis

### 1. Quality
- Positive: 30 | Neutral: 5 | Negative: 5

## Content Themes
### Theme: Product Quality
- Frequency: 40 comments
- Description: Users love the build quality
""",
            "key_findings_audience": """## Key Findings

### Finding 1: Quality praised
- Evidence: 80% positive about quality
- Business Impact: Key selling point

## Audience Profile
### Primary Demographics
Young adults

### Psychographics
Quality-focused

### Knowledge Level
Expert

### Engagement Style
Active

## Executive Summary
Great product with quality focus.
""",
            "recommendations_risks": """## Actionable Recommendations

### [HIGH] Lower price point
- Rationale: Price complaints
- Expected Outcome: More sales

## Opportunities

### Opportunity 1: Premium tier
- Evidence: Willingness to pay for quality
- Suggested Action: Launch premium

## Risks

### [MEDIUM] Competition
- Evidence: Competitor mentions
- Mitigation: Differentiate
""",
        }

        insight = compose_customer_insight(parsed_results)

        # Check all major sections exist
        assert "sentiment_overview" in insight
        assert insight["sentiment_overview"]["overall"] == "positive"
        assert insight["sentiment_overview"]["positive_percentage"] == 60

        assert "content_themes" in insight
        assert len(insight["content_themes"]) >= 1

        assert "key_findings" in insight
        assert len(insight["key_findings"]) >= 1

        assert "audience_profile" in insight
        assert insight["audience_profile"]["primary_demographics"] != ""

        assert "executive_summary" in insight
        assert insight["executive_summary"] != ""

        assert "actionable_recommendations" in insight
        assert len(insight["actionable_recommendations"]) >= 1

        assert "opportunities" in insight
        assert "risks" in insight

        # Check _aspect_sentiment for heatmap
        assert "_aspect_sentiment" in insight
        assert "quality" in insight["_aspect_sentiment"]


class TestInsightToTagSummary:
    def test_conversion(self):
        from ai.notebooklm_parser import insight_to_tag_summary

        insight = {
            "_aspect_sentiment": {
                "price": {"positive": 5, "neutral": 3, "negative": 20},
                "quality": {"positive": 25, "neutral": 5, "negative": 2},
            },
            "sentiment_overview": {
                "positive_percentage": 55,
                "negative_percentage": 25,
                "neutral_percentage": 20,
            },
        }

        tag_summary = insight_to_tag_summary(insight)
        assert tag_summary is not None
        assert tag_summary["aspect_sentiment"]["price"]["negative"] == 20
        assert tag_summary["sentiment_distribution"]["positive"] == 55

    def test_no_aspects(self):
        from ai.notebooklm_parser import insight_to_tag_summary

        insight = {"sentiment_overview": {"positive_percentage": 50}}
        assert insight_to_tag_summary(insight) is None


# ═══════════════════════════════════════════════════════════════════
# Tests for utils/notebooklm_export.py
# ═══════════════════════════════════════════════════════════════════


class TestExportCommentsMarkdown:
    def _make_comments(self, n=5, platform="youtube"):
        return [
            {
                "text": f"Comment {i} about the product",
                "username": f"user{i}",
                "likes": i * 10,
                "date": f"2024-01-{i+1:02d}",
                "platform": platform,
                "is_reply": False,
                "comment_id": f"c{i}",
                "parent_id": "",
                "source_url": f"https://youtube.com/watch?v=test{i}",
            }
            for i in range(n)
        ]

    def test_basic_export(self):
        from utils.notebooklm_export import export_comments_markdown

        comments = self._make_comments(3)
        md = export_comments_markdown(comments, "Test Product")

        assert "# Social Media Comments: Test Product" in md
        assert "Total comments:** 3" in md
        assert "Youtube Comments (3)" in md
        assert "@user0" in md
        assert "Comment 0 about the product" in md

    def test_multi_platform(self):
        from utils.notebooklm_export import export_comments_markdown

        comments = (
            self._make_comments(2, "youtube") +
            self._make_comments(3, "tiktok")
        )
        md = export_comments_markdown(comments, "Multi Test")

        assert "Youtube Comments (2)" in md
        assert "Tiktok Comments (3)" in md
        assert "Total comments:** 5" in md

    def test_empty_comments(self):
        from utils.notebooklm_export import export_comments_markdown

        md = export_comments_markdown([], "Empty")
        assert "No comments collected" in md

    def test_replies_threaded(self):
        from utils.notebooklm_export import export_comments_markdown

        comments = [
            {
                "text": "Top level comment",
                "username": "user1",
                "likes": 10,
                "date": "2024-01-01",
                "platform": "youtube",
                "is_reply": False,
                "comment_id": "c1",
                "parent_id": "",
            },
            {
                "text": "Reply to top level",
                "username": "user2",
                "likes": 5,
                "date": "2024-01-02",
                "platform": "youtube",
                "is_reply": True,
                "comment_id": "c2",
                "parent_id": "c1",
            },
        ]
        md = export_comments_markdown(comments, "Thread Test")

        assert "Top level comment" in md
        assert "[Reply] @user2" in md

    def test_word_count_estimate(self):
        from utils.notebooklm_export import estimate_word_count

        comments = self._make_comments(10)
        count = estimate_word_count(comments)
        assert count > 0
        # Each comment has ~5 words + 10 overhead = ~15 per comment
        assert count >= 100  # 10 * 10 minimum

    def test_split_for_large(self):
        from utils.notebooklm_export import split_for_notebooklm

        # Create many comments to exceed a tiny limit
        comments = self._make_comments(100)
        files = split_for_notebooklm(comments, "Split Test", max_words=50)

        assert len(files) > 1
        for f in files:
            assert "# Social Media Comments:" in f


# ═══════════════════════════════════════════════════════════════════
# Tests for ai/notebooklm_queries.py
# ═══════════════════════════════════════════════════════════════════


class TestQueryTemplates:
    def test_required_queries_always_present(self):
        from ai.notebooklm_queries import get_analysis_queries

        queries = get_analysis_queries("Test", 10, ["youtube"])
        required_ids = {q["id"] for q in queries if q["required"]}

        assert "sentiment_overview" in required_ids
        assert "aspects_analysis" in required_ids
        assert "key_findings_audience" in required_ids
        assert "recommendations_risks" in required_ids

    def test_conditional_queries_for_small_dataset(self):
        from ai.notebooklm_queries import get_analysis_queries

        queries = get_analysis_queries("Test", 10, ["youtube"])
        ids = {q["id"] for q in queries}

        # Should NOT include conditional queries for only 10 comments
        assert "pain_points" not in ids  # needs 50+
        assert "customer_personas" not in ids  # needs 100+

    def test_conditional_queries_for_large_dataset(self):
        from ai.notebooklm_queries import get_analysis_queries

        queries = get_analysis_queries("Test", 200, ["youtube", "tiktok"])
        ids = {q["id"] for q in queries}

        # Should include all queries for 200 comments
        assert "pain_points" in ids
        assert "competitive_intel" in ids
        assert "customer_personas" in ids

    def test_query_count(self):
        from ai.notebooklm_queries import get_query_count

        assert get_query_count(10) == 4  # only required
        assert get_query_count(200) == 7  # all queries

    def test_queries_contain_topic(self):
        from ai.notebooklm_queries import get_analysis_queries

        queries = get_analysis_queries("Tesla Model 3", 50, ["youtube"])
        for q in queries:
            assert "Tesla Model 3" in q["question"]


# ═══════════════════════════════════════════════════════════════════
# Tests for search/pipeline.py — VADER tagging
# ═══════════════════════════════════════════════════════════════════


class TestVaderTags:
    def test_apply_vader_tags(self):
        from search.pipeline import _apply_vader_tags

        comments = [
            {"text": "I absolutely love this product! It's amazing!"},
            {"text": "This is terrible, worst purchase ever."},
            {"text": "The package arrived on Tuesday."},
            {"text": ""},
        ]
        _apply_vader_tags(comments, {})

        assert comments[0]["ai_sentiment"] == "positive"
        assert comments[1]["ai_sentiment"] == "negative"
        # VADER treats "The package arrived on Tuesday" as neutral
        assert comments[2]["ai_sentiment"] == "neutral"
        # Empty text defaults to neutral
        assert comments[3]["ai_sentiment"] == "neutral"

    def test_vader_handles_clearly_negative(self):
        from search.pipeline import _apply_vader_tags

        comments = [
            {"text": "I hate this product, it's awful and broken!"},
            {"text": "Disgusting service, never buying again"},
        ]
        _apply_vader_tags(comments, {})
        assert all(c["ai_sentiment"] == "negative" for c in comments)

    def test_vader_tag_summary(self):
        from search.pipeline import _vader_tag_summary

        comments = [
            {"ai_sentiment": "positive"},
            {"ai_sentiment": "positive"},
            {"ai_sentiment": "negative"},
            {"ai_sentiment": "neutral"},
        ]
        summary = _vader_tag_summary(comments)

        assert summary["sentiment_distribution"]["positive"] == 50.0
        assert summary["sentiment_distribution"]["negative"] == 25.0
        assert summary["sentiment_distribution"]["neutral"] == 25.0
        assert summary["aspect_sentiment"] == {}


# ═══════════════════════════════════════════════════════════════════
# Tests for ai/client.py — NotebookLM provider
# ═══════════════════════════════════════════════════════════════════


class TestClientNotebookLM:
    def test_notebooklm_in_providers(self):
        from ai.client import PROVIDERS
        assert "notebooklm" in PROVIDERS

    def test_notebooklm_analyze_raises(self):
        """NotebookLM should not allow direct analyze() calls."""
        from ai.client import LLMClient

        # Temporarily set provider
        client = LLMClient()
        client.provider = "notebooklm"
        client.api_key = "notebooklm-no-key-needed"

        import asyncio
        with pytest.raises(ValueError, match="corpus-level"):
            asyncio.run(client.analyze("test prompt"))


# ═══════════════════════════════════════════════════════════════════
# Tests for ai/notebooklm_bridge.py — budget tracking
# ═══════════════════════════════════════════════════════════════════


class TestBridgeBudget:
    def test_queries_remaining_default(self):
        from ai.notebooklm_bridge import NotebookLMBridge

        # Without streamlit, should return full budget
        remaining = NotebookLMBridge.queries_remaining()
        assert remaining == 50


# ═══════════════════════════════════════════════════════════════════
# Edge case / robustness tests for parser
# ═══════════════════════════════════════════════════════════════════


class TestParserEdgeCases:
    def test_sentiment_with_extra_whitespace(self):
        from ai.notebooklm_parser import parse_sentiment_overview

        text = """
## Overall Sentiment

  positive

## Sentiment Distribution
 - Positive:   72 %
 - Negative:  18 %
 - Neutral:  10 %
"""
        result = parse_sentiment_overview(text)
        assert result["overall"] == "positive"
        assert result["positive_percentage"] == 72

    def test_aspects_with_no_theme_section(self):
        from ai.notebooklm_parser import parse_aspects

        text = """## Aspects Analysis

### 1. Price
- Positive: 5 | Neutral: 3 | Negative: 20
"""
        aspects, themes = parse_aspects(text)
        assert "price" in aspects
        assert aspects["price"]["negative"] == 20
        assert themes == []

    def test_recommendations_with_no_risks(self):
        from ai.notebooklm_parser import parse_recommendations

        text = """## Actionable Recommendations

### [HIGH] Do something important
- Rationale: Because data says so
- Expected Outcome: Good things happen
"""
        recs, opps, risks = parse_recommendations(text)
        assert len(recs) == 1
        assert opps == []
        assert risks == []

    def test_compose_with_partial_data(self):
        """Should not crash if some queries returned empty."""
        from ai.notebooklm_parser import compose_customer_insight

        parsed = {
            "sentiment_overview": """## Overall Sentiment
negative
## Sentiment Distribution
- Positive: 20%
- Negative: 60%
- Neutral: 20%
""",
            "aspects_analysis": "",
            "key_findings_audience": "",
            "recommendations_risks": "",
        }
        insight = compose_customer_insight(parsed)
        assert insight["sentiment_overview"]["overall"] == "negative"
        # Missing sections should not be present or should be empty
        assert insight.get("key_findings", []) == [] or "key_findings" not in insight

    def test_findings_with_varied_formatting(self):
        """NLM may use slightly different heading styles."""
        from ai.notebooklm_parser import parse_key_findings

        text = """## Key Findings

### Finding 1: People love the battery life
- Evidence: 45 comments mention battery positively
- Business Impact: Battery is the #1 purchase driver

## Audience Profile
### Primary Demographics
College students and young professionals, 18-30

### Psychographics
Value practicality and portability

### Knowledge Level
Moderate - familiar with basics but not expert

### Engagement Style
Quick comments, share personal experiences

## Executive Summary
Battery life is the standout feature driving positive sentiment among young users.
"""
        findings, audience, summary = parse_key_findings(text)
        assert len(findings) == 1
        assert "battery" in findings[0]["finding"].lower()
        assert "18-30" in audience["primary_demographics"] or "College" in audience["primary_demographics"]
        assert "battery" in summary.lower() or "Battery" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
