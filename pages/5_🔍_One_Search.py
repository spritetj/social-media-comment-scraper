"""
One Search — Interactive step-by-step social listening workflow.

Steps:
  0. Input — topic, platforms, options
  1. Review Queries — edit LLM-generated queries before searching
  2. Review URLs — select/deselect discovered URLs before scraping
  3. Scraping — progress tracker while scraping + analysis
  4. Results — comments table, analysis dashboard, AI Customer Insight
"""

import re
import streamlit as st
import pandas as pd
from pathlib import Path

from utils.async_runner import run_async

st.set_page_config(
    page_title="One Search — Comment Scraper",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Load custom CSS
css_path = Path(__file__).parent.parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Navigation
from utils.nav import render_nav
render_nav()

# Page header
st.markdown('<div class="page-header"><h1>One Search</h1></div>', unsafe_allow_html=True)
st.markdown(
    '<p class="page-desc">'
    'Type a brand, product, or topic — get comprehensive social listening insights across all platforms.'
    '</p>',
    unsafe_allow_html=True,
)

# Check tier access
st.session_state.setdefault("user_tier", "pro")
try:
    from config.gating import check_feature
    if not check_feature("one_search"):
        st.stop()
except ImportError:
    pass


# ═══════════════════════════════════════════════════════════════════════════
# Workflow state
# ═══════════════════════════════════════════════════════════════════════════

_STEP_LABELS_DEFAULT = ["Input", "Queries", "URLs", "Scraping", "Results"]
_STEP_LABELS_NLM = ["Input", "Queries", "URLs", "Scraping", "NotebookLM Setup", "Results"]


def _is_nlm_mode() -> bool:
    """Check if NotebookLM is the active analysis provider."""
    return st.session_state.get("active_provider") == "notebooklm"


def _get_step_labels() -> list[str]:
    """Get step labels based on current mode."""
    return _STEP_LABELS_NLM if _is_nlm_mode() else _STEP_LABELS_DEFAULT


def _get_wf() -> dict:
    """Get or initialize workflow state."""
    if "os_wf" not in st.session_state:
        st.session_state["os_wf"] = {"step": 0}
    return st.session_state["os_wf"]


def _reset_wf():
    """Reset workflow to step 0."""
    st.session_state["os_wf"] = {"step": 0}


# ═══════════════════════════════════════════════════════════════════════════
# Query display helpers — hide Google operators from user
# ═══════════════════════════════════════════════════════════════════════════

def _strip_operators(query: str) -> str:
    """Strip Google dork operators from a query for user-friendly display.

    Removes: site:..., after:..., before:..., intitle:, inurl:, -inurl:...
    Keeps the actual search terms.
    """
    q = query
    # Remove site:anything (including site:youtube.com/shorts)
    q = re.sub(r'site:\S+', '', q)
    # Remove after:YYYY-MM-DD and before:YYYY-MM-DD
    q = re.sub(r'(?:after|before):\d{4}-\d{2}-\d{2}', '', q)
    # Remove intitle: and -inurl: prefixes
    q = re.sub(r'-?(?:intitle|inurl):', '', q)
    # Collapse whitespace
    q = re.sub(r'\s+', ' ', q).strip()
    return q


def _restore_operators(clean_query: str, platform: str, date_range: str) -> str:
    """Re-add Google operators to a clean query for actual search execution."""
    site_map = {
        "youtube": "youtube.com",
        "tiktok": "tiktok.com",
        "facebook": "facebook.com",
        "instagram": "instagram.com",
    }
    site = site_map.get(platform, "")
    parts = [f"site:{site}", clean_query] if site else [clean_query]

    # Add date filter
    if date_range and date_range != "any":
        from datetime import datetime, timedelta
        now = datetime.now()
        days = {"week": 7, "month": 30, "year": 365}.get(date_range, 0)
        if days:
            after = (now - timedelta(days=days)).strftime("%Y-%m-%d")
            parts.append(f"after:{after}")

    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Step indicator
# ═══════════════════════════════════════════════════════════════════════════

def _render_step_indicator(current_step: int):
    """Render a horizontal step progress bar."""
    step_labels = _get_step_labels()
    steps_html = ""
    for i, label in enumerate(step_labels):
        if i < current_step:
            cls = "osstep-done"
            icon = "&#10003;"
        elif i == current_step:
            cls = "osstep-active"
            icon = str(i + 1)
        else:
            cls = "osstep-pending"
            icon = str(i + 1)
        connector = '<span class="osstep-connector"></span>' if i > 0 else ""
        steps_html += (
            f'{connector}'
            f'<span class="osstep {cls}">'
            f'<span class="osstep-icon">{icon}</span>'
            f'<span class="osstep-label">{label}</span>'
            f'</span>'
        )

    st.markdown(
        '<style>'
        '.osstep-bar{display:flex;align-items:center;justify-content:center;'
        'gap:0;margin:0.5rem 0 1.5rem 0;flex-wrap:wrap}'
        '.osstep{display:inline-flex;align-items:center;gap:0.3rem;'
        'padding:6px 14px;border-radius:8px;font-size:0.82rem;font-weight:500}'
        '.osstep-icon{width:22px;height:22px;border-radius:50%;display:inline-flex;'
        'align-items:center;justify-content:center;font-size:0.72rem;font-weight:700}'
        '.osstep-done{color:#34D399}'
        '.osstep-done .osstep-icon{background:rgba(52,211,153,0.15);color:#34D399}'
        '.osstep-active{color:#3B82F6;background:rgba(59,130,246,0.08)}'
        '.osstep-active .osstep-icon{background:rgba(59,130,246,0.18);color:#3B82F6}'
        '.osstep-pending{color:#64748B}'
        '.osstep-pending .osstep-icon{background:rgba(100,116,139,0.1);color:#64748B}'
        '.osstep-connector{width:28px;height:2px;background:rgba(255,255,255,0.08);'
        'display:inline-block;margin:0 2px}'
        '.osstep-done+.osstep-connector,.osstep-connector+.osstep-done .osstep-connector'
        '{background:rgba(52,211,153,0.3)}'
        '</style>'
        f'<div class="osstep-bar">{steps_html}</div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Step 0: Input
# ═══════════════════════════════════════════════════════════════════════════

def _render_input():
    """Render the input form (step 0)."""
    topic = st.text_input(
        "What do you want to research?",
        placeholder="Tesla Model 3, iPhone 16, Nike Air Max...",
        label_visibility="collapsed",
    )

    with st.expander("Search Options", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            platforms = st.multiselect(
                "Platforms",
                ["youtube", "tiktok", "facebook", "instagram"],
                default=["youtube", "tiktok", "facebook", "instagram"],
                format_func=str.title,
            )
        with col2:
            date_range = st.selectbox(
                "Date range",
                ["any", "week", "month", "year"],
                format_func=lambda x: {
                    "any": "Any time", "week": "Past week",
                    "month": "Past month", "year": "Past year",
                }[x],
            )

        adv1, adv2 = st.columns(2)
        with adv1:
            max_urls = st.slider("Max URLs per platform", 5, 50, 15, step=5)
        with adv2:
            max_comments = st.slider("Max comments per URL", 50, 500, 200, step=50)

        cookies_map = {}
        if "facebook" in platforms:
            fb_cookies = st.file_uploader(
                "Facebook cookies (required for Facebook)",
                type=["txt", "json"],
                key="onesearch_fb_cookies",
            )
            if fb_cookies:
                from utils.common import load_cookies_as_list
                content = fb_cookies.read().decode("utf-8")
                cookies_map["facebook"] = load_cookies_as_list(content, "facebook.com")

        if "instagram" in platforms:
            ig_cookies = st.file_uploader(
                "Instagram cookies (optional, improves results)",
                type=["txt", "json"],
                key="onesearch_ig_cookies",
            )
            if ig_cookies:
                from utils.common import load_cookies_as_list
                content = ig_cookies.read().decode("utf-8")
                cookies_map["instagram"] = load_cookies_as_list(content, "instagram.com")

    if st.button("Start Research", type="primary", use_container_width=True):
        if not topic.strip():
            st.warning("Please enter a topic to research.")
            return
        if not platforms:
            st.warning("Please select at least one platform.")
            return

        # Generate queries
        with st.spinner("Generating search queries..."):
            from search.pipeline import step_generate_queries
            qr = run_async(step_generate_queries(
                topic=topic.strip(),
                platforms=platforms,
                date_range=date_range,
            ))

        # Initialize workflow state
        wf = _get_wf()
        wf.update({
            "step": 1,
            "topic": topic.strip(),
            "platforms": platforms,
            "date_range": date_range,
            "max_urls": max_urls,
            "max_comments": max_comments,
            "cookies_map": cookies_map,
            "queries": qr["queries"],
            "relevance_keywords": qr["relevance_keywords"],
            "research_question": qr["research_question"],
            "hypotheses": qr["hypotheses"],
            "search_results": {},
            "url_selections": {},
            "result": None,
        })
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Review Queries
# ═══════════════════════════════════════════════════════════════════════════

def _render_query_review():
    """Render the query review/edit step."""
    wf = _get_wf()

    # Research context
    if wf.get("research_question"):
        st.info(f"**Research Question:** {wf['research_question']}")
    if wf.get("hypotheses"):
        with st.expander("Research Hypotheses", expanded=False):
            for h in wf["hypotheses"]:
                st.markdown(f"- {h}")

    st.markdown("#### Edit Search Queries")
    st.caption("One query per line. Add, remove, or edit freely. Platform targeting and date filters are applied automatically.")

    # Per-platform text areas — show clean queries (no site:/after: operators)
    edited_clean_queries = {}
    tabs = st.tabs([p.title() for p in wf["platforms"]])
    for i, platform in enumerate(wf["platforms"]):
        with tabs[i]:
            current = wf["queries"].get(platform, [])
            clean = [_strip_operators(q) for q in current]
            # Deduplicate after stripping (operators may have been the only difference)
            seen = set()
            deduped = []
            for q in clean:
                if q and q not in seen:
                    seen.add(q)
                    deduped.append(q)
            text = st.text_area(
                f"Queries for {platform.title()}",
                value="\n".join(deduped),
                height=200,
                key=f"qa_{platform}",
                label_visibility="collapsed",
            )
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            edited_clean_queries[platform] = lines
            st.caption(f"{len(lines)} queries")

    # Action buttons
    col_back, col_approve = st.columns([1, 3])
    with col_back:
        if st.button("Back", use_container_width=True):
            wf["step"] = 0
            st.rerun()
    with col_approve:
        if st.button("Approve & Search Google", type="primary", use_container_width=True):
            # Restore Google operators for actual search
            full_queries = {}
            for platform, clean_list in edited_clean_queries.items():
                full_queries[platform] = [
                    _restore_operators(q, platform, wf.get("date_range", "any"))
                    for q in clean_list
                ]
            wf["queries"] = full_queries

            # Run URL search with live progress
            progress_placeholder = st.empty()
            status_text = st.empty()

            def _search_progress(msg: str):
                """Update progress display during URL search."""
                msg = str(msg).strip()
                if not msg:
                    return
                status_text.markdown(
                    f'<div style="font-size:0.82rem;color:#94A3B8;padding:2px 0">'
                    f'{msg}</div>',
                    unsafe_allow_html=True,
                )

            progress_placeholder.info("Searching Google for URLs across platforms...")

            from search.pipeline import step_search_urls
            url_result = step_search_urls(
                queries=full_queries,
                platforms=wf["platforms"],
                max_urls_per_platform=wf["max_urls"],
                topic=wf["topic"],
                relevance_keywords=wf.get("relevance_keywords"),
                progress_callback=_search_progress,
            )

            progress_placeholder.empty()
            status_text.empty()

            wf["search_results"] = url_result["search_results"]

            # Build initial url_selections (all selected by default)
            url_selections = {}
            for platform, details in url_result["url_map_detail"].items():
                url_selections[platform] = [
                    {"url": d["url"], "title": d["title"], "selected": True}
                    for d in details
                ]
            wf["url_selections"] = url_selections
            wf["step"] = 2
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Review URLs
# ═══════════════════════════════════════════════════════════════════════════

def _render_url_review():
    """Render the URL review/selection step."""
    wf = _get_wf()
    url_selections = wf.get("url_selections", {})

    # Summary counts
    total_urls = sum(len(v) for v in url_selections.values())
    total_selected = sum(
        1 for v in url_selections.values() for item in v if item.get("selected", True)
    )
    st.markdown(
        f"#### Review Discovered URLs &nbsp; "
        f"<span style='color:#94A3B8;font-size:0.85rem'>"
        f"{total_selected} of {total_urls} selected</span>",
        unsafe_allow_html=True,
    )
    st.caption("Deselect irrelevant URLs to avoid scraping wrong content.")

    # Per-platform tabs with data editors
    tabs = st.tabs([p.title() for p in wf["platforms"]])
    updated_selections = {}

    for i, platform in enumerate(wf["platforms"]):
        with tabs[i]:
            items = url_selections.get(platform, [])
            if not items:
                st.info(f"No URLs found for {platform.title()}.")
                updated_selections[platform] = []
                continue

            df = pd.DataFrame(items)
            # Ensure column order
            if "selected" not in df.columns:
                df["selected"] = True
            df = df[["selected", "title", "url"]]

            edited_df = st.data_editor(
                df,
                column_config={
                    "selected": st.column_config.CheckboxColumn("Select", default=True, width="small"),
                    "title": st.column_config.TextColumn("Title", width="large"),
                    "url": st.column_config.LinkColumn("URL", width="large"),
                },
                use_container_width=True,
                hide_index=True,
                key=f"url_editor_{platform}",
                num_rows="fixed",
            )

            updated_selections[platform] = edited_df.to_dict("records")
            selected_count = sum(1 for r in edited_df.to_dict("records") if r.get("selected"))
            st.caption(f"{selected_count} of {len(items)} selected")

    # Action buttons
    col_back, col_more, col_scrape = st.columns([1, 1, 2])

    with col_back:
        if st.button("Back to Queries", use_container_width=True):
            wf["step"] = 1
            st.rerun()

    with col_more:
        if st.button("Search More URLs", use_container_width=True):
            # Re-run search and merge new URLs
            progress_ph = st.empty()
            status_ph = st.empty()

            def _more_progress(msg: str):
                msg = str(msg).strip()
                if msg:
                    status_ph.markdown(
                        f'<div style="font-size:0.82rem;color:#94A3B8;padding:2px 0">'
                        f'{msg}</div>',
                        unsafe_allow_html=True,
                    )

            progress_ph.info("Searching for more URLs...")

            from search.pipeline import step_search_urls
            url_result = step_search_urls(
                queries=wf["queries"],
                platforms=wf["platforms"],
                max_urls_per_platform=wf["max_urls"] * 2,  # wider search
                topic=wf["topic"],
                relevance_keywords=wf.get("relevance_keywords"),
                progress_callback=_more_progress,
            )
            progress_ph.empty()
            status_ph.empty()

            # Merge: keep existing selections, add new URLs as selected
            for platform, new_details in url_result["url_map_detail"].items():
                existing_urls = {
                    item["url"] for item in updated_selections.get(platform, [])
                }
                current = list(updated_selections.get(platform, []))
                for d in new_details:
                    if d["url"] not in existing_urls:
                        current.append({
                            "url": d["url"], "title": d["title"], "selected": True,
                        })
                        existing_urls.add(d["url"])
                updated_selections[platform] = current

            wf["url_selections"] = updated_selections
            st.rerun()

    with col_scrape:
        if st.button("Scrape Selected URLs", type="primary", use_container_width=True):
            # Save current selections
            wf["url_selections"] = updated_selections

            # Build url_map from selected URLs only
            url_map = {}
            for platform, items in updated_selections.items():
                selected_urls = [
                    item["url"] for item in items if item.get("selected", True)
                ]
                if selected_urls:
                    url_map[platform] = selected_urls

            if not url_map:
                st.warning("No URLs selected. Please select at least one URL.")
                return

            wf["url_map_for_scrape"] = url_map
            wf["step"] = 3
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Scraping (auto-runs, then advances to step 4)
# ═══════════════════════════════════════════════════════════════════════════

def _render_scraping():
    """Run scraping with progress, then auto-advance to results."""
    wf = _get_wf()

    from utils.one_search_progress import OneSearchProgress

    progress_placeholder = st.empty()
    tracker = OneSearchProgress(progress_placeholder)

    url_map = wf.get("url_map_for_scrape", {})

    try:
        from search.pipeline import step_scrape_and_analyze

        result = run_async(
            step_scrape_and_analyze(
                url_map=url_map,
                platforms=wf["platforms"],
                cookies_map=wf.get("cookies_map") or None,
                max_comments_per_url=wf.get("max_comments", 200),
                topic=wf["topic"],
                progress_callback=tracker.on_message,
            )
        )

        tracker.complete(result.get("total_comments", 0))

        # Attach pipeline metadata to result
        result["queries"] = wf.get("queries", {})
        result["url_map_detail"] = {
            platform: [
                {"url": item["url"], "title": item["title"]}
                for item in wf.get("url_selections", {}).get(platform, [])
                if item.get("selected", True)
            ]
            for platform in wf["platforms"]
        }

        wf["result"] = result

        # In NLM mode, go to NLM setup step (step 4); otherwise go to Results (step 4)
        if _is_nlm_mode():
            wf["step"] = 4  # NLM Setup step
        else:
            wf["step"] = 4  # Results step (same index, but different label)
        st.rerun()

    except Exception as e:
        import traceback
        st.error(f"Scraping failed: {e}")
        st.code(traceback.format_exc(), language="text")
        # Allow going back
        if st.button("Back to URL Review"):
            wf["step"] = 2
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Results
# ═══════════════════════════════════════════════════════════════════════════

def _render_pipeline_details(result: dict):
    """Render an expandable panel showing pipeline transparency details."""
    with st.expander("Pipeline Details — Queries, URLs & Scrape Log", expanded=False):
        tab1, tab2, tab3 = st.tabs(["Generated Queries", "Discovered URLs", "Scrape Log"])

        with tab1:
            queries = result.get("queries", {})
            if queries:
                for platform, q_list in queries.items():
                    st.markdown(f"**{platform.title()}** ({len(q_list)} queries)")
                    st.code("\n".join(q_list), language="text")
            else:
                st.info("No query data available.")

        with tab2:
            url_map_detail = result.get("url_map_detail", {})
            if url_map_detail:
                for platform, details in url_map_detail.items():
                    if details:
                        st.markdown(f"**{platform.title()}** ({len(details)} URLs)")
                        df_urls = pd.DataFrame(details)
                        st.dataframe(
                            df_urls,
                            column_config={
                                "url": st.column_config.LinkColumn("URL", width="large"),
                                "title": st.column_config.TextColumn("Title", width="large"),
                            },
                            use_container_width=True,
                            hide_index=True,
                        )
            else:
                st.info("No URL detail data available.")

        with tab3:
            scrape_log = result.get("scrape_log", [])
            if scrape_log:
                df_log = pd.DataFrame(scrape_log)
                ok_count = sum(1 for s in scrape_log if s["status"] == "ok")
                empty_count = sum(1 for s in scrape_log if s["status"] == "empty")
                total_scraped_comments = sum(s["comment_count"] for s in scrape_log)
                m1, m2, m3 = st.columns(3)
                m1.metric("URLs with comments", ok_count)
                m2.metric("Empty URLs", empty_count)
                m3.metric("Total comments", total_scraped_comments)

                st.dataframe(
                    df_log,
                    column_config={
                        "platform": st.column_config.TextColumn("Platform", width="small"),
                        "url": st.column_config.LinkColumn("URL", width="large"),
                        "title": st.column_config.TextColumn("Title", width="medium"),
                        "comment_count": st.column_config.NumberColumn("Comments", width="small"),
                        "status": st.column_config.TextColumn("Status", width="small"),
                    },
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No scrape log data available.")


def _render_customer_insight(insight: dict, topic: str):
    """Render the AI Customer Insight Report."""
    if not isinstance(insight, dict):
        return

    st.markdown("### AI Customer Insight Report")

    # Executive Summary
    summary = insight.get("executive_summary", "")
    if summary:
        st.markdown(
            f'<div style="background:rgba(99,102,241,0.06);border-left:3px solid '
            f'rgba(99,102,241,0.4);padding:1rem 1.2rem;border-radius:0 8px 8px 0;'
            f'margin-bottom:1rem;font-size:0.92rem;line-height:1.6">{summary}</div>',
            unsafe_allow_html=True,
        )

    # Key Findings
    findings = insight.get("key_findings", [])
    if findings:
        with st.expander("Key Findings", expanded=True):
            for f in findings:
                if isinstance(f, dict):
                    st.markdown(f"**{f.get('finding', '')}**")
                    if f.get("evidence"):
                        st.caption(f"Evidence: {f['evidence']}")
                    if f.get("business_impact"):
                        st.markdown(f"*Impact:* {f['business_impact']}")
                    st.markdown("---")
                else:
                    st.markdown(f"- {f}")

    # Sentiment Overview
    sentiment = insight.get("sentiment_overview", {})
    if sentiment and isinstance(sentiment, dict):
        with st.expander("Sentiment Overview", expanded=True):
            overall = sentiment.get("overall", "unknown")
            sentiment_colors = {
                "positive": "#34D399", "negative": "#F87171",
                "neutral": "#94A3B8", "mixed": "#FBBF24",
            }
            color = sentiment_colors.get(overall, "#94A3B8")
            st.markdown(
                f"Overall: <span style='color:{color};font-weight:600'>"
                f"{overall.upper()}</span>",
                unsafe_allow_html=True,
            )

            sc1, sc2, sc3 = st.columns(3)
            sc1.metric("Positive", f"{sentiment.get('positive_percentage', 0)}%")
            sc2.metric("Negative", f"{sentiment.get('negative_percentage', 0)}%")
            sc3.metric("Neutral", f"{sentiment.get('neutral_percentage', 0)}%")

            drivers = sentiment.get("sentiment_drivers", [])
            if drivers:
                st.markdown("**Sentiment Drivers:**")
                for d in drivers:
                    st.markdown(f"- {d}")

    # Audience Profile
    audience = insight.get("audience_profile", {})
    if audience and isinstance(audience, dict):
        with st.expander("Audience Profile", expanded=False):
            for key in ["primary_demographics", "psychographics", "knowledge_level", "engagement_style"]:
                val = audience.get(key, "")
                if val:
                    label = key.replace("_", " ").title()
                    st.markdown(f"**{label}:** {val}")

    # Content Themes
    themes = insight.get("content_themes", [])
    if themes:
        with st.expander("Content Themes", expanded=False):
            for t in themes:
                if isinstance(t, dict):
                    freq = t.get("frequency", "")
                    freq_str = f" ({freq} mentions)" if freq else ""
                    st.markdown(f"**{t.get('theme', '')}{freq_str}**")
                    if t.get("description"):
                        st.markdown(t["description"])
                    quotes = t.get("notable_quotes", [])
                    for q in quotes[:2]:
                        st.caption(f'"{q}"')
                    st.markdown("---")

    # Recommendations
    recs = insight.get("actionable_recommendations", [])
    if recs:
        with st.expander("Actionable Recommendations", expanded=True):
            for r in recs:
                if isinstance(r, dict):
                    priority = r.get("priority", "medium")
                    p_colors = {"high": "#F87171", "medium": "#FBBF24", "low": "#34D399"}
                    p_color = p_colors.get(priority, "#94A3B8")
                    st.markdown(
                        f"<span style='color:{p_color};font-weight:600'>"
                        f"[{priority.upper()}]</span> {r.get('recommendation', '')}",
                        unsafe_allow_html=True,
                    )
                    if r.get("rationale"):
                        st.caption(r["rationale"])

    # Opportunities & Risks side by side
    opportunities = insight.get("opportunities", [])
    risks = insight.get("risks", [])
    if opportunities or risks:
        oc, rc = st.columns(2)
        with oc:
            if opportunities:
                with st.expander("Opportunities", expanded=False):
                    for o in opportunities:
                        if isinstance(o, dict):
                            st.markdown(f"**{o.get('opportunity', '')}**")
                            if o.get("suggested_action"):
                                st.caption(f"Action: {o['suggested_action']}")
        with rc:
            if risks:
                with st.expander("Risks", expanded=False):
                    for r in risks:
                        if isinstance(r, dict):
                            sev = r.get("severity", "medium")
                            st.markdown(f"**[{sev.upper()}]** {r.get('risk', '')}")
                            if r.get("mitigation"):
                                st.caption(f"Mitigation: {r['mitigation']}")


def _render_cross_platform(result: dict):
    """Render cross-platform comparison if 2+ platforms have data."""
    try:
        from utils.analysis_ui import render_platform_comparison
        render_platform_comparison(result)
    except Exception:
        pass


def _render_aspect_heatmap(result: dict):
    """Render aspect-based sentiment heatmap from AI tags."""
    tag_summary = result.get("tag_summary")
    if not tag_summary:
        return

    aspect_sentiment = tag_summary.get("aspect_sentiment", {})
    if not aspect_sentiment:
        return

    st.markdown("---")
    st.markdown("### Aspect-Based Sentiment")
    st.caption("What people specifically like and dislike — auto-discovered from comments.")

    # Build heatmap data
    rows = []
    for aspect, counts in aspect_sentiment.items():
        pos = counts.get("positive", 0)
        neu = counts.get("neutral", 0)
        neg = counts.get("negative", 0)
        total = pos + neu + neg
        if total > 0:
            rows.append({
                "Aspect": aspect.title(),
                "Positive": pos,
                "Neutral": neu,
                "Negative": neg,
                "Total": total,
            })

    if not rows:
        return

    # Sort by total mentions descending
    rows.sort(key=lambda r: r["Total"], reverse=True)
    # Limit to top 15 aspects
    rows = rows[:15]

    df = pd.DataFrame(rows)

    # Render as colored table
    col_map = {
        "Positive": "#34D399",
        "Neutral": "#94A3B8",
        "Negative": "#F87171",
    }

    # Build HTML table
    html = '<table style="width:100%;border-collapse:collapse;font-size:0.85rem">'
    html += '<tr style="border-bottom:2px solid rgba(255,255,255,0.1)">'
    for col in ["Aspect", "Positive", "Neutral", "Negative", "Total"]:
        html += f'<th style="text-align:left;padding:8px 12px;color:#94A3B8">{col}</th>'
    html += '</tr>'

    max_count = max(r["Total"] for r in rows) if rows else 1
    for row in rows:
        html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.05)">'
        html += f'<td style="padding:8px 12px;font-weight:600">{row["Aspect"]}</td>'
        for sent in ["Positive", "Neutral", "Negative"]:
            val = row[sent]
            color = col_map[sent]
            # Bar width proportional to count
            bar_width = int(val / max_count * 100) if max_count > 0 else 0
            html += (
                f'<td style="padding:8px 12px">'
                f'<div style="display:flex;align-items:center;gap:6px">'
                f'<div style="background:{color};height:8px;width:{bar_width}%;'
                f'border-radius:4px;min-width:2px;opacity:0.7"></div>'
                f'<span style="color:{color};font-size:0.8rem">{val}</span>'
                f'</div></td>'
            )
        html += f'<td style="padding:8px 12px;color:#64748B">{row["Total"]}</td>'
        html += '</tr>'
    html += '</table>'

    st.markdown(html, unsafe_allow_html=True)

    # Clickable aspect drill-down
    comments = result.get("comments_clean", [])
    if comments:
        aspect_names = [r["Aspect"].lower() for r in rows]
        selected_aspect = st.selectbox(
            "Drill into aspect",
            ["(select an aspect)"] + [r["Aspect"] for r in rows],
            key="aspect_drill",
        )
        if selected_aspect and selected_aspect != "(select an aspect)":
            aspect_lower = selected_aspect.lower()
            matching = []
            for c in comments:
                for asp in c.get("ai_aspects", []):
                    if asp.get("aspect", "").lower() == aspect_lower:
                        matching.append({
                            "text": c.get("text", ""),
                            "platform": c.get("platform", ""),
                            "aspect_sentiment": asp.get("sentiment", "neutral"),
                            "likes": c.get("likes", 0),
                        })
                        break
            if matching:
                st.markdown(f"**{len(matching)} comments about {selected_aspect}:**")
                for m in matching[:20]:
                    sent_color = {
                        "positive": "#34D399", "negative": "#F87171", "neutral": "#94A3B8",
                    }.get(m["aspect_sentiment"], "#94A3B8")
                    st.markdown(
                        f'<div style="border-left:3px solid {sent_color};padding:4px 12px;'
                        f'margin:4px 0;font-size:0.85rem">{m["text"][:300]}'
                        f'<span style="color:#64748B;font-size:0.75rem"> — {m["platform"].title()}'
                        f' | {m["likes"]} likes</span></div>',
                        unsafe_allow_html=True,
                    )


def _render_comment_explorer(result: dict, wf: dict):
    """Render the smart comment explorer with filters and search."""
    comments = result.get("comments_clean", [])
    if not comments:
        return

    st.markdown("---")
    st.markdown("### Comment Explorer")

    has_tags = any(c.get("ai_sentiment") for c in comments)
    # Full AI tags include intent and aspects (from LLM tagger, not VADER)
    has_full_tags = any(c.get("ai_intent") for c in comments)

    # Filter controls
    filter_cols = st.columns([1, 1, 1, 1, 2])

    with filter_cols[0]:
        all_platforms = sorted(set(c.get("platform", "unknown") for c in comments))
        sel_platforms = st.multiselect(
            "Platform", all_platforms,
            default=all_platforms,
            format_func=str.title,
            key="exp_platform",
        )

    with filter_cols[1]:
        if has_tags:
            sentiments = ["positive", "negative", "neutral", "mixed"]
            sel_sentiments = st.multiselect(
                "Sentiment", sentiments,
                default=sentiments,
                format_func=str.title,
                key="exp_sentiment",
            )
        else:
            sel_sentiments = None

    with filter_cols[2]:
        # Only show intent filter when full LLM tags are available (not VADER-only)
        if has_full_tags:
            all_intents = sorted(set(c.get("ai_intent", "other") for c in comments))
            sel_intents = st.multiselect(
                "Intent", all_intents,
                default=all_intents,
                format_func=lambda x: x.replace("_", " ").title(),
                key="exp_intent",
            )
        else:
            sel_intents = None

    with filter_cols[3]:
        sort_by = st.selectbox(
            "Sort by",
            ["likes", "date", "sentiment"],
            format_func=lambda x: x.title(),
            key="exp_sort",
        )

    with filter_cols[4]:
        search_text = st.text_input(
            "Search comments",
            placeholder="Type to search...",
            key="exp_search",
        )

    # Apply filters
    filtered = comments
    if sel_platforms:
        filtered = [c for c in filtered if c.get("platform", "unknown") in sel_platforms]
    if sel_sentiments and has_tags:
        filtered = [c for c in filtered if c.get("ai_sentiment", "neutral") in sel_sentiments]
    if sel_intents and has_tags:
        filtered = [c for c in filtered if c.get("ai_intent", "other") in sel_intents]
    if search_text:
        search_lower = search_text.lower()
        filtered = [c for c in filtered if search_lower in c.get("text", "").lower()]

    # Sort
    if sort_by == "likes":
        filtered.sort(key=lambda c: c.get("likes", 0), reverse=True)
    elif sort_by == "date":
        filtered.sort(key=lambda c: c.get("date", ""), reverse=True)
    elif sort_by == "sentiment" and has_tags:
        sent_order = {"negative": 0, "mixed": 1, "neutral": 2, "positive": 3}
        filtered.sort(key=lambda c: sent_order.get(c.get("ai_sentiment", "neutral"), 2))

    # Quick stats bar
    total_all = len(comments)
    total_shown = len(filtered)
    stats_parts = [f"Showing **{total_shown:,}** of {total_all:,} comments"]
    if has_tags and filtered:
        from collections import Counter
        sent_counts = Counter(c.get("ai_sentiment", "neutral") for c in filtered)
        top_sent = sent_counts.most_common(1)[0] if sent_counts else ("neutral", 0)
        pct = round(top_sent[1] / total_shown * 100) if total_shown else 0
        stats_parts.append(f"{pct}% {top_sent[0]}")

        # Top aspect
        aspect_counts = Counter()
        for c in filtered:
            for a in c.get("ai_aspects", []):
                aspect_counts[a.get("aspect", "")] += 1
        if aspect_counts:
            top_aspect = aspect_counts.most_common(1)[0][0]
            stats_parts.append(f"Top aspect: {top_aspect}")

    st.markdown(" | ".join(stats_parts))

    # Render comments as cards
    if not filtered:
        st.info("No comments match your filters.")
        return

    # Show up to 100 comments with pagination
    page_size = 50
    total_pages = (total_shown + page_size - 1) // page_size
    if total_pages > 1:
        page = st.number_input(
            "Page", min_value=1, max_value=total_pages, value=1, key="exp_page"
        )
    else:
        page = 1

    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_shown)
    page_comments = filtered[start_idx:end_idx]

    sent_colors = {
        "positive": "#34D399", "negative": "#F87171",
        "neutral": "#64748B", "mixed": "#FBBF24",
    }

    for c in page_comments:
        text = c.get("text", "")[:500]
        platform = c.get("platform", "unknown")
        username = c.get("username", "Anonymous")
        likes = c.get("likes", 0)
        date = c.get("date", "")

        # Build tag badges
        badges = f'<span style="background:rgba(59,130,246,0.15);color:#60A5FA;padding:1px 6px;border-radius:3px;font-size:0.7rem;margin-right:4px">{platform.title()}</span>'

        if has_tags:
            sentiment = c.get("ai_sentiment", "neutral")
            s_color = sent_colors.get(sentiment, "#64748B")
            badges += f'<span style="background:{s_color}22;color:{s_color};padding:1px 6px;border-radius:3px;font-size:0.7rem;margin-right:4px">{sentiment}</span>'

            # Intent and aspect badges only when full LLM tags are available
            if has_full_tags:
                intent = c.get("ai_intent", "other")
                badges += f'<span style="background:rgba(139,92,246,0.15);color:#A78BFA;padding:1px 6px;border-radius:3px;font-size:0.7rem;margin-right:4px">{intent.replace("_", " ")}</span>'

                # Aspect chips
                for asp in c.get("ai_aspects", [])[:3]:
                    a_name = asp.get("aspect", "")
                    a_sent = asp.get("sentiment", "neutral")
                    a_color = sent_colors.get(a_sent, "#64748B")
                    badges += f'<span style="background:{a_color}15;color:{a_color};padding:1px 6px;border-radius:3px;font-size:0.68rem;margin-right:3px">{a_name}</span>'

        st.markdown(
            f'<div style="border:1px solid rgba(255,255,255,0.06);border-radius:8px;'
            f'padding:10px 14px;margin:4px 0">'
            f'<div style="margin-bottom:4px">{badges}</div>'
            f'<div style="font-size:0.88rem;line-height:1.5">{text}</div>'
            f'<div style="font-size:0.72rem;color:#64748B;margin-top:4px">'
            f'@{username} | {likes} likes | {date}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if total_pages > 1:
        st.caption(f"Page {page} of {total_pages}")


def _regenerate_insight(wf: dict, result: dict):
    """Regenerate the AI Customer Insight Report using current data."""
    from ai.client import LLMClient
    from ai.prompts import format_comments_for_prompt, CUSTOMER_INSIGHT_REPORT

    all_clean = result.get("comments_clean", [])
    platforms_str = ", ".join(wf["platforms"])
    formatted = format_comments_for_prompt(all_clean[:500])

    tag_context = ""
    if result.get("tag_summary"):
        ts = result["tag_summary"]
        tag_context = (
            f"\n\nAI TAG SUMMARY (pre-classified data):\n"
            f"Sentiment: {ts.get('sentiment_distribution', {})}\n"
            f"Emotions: {ts.get('emotion_distribution', {})}\n"
            f"Intents: {ts.get('intent_distribution', {})}\n"
            f"Urgency: {ts.get('urgency_distribution', {})}\n"
            f"Aspect-Sentiment: {ts.get('aspect_sentiment', {})}\n"
            f"Use this pre-classified data to ground your analysis with precise numbers.\n"
        )

    prompt = CUSTOMER_INSIGHT_REPORT.format(
        comment_count=len(all_clean),
        topic=wf["topic"],
        platforms=platforms_str,
        comments=formatted + tag_context,
    )
    client = LLMClient()
    insight = run_async(client.analyze(prompt=prompt))
    result["customer_insight"] = insight


def _render_notebooklm_setup():
    """Render NotebookLM setup step: export comments, get notebook URL, run analysis."""
    wf = _get_wf()
    result = wf.get("result")

    if not result or not result.get("comments_clean"):
        st.warning("No comments available for analysis.")
        if st.button("Back to Scraping"):
            wf["step"] = 3
            st.rerun()
        return

    comments = result["comments_clean"]
    topic = wf.get("topic", "")

    st.markdown("### NotebookLM Analysis Setup")
    st.markdown(
        '<p style="font-size:0.88rem;color:#94A3B8">'
        'Upload your comments to NotebookLM for free AI-powered analysis. '
        'Follow the steps below.</p>',
        unsafe_allow_html=True,
    )

    # --- Step 1: Download comment file ---
    st.markdown("#### Step 1: Download Comment File")

    from utils.notebooklm_export import export_comments_markdown, estimate_word_count, split_for_notebooklm

    word_count = estimate_word_count(comments)
    files = split_for_notebooklm(comments, topic)

    if len(files) == 1:
        st.download_button(
            f"Download Comments ({len(comments):,} comments, ~{word_count:,} words)",
            data=files[0],
            file_name=f"comments_{topic.replace(' ', '_')}.md",
            mime="text/markdown",
            use_container_width=True,
            type="primary",
        )
    else:
        st.warning(f"Comments exceed NotebookLM's limit. Split into {len(files)} files.")
        for i, file_content in enumerate(files, 1):
            st.download_button(
                f"Download Part {i}/{len(files)}",
                data=file_content,
                file_name=f"comments_{topic.replace(' ', '_')}_part{i}.md",
                mime="text/markdown",
                use_container_width=True,
                key=f"nlm_download_{i}",
            )

    # --- Step 2: Instructions ---
    st.markdown("#### Step 2: Create NotebookLM Notebook")
    with st.expander("How to set up NotebookLM", expanded=False):
        st.markdown("""
1. Go to [notebooklm.google.com](https://notebooklm.google.com)
2. Click **+ New** to create a new notebook
3. Upload the downloaded comment file(s) as a source
4. Click **Share** (top right) and set to **"Anyone with the link"**
5. Copy the notebook URL and paste it below
        """)

    # --- Step 3: Notebook URL input ---
    st.markdown("#### Step 3: Paste Notebook URL")

    default_url = st.session_state.get("nlm_notebook_url", "")
    notebook_url = st.text_input(
        "NotebookLM Notebook URL",
        value=default_url,
        placeholder="https://notebooklm.google.com/notebook/...",
        key="nlm_url_onesearch",
        label_visibility="collapsed",
    )
    if notebook_url:
        st.session_state["nlm_notebook_url"] = notebook_url

    # Query budget info
    try:
        from ai.notebooklm_bridge import NotebookLMBridge
        from ai.notebooklm_queries import get_query_count
        n_queries = get_query_count(len(comments))
        remaining = NotebookLMBridge.queries_remaining()
        st.caption(
            f"This analysis will use ~{n_queries} queries. "
            f"You have {remaining} queries remaining today."
        )
        if n_queries > remaining:
            st.warning(
                f"Not enough queries remaining ({remaining} left, need {n_queries}). "
                "Try again tomorrow or switch to Paid API in Settings."
            )
    except Exception:
        pass

    # --- Action buttons ---
    col_back, col_skip, col_analyze = st.columns([1, 1, 2])

    with col_back:
        if st.button("Back", use_container_width=True, key="nlm_back"):
            wf["step"] = 2
            st.rerun()

    with col_skip:
        if st.button("Skip to Results", use_container_width=True, key="nlm_skip"):
            wf["step"] = 5  # Results
            st.rerun()

    with col_analyze:
        analyze_disabled = not notebook_url
        if st.button(
            "Analyze with NotebookLM",
            type="primary",
            use_container_width=True,
            disabled=analyze_disabled,
            key="nlm_analyze",
        ):
            if not notebook_url:
                st.warning("Please paste a NotebookLM notebook URL first.")
                return

            _run_notebooklm_analysis(wf, result, notebook_url)


def _run_notebooklm_analysis(wf: dict, result: dict, notebook_url: str):
    """Execute NotebookLM queries and populate the customer_insight."""
    from ai.notebooklm_bridge import get_bridge, NotebookLMBridge
    from ai.notebooklm_queries import get_analysis_queries
    from ai.notebooklm_parser import compose_customer_insight, insight_to_tag_summary

    comments = result.get("comments_clean", [])
    topic = wf.get("topic", "")
    platforms = wf.get("platforms", [])

    queries = get_analysis_queries(topic, len(comments), platforms)
    bridge = get_bridge()

    progress = st.progress(0.0, text="Connecting to NotebookLM...")
    parsed_results = {}
    session_id = None

    for i, query in enumerate(queries):
        qid = query["id"]
        progress_pct = (i + 1) / len(queries)
        progress.progress(
            progress_pct,
            text=f"Querying NotebookLM ({i+1}/{len(queries)}): {qid.replace('_', ' ').title()}...",
        )

        try:
            answer, session_id = run_async(
                bridge.ask_question(
                    question=query["question"],
                    notebook_url=notebook_url,
                    session_id=session_id,
                )
            )
            parsed_results[qid] = answer
            NotebookLMBridge.increment_usage()
        except Exception as e:
            st.warning(f"Query '{qid}' failed: {e}")
            parsed_results[qid] = ""

    progress.progress(1.0, text="Analysis complete!")

    # Compose the customer insight
    if any(parsed_results.values()):
        insight = compose_customer_insight(parsed_results)
        result["customer_insight"] = insight

        # Reconstruct tag_summary for heatmap
        tag_summary = insight_to_tag_summary(insight)
        if tag_summary:
            # Merge with existing VADER-based tag_summary
            existing = result.get("tag_summary", {})
            existing["aspect_sentiment"] = tag_summary.get("aspect_sentiment", {})
            result["tag_summary"] = existing

        wf["result"] = result
        st.success(f"NotebookLM analysis complete! Used {len(queries)} queries.")
    else:
        st.error("All queries failed. Check the notebook URL and try again.")
        return

    wf["step"] = 5  # Results
    st.rerun()


def _render_results():
    """Render the results step."""
    wf = _get_wf()
    result = wf.get("result")

    if not result:
        st.warning("No results available.")
        if st.button("New Search", type="primary"):
            _reset_wf()
            st.rerun()
        return

    from utils.common import export_csv_bytes, export_json_bytes, fmt_num

    total = result.get("total_comments", 0)

    if total > 0:
        # Platform breakdown
        st.markdown("### Results Summary")
        raw_by_platform = result.get("comments_raw", {})
        platforms = wf["platforms"]
        summary_cols = st.columns(len(platforms))
        for i, platform in enumerate(platforms):
            count = len(raw_by_platform.get(platform, []))
            summary_cols[i].metric(platform.title(), fmt_num(count))

        # Store in session state for other pages
        clean_comments = result.get("comments_clean", [])
        st.session_state["last_scrape"] = {
            "comments": clean_comments,
            "raw_comments": [],
            "platform": "multi",
            "count": len(clean_comments),
        }

        # --- AI Customer Insight Report (prominent, at top) ---
        customer_insight = result.get("customer_insight")
        if customer_insight:
            _render_customer_insight(customer_insight, wf["topic"])
            # Regenerate button
            if _is_nlm_mode():
                if st.button("Re-analyze with NotebookLM", key="regen_insight"):
                    wf["step"] = 4  # Back to NLM Setup
                    st.rerun()
            elif st.button("Regenerate AI Report", key="regen_insight"):
                with st.spinner("Regenerating AI Customer Insight Report..."):
                    try:
                        _regenerate_insight(wf, result)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Regeneration failed: {e}")
        elif not customer_insight and clean_comments:
            # Show a button to generate if it wasn't auto-generated
            st.markdown("---")
            if _is_nlm_mode():
                # In NLM mode, offer to go back to NLM setup
                if st.button("Generate Report via NotebookLM", type="primary", key="gen_insight_nlm"):
                    wf["step"] = 4  # NLM Setup
                    st.rerun()
            elif st.button("Generate AI Customer Insight Report", type="primary", key="gen_insight"):
                with st.spinner("Generating AI Customer Insight Report..."):
                    try:
                        _regenerate_insight(wf, result)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Generation failed: {e}")

        # --- Cross-Platform Comparison (if 2+ platforms) ---
        _render_cross_platform(result)

        # --- Aspect-Based Sentiment Heatmap (if tags available) ---
        _render_aspect_heatmap(result)

        # --- Smart Comment Explorer ---
        _render_comment_explorer(result, wf)

        # Download buttons
        st.markdown("")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Export CSV",
                data=export_csv_bytes(clean_comments),
                file_name=f"one_search_{wf['topic'].replace(' ', '_')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "Export JSON",
                data=export_json_bytes(clean_comments),
                file_name=f"one_search_{wf['topic'].replace(' ', '_')}.json",
                mime="application/json",
                use_container_width=True,
            )

        # Pipeline transparency
        _render_pipeline_details(result)

        # Analysis dashboard (VADER + LDA — fallback / supplementary)
        analysis = result.get("analysis")
        if analysis:
            try:
                from utils.analysis_ui import render_analysis_dashboard
                render_analysis_dashboard(analysis)
            except ImportError:
                pass

    else:
        st.info(
            "No comments found for this topic. Try a different search term, "
            "broader date range, or different platforms."
        )
        _render_pipeline_details(result)

    # New Search button
    st.markdown("")
    if st.button("New Search", type="primary", use_container_width=True):
        _reset_wf()
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# Main page logic — route to current step
# ═══════════════════════════════════════════════════════════════════════════

wf = _get_wf()
current_step = wf.get("step", 0)

# Show step indicator for steps > 0
if current_step > 0:
    _render_step_indicator(current_step)

# Route to the current step
if current_step == 0:
    _render_input()
elif current_step == 1:
    _render_query_review()
elif current_step == 2:
    _render_url_review()
elif current_step == 3:
    _render_scraping()
elif current_step == 4:
    if _is_nlm_mode():
        _render_notebooklm_setup()
    else:
        _render_results()
elif current_step == 5:
    _render_results()
