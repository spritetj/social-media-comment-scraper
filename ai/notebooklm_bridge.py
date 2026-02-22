"""
NotebookLM MCP Bridge
======================
Spawns the NotebookLM MCP server as a subprocess and communicates
via JSON-RPC over stdin/stdout. Provides a simple Python interface
for querying NotebookLM notebooks.

Usage:
    bridge = NotebookLMBridge()
    answer, session_id = await bridge.ask_question(
        "What are the main themes?",
        notebook_url="https://notebooklm.google.com/notebook/...",
    )
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)

# Daily query budget for free tier
NLM_DAILY_LIMIT = 50
NLM_WARN_THRESHOLD = 40


class NotebookLMBridge:
    """Manages a NotebookLM MCP server subprocess and provides
    async methods to interact with it."""

    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Spawn the MCP server subprocess and perform the handshake."""
        if self._process and self._process.poll() is None:
            return  # already running

        env = os.environ.copy()
        # Streamlit may run with a restricted PATH that excludes Node.js.
        # Prepend common Node.js installation paths to ensure npx is found.
        extra_paths = [
            "/opt/homebrew/bin",        # macOS Homebrew ARM
            "/usr/local/bin",           # macOS Homebrew Intel / Linux
            os.path.expanduser("~/.nvm/current/bin"),  # nvm
            os.path.expanduser("~/.local/bin"),
        ]
        existing_path = env.get("PATH", "/usr/bin:/bin")
        env["PATH"] = ":".join(extra_paths) + ":" + existing_path

        # Try to resolve npx to an absolute path for reliability
        npx_cmd = shutil.which("npx", path=env["PATH"]) or "npx"

        try:
            self._process = subprocess.Popen(
                [npx_cmd, "-y", "notebooklm-mcp"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "npx not found. Install Node.js (v18+) to use NotebookLM integration."
            )

        # MCP handshake: send initialize request
        init_result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "social-scraper", "version": "1.0"},
        })
        logger.info("NotebookLM MCP initialized: %s", init_result)

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

    async def stop(self):
        """Gracefully shut down the MCP server."""
        if self._process and self._process.poll() is None:
            try:
                self._process.stdin.close()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None

    async def _ensure_running(self):
        """Auto-start the server if not running."""
        if not self._process or self._process.poll() is not None:
            await self.start()

    # ------------------------------------------------------------------
    # JSON-RPC communication
    # ------------------------------------------------------------------

    async def _send_request(
        self, method: str, params: dict, timeout: float = 120.0
    ) -> Any:
        """Send a JSON-RPC request and wait for the response."""
        self._request_id += 1
        request_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        line = json.dumps(message) + "\n"

        async with self._lock:
            proc = self._process
            if not proc or proc.poll() is not None:
                raise RuntimeError("MCP server is not running")

            try:
                proc.stdin.write(line)
                proc.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                raise RuntimeError(f"Failed to write to MCP server: {e}")

            # Read response with timeout
            loop = asyncio.get_event_loop()
            try:
                response_line = await asyncio.wait_for(
                    loop.run_in_executor(None, proc.stdout.readline),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"MCP server did not respond within {timeout}s"
                )

            if not response_line:
                raise RuntimeError("MCP server closed connection")

            response = json.loads(response_line.strip())

        if "error" in response:
            err = response["error"]
            raise RuntimeError(
                f"MCP error [{err.get('code', '?')}]: {err.get('message', 'Unknown')}"
            )

        return response.get("result")

    async def _send_notification(self, method: str, params: dict):
        """Send a JSON-RPC notification (no response expected)."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        line = json.dumps(message) + "\n"
        proc = self._process
        if proc and proc.poll() is None:
            try:
                proc.stdin.write(line)
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    # ------------------------------------------------------------------
    # MCP tool calls
    # ------------------------------------------------------------------

    async def _call_tool(
        self, tool_name: str, arguments: dict, timeout: float = 120.0
    ) -> str:
        """Call an MCP tool and return its text content."""
        result = await self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            timeout=timeout,
        )
        # MCP tool results have a "content" array
        content_items = result.get("content", [])
        texts = [c.get("text", "") for c in content_items if c.get("type") == "text"]
        return "\n".join(texts)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ask_question(
        self,
        question: str,
        notebook_url: str | None = None,
        notebook_id: str | None = None,
        session_id: str | None = None,
    ) -> tuple[str, str]:
        """Ask a question to NotebookLM.

        Returns (answer_text, session_id) for session continuity.
        Retries once on timeout.
        """
        await self._ensure_running()

        args: dict[str, Any] = {"question": question}
        if notebook_url:
            args["notebook_url"] = notebook_url
        if notebook_id:
            args["notebook_id"] = notebook_id
        if session_id:
            args["session_id"] = session_id

        for attempt in range(2):
            try:
                text = await self._call_tool("ask_question", args, timeout=120.0)
                # Extract session_id from response if present
                # The MCP server typically includes it in the response
                resp_session_id = session_id or ""
                if "session_id" not in args and text:
                    # Try to extract session_id from response metadata
                    # For now, use the provided one or generate a placeholder
                    resp_session_id = session_id or "default"
                return text, resp_session_id
            except TimeoutError:
                if attempt == 0:
                    logger.warning("NotebookLM query timed out, retrying...")
                    continue
                raise

        return "", session_id or ""

    async def get_health(self) -> dict:
        """Check the MCP server health and auth status."""
        await self._ensure_running()
        text = await self._call_tool("get_health", {}, timeout=30.0)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"authenticated": False, "raw": text}

    async def setup_auth(self) -> str:
        """Open browser for Google login. Returns status message."""
        await self._ensure_running()
        return await self._call_tool("setup_auth", {}, timeout=300.0)

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
