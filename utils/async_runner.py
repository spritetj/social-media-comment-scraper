"""
Async runner — execute async code from sync Streamlit context.

Python 3.14 broke nest_asyncio + aiohttp compatibility because
asyncio.current_task() returns None in nested loops, and aiohttp's
internal timer requires a proper task context.

Solution: run async code in a separate thread with its own event loop.
"""

import asyncio
import threading


def run_async(coro):
    """Run an async coroutine in a fresh event loop on a new thread.

    This avoids the Python 3.14 + nest_asyncio + aiohttp incompatibility
    where aiohttp's internal timeout context manager requires
    asyncio.current_task() to return a proper task.

    Args:
        coro: An awaitable coroutine

    Returns:
        The result of the coroutine

    Raises:
        Any exception raised by the coroutine
    """
    result = [None]
    error = [None]

    def _target():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result[0] = loop.run_until_complete(coro)
            loop.close()
        except Exception as e:
            error[0] = e

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join(timeout=600)  # 10 min max

    if error[0]:
        raise error[0]
    return result[0]
