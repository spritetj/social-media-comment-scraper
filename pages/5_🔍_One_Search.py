"""
One Search — Multi-platform social listening in one click.
"""

import streamlit as st
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

# Check tier access (set to "pro" for testing — remove in production)
st.session_state.setdefault("user_tier", "pro")
try:
    from config.gating import check_feature
    if not check_feature("one_search"):
        st.stop()
except ImportError:
    pass

# Search input
topic = st.text_input(
    "What do you want to research?",
    placeholder="Tesla Model 3, iPhone 16, Nike Air Max...",
    label_visibility="collapsed",
)

# Platform selection
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
                "any": "Any time",
                "week": "Past week",
                "month": "Past month",
                "year": "Past year",
            }[x],
        )

    adv1, adv2 = st.columns(2)
    with adv1:
        max_urls = st.slider("Max URLs per platform", 5, 50, 15, step=5)
    with adv2:
        max_comments = st.slider("Max comments per URL", 50, 500, 200, step=50)

    # Cookie uploads for auth-required platforms
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

# Start button
search_btn = st.button("Start Research", type="primary", use_container_width=True)

if search_btn and topic.strip():
    from utils.one_search_progress import OneSearchProgress
    from utils.common import export_csv_bytes, export_json_bytes, fmt_num

    # Progress tracker
    progress_placeholder = st.empty()
    tracker = OneSearchProgress(progress_placeholder)

    # Run the pipeline
    try:
        from search.pipeline import run_one_search

        result = run_async(
            run_one_search(
                topic=topic.strip(),
                platforms=platforms,
                date_range=date_range,
                max_urls_per_platform=max_urls,
                max_comments_per_url=max_comments,
                cookies_map=cookies_map or None,
                progress_callback=tracker.on_message,
            )
        )

        tracker.complete(result.get("total_comments", 0))

    except Exception as e:
        import traceback
        st.error(f"One Search failed: {e}")
        st.code(traceback.format_exc(), language="text")
        result = None

    if result and result.get("total_comments", 0) > 0:
        st.markdown("")

        # Platform breakdown
        st.markdown("### Results Summary")
        raw_by_platform = result.get("comments_raw", {})
        summary_cols = st.columns(len(platforms))
        for i, platform in enumerate(platforms):
            count = len(raw_by_platform.get(platform, []))
            summary_cols[i].metric(platform.title(), fmt_num(count))

        # Store in session state
        clean_comments = result.get("comments_clean", [])
        st.session_state["last_scrape"] = {
            "comments": clean_comments,
            "raw_comments": [],
            "platform": "multi",
            "count": len(clean_comments),
        }

        # Data table
        if clean_comments:
            import pandas as pd
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
                file_name=f"one_search_{topic.strip().replace(' ', '_')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "Export JSON",
                data=export_json_bytes(clean_comments),
                file_name=f"one_search_{topic.strip().replace(' ', '_')}.json",
                mime="application/json",
                use_container_width=True,
            )

        # Analysis dashboard
        analysis = result.get("analysis")
        if analysis:
            try:
                from utils.analysis_ui import render_analysis_dashboard
                render_analysis_dashboard(analysis)
            except ImportError:
                pass

    elif result:
        st.info(
            "No comments found for this topic. Try a different search term, "
            "broader date range, or different platforms."
        )

elif search_btn:
    st.warning("Please enter a topic to research.")
