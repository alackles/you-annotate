"""Live updates: in-memory pub/sub per text, delivered as Server-Sent Events.

The subscriber table lives in process memory, so the app must run as one process (one
uvicorn worker, one Fly machine). Events carry no data; a client that hears "changed"
refetches the text's annotations.
"""

import asyncio
from collections import defaultdict

from fastapi import Request

HEARTBEAT_SECONDS = 15  # keeps idle streams alive through Fly's proxy

_subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)


def publish(text_id: int) -> None:
    for queue in list(_subscribers.get(text_id, ())):
        queue.put_nowait("changed")


async def stream(request: Request, text_id: int):
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers[text_id].add(queue)
    try:
        yield "retry: 3000\n\n"
        while not await request.is_disconnected():
            try:
                message = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
                yield f"data: {message}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        _subscribers[text_id].discard(queue)
        if not _subscribers[text_id]:
            del _subscribers[text_id]
