"""Vision backend protocol + built-in stubs.

A backend is anything that turns a `Screenshot` + natural-language question
into a short text summary. Real models will land in Phase 6 polish; for the
Phase 4 foundation we ship only the null backend so the wiring can be
exercised end-to-end without any API cost or model download.

To add a new backend (e.g. OpenClaw, OpenAI, Moondream):
  1. Implement `VisionBackend.analyse(...)`.
  2. Register it in `build_backend(...)`.
  3. Add any required config to `kobe.config.Settings`.

Backends MUST NOT block the event loop — use `asyncio.to_thread` inside the
implementation for any synchronous HTTP / GPU work.
"""
from __future__ import annotations

from typing import Protocol

import structlog

from kobe.config import Settings
from kobe.vision.capture import Screenshot

log = structlog.get_logger(__name__)


class VisionBackend(Protocol):
    """One-shot image-plus-question answerer. Async so real backends can be
    streamed without blocking the event loop."""

    name: str

    async def analyse(self, shot: Screenshot, question: str) -> str:
        """Return a short human-readable answer. Must never raise for normal
        failure modes — return a descriptive fallback string instead so the
        TTS layer always has something to say.
        """
        ...


class NullBackend:
    """Foundation stub: describes the screenshot without any model call.

    Useful for exercising the pipeline (action → capture → result → TTS) with
    zero API cost and zero network dependency. Returns a short deterministic
    summary so smoke tests can assert on it.
    """

    name = "null"

    async def analyse(self, shot: Screenshot, question: str) -> str:
        win = f' "{shot.window_title}"' if shot.window_title else ""
        return (
            f"Screen vision backend is not configured yet. "
            f"Captured a {shot.width}x{shot.height} {shot.mode} screenshot{win}. "
            f"Your question was: {question.strip() or '(none)'}."
        )


def build_backend(settings: Settings) -> VisionBackend:
    """Pick a backend from config. Unknown or unconfigured → NullBackend."""
    choice = (settings.vision_backend or "null").strip().lower()
    if choice in ("", "null", "none", "stub"):
        return NullBackend()
    # Phase 4 foundation only ships the null backend. Anything else falls back
    # with a warning so we never silently pretend to use a real model.
    log.warning(
        "vision_backend_not_implemented_yet",
        requested=choice,
        fallback="null",
        hint="Only the null backend is wired up in Phase 4. OpenClaw/OpenAI/local come later.",
    )
    return NullBackend()
