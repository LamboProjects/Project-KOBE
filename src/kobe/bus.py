"""In-process async event bus.

Subscribers get a queue per event type. Publishers fan out to every subscriber of the
published event's exact type. No inheritance-based matching — keeps the contract simple.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator, TypeVar

import structlog

log = structlog.get_logger(__name__)

E = TypeVar("E")


class Bus:
    def __init__(self, queue_maxsize: int = 64) -> None:
        self._subs: dict[type, list[asyncio.Queue]] = defaultdict(list)
        self._maxsize = queue_maxsize

    def subscribe(self, event_type: type[E]) -> asyncio.Queue[E]:
        q: asyncio.Queue[E] = asyncio.Queue(maxsize=self._maxsize)
        self._subs[event_type].append(q)
        return q

    def unsubscribe(self, event_type: type[E], q: asyncio.Queue[E]) -> None:
        if q in self._subs.get(event_type, []):
            self._subs[event_type].remove(q)

    @asynccontextmanager
    async def stream(self, event_type: type[E]) -> AsyncIterator[asyncio.Queue[E]]:
        q = self.subscribe(event_type)
        try:
            yield q
        finally:
            self.unsubscribe(event_type, q)

    async def publish(self, event: object) -> None:
        subs = self._subs.get(type(event), [])
        if not subs:
            log.debug("no_subscribers", event_type=type(event).__name__)
            return
        for q in subs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest and retry — stale audio-pipeline events have no value.
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    log.warning("queue_drop", event_type=type(event).__name__)
