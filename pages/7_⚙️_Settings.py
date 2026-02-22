"""
Settings — AI Provider Configuration
======================================
Configure API keys for Claude, ChatGPT, and Gemini.
Keys are stored only in session state, never written to disk.
"""

import streamlit as st
from pathlib import Path

st.set_page_config(
    page_title="Settings",
    page_icon="⚙️",
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
st.markdown('<div class="page-header"><h1>Settings</h1></div>', unsafe_allow_html=True)
st.markdown(
    '<p class="page-desc">Configure AI providers for market research analysis. '
    "Keys are stored in memory only and never saved to disk.</p>",
    unsafe_allow_html=True,
)

# Imports
from utils.api_keys import PROVIDERS, save_api_key, get_api_key, get_active_provider, set_active_provider, validate_api_key

# ---------------------------------------------------------------------------
# Active provider selector
# ---------------------------------------------------------------------------

st.markdown("### Active Provider")

provider_options = list(PROVIDERS.keys())
provider_labels = [PROVIDERS[p]["name"] for p in provider_options]
current = get_active_provider()
current_idx = provider_options.index(current) if current in provider_options else 0

selected_label = st.radio(
    "Choose which AI provider to use for analysis",
    options=provider_labels,
    index=current_idx,
    horizontal=True,
)
selected_provider = provider_options[provider_labels.index(selected_label)]
set_active_provider(selected_provider)

st.markdown("---")

# ---------------------------------------------------------------------------
# Per-provider API key sections
# ---------------------------------------------------------------------------

st.markdown("### API Keys")

for provider_slug, info in PROVIDERS.items():
    with st.expander(f"{info['name']}", expanded=(provider_slug == selected_provider)):
        st.markdown(
            f'<p style="font-size:0.88rem;color:#94A3B8;margin-bottom:0.75rem">{info["description"]}</p>',
            unsafe_allow_html=True,
        )

        existing_key = get_api_key(provider_slug) or ""
        key_input = st.text_input(
            f"API Key",
            value=existing_key,
            type="password",
            placeholder=info["placeholder"],
            key=f"key_{provider_slug}",
        )

        # Save key on change
        if key_input and key_input != existing_key:
            save_api_key(provider_slug, key_input)

        col_validate, col_status = st.columns([1, 3])

        with col_validate:
            validate_btn = st.button("Validate", key=f"validate_{provider_slug}", use_container_width=True)

        with col_status:
            if validate_btn:
                current_key = key_input or get_api_key(provider_slug)
                if not current_key:
                    st.warning("Enter an API key first.")
                else:
                    with st.spinner("Testing..."):
                        valid = validate_api_key(provider_slug, current_key)
                    if valid:
                        save_api_key(provider_slug, current_key)
                        st.success("Key is valid.")
                    else:
                        st.error("Validation failed. Check the key and try again.")

            # Show current status
            stored = get_api_key(provider_slug)
            if stored:
                masked = stored[:8] + "..." + stored[-4:] if len(stored) > 12 else "****"
                st.markdown(
                    f'<span style="font-size:0.8rem;color:#94A3B8">Stored: <code>{masked}</code></span>',
                    unsafe_allow_html=True,
                )

# ---------------------------------------------------------------------------
# Search API Configuration (for One Search)
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown("### Search API (for One Search)")
st.markdown(
    '<p class="page-desc">'
    "One Search uses Google to find posts across platforms. "
    "A search API key is needed for full Google operator support "
    "(site:, intext:, -inurl:, after:, etc.)."
    "</p>",
    unsafe_allow_html=True,
)

search_tab1, search_tab2 = st.tabs(["Serper.dev (Recommended)", "SerpAPI"])

with search_tab1:
    st.markdown(
        '<p style="font-size:0.88rem;color:#94A3B8">'
        "Free: 2,500 queries. Get your key at "
        '<a href="https://serper.dev" target="_blank" style="color:#3B82F6">serper.dev</a>'
        "</p>",
        unsafe_allow_html=True,
    )
    serper_key = st.text_input(
        "Serper API Key",
        value=st.session_state.get("serper_api_key", ""),
        type="password",
        placeholder="paste your Serper.dev API key",
        key="serper_key_input",
    )
    if serper_key:
        st.session_state["serper_api_key"] = serper_key
        masked = serper_key[:8] + "..." + serper_key[-4:] if len(serper_key) > 12 else "****"
        st.markdown(
            f'<span style="font-size:0.8rem;color:#94A3B8">Stored: <code>{masked}</code></span>',
            unsafe_allow_html=True,
        )

with search_tab2:
    st.markdown(
        '<p style="font-size:0.88rem;color:#94A3B8">'
        "Free: 100 queries/month. Get your key at "
        '<a href="https://serpapi.com" target="_blank" style="color:#3B82F6">serpapi.com</a>'
        "</p>",
        unsafe_allow_html=True,
    )
    serpapi_key = st.text_input(
        "SerpAPI Key",
        value=st.session_state.get("serpapi_key", ""),
        type="password",
        placeholder="paste your SerpAPI key",
        key="serpapi_key_input",
    )
    if serpapi_key:
        st.session_state["serpapi_key"] = serpapi_key
        masked = serpapi_key[:8] + "..." + serpapi_key[-4:] if len(serpapi_key) > 12 else "****"
        st.markdown(
            f'<span style="font-size:0.8rem;color:#94A3B8">Stored: <code>{masked}</code></span>',
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.markdown(
    '<p style="font-size:0.82rem;color:#64748B;text-align:center">'
    "All keys are stored in your browser session only. "
    "They are cleared when you close the tab or refresh the page."
    "</p>",
    unsafe_allow_html=True,
)
