"""
Python Stats Report
====================
Transforms the local analysis pipeline output (VADER sentiment,
TF-IDF keywords, LDA topics, engagement metrics, temporal patterns)
into a structured report and renders it as a professional card-based UI.

Always available — no API key needed.
"""

import streamlit as st


def compose_stats_report(analysis: dict) -> dict | None:
    """Transform run_full_analysis() output into a structured report.

    Args:
        analysis: Output from analysis/pipeline.py run_full_analysis().

    Returns:
        Structured report dict, or None if analysis is insufficient.
    """
    if not analysis or analysis.get("comment_count", 0) < 10:
        return None

    report: dict = {
        "comment_count": analysis["comment_count"],
        "errors": analysis.get("errors", []),
    }

    # --- Sentiment Overview ---
    sentiment = analysis.get("sentiment")
    if sentiment:
        dist = sentiment.get("distribution", {})
        report["sentiment"] = {
            "positive": dist.get("positive", 0),
            "neutral": dist.get("neutral", 0),
            "negative": dist.get("negative", 0),
            "avg_compound": sentiment.get("avg_compound", 0),
            "top_positive": sentiment.get("top_positive", [])[:3],
            "top_negative": sentiment.get("top_negative", [])[:3],
        }

    # --- Content Themes (bigrams + TF-IDF) ---
    keywords = analysis.get("keywords")
    if keywords:
        report["keywords"] = {
            "tfidf": keywords.get("tfidf_keywords", [])[:15],
            "bigrams": keywords.get("bigrams", [])[:10],
            "trigrams": keywords.get("trigrams", [])[:5],
            "wordcloud_bytes": keywords.get("wordcloud_bytes"),
        }

    # --- Topics (LDA) ---
    topics = analysis.get("topics")
    if topics:
        report["topics"] = {
            "items": topics.get("topics", []),
            "reason": topics.get("reason"),
        }

    # --- Engagement ---
    engagement = analysis.get("engagement")
    if engagement:
        report["engagement"] = {
            "total_comments": engagement.get("total_comments", 0),
            "reply_rate": engagement.get("reply_rate", 0),
            "avg_likes": engagement.get("avg_likes", 0),
            "engagement_score": engagement.get("engagement_score", 0),
            "top_liked": engagement.get("top_liked", [])[:3],
            "most_active_users": engagement.get("most_active_users", [])[:5],
        }

    # --- Temporal ---
    temporal = analysis.get("temporal")
    if temporal:
        report["temporal"] = {
            "peak_hour": temporal.get("peak_hour"),
            "peak_day": temporal.get("peak_day"),
            "date_range": temporal.get("date_range", {}),
            "by_date": temporal.get("by_date", []),
            "by_hour": temporal.get("by_hour", []),
            "reason": temporal.get("reason"),
        }

    # --- Auto-generated executive summary ---
    report["summary"] = _generate_summary(report)

    return report


def _generate_summary(report: dict) -> str:
    """Auto-generate an executive summary from stats."""
    parts = []

    comment_count = report.get("comment_count", 0)
    parts.append(f"Analysis of {comment_count:,} comments")

    # Sentiment
    sent = report.get("sentiment")
    if sent:
        dominant = max(
            ["positive", "neutral", "negative"],
            key=lambda s: sent.get(s, 0),
        )
        pct = sent.get(dominant, 0)
        parts.append(f"with {dominant} sentiment dominant ({pct}%)")

    # Top keywords
    kw = report.get("keywords")
    if kw and kw.get("tfidf"):
        top_words = [w for w, _ in kw["tfidf"][:3]]
        parts.append(f"Top themes: {', '.join(top_words)}")

    # Engagement
    eng = report.get("engagement")
    if eng:
        parts.append(f"Avg {eng.get('avg_likes', 0)} likes/comment")

    # Temporal
    temp = report.get("temporal")
    if temp and temp.get("peak_hour") is not None:
        parts.append(f"Peak activity at {temp['peak_hour']}:00")

    return ". ".join(parts) + "."


def render_stats_report(report: dict):
    """Render the Python Stats Report as a professional card-based UI.

    Args:
        report: Output from compose_stats_report().
    """
    if not report:
        return

    st.markdown("### Python Stats Report")
    st.caption("Local analysis — VADER sentiment, TF-IDF keywords, LDA topics, engagement & temporal patterns")

    # Executive summary
    summary = report.get("summary", "")
    if summary:
        st.markdown(
            f'<div style="background:rgba(52,211,153,0.06);border-left:3px solid '
            f'rgba(52,211,153,0.4);padding:0.8rem 1.2rem;border-radius:0 8px 8px 0;'
            f'margin-bottom:1rem;font-size:0.9rem;line-height:1.5">{summary}</div>',
            unsafe_allow_html=True,
        )

    # Errors
    for err in report.get("errors", []):
        st.warning(err)

    # --- Sentiment Overview ---
    sent = report.get("sentiment")
    if sent:
        with st.expander("Sentiment Overview", expanded=True):
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Positive", f"{sent['positive']}%")
            sc2.metric("Neutral", f"{sent['neutral']}%")
            sc3.metric("Negative", f"{sent['negative']}%")
            sc4.metric("Avg Score", f"{sent['avg_compound']:.2f}")

            # Sentiment bar
            _render_sentiment_bar(sent["positive"], sent["neutral"], sent["negative"])

            # Top comments
            col_p, col_n = st.columns(2)
            with col_p:
                if sent.get("top_positive"):
                    st.markdown("**Top Positive**")
                    for c in sent["top_positive"]:
                        st.markdown(
                            f'<div style="border-left:3px solid #34D399;padding:4px 10px;'
                            f'margin:4px 0;font-size:0.82rem">{c.get("text", "")[:200]}</div>',
                            unsafe_allow_html=True,
                        )
            with col_n:
                if sent.get("top_negative"):
                    st.markdown("**Top Negative**")
                    for c in sent["top_negative"]:
                        st.markdown(
                            f'<div style="border-left:3px solid #F87171;padding:4px 10px;'
                            f'margin:4px 0;font-size:0.82rem">{c.get("text", "")[:200]}</div>',
                            unsafe_allow_html=True,
                        )

    # --- Content Themes ---
    kw = report.get("keywords")
    if kw:
        with st.expander("Content Themes", expanded=True):
            col_kw, col_wc = st.columns([1, 1])

            with col_kw:
                # TF-IDF keywords as tag chips
                if kw.get("tfidf"):
                    st.markdown("**Key Terms** (TF-IDF)")
                    tags_html = " ".join(
                        f'<span style="display:inline-block;background:rgba(59,130,246,0.12);'
                        f'border:1px solid rgba(59,130,246,0.2);border-radius:4px;'
                        f'padding:3px 10px;margin:3px;font-size:0.8rem;color:#60A5FA">'
                        f'{w} <span style="color:#94A3B8">({s:.2f})</span></span>'
                        for w, s in kw["tfidf"][:15]
                    )
                    st.markdown(tags_html, unsafe_allow_html=True)

                # Bigrams
                if kw.get("bigrams"):
                    st.markdown("**Top Phrases** (Bigrams)")
                    for phrase, count in kw["bigrams"][:8]:
                        st.markdown(f"- **{phrase}** ({count})")

            with col_wc:
                wc_bytes = kw.get("wordcloud_bytes")
                if wc_bytes:
                    st.image(wc_bytes, caption="Word Cloud", use_container_width=True)

    # --- Key Topics (LDA) ---
    topics = report.get("topics")
    if topics:
        if topics.get("reason"):
            pass  # Skip if LDA had insufficient data
        elif topics.get("items"):
            with st.expander("Key Topics (LDA)", expanded=False):
                for topic_item in topics["items"]:
                    keywords_list = topic_item.get("keywords", [])
                    label = f"Topic {topic_item.get('id', '?')}: {', '.join(keywords_list[:4])}"
                    st.markdown(f"**{label}**")
                    # Keyword tags
                    tags = " ".join(
                        f'<span style="display:inline-block;background:rgba(139,92,246,0.12);'
                        f'border-radius:4px;padding:2px 8px;margin:2px;font-size:0.78rem;'
                        f'color:#A78BFA">{kw}</span>'
                        for kw in keywords_list
                    )
                    st.markdown(tags, unsafe_allow_html=True)
                    # Representative comments
                    for comment in topic_item.get("representative_comments", [])[:2]:
                        if comment.strip():
                            st.caption(f"> {comment[:200]}")
                    st.markdown("---")

    # --- Engagement Metrics ---
    eng = report.get("engagement")
    if eng:
        with st.expander("Engagement Metrics", expanded=False):
            em1, em2, em3, em4 = st.columns(4)
            em1.metric("Total Comments", f"{eng.get('total_comments', 0):,}")
            em2.metric("Reply Rate", f"{eng.get('reply_rate', 0)}%")
            em3.metric("Avg Likes", f"{eng.get('avg_likes', 0)}")
            em4.metric("Engagement Score", f"{eng.get('engagement_score', 0)}")

            col_top, col_active = st.columns(2)
            with col_top:
                if eng.get("top_liked"):
                    st.markdown("**Most Liked Comments**")
                    for c in eng["top_liked"]:
                        st.markdown(
                            f'<div style="border-left:3px solid #FBBF24;padding:4px 10px;'
                            f'margin:4px 0;font-size:0.82rem">{c.get("text", "")[:200]}'
                            f'<span style="color:#94A3B8"> — {c.get("likes", 0)} likes</span></div>',
                            unsafe_allow_html=True,
                        )
            with col_active:
                if eng.get("most_active_users"):
                    st.markdown("**Most Active Users**")
                    for user, count in eng["most_active_users"]:
                        st.markdown(f"- **@{user}** — {count} comments")

    # --- Temporal Patterns ---
    temp = report.get("temporal")
    if temp:
        if temp.get("reason"):
            pass  # Skip if temporal had insufficient data
        else:
            with st.expander("Temporal Patterns", expanded=False):
                import pandas as pd

                tm1, tm2, tm3 = st.columns(3)
                if temp.get("peak_hour") is not None:
                    tm1.metric("Peak Hour", f"{temp['peak_hour']}:00")
                if temp.get("peak_day"):
                    tm2.metric("Peak Day", temp["peak_day"])
                date_range = temp.get("date_range", {})
                if date_range.get("earliest"):
                    tm3.metric("Date Range", f"{date_range['earliest']} → {date_range['latest']}")

                col_date, col_hour = st.columns(2)
                with col_date:
                    by_date = temp.get("by_date", [])
                    if by_date:
                        df_date = pd.DataFrame(by_date, columns=["Date", "Comments"])
                        st.line_chart(df_date.set_index("Date"), height=200)

                with col_hour:
                    by_hour = temp.get("by_hour", [])
                    if by_hour:
                        df_hour = pd.DataFrame(by_hour, columns=["Hour", "Comments"])
                        st.bar_chart(df_hour.set_index("Hour"), height=200)


def _render_sentiment_bar(positive: int, neutral: int, negative: int):
    """Render a horizontal stacked sentiment bar."""
    total = positive + neutral + negative
    if total == 0:
        return

    st.markdown(
        f'<div style="display:flex;height:10px;border-radius:5px;overflow:hidden;margin:6px 0 12px 0">'
        f'<div style="width:{positive}%;background:#34D399" title="Positive {positive}%"></div>'
        f'<div style="width:{neutral}%;background:#64748B" title="Neutral {neutral}%"></div>'
        f'<div style="width:{negative}%;background:#F87171" title="Negative {negative}%"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
