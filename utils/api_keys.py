"""
API Key Management
===================
In-memory key storage using Streamlit session state.
Keys are NEVER written to disk.
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Provider definitions
# ---------------------------------------------------------------------------

PROVIDERS = {
    "claude": {
        "name": "Claude (Anthropic)",
        "env_var": "ANTHROPIC_API_KEY",
        "placeholder": "sk-ant-...",
        "description": "Anthropic Claude Sonnet — excellent at structured analysis and nuanced reasoning.",
    },
    "openai": {
        "name": "ChatGPT (OpenAI)",
        "env_var": "OPENAI_API_KEY",
        "placeholder": "sk-...",
        "description": "OpenAI GPT-4o — fast, versatile, and widely supported.",
    },
    "gemini": {
        "name": "Gemini (Google)",
        "env_var": "GOOGLE_API_KEY",
        "placeholder": "AI...",
        "description": "Google Gemini 1.5 Pro — large context window, competitive pricing.",
    },
}


# ---------------------------------------------------------------------------
# Key CRUD
# ---------------------------------------------------------------------------

def save_api_key(provider: str, key: str) -> None:
    """Store an API key in session state (never touches disk)."""
    if "api_keys" not in st.session_state:
        st.session_state["api_keys"] = {}
    st.session_state["api_keys"][provider] = key.strip()


def get_api_key(provider: str) -> str | None:
    """Retrieve a stored API key, or None if not set."""
    keys = st.session_state.get("api_keys", {})
    key = keys.get(provider, "")
    return key if key else None


def get_active_provider() -> str | None:
    """Return the currently active provider slug, or None."""
    return st.session_state.get("active_provider")


def set_active_provider(provider: str) -> None:
    """Set the active AI provider."""
    st.session_state["active_provider"] = provider


# ---------------------------------------------------------------------------
# Key validation
# ---------------------------------------------------------------------------

def validate_api_key(provider: str, key: str) -> bool:
    """Make a minimal test call to verify the API key works.
    Returns True on success, False on any error."""

    if not key or not key.strip():
        return False

    try:
        if provider == "claude":
            import anthropic
            client = anthropic.Anthropic(api_key=key.strip())
            client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}],
            )
            return True

        elif provider == "openai":
            import openai
            client = openai.OpenAI(api_key=key.strip())
            client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=10,
            )
            return True

        elif provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=key.strip())
            model = genai.GenerativeModel("gemini-2.5-flash")
            model.generate_content("Hi")
            return True

    except Exception as e:
        # Rate limit (429) means the key is valid, just quota exceeded
        if "ResourceExhausted" in type(e).__name__ or "429" in str(e):
            return True
        return False

    return False
