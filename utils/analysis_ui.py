"""
Analysis dashboard UI — renders analysis results as a Streamlit dashboard.
"""

import streamlit as st


def render_analysis_dashboard(analysis: dict):
    """Render the full analysis dashboard below scraping results."""
    if not analysis or analysis.get("comment_count", 0) < 10:
        return

    st.markdown("---")
    st.markdown('<div class="page-header"><h1>Analysis</h1></div>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="page-desc">Insights from {analysis["comment_count"]} comments</p>',
        unsafe_allow_html=True,
    )

    # Show any errors
    for err in analysis.get("errors", []):
        st.warning(err)

    # Sentiment section
    sentiment = analysis.get("sentiment")
    if sentiment and sentiment.get("distribution"):
        _render_sentiment(sentiment)

    # Keywords section
    keywords = analysis.get("keywords")
    if keywords and (keywords.get("tfidf_keywords") or keywords.get("frequency_keywords")):
        _render_keywords(keywords)

    # Topics section
    topics = analysis.get("topics")
    if topics and topics.get("topics"):
        _render_topics(topics)

    # Engagement section
    engagement = analysis.get("engagement")
    if engagement and engagement.get("total_comments"):
        _render_engagement(engagement)

    # Temporal section
    temporal = analysis.get("temporal")
    if temporal and temporal.get("by_date"):
        _render_temporal(temporal)

    # AI analysis section
    _render_ai_section()


def _render_sentiment(data: dict):
    """Render sentiment analysis results."""
    st.markdown("### Sentiment")

    dist = data.get("distribution", {})
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Positive", f"{dist.get('positive', 0)}%")
    m2.metric("Neutral", f"{dist.get('neutral', 0)}%")
    m3.metric("Negative", f"{dist.get('negative', 0)}%")
    m4.metric("Avg Score", f"{data.get('avg_compound', 0):.2f}")

    # Bar chart
    import pandas as pd
    chart_data = pd.DataFrame({
        "Sentiment": ["Positive", "Neutral", "Negative"],
        "Percentage": [dist.get("positive", 0), dist.get("neutral", 0), dist.get("negative", 0)],
    })
    st.bar_chart(chart_data.set_index("Sentiment"), height=200)

    # Top positive/negative
    col1, col2 = st.columns(2)
    with col1:
        with st.expander("Top Positive Comments"):
            for c in data.get("top_positive", [])[:5]:
                st.markdown(f"> {c.get('text', '')[:200]}")
                st.caption(f"Score: {c.get('compound', 0):.2f} | Likes: {c.get('likes', 0)}")
    with col2:
        with st.expander("Top Negative Comments"):
            for c in data.get("top_negative", [])[:5]:
                st.markdown(f"> {c.get('text', '')[:200]}")
                st.caption(f"Score: {c.get('compound', 0):.2f} | Likes: {c.get('likes', 0)}")


def _render_keywords(data: dict):
    """Render keyword analysis results."""
    st.markdown("### Keywords")

    col1, col2 = st.columns(2)

    with col1:
        # Word cloud
        wc_bytes = data.get("wordcloud_bytes")
        if wc_bytes:
            st.image(wc_bytes, caption="Word Cloud", use_container_width=True)
        else:
            st.info("Word cloud unavailable (install wordcloud package)")

    with col2:
        # Top keywords table
        keywords = data.get("tfidf_keywords") or data.get("frequency_keywords", [])
        if keywords:
            import pandas as pd
            kw_data = [(w, round(s, 2) if isinstance(s, float) else s) for w, s in keywords[:20]]
            df = pd.DataFrame(kw_data, columns=["Keyword", "Score"])
            st.dataframe(df, use_container_width=True, height=350, hide_index=True)

    # N-grams
    bigrams = data.get("bigrams", [])
    trigrams = data.get("trigrams", [])
    if bigrams or trigrams:
        g1, g2 = st.columns(2)
        with g1:
            if bigrams:
                with st.expander("Top Bigrams"):
                    for phrase, count in bigrams[:10]:
                        st.markdown(f"**{phrase}** ({count})")
        with g2:
            if trigrams:
                with st.expander("Top Trigrams"):
                    for phrase, count in trigrams[:10]:
                        st.markdown(f"**{phrase}** ({count})")


def _render_topics(data: dict):
    """Render topic modeling results."""
    st.markdown("### Topics")

    if data.get("reason"):
        st.info(data["reason"])
        return

    for topic in data.get("topics", []):
        keywords = topic.get("keywords", [])
        label = f"Topic {topic.get('id', '?')}: {', '.join(keywords[:4])}" if keywords else f"Topic {topic.get('id', '?')}"
        with st.expander(label):
            # Keyword tags
            tags_html = " ".join(
                f'<span style="display:inline-block;background:rgba(59,130,246,0.15);'
                f'border:1px solid rgba(59,130,246,0.25);border-radius:4px;'
                f'padding:2px 8px;margin:2px;font-size:0.8rem;color:#60A5FA;">{kw}</span>'
                for kw in keywords
            )
            st.markdown(tags_html, unsafe_allow_html=True)

            # Representative comments
            if topic.get("representative_comments"):
                st.markdown("**Representative comments:**")
                for comment in topic["representative_comments"]:
                    if comment.strip():
                        st.markdown(f"> {comment}")


def _render_engagement(data: dict):
    """Render engagement metrics."""
    st.markdown("### Engagement")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Comments", f"{data.get('total_comments', 0):,}")
    m2.metric("Reply Rate", f"{data.get('reply_rate', 0)}%")
    m3.metric("Avg Likes", f"{data.get('avg_likes', 0)}")
    m4.metric("Engagement Score", f"{data.get('engagement_score', 0)}")

    col1, col2 = st.columns(2)
    with col1:
        with st.expander("Top Liked Comments"):
            for c in data.get("top_liked", [])[:5]:
                st.markdown(f"> {c.get('text', '')[:200]}")
                st.caption(f"@{c.get('username', '?')} | {c.get('likes', 0)} likes")

    with col2:
        with st.expander("Most Active Users"):
            for user, count in data.get("most_active_users", [])[:10]:
                st.markdown(f"**@{user}** — {count} comments")


def _render_temporal(data: dict):
    """Render temporal analysis results."""
    st.markdown("### Time Patterns")

    if data.get("reason"):
        st.info(data["reason"])
        return

    import pandas as pd

    m1, m2, m3 = st.columns(3)
    m1.metric("Peak Hour", f"{data.get('peak_hour', '?')}:00")
    m2.metric("Peak Day", data.get("peak_day", "?"))
    date_range = data.get("date_range", {})
    m3.metric("Date Range", f"{date_range.get('earliest', '?')} to {date_range.get('latest', '?')}")

    col1, col2 = st.columns(2)

    with col1:
        # Volume over time
        by_date = data.get("by_date", [])
        if by_date:
            df_date = pd.DataFrame(by_date, columns=["Date", "Comments"])
            st.line_chart(df_date.set_index("Date"), height=250)

    with col2:
        # Hour distribution
        by_hour = data.get("by_hour", [])
        if by_hour:
            df_hour = pd.DataFrame(by_hour, columns=["Hour", "Comments"])
            st.bar_chart(df_hour.set_index("Hour"), height=250)


def render_platform_comparison(result: dict):
    """Render cross-platform comparison dashboard.

    Only shown when 2+ platforms have comments.
    Uses AI tags (ai_sentiment) if available, otherwise falls back to raw counts.
    """
    import pandas as pd
    from collections import Counter

    comments = result.get("comments_clean", [])
    if not comments:
        return

    # Group by platform
    by_platform: dict[str, list[dict]] = {}
    for c in comments:
        p = c.get("platform", "unknown")
        by_platform.setdefault(p, []).append(c)

    # Only show if 2+ platforms have data
    platforms_with_data = {p: cs for p, cs in by_platform.items() if cs}
    if len(platforms_with_data) < 2:
        return

    st.markdown("---")
    st.markdown("### Cross-Platform Comparison")

    # --- Sentiment distribution per platform ---
    has_ai_tags = any(c.get("ai_sentiment") for c in comments)

    sentiment_data = []
    for platform, cs in sorted(platforms_with_data.items()):
        counts = Counter()
        for c in cs:
            if has_ai_tags:
                s = c.get("ai_sentiment", "neutral")
            else:
                s = "neutral"
            counts[s] += 1
        total = len(cs)
        for sent in ["positive", "neutral", "negative", "mixed"]:
            pct = round(counts.get(sent, 0) / total * 100, 1) if total else 0
            sentiment_data.append({
                "Platform": platform.title(),
                "Sentiment": sent.title(),
                "Percentage": pct,
            })

    if has_ai_tags and sentiment_data:
        st.markdown("#### Sentiment by Platform")
        df_sent = pd.DataFrame(sentiment_data)
        # Pivot for grouped bar chart
        df_pivot = df_sent.pivot(index="Platform", columns="Sentiment", values="Percentage").fillna(0)
        # Reorder columns
        col_order = [c for c in ["Positive", "Neutral", "Negative", "Mixed"] if c in df_pivot.columns]
        df_pivot = df_pivot[col_order]
        st.bar_chart(df_pivot, height=300)

    # --- Engagement comparison ---
    st.markdown("#### Engagement by Platform")
    eng_cols = st.columns(len(platforms_with_data))
    for i, (platform, cs) in enumerate(sorted(platforms_with_data.items())):
        with eng_cols[i]:
            total_likes = sum(c.get("likes", 0) for c in cs)
            avg_likes = round(total_likes / len(cs), 1) if cs else 0
            replies = sum(1 for c in cs if c.get("is_reply"))
            reply_rate = round(replies / len(cs) * 100, 1) if cs else 0
            st.markdown(f"**{platform.title()}**")
            st.metric("Comments", f"{len(cs):,}")
            st.metric("Avg Likes", f"{avg_likes}")
            st.metric("Reply Rate", f"{reply_rate}%")

    # --- Top keywords per platform ---
    st.markdown("#### Top Keywords by Platform")
    kw_cols = st.columns(len(platforms_with_data))
    for i, (platform, cs) in enumerate(sorted(platforms_with_data.items())):
        with kw_cols[i]:
            st.markdown(f"**{platform.title()}**")
            # Simple frequency-based keywords
            from collections import Counter
            words = Counter()
            for c in cs:
                text = c.get("text", "").lower()
                for w in text.split():
                    w = w.strip(".,!?;:\"'()[]{}#@")
                    if len(w) > 2 and w not in _STOP_WORDS:
                        words[w] += 1
            top_kw = words.most_common(10)
            if top_kw:
                for word, count in top_kw:
                    st.markdown(f"- **{word}** ({count})")
            else:
                st.caption("No keywords")


# Minimal stopwords for cross-platform keyword comparison
_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "about", "like",
    "and", "but", "or", "nor", "not", "so", "yet", "this", "that",
    "these", "those", "it", "its", "he", "she", "they", "we", "you",
    "i", "me", "my", "your", "his", "her", "our", "their", "what",
    "which", "who", "whom", "how", "when", "where", "why", "all",
    "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "than", "too", "very", "just", "also", "now", "then",
}


def _get_llm_provider_and_key() -> tuple[str | None, str | None]:
    """Detect active LLM provider and key from session state or env vars.

    Mirrors the same logic as ai.client.LLMClient so the UI gate
    matches the actual availability.
    """
    import os
    # 1. Session state
    provider = st.session_state.get("active_provider")
    if provider:
        # NotebookLM doesn't need an API key
        if provider == "notebooklm":
            return "notebooklm", "notebooklm-no-key-needed"
        keys = st.session_state.get("api_keys", {})
        if keys.get(provider):
            return provider, keys[provider]
    # 2. Environment variables
    env_map = {
        "claude": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GOOGLE_API_KEY",
    }
    for prov, env_var in env_map.items():
        key = os.environ.get(env_var)
        if key:
            return prov, key
    return None, None


def _render_ai_section():
    """Render AI analysis CTA or results."""
    st.markdown("### AI-Powered Analysis")

    # Check if API key is configured (session state OR env vars)
    active_provider, api_key = _get_llm_provider_and_key()

    if not active_provider or not api_key:
        st.info(
            "Unlock deeper insights with AI analysis. "
            "Configure your API key in Settings (or set an environment variable) to access "
            "pain point extraction, feature request mining, competitive intelligence, and more."
        )
        st.page_link("pages/7_⚙️_Settings.py", label="Go to Settings", use_container_width=True)
        return

    # AI analysis controls
    last_scrape = st.session_state.get("last_scrape", {})
    comments = last_scrape.get("comments", [])

    if not comments:
        st.info("Scrape some comments first to run AI analysis.")
        return

    try:
        from ai.prompts import ANALYSIS_TYPES
        from ai.cost import estimate_cost
    except ImportError:
        st.warning("AI modules not available.")
        return

    analysis_type = st.selectbox(
        "Analysis type",
        list(ANALYSIS_TYPES.keys()),
        format_func=lambda x: ANALYSIS_TYPES[x],
    )

    # Cost estimate
    cost_info = estimate_cost(comments, active_provider, analysis_type)
    st.caption(f"Estimated cost: {cost_info['formatted']}")

    if st.button("Run AI Analysis", type="primary", use_container_width=True):
        try:
            from ai.client import LLMClient
            from ai.prompts import get_prompt
            from utils.ai_results_ui import render_ai_results
            from utils.async_runner import run_async

            client = LLMClient()
            prompt = get_prompt(analysis_type, comments)

            with st.spinner(f"Running {ANALYSIS_TYPES[analysis_type]}..."):
                result = run_async(client.analyze(prompt))

            if result:
                st.session_state["last_ai_result"] = {
                    "result": result,
                    "analysis_type": analysis_type,
                }
                render_ai_results(result, analysis_type)
            else:
                st.error("AI analysis returned empty results. Check your API key and try again.")
        except Exception as e:
            st.error(f"AI analysis failed: {e}")

    # Show previous results if available
    elif "last_ai_result" in st.session_state:
        try:
            from utils.ai_results_ui import render_ai_results
            prev = st.session_state["last_ai_result"]
            render_ai_results(prev["result"], prev["analysis_type"])
        except ImportError:
            pass
