"""
Social Media Comment Scraper — Landing Page
=============================================
Streamlit multi-page app entry point.
"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Social Media Comment Scraper",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load custom CSS
css_path = Path(__file__).parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### 💬 Comment Scraper")
    st.markdown("---")
    st.markdown("Select a platform from the sidebar to start scraping comments.")
    st.markdown("")
    st.markdown(
        "**Supported Platforms:**\n"
        "- 🎬 YouTube\n"
        "- 🎵 TikTok\n"
        "- 📘 Facebook\n"
        "- 📷 Instagram"
    )
    st.markdown("---")
    qr_path = Path(__file__).parent / "assets" / "qr_payment.jpeg"
    if qr_path.exists():
        with st.popover("☕ Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)

# Hero section
st.markdown("")
st.markdown(
    '<h1 class="hero-title">Social Media Comment Scraper</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    "**Extract comments from any social media post — fast and easy.**"
)
st.markdown("---")

# Platform cards in 2x2 grid
col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        <div class="platform-card">
            <h3>🎬 YouTube</h3>
            <p>Extract comments & replies from any YouTube video. Supports sorting, bulk URLs, and full reply threads.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Start Scraping YouTube →", key="yt_btn", use_container_width=True):
        st.switch_page("pages/1_🎬_YouTube.py")

    st.markdown("")

    st.markdown(
        """
        <div class="platform-card">
            <h3>📘 Facebook</h3>
            <p>Scrape comments from Facebook posts, reels, and videos. Supports all comment types and nested replies.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Start Scraping Facebook →", key="fb_btn", use_container_width=True):
        st.switch_page("pages/3_📘_Facebook.py")

with col2:
    st.markdown(
        """
        <div class="platform-card">
            <h3>🎵 TikTok</h3>
            <p>Extract comments & replies from TikTok videos. Includes video captions and reply threads.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Start Scraping TikTok →", key="tt_btn", use_container_width=True):
        st.switch_page("pages/2_🎵_TikTok.py")

    st.markdown("")

    st.markdown(
        """
        <div class="platform-card">
            <h3>📷 Instagram</h3>
            <p>Scrape comments from Instagram posts and reels. Includes nested replies and captions.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Start Scraping Instagram →", key="ig_btn", use_container_width=True):
        st.switch_page("pages/4_📷_Instagram.py")

# Footer
st.markdown("---")

footer_col1, footer_col2 = st.columns([4, 1])
with footer_col1:
    st.markdown(
        '<div class="pro-footer" style="text-align:left;">Built with care. All platforms supported.</div>',
        unsafe_allow_html=True,
    )
with footer_col2:
    qr_path = Path(__file__).parent / "assets" / "qr_payment.jpeg"
    if qr_path.exists():
        with st.popover("☕ Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)
