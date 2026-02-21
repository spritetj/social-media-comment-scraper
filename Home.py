"""
Social Media Comment Scraper — Landing Page
=============================================
Streamlit multi-page app entry point.
"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Comment Scraper",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Load custom CSS
css_path = Path(__file__).parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Sidebar — minimal
with st.sidebar:
    st.markdown("### Comment Scraper")
    qr_path = Path(__file__).parent / "assets" / "qr_payment.jpeg"
    if qr_path.exists():
        with st.popover("Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)

# Navigation bar
nav_cols = st.columns(5)
with nav_cols[0]:
    st.page_link("Home.py", label="Home", icon="🏠")
with nav_cols[1]:
    st.page_link("pages/1_🎬_YouTube.py", label="YouTube", icon="🎬")
with nav_cols[2]:
    st.page_link("pages/2_🎵_TikTok.py", label="TikTok", icon="🎵")
with nav_cols[3]:
    st.page_link("pages/3_📘_Facebook.py", label="Facebook", icon="📘")
with nav_cols[4]:
    st.page_link("pages/4_📷_Instagram.py", label="Instagram", icon="📷")

# Hero section
st.markdown("")
st.markdown('<p class="hero-eyebrow">Social Media Toolkit</p>', unsafe_allow_html=True)
st.markdown(
    '<h1 class="hero-title">Comment Scraper.</h1>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="hero-subtitle">Extract comments from any platform. Fast, simple, powerful.</p>',
    unsafe_allow_html=True,
)

st.markdown("")
st.markdown("")

# Platform cards in 2x2 grid
col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        <div class="platform-card">
            <div class="platform-card-icon yt">🎬</div>
            <h3>YouTube</h3>
            <p>Comments and replies from any video.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open", key="yt_btn", use_container_width=True):
        st.switch_page("pages/1_🎬_YouTube.py")

    st.markdown("")

    st.markdown(
        """
        <div class="platform-card">
            <div class="platform-card-icon fb">📘</div>
            <h3>Facebook</h3>
            <p>Posts, reels, and video comments.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open", key="fb_btn", use_container_width=True):
        st.switch_page("pages/3_📘_Facebook.py")

with col2:
    st.markdown(
        """
        <div class="platform-card">
            <div class="platform-card-icon tt">🎵</div>
            <h3>TikTok</h3>
            <p>Video comments and reply threads.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open", key="tt_btn", use_container_width=True):
        st.switch_page("pages/2_🎵_TikTok.py")

    st.markdown("")

    st.markdown(
        """
        <div class="platform-card">
            <div class="platform-card-icon ig">📷</div>
            <h3>Instagram</h3>
            <p>Post and reel comments with replies.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open", key="ig_btn", use_container_width=True):
        st.switch_page("pages/4_📷_Instagram.py")

# Footer
st.markdown("")
st.markdown(
    '<div class="pro-footer">Built with care. All platforms supported.</div>',
    unsafe_allow_html=True,
)
