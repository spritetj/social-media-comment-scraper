"""
Instagram Comment Scraper — Streamlit Page
"""

import streamlit as st
import nest_asyncio
import asyncio
import time

nest_asyncio.apply()

st.set_page_config(page_title="Instagram Scraper", page_icon="📷", layout="wide")

st.markdown("## 📷 Instagram Comment Scraper")
st.markdown("Scrape comments from Instagram posts and reels using embedded Relay data extraction.")
st.markdown("---")

# Cookie info
st.info(
    "**Cookies Optional but Recommended:** Instagram works without cookies for basic comment extraction. "
    "Upload cookies for authenticated access to get more comments and replies. "
    "[How to export cookies](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)"
)

# Check for Playwright
playwright_available = False
try:
    import playwright
    playwright_available = True
except ImportError:
    pass

if not playwright_available:
    st.error(
        "**Playwright is required** for Instagram scraping. "
        "Install it with:\n```\npip install playwright && python -m playwright install chromium\n```"
    )
    st.stop()

# Sidebar settings
with st.sidebar:
    st.markdown("### Cookies (Optional)")
    cookie_file = st.file_uploader(
        "Upload cookies.txt or cookies.json",
        type=["txt", "json"],
        help="Export cookies from your browser while logged into Instagram",
    )

    st.markdown("---")
    st.markdown("### Info")
    st.markdown(
        "Instagram comments are extracted from embedded Relay/GraphQL data in the page. "
        "With cookies, the scraper can paginate through all comments via the REST API."
    )

# Main input
url_input = st.text_area(
    "Enter Instagram post URL(s)",
    placeholder="https://www.instagram.com/p/ABC123/\nhttps://www.instagram.com/reel/XYZ789/",
    height=100,
    help="One URL per line. Supports /p/ (posts) and /reel/ URLs.",
)

col_btn, col_info = st.columns([1, 3])
with col_btn:
    scrape_btn = st.button("🚀 Start Scraping", type="primary", use_container_width=True)
with col_info:
    st.caption("Uses Playwright to load the page and extract embedded comment data.")

# Results area
if scrape_btn and url_input.strip():
    urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

    if not urls:
        st.warning("Please enter at least one Instagram URL.")
        st.stop()

    # Import scraper
    try:
        from scrapers.instagram import scrape_post_urls
        from utils.common import load_cookies_as_list, export_csv_bytes, export_json_bytes, fmt_num
    except ImportError as e:
        st.error(f"Import error: {e}. Make sure you're running from the project directory.")
        st.stop()

    # Load cookies if uploaded
    cookies = None
    if cookie_file:
        cookie_content = cookie_file.read().decode("utf-8")
        cookies = load_cookies_as_list(cookie_content, "instagram.com")
        if cookies:
            st.sidebar.success(f"Loaded {len(cookies)} cookies")
        else:
            st.sidebar.warning("Could not parse cookies from file")

    # Progress display
    progress_container = st.status(f"Scraping {len(urls)} post(s)...", expanded=True)

    def on_progress(msg):
        progress_container.write(msg)

    # Run scraper
    start_time = time.time()

    loop = asyncio.new_event_loop()
    try:
        all_comments = loop.run_until_complete(
            scrape_post_urls(urls, cookies=cookies, progress_callback=on_progress)
        )
    except Exception as e:
        all_comments = []
        on_progress(f"Error: {e}")
    loop.close()

    elapsed = time.time() - start_time
    progress_container.update(label=f"Done! {len(all_comments)} comments in {elapsed:.1f}s", state="complete")

    # Results
    if all_comments:
        st.markdown("---")
        st.markdown("### Results")

        # Summary metrics
        top_level = [c for c in all_comments if c.get("threadingDepth", 0) == 0]
        replies = [c for c in all_comments if c.get("threadingDepth", 0) > 0]
        total_likes = sum(c.get("likesCount", 0) for c in all_comments)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Comments", fmt_num(len(all_comments)))
        m2.metric("Top-level", fmt_num(len(top_level)))
        m3.metric("Replies", fmt_num(len(replies)))
        m4.metric("Total Likes", fmt_num(total_likes))

        # Data table
        import pandas as pd
        df = pd.DataFrame(all_comments)
        display_cols = ["ownerUsername", "text", "likesCount", "repliesCount", "date", "threadingDepth"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[available_cols], use_container_width=True, height=400)

        # Download buttons
        st.markdown("### Download")
        dl1, dl2 = st.columns(2)
        with dl1:
            st.download_button(
                "📥 Download CSV",
                data=export_csv_bytes(all_comments),
                file_name="instagram_comments.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with dl2:
            st.download_button(
                "📥 Download JSON",
                data=export_json_bytes(all_comments),
                file_name="instagram_comments.json",
                mime="application/json",
                use_container_width=True,
            )
    else:
        st.info("No comments were found. The post may have no comments or require login.")

elif scrape_btn:
    st.warning("Please enter at least one Instagram URL above.")
