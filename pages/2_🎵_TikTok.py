"""
TikTok Comment Scraper — Streamlit Page
"""

import streamlit as st
import nest_asyncio
import asyncio
import time

nest_asyncio.apply()

st.set_page_config(page_title="TikTok Scraper", page_icon="🎵", layout="wide")

st.markdown("## 🎵 TikTok Comment Scraper")
st.markdown("Extract comments & replies from TikTok videos using direct API with browser fallback.")
st.markdown("---")

# Sidebar settings
with st.sidebar:
    st.markdown("### Settings")
    max_comments = st.slider(
        "Max comments per video",
        min_value=0, max_value=5000, value=0, step=100,
        help="0 = fetch all comments",
    )
    max_replies = st.slider(
        "Max replies per comment",
        min_value=-1, max_value=100, value=5, step=1,
        help="-1 = skip replies, 0 = all replies",
    )

    st.markdown("---")
    st.info(
        "TikTok's direct API works without a browser. "
        "If it fails, the scraper will try browser-based methods (requires Playwright)."
    )

# Main input
url_input = st.text_area(
    "Enter TikTok video URL(s)",
    placeholder="https://www.tiktok.com/@username/video/1234567890\nhttps://vm.tiktok.com/abcdef/",
    height=100,
    help="One URL per line. Supports full URLs and short URLs (vm.tiktok.com).",
)

col_btn, col_info = st.columns([1, 3])
with col_btn:
    scrape_btn = st.button("🚀 Start Scraping", type="primary", use_container_width=True)
with col_info:
    st.caption("Uses TikTok's comment API directly — fast and reliable.")

# Results area
if scrape_btn and url_input.strip():
    urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

    if not urls:
        st.warning("Please enter at least one TikTok URL.")
        st.stop()

    # Import scraper
    try:
        from scrapers.tiktok import TikTokCommentScraper
        from utils.common import export_csv_bytes, export_json_bytes, fmt_num
    except ImportError as e:
        st.error(f"Import error: {e}. Make sure you're running from the project directory.")
        st.stop()

    # Progress display
    progress_container = st.status(f"Scraping {len(urls)} video(s)...", expanded=True)
    all_comments = []

    def on_progress(msg):
        progress_container.write(msg)

    # Create scraper
    scraper = TikTokCommentScraper(
        headless=True,
        max_comments=max_comments,
        max_replies=max_replies,
        progress_callback=on_progress,
    )

    # Run scraper
    start_time = time.time()

    loop = asyncio.new_event_loop()
    for i, url in enumerate(urls):
        on_progress(f"--- Video {i+1}/{len(urls)} ---")
        try:
            comments = loop.run_until_complete(scraper.scrape_video_comments(url))
            if comments:
                all_comments.extend(comments)
                on_progress(f"Got {len(comments)} comments!")
            else:
                on_progress("No comments found for this video")
        except Exception as e:
            on_progress(f"Error: {e}")
    loop.close()

    elapsed = time.time() - start_time
    progress_container.update(label=f"Done! {len(all_comments)} comments in {elapsed:.1f}s", state="complete")

    # Results
    if all_comments:
        st.markdown("---")
        st.markdown("### Results")

        # Summary metrics
        top_level = [c for c in all_comments if not c.get("is_reply")]
        replies = [c for c in all_comments if c.get("is_reply")]
        total_likes = sum(c.get("like_count", 0) for c in all_comments)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Comments", fmt_num(len(all_comments)))
        m2.metric("Top-level", fmt_num(len(top_level)))
        m3.metric("Replies", fmt_num(len(replies)))
        m4.metric("Total Likes", fmt_num(total_likes))

        # Data table
        import pandas as pd
        df = pd.DataFrame(all_comments)
        display_cols = ["username", "text", "like_count", "reply_count", "created_at", "is_reply"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available_cols], use_container_width=True, height=400)

        # Download buttons
        st.markdown("### Download")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "📥 Download CSV",
                data=export_csv_bytes(all_comments),
                file_name="tiktok_comments.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "📥 Download JSON",
                data=export_json_bytes(all_comments),
                file_name="tiktok_comments.json",
                mime="application/json",
                use_container_width=True,
            )
    else:
        st.info("No comments were found. The video may have no comments or comments may be disabled.")

elif scrape_btn:
    st.warning("Please enter at least one TikTok URL above.")
