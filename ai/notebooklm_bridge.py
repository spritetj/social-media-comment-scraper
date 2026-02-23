"""
NotebookLM Bridge (notebooklm-py)
==================================
Pure Python client for NotebookLM using the notebooklm-py library.
No Node.js or browser required at runtime — uses HTTP calls to
NotebookLM's internal RPC endpoints.

Auth priority:
    1. Session state (user uploaded cookies.txt in Settings)
    2. NOTEBOOKLM_AUTH_JSON env var
    3. Streamlit Cloud secrets
    4. Default local path (~/.notebooklm/storage_state.json)

Usage:
    bridge = get_bridge()
    await bridge.start()
    results = await bridge.create_and_query(comments_md, topic, queries)
"""

import asyncio
import json
import logging
import os
import time
from typing import Callable

logger = logging.getLogger(__name__)

# Daily query budget for free tier
NLM_DAILY_LIMIT = 50
NLM_WARN_THRESHOLD = 40


def _parse_cookies_txt(text: str) -> str:
    """Convert Netscape cookies.txt to Playwright storage_state.json format.

    Args:
        text: Contents of a Netscape-format cookies.txt file.

    Returns:
        JSON string in Playwright storage_state format.
    """
    cookies = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _host_only, path, secure, expiry, name, value = parts[:7]
        cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "expires": int(expiry) if expiry.isdigit() else -1,
            "secure": secure.upper() == "TRUE",
            "httpOnly": False,
            "sameSite": "None",
        })
    if not cookies:
        raise ValueError("No valid cookies found in cookies.txt")
    return json.dumps({"cookies": cookies, "origins": []})


def _inject_auth_from_secrets():
    """Inject NOTEBOOKLM_AUTH_JSON from session state, env, or secrets."""
    if "NOTEBOOKLM_AUTH_JSON" not in os.environ:
        try:
            import streamlit as st
            # Priority 1: user-uploaded cookies in session state
            val = st.session_state.get("nlm_auth_json", "")
            # Priority 2: already in env (checked above)
            # Priority 3: Streamlit Cloud secrets
            if not val:
                val = st.secrets.get("NOTEBOOKLM_AUTH_JSON", "")
            if val:
                os.environ["NOTEBOOKLM_AUTH_JSON"] = val
        except Exception:
            pass


class NotebookLMBridge:
    """Manages a NotebookLM client via notebooklm-py and provides
    async methods to interact with it."""

    def __init__(self):
        self._client = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Initialize the httpx-based client from stored cookies."""
        if self._client is not None:
            return  # already initialized

        _inject_auth_from_secrets()

        try:
            from notebooklm import NotebookLMClient
            client = await NotebookLMClient.from_storage()
            # Enter the async context manager to initialize the httpx session
            self._client = await client.__aenter__()
        except ImportError:
            raise RuntimeError(
                "notebooklm-py is not installed. "
                "Run: pip install notebooklm-py"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize NotebookLM client: {e}\n"
                "Make sure NOTEBOOKLM_AUTH_JSON is set with valid cookies. "
                "Run 'notebooklm login' locally to generate fresh cookies."
            )

    async def stop(self):
        """Close the client connection."""
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None

    async def _ensure_running(self):
        """Auto-start the client if not initialized."""
        if self._client is None:
            await self.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_and_query(
        self,
        comments_md: str,
        topic: str,
        queries: list[dict],
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> dict:
        """Create a notebook, upload comments, run all queries, return parsed results.

        Args:
            comments_md: Markdown-formatted comments to upload as source.
            topic: The research topic (used for notebook/source title).
            queries: List of query dicts with 'id' and 'question' keys.
            progress_cb: Optional callback(progress_float, status_message).

        Returns:
            Dict mapping query IDs to answer strings.
        """
        await self._ensure_running()

        nb = None
        try:
            # 1. Create notebook
            if progress_cb:
                progress_cb(0.05, "Creating notebook...")
            nb = await self._client.notebooks.create(f"Analysis: {topic}")
            logger.info("Created notebook: %s (%s)", nb.title, nb.id)

            # 2. Add comments as text source
            if progress_cb:
                progress_cb(0.10, "Uploading comments...")
            source = await self._client.sources.add_text(
                nb.id,
                title=f"Comments: {topic}",
                content=comments_md,
                wait=True,
                wait_timeout=120.0,
            )
            logger.info("Source ready: %s", source.title)

            # 3. Ask each query
            parsed_results = {}
            conversation_id = None

            for i, q in enumerate(queries):
                qid = q["id"]
                question = q["question"]
                progress_pct = 0.15 + (0.80 * (i + 1) / len(queries))

                if progress_cb:
                    progress_cb(
                        progress_pct,
                        f"Querying ({i+1}/{len(queries)}): "
                        f"{qid.replace('_', ' ').title()}...",
                    )

                try:
                    result = await self._client.chat.ask(
                        nb.id,
                        question,
                        conversation_id=conversation_id,
                    )
                    parsed_results[qid] = result.answer
                    conversation_id = result.conversation_id
                except Exception as e:
                    logger.warning("Query '%s' failed: %s", qid, e)
                    parsed_results[qid] = ""

            if progress_cb:
                progress_cb(1.0, "Analysis complete!")

            return parsed_results

        finally:
            # 4. Cleanup: delete notebook after analysis
            if nb is not None:
                try:
                    await self._client.notebooks.delete(nb.id)
                    logger.info("Deleted notebook: %s", nb.id)
                except Exception as e:
                    logger.warning("Failed to delete notebook %s: %s", nb.id, e)

    async def check_auth(self) -> bool:
        """Verify cookies are valid by listing notebooks."""
        try:
            await self._ensure_running()
            await self._client.notebooks.list()
            return True
        except Exception:
            return False

    async def ask_question(
        self,
        question: str,
        notebook_id: str | None = None,
        conversation_id: str | None = None,
        **kwargs,
    ) -> tuple[str, str]:
        """Ask a question to a specific notebook (low-level API).

        Returns (answer_text, conversation_id).
        """
        await self._ensure_running()

        if not notebook_id:
            raise ValueError("notebook_id is required")

        result = await self._client.chat.ask(
            notebook_id,
            question,
            conversation_id=conversation_id,
        )
        return result.answer, result.conversation_id

    # ------------------------------------------------------------------
    # Query budget tracking
    # ------------------------------------------------------------------

    @staticmethod
    def get_daily_usage() -> dict:
        """Get today's query usage from session state."""
        try:
            import streamlit as st
            today = time.strftime("%Y-%m-%d")
            usage = st.session_state.get("nlm_usage", {})
            if usage.get("date") != today:
                usage = {"date": today, "count": 0}
                st.session_state["nlm_usage"] = usage
            return usage
        except Exception:
            return {"date": time.strftime("%Y-%m-%d"), "count": 0}

    @staticmethod
    def increment_usage(n: int = 1):
        """Increment today's query count."""
        try:
            import streamlit as st
            today = time.strftime("%Y-%m-%d")
            usage = st.session_state.get("nlm_usage", {})
            if usage.get("date") != today:
                usage = {"date": today, "count": 0}
            usage["count"] = usage.get("count", 0) + n
            st.session_state["nlm_usage"] = usage
        except Exception:
            pass

    @staticmethod
    def queries_remaining() -> int:
        """How many queries remain today."""
        try:
            import streamlit as st
            today = time.strftime("%Y-%m-%d")
            usage = st.session_state.get("nlm_usage", {})
            if usage.get("date") != today:
                return NLM_DAILY_LIMIT
            return max(0, NLM_DAILY_LIMIT - usage.get("count", 0))
        except Exception:
            return NLM_DAILY_LIMIT


# Module-level singleton
_bridge: NotebookLMBridge | None = None


def get_bridge() -> NotebookLMBridge:
    """Get or create the singleton bridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = NotebookLMBridge()
    return _bridge


def reset_bridge():
    """Clear the singleton so new cookies take effect on next call."""
    global _bridge
    if _bridge is not None:
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(_bridge.stop())
        except Exception:
            pass
        _bridge = None
    # Also clear env so _inject_auth_from_secrets re-reads session state
    os.environ.pop("NOTEBOOKLM_AUTH_JSON", None)
