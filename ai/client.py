"""
Multi-provider LLM Client
==========================
Routes analysis requests to Claude (Anthropic), OpenAI (ChatGPT),
or Gemini based on user-configured provider. Uses official SDKs
with graceful fallback when packages are not installed.
"""

import json
import math
import os

# ---------------------------------------------------------------------------
# Optional SDK imports — app works without them, user just can't use
# the provider whose SDK is missing.
# ---------------------------------------------------------------------------

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None
    HAS_ANTHROPIC = False

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    openai = None
    HAS_OPENAI = False

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    genai = None
    HAS_GEMINI = False


# ---------------------------------------------------------------------------
# Provider constants
# ---------------------------------------------------------------------------

_ENV_VAR_MAP = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}

PROVIDERS = ("claude", "openai", "gemini")

PROVIDER_MODELS = {
    "claude": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "gemini": "gemini-2.5-flash",
}

SDK_AVAILABLE = {
    "claude": HAS_ANTHROPIC,
    "openai": HAS_OPENAI,
    "gemini": HAS_GEMINI,
}


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

class LLMClient:
    """Unified async interface to Claude, OpenAI, or Gemini."""

    def __init__(self):
        self.provider = self._get_provider()
        self.api_key = self._get_api_key()

    # ----- public -----------------------------------------------------------

    async def analyze(self, prompt: str, data: str = "") -> dict | str:
        """Send *prompt* (optionally with *data* appended) to the active
        provider and return parsed JSON or raw text."""

        if not self.provider:
            raise ValueError("No AI provider configured. Go to Settings to set one up.")
        if not self.api_key:
            raise ValueError(f"No API key found for {self.provider}. Add one in Settings.")
        if not SDK_AVAILABLE.get(self.provider):
            raise ImportError(
                f"The SDK for {self.provider} is not installed. "
                f"pip install {'anthropic' if self.provider == 'claude' else 'openai' if self.provider == 'openai' else 'google-generativeai'}"
            )

        full_prompt = f"{prompt}\n\n{data}" if data else prompt

        dispatch = {
            "claude": self._call_claude,
            "openai": self._call_openai,
            "gemini": self._call_gemini,
        }
        raw_text = await dispatch[self.provider](full_prompt)
        return self._parse_response(raw_text)

    # ----- private: provider calls -----------------------------------------

    async def _call_claude(self, prompt: str) -> str:
        """Call the Anthropic Messages API (sync SDK wrapped for async)."""
        client = anthropic.Anthropic(api_key=self.api_key)
        message = client.messages.create(
            model=PROVIDER_MODELS["claude"],
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    async def _call_openai(self, prompt: str) -> str:
        """Call the OpenAI Chat Completions API."""
        client = openai.OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=PROVIDER_MODELS["openai"],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )
        return response.choices[0].message.content

    async def _call_gemini(self, prompt: str) -> str:
        """Call the Google Generative AI (Gemini) API."""
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(PROVIDER_MODELS["gemini"])
        response = model.generate_content(prompt)
        return response.text

    # ----- helpers ----------------------------------------------------------

    @staticmethod
    def _get_provider() -> str | None:
        # 1. Try Streamlit session state
        try:
            import streamlit as st
            provider = st.session_state.get("active_provider")
            if provider:
                return provider
        except Exception:
            pass
        # 2. Fall back to env vars — return first provider with a key set
        for provider, env_var in _ENV_VAR_MAP.items():
            if os.environ.get(env_var):
                return provider
        return None

    @staticmethod
    def _get_api_key() -> str | None:
        # 1. Try Streamlit session state
        try:
            import streamlit as st
            provider = st.session_state.get("active_provider")
            if provider:
                keys = st.session_state.get("api_keys", {})
                key = keys.get(provider)
                if key:
                    return key
        except Exception:
            pass
        # 2. Fall back to env vars
        for provider, env_var in _ENV_VAR_MAP.items():
            key = os.environ.get(env_var)
            if key:
                return key
        return None

    @staticmethod
    def _parse_response(text: str) -> dict | str:
        """Try to extract JSON from the response.  Falls back to raw text."""
        text = text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines[1:] if l.strip() != "```"]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return text


# ---------------------------------------------------------------------------
# Comment chunking utility
# ---------------------------------------------------------------------------

def chunk_comments(comments: list[dict], max_tokens: int = 80_000) -> list[list[dict]]:
    """Split a list of comment dicts into chunks that fit within
    *max_tokens* (estimated).  Each comment is roughly
    ``len(json.dumps(comment)) / 4`` tokens."""

    if not comments:
        return []

    chunks: list[list[dict]] = []
    current_chunk: list[dict] = []
    current_tokens = 0

    for comment in comments:
        est_tokens = len(json.dumps(comment, ensure_ascii=False, default=str)) // 4
        if current_tokens + est_tokens > max_tokens and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0
        current_chunk.append(comment)
        current_tokens += est_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks
