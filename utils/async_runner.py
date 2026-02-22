"""
Async runner — execute async code from sync Streamlit context.

Python 3.14 broke nest_asyncio + aiohttp compatibility because
asyncio.current_task() returns None in nested loops, and aiohttp's
internal timer requires a proper task context.

Solution: run async code in a separate thread with its own event loop,
propagating the Streamlit ScriptRunContext so session_state and UI
calls work from the child thread.
"""

import asyncio
import threading


def _get_streamlit_ctx():
    """Get the current Streamlit ScriptRunContext (if running in Streamlit)."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx()
    except ImportError:
        return None


def _set_streamlit_ctx(thread, ctx):
    """Attach a Streamlit ScriptRunContext to the given thread."""
    if ctx is None:
        return
    try:
        from streamlit.runtime.scriptrunner import add_script_run_ctx
        add_script_run_ctx(thread, ctx)
    except ImportError:
        pass


def run_async(coro):
    """Run an async coroutine in a fresh event loop on a new thread.

    This avoids the Python 3.14 + nest_asyncio + aiohttp incompatibility
    where aiohttp's internal timeout context manager requires
    asyncio.current_task() to return a proper task.

    The Streamlit ScriptRunContext is propagated to the child thread so
    that st.session_state and UI placeholder updates work correctly.

    Args:
        coro: An awaitable coroutine

    Returns:
        The result of the coroutine

    Raises:
        Any exception raised by the coroutine
    """
    result = [None]
    error = [None]
    ctx = _get_streamlit_ctx()

    def _target():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result[0] = loop.run_until_complete(coro)
            loop.close()
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=_target)
    _set_streamlit_ctx(thread, ctx)
    thread.start()
    thread.join(timeout=600)  # 10 min max

    if error[0]:
        raise error[0]
    return result[0]
