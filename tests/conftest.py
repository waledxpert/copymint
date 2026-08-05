"""Cross-platform pytest event-loop policy."""

import asyncio
import sys


def pytest_asyncio_loop_factories(config: object, item: object) -> dict[str, object]:
    if sys.platform == "win32":
        return {"windows_selector": asyncio.SelectorEventLoop}
    return {"default": asyncio.new_event_loop}
