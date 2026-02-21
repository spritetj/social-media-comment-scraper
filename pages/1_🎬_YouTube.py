"""
YouTube Comment Scraper — Streamlit Page
"""

import streamlit as st
import nest_asyncio
import asyncio
import time
from pathlib import Path

nest_asyncio.apply()

st.set_page_config(
    page_title="YouTube — Comment Scraper",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Load custom CSS
css_path = Path(__file__).parent.parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Navigation — compact centered
_, n1, n2, n3, n4, n5, n6, _ = st.columns([3, 1, 1, 1, 1, 1, 0.8, 3])
with n1:
    st.page_link("Home.py", label="Home")
with n2:
    st.page_link("pages/1_🎬_YouTube.py", label="YouTube")
with n3:
    st.page_link("pages/2_🎵_TikTok.py", label="TikTok")
with n4:
    st.page_link("pages/3_📘_Facebook.py", label="Facebook")
with n5:
    st.page_link("pages/4_📷_Instagram.py", label="Instagram")
with n6:
    qr_path = Path(__file__).parent.parent / "assets" / "qr_payment.jpeg"
    if qr_path.exists():
        with st.popover("Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)

st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)

# Page header
st.markdown('<div class="page-header"><h1>YouTube</h1></div>', unsafe_allow_html=True)
st.markdown('<p class="page-desc">Extract comments and replies from any YouTube video.</p>', unsafe_allow_html=True)

# URL input
url_input = st.text_area(
    "Enter YouTube video URL(s)",
    placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ\nhttps://youtu.be/jNQXAC9IVRw",
    height=100,
    label_visibility="collapsed",
)

# Settings expander
with st.expander("Settings"):
    s1, s2, s3 = st.columns(3)
    with s1:
        max_comments = st.slider(
            "Max comments per video",
            min_value=0, max_value=5000, value=0, step=100,
            help="0 = fetch all comments",
        )
    with s2:
        max_replies = st.slider(
            "Max replies per comment",
            min_value=-1, max_value=100, value=5, step=1,
            help="-1 = skip replies, 0 = all replies",
        )
    with s3:
        sort_by = st.selectbox("Sort comments by", ["top", "newest"], index=0)

# Authentication expander
with st.expander("Authentication"):
    cookie_file = st.file_uploader(
        "Upload cookies.txt (optional)",
        type=["txt", "json"],
        help="Upload YouTube cookies for authenticated access",
    )

# Start button
scrape_btn = st.button("Start Scraping", type="primary", use_container_width=True)

# Results area
if scrape_btn and url_input.strip():
    urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

    if not urls:
        st.warning("Please enter at least one YouTube URL.")
        st.stop()

    # Import scraper
    try:
        from scrapers.youtube import YouTubeCommentScraper, extract_video_id
        from utils.common import export_csv_bytes, export_json_bytes, fmt_num
        from utils.progress_ui import ProgressTracker
    except ImportError as e:
        st.error(f"Import error: {e}. Make sure you're running from the project directory.")
        st.stop()

    # Validate URLs
    valid_urls = []
    for url in urls:
        vid = extract_video_id(url)
        if vid:
            valid_urls.append(url)
        else:
            st.warning(f"Skipping invalid URL: {url}")

    if not valid_urls:
        st.error("No valid YouTube URLs found.")
        st.stop()

    # Load cookies if uploaded
    cookies = {}
    if cookie_file:
        from utils.common import load_cookies_generic
        content = cookie_file.read().decode("utf-8")
        cookies = load_cookies_generic(content, "youtube.com")

    # Progress display
    progress_placeholder = st.empty()
    tracker = ProgressTracker(total_videos=len(valid_urls), placeholder=progress_placeholder)
    all_comments = []

    # Create scraper
    scraper = YouTubeCommentScraper(
        headless=True,
        max_comments=max_comments,
        max_replies=max_replies,
        sort_by=sort_by,
        progress_callback=tracker.on_message,
    )
    if cookies:
        scraper.set_cookies(cookies)

    # Run scraper
    start_time = time.time()

    loop = asyncio.new_event_loop()
    for i, url in enumerate(valid_urls):
        tracker.on_message(f"--- Video {i+1}/{len(valid_urls)} ---")
        try:
            comments = loop.run_until_complete(scraper.scrape_video_comments(url))
            if comments:
                all_comments.extend(comments)
                tracker.on_message(f"Got {len(comments)} comments!")
            else:
                tracker.on_message("No comments found.")
        except Exception as e:
            tracker.on_message(f"Something went wrong. Please try again.")
    loop.close()

    elapsed = time.time() - start_time
    tracker.complete(len(all_comments), elapsed)

    # Results
    if all_comments:
        st.markdown("")

        # Summary metrics
        replies = [c for c in all_comments if c.get("threadingDepth", 0) > 0]
        total_likes = sum(c.get("likesCount", 0) for c in all_comments)

        m1, m2, m3 = st.columns(3)
        m1.metric("Comments", fmt_num(len(all_comments)))
        m2.metric("Replies", fmt_num(len(replies)))
        m3.metric("Total Likes", fmt_num(total_likes))

        # Data table
        import pandas as pd
        df = pd.DataFrame(all_comments)
        display_cols = ["profileName", "text", "likesCount", "commentsCount", "date", "threadingDepth"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available_cols], use_container_width=True, height=400)

        # Download buttons
        st.markdown("")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "Export CSV",
                data=export_csv_bytes(all_comments),
                file_name="youtube_comments.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "Export JSON",
                data=export_json_bytes(all_comments),
                file_name="youtube_comments.json",
                mime="application/json",
                use_container_width=True,
            )
    else:
        st.info("No comments were found. The video(s) may have comments disabled.")

elif scrape_btn:
    st.warning("Please enter at least one YouTube URL above.")
