"""
Social Listening Platform — Landing Page
==========================================
Product landing page with hero, One Search CTA, platform cards,
and Free vs Pro comparison.
"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Social Listening Platform",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Load custom CSS
css_path = Path(__file__).parent / "assets" / "style.css"
if css_path.exists():
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

# Navigation
from utils.nav import render_nav
render_nav()

# Hero Section
st.markdown(
    """
    <div class="hero-section">
        <h1 class="hero-title">Social Listening Made Simple</h1>
        <p class="hero-subtitle">
            Turn social media comments into actionable insights.
            Scrape, analyze, and understand what people are saying
            across YouTube, TikTok, Facebook, and Instagram.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

# One Search CTA
st.markdown(
    """
    <div class="cta-card">
        <div class="cta-badge">NEW</div>
        <h2 class="cta-title">One Search</h2>
        <p class="cta-desc">
            Type a brand or topic — get comprehensive insights
            across all platforms in one click.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.page_link(
    "pages/5_🔍_One_Search.py",
    label="Try One Search  →",
    use_container_width=True,
)

st.markdown("")

# Platform Cards
st.markdown(
    '<p style="text-align:center;color:var(--text-2);font-size:0.85rem;'
    'text-transform:uppercase;letter-spacing:0.06em;margin:2rem 0 1rem">'
    'Or scrape a specific platform</p>',
    unsafe_allow_html=True,
)

r1c1, r1c2 = st.columns(2, gap="medium")

with r1c1:
    st.markdown(
        """
        <div class="space-card accent-red d1">
            <div class="card-icon-wrap ic-red"><span>🎬</span></div>
            <h3>YouTube</h3>
            <p>Extract comments and replies from any video.</p>
            <span class="card-badge badge-open">No login needed</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/1_🎬_YouTube.py",
        label="Open YouTube  →",
        use_container_width=True,
    )

with r1c2:
    st.markdown(
        """
        <div class="space-card accent-cyan d2">
            <div class="card-icon-wrap ic-cyan"><span>🎵</span></div>
            <h3>TikTok</h3>
            <p>Video comments and reply threads.</p>
            <span class="card-badge badge-open">No login needed</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/2_🎵_TikTok.py",
        label="Open TikTok  →",
        use_container_width=True,
    )

r2c1, r2c2 = st.columns(2, gap="medium")

with r2c1:
    st.markdown(
        """
        <div class="space-card accent-blue d3">
            <div class="card-icon-wrap ic-blue"><span>📘</span></div>
            <h3>Facebook</h3>
            <p>Scrape comments from posts, reels, and videos.</p>
            <span class="card-badge badge-auth">Cookies required</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/3_📘_Facebook.py",
        label="Open Facebook  →",
        use_container_width=True,
    )

with r2c2:
    st.markdown(
        """
        <div class="space-card accent-violet d4">
            <div class="card-icon-wrap ic-violet"><span>📷</span></div>
            <h3>Instagram</h3>
            <p>Post and reel comments with replies.</p>
            <span class="card-badge badge-auth">Cookies optional</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(
        "pages/4_📷_Instagram.py",
        label="Open Instagram  →",
        use_container_width=True,
    )

# Free vs Pro Comparison
st.markdown("")
st.markdown(
    """
    <div class="tier-section">
        <h2 class="tier-title">Free vs Pro</h2>
        <p class="tier-subtitle">Start free, upgrade when you need more power.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Comparison table
st.markdown(
    """
    <div class="tier-table">
        <table>
            <thead>
                <tr>
                    <th>Feature</th>
                    <th>Free</th>
                    <th class="tier-pro-col">Pro <span class="tier-price">$29/mo</span></th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Per-platform scraping</td>
                    <td>5 URLs/session</td>
                    <td>50 URLs/session</td>
                </tr>
                <tr>
                    <td>Sentiment &amp; keyword analysis</td>
                    <td>✓</td>
                    <td>✓</td>
                </tr>
                <tr>
                    <td>Advanced analysis (topics, temporal)</td>
                    <td>Limited</td>
                    <td>Full</td>
                </tr>
                <tr>
                    <td>AI analysis (BYOK)</td>
                    <td>—</td>
                    <td>✓</td>
                </tr>
                <tr>
                    <td><strong>One Search</strong></td>
                    <td>—</td>
                    <td><strong>5 searches/day</strong></td>
                </tr>
                <tr>
                    <td>Export CSV / JSON</td>
                    <td>✓</td>
                    <td>✓</td>
                </tr>
                <tr>
                    <td>Export PDF report</td>
                    <td>—</td>
                    <td>✓</td>
                </tr>
            </tbody>
        </table>
    </div>
    """,
    unsafe_allow_html=True,
)

# Footer
qr_path = Path(__file__).parent / "assets" / "qr_payment.jpeg"
_, fc, _ = st.columns([4, 1, 4])
with fc:
    if qr_path.exists():
        with st.popover("☕ Donate"):
            st.image(str(qr_path), caption="PromptPay", width=200)

st.markdown(
    '<div class="platform-footer">Social Listening Platform &mdash; All platforms supported</div>',
    unsafe_allow_html=True,
)
