"""
Settings — AI Provider Configuration
======================================
Configure API keys for Claude, ChatGPT, and Gemini.
Keys are stored only in session state, never written to disk.
"""

import json
import os

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
# Analysis Engine Toggle (NotebookLM vs Paid API)
# ---------------------------------------------------------------------------

st.markdown("### Analysis Engine")

engine_options = {
    "notebooklm": "NotebookLM (Free - powered by Gemini)",
    "paid_api": "Paid API (Claude / ChatGPT / Gemini)",
}

current_provider = get_active_provider()
# Map current provider to engine type
current_engine = "notebooklm" if current_provider == "notebooklm" else "paid_api"

engine_choice = st.radio(
    "Choose your analysis engine",
    options=list(engine_options.keys()),
    format_func=lambda x: engine_options[x],
    index=0 if current_engine == "notebooklm" else 1,
    horizontal=True,
    key="engine_toggle",
)

if engine_choice == "notebooklm":
    # Set NotebookLM as active provider
    set_active_provider("notebooklm")

    st.markdown(
        '<div style="background:rgba(52,211,153,0.06);border:1px solid rgba(52,211,153,0.2);'
        'border-radius:8px;padding:1rem;margin:0.5rem 0">'
        '<p style="font-size:0.88rem;color:#94A3B8;margin:0">'
        'NotebookLM provides <strong style="color:#34D399">free</strong> AI-powered analysis '
        'backed by Google Gemini. You upload your comments to a NotebookLM notebook, '
        'then the app queries it for insights.</p>'
        '<p style="font-size:0.82rem;color:#64748B;margin:0.5rem 0 0 0">'
        'Free tier: 50 queries/day (enough for 7-10 full analyses)</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # NotebookLM auth & status section
    from ai.notebooklm_bridge import get_bridge, reset_bridge, _parse_cookies_txt
    from utils.async_runner import run_async

    # --- Auth status indicator ---
    has_session_cookies = bool(st.session_state.get("nlm_auth_json"))
    has_env_cookies = bool(os.environ.get("NOTEBOOKLM_AUTH_JSON"))

    if has_session_cookies:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;margin:0.5rem 0">'
            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#34D399"></span>'
            '<span style="font-size:0.88rem;color:#34D399;font-weight:600">Connected</span>'
            '<span style="font-size:0.82rem;color:#64748B">— cookies uploaded this session</span>'
            '</div>',
            unsafe_allow_html=True,
        )
    elif has_env_cookies:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;margin:0.5rem 0">'
            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#34D399"></span>'
            '<span style="font-size:0.88rem;color:#34D399;font-weight:600">Connected</span>'
            '<span style="font-size:0.82rem;color:#64748B">— using env/secrets</span>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:8px;margin:0.5rem 0">'
            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#F87171"></span>'
            '<span style="font-size:0.88rem;color:#F87171;font-weight:600">Not configured</span>'
            '<span style="font-size:0.82rem;color:#64748B">— upload cookies.txt below</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    # --- Cookie upload ---
    uploaded_file = st.file_uploader(
        "Upload cookies.txt",
        type=["txt"],
        help="Export cookies from a browser extension (e.g. 'Get cookies.txt LOCALLY') and upload the file here.",
        key="nlm_cookie_upload",
    )
    if uploaded_file is not None:
        try:
            raw_text = uploaded_file.read().decode("utf-8")
            auth_json = _parse_cookies_txt(raw_text)
            st.session_state["nlm_auth_json"] = auth_json
            reset_bridge()
            st.success(f"Cookies loaded — {len(json.loads(auth_json)['cookies'])} cookies imported.")
        except Exception as e:
            st.error(f"Failed to parse cookies.txt: {e}")

    # --- Status row: query usage + auth check ---
    col_status, col_auth = st.columns([2, 1])
    with col_status:
        # Query usage counter
        try:
            from ai.notebooklm_bridge import NotebookLMBridge
            usage = NotebookLMBridge.get_daily_usage()
            remaining = NotebookLMBridge.queries_remaining()
            count = usage.get("count", 0)

            bar_pct = min(count / 50 * 100, 100)
            bar_color = "#34D399" if count < 40 else "#FBBF24" if count < 50 else "#F87171"
            st.markdown(
                f'<div style="font-size:0.85rem;margin:0.5rem 0">'
                f'Queries today: <strong>{count}</strong> / 50 '
                f'<span style="color:#64748B">({remaining} remaining)</span>'
                f'</div>'
                f'<div style="background:rgba(255,255,255,0.05);border-radius:4px;height:6px;margin:4px 0">'
                f'<div style="background:{bar_color};height:100%;border-radius:4px;width:{bar_pct}%"></div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if count >= 40:
                st.warning(f"Approaching daily limit ({remaining} queries remaining).")
        except Exception:
            st.caption("Query tracking will start after first analysis.")

    with col_auth:
        if st.button("Check Auth Status", use_container_width=True, key="nlm_auth_check"):
            with st.spinner("Checking cookies..."):
                try:
                    bridge = get_bridge()
                    is_valid = run_async(bridge.check_auth())
                    if is_valid:
                        st.success("Connected — cookies are valid.")
                    else:
                        st.error("Cookies expired. Upload fresh cookies.txt.")
                except Exception as e:
                    st.error(f"Auth check failed: {e}")

    # Cookie setup instructions
    with st.expander("How to get cookies.txt", expanded=False):
        st.markdown(
            "**Step 1:** Install a cookie export extension in your browser:\n"
            "- Chrome: [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)\n"
            "- Firefox: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)\n\n"
            "**Step 2:** Go to [notebooklm.google.com](https://notebooklm.google.com) and sign in\n\n"
            "**Step 3:** Click the extension icon and export cookies for the current site\n\n"
            "**Step 4:** Upload the downloaded `cookies.txt` file above\n\n"
            "Cookies typically last 1-2 weeks. Re-upload when they expire.\n\n"
            "*Alternative:* Set `NOTEBOOKLM_AUTH_JSON` env var or Streamlit Cloud secrets "
            "with Playwright storage_state.json format."
        )

    st.markdown("---")

else:
    # Paid API mode — show existing provider selector
    st.markdown("---")

    # ---------------------------------------------------------------------------
    # Active provider selector (only shown in Paid API mode)
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
# Per-provider API key sections (always shown for reference)
# ---------------------------------------------------------------------------

st.markdown("### API Keys")
if engine_choice == "notebooklm":
    st.caption("API keys are only needed for the Paid API engine. Configure them here for when you switch.")

for provider_slug, info in PROVIDERS.items():
    with st.expander(f"{info['name']}", expanded=(engine_choice == "paid_api" and provider_slug == get_active_provider())):
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
