"""
One Search — Interactive step-by-step social listening workflow.

Steps:
  0. Input — topic, platforms, options
  1. Review Queries — edit LLM-generated queries before searching
  2. Review URLs — select/deselect discovered URLs before scraping
  3. Scraping — progress tracker while scraping + analysis
  4. Results — comments table, analysis dashboard, AI Customer Insight
"""

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

_STEP_LABELS = ["Input", "Queries", "URLs", "Scraping", "Results"]


def _get_wf() -> dict:
    """Get or initialize workflow state."""
    if "os_wf" not in st.session_state:
        st.session_state["os_wf"] = {"step": 0}
    return st.session_state["os_wf"]


def _reset_wf():
    """Reset workflow to step 0."""
    st.session_state["os_wf"] = {"step": 0}


# ═══════════════════════════════════════════════════════════════════════════
# Step indicator
# ═══════════════════════════════════════════════════════════════════════════

def _render_step_indicator(current_step: int):
    """Render a horizontal step progress bar."""
    steps_html = ""
    for i, label in enumerate(_STEP_LABELS):
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
    st.caption("One query per line. Add, remove, or edit freely.")

    # Per-platform text areas
    edited_queries = {}
    tabs = st.tabs([p.title() for p in wf["platforms"]])
    for i, platform in enumerate(wf["platforms"]):
        with tabs[i]:
            current = wf["queries"].get(platform, [])
            text = st.text_area(
                f"Queries for {platform.title()}",
                value="\n".join(current),
                height=200,
                key=f"qa_{platform}",
                label_visibility="collapsed",
            )
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            edited_queries[platform] = lines
            st.caption(f"{len(lines)} queries")

    # Action buttons
    col_back, col_approve = st.columns([1, 3])
    with col_back:
        if st.button("Back", use_container_width=True):
            wf["step"] = 0
            st.rerun()
    with col_approve:
        if st.button("Approve & Search Google", type="primary", use_container_width=True):
            wf["queries"] = edited_queries

            # Run URL search
            with st.spinner("Searching Google for URLs..."):
                from search.pipeline import step_search_urls
                url_result = step_search_urls(
                    queries=edited_queries,
                    platforms=wf["platforms"],
                    max_urls_per_platform=wf["max_urls"],
                    topic=wf["topic"],
                    relevance_keywords=wf.get("relevance_keywords"),
                )

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
            with st.spinner("Searching for more URLs..."):
                from search.pipeline import step_search_urls
                url_result = step_search_urls(
                    queries=wf["queries"],
                    platforms=wf["platforms"],
                    max_urls_per_platform=wf["max_urls"] * 2,  # wider search
                    topic=wf["topic"],
                    relevance_keywords=wf.get("relevance_keywords"),
                )

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
        wf["step"] = 4
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

        # Data table
        if clean_comments:
            df = pd.DataFrame(clean_comments)
            display_cols = ["platform", "username", "text", "likes", "replies", "date"]
            available_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[available_cols], use_container_width=True, height=400)

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

        # Analysis dashboard
        analysis = result.get("analysis")
        if analysis:
            try:
                from utils.analysis_ui import render_analysis_dashboard
                render_analysis_dashboard(analysis)
            except ImportError:
                pass

        # AI Customer Insight Report
        customer_insight = result.get("customer_insight")
        if customer_insight:
            _render_customer_insight(customer_insight, wf["topic"])

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
    _render_results()
