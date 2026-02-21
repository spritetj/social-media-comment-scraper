"""
Social Media Comment Scraper — Landing Page
=============================================
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

# Navigation — compact centered like Apple.com
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
    qr_path = Path(__file__).parent / "assets" / "qr_payment.jpeg"
    if qr_path.exists():
        with st.popover("Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)

st.markdown('<hr class="nav-divider">', unsafe_allow_html=True)

# Hero — centered, Apple scale
st.markdown(
    """
    <div class="hero-section">
        <p class="hero-eyebrow">Social Media Toolkit</p>
        <h1 class="hero-title">Comment Scraper.</h1>
        <p class="hero-subtitle">Extract comments from any platform.<br>Fast, simple, powerful.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Platform tiles — 2x2 grid with 12px gap
col1, col2 = st.columns(2, gap="small")

with col1:
    st.markdown(
        """
        <div class="platform-tile">
            <span class="tile-icon">🎬</span>
            <h3>YouTube</h3>
            <p>Comments and replies from any video.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="tile-cta">', unsafe_allow_html=True)
    st.page_link("pages/1_🎬_YouTube.py", label="Learn more  ›")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")

    st.markdown(
        """
        <div class="platform-tile tile-dark">
            <span class="tile-icon">📘</span>
            <h3>Facebook</h3>
            <p>Posts, reels, and video comments.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="tile-cta">', unsafe_allow_html=True)
    st.page_link("pages/3_📘_Facebook.py", label="Learn more  ›")
    st.markdown('</div>', unsafe_allow_html=True)

with col2:
    st.markdown(
        """
        <div class="platform-tile">
            <span class="tile-icon">🎵</span>
            <h3>TikTok</h3>
            <p>Video comments and reply threads.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="tile-cta">', unsafe_allow_html=True)
    st.page_link("pages/2_🎵_TikTok.py", label="Learn more  ›")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("")

    st.markdown(
        """
        <div class="platform-tile tile-dark">
            <span class="tile-icon">📷</span>
            <h3>Instagram</h3>
            <p>Post and reel comments with replies.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="tile-cta">', unsafe_allow_html=True)
    st.page_link("pages/4_📷_Instagram.py", label="Learn more  ›")
    st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.markdown(
    '<div class="pro-footer">Built with care. All platforms supported.</div>',
    unsafe_allow_html=True,
)
