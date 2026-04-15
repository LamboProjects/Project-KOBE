"""Persona prompt presets for the OpenClaw brain.

Each persona is a short system-prompt prefix the router prepends to outgoing
OpenClaw requests. OpenClaw is responsible for actually honoring the prefix
(it wires the string into the system prompt for its LLM call). The router
only ships it — unknown names fall back to ``PERSONAS["default"]`` with a
warning log.

Kept intentionally tiny: five named presets, a lookup helper, nothing else.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


PERSONAS: dict[str, str] = {
    "default": "Keep responses concise, 1-2 sentences. Factual and warm.",
    "concise": "Answer in one short sentence. No filler.",
    "warm":    "Be warm and conversational but still brief.",
    "terse":   "Be blunt. No pleasantries.",
    "excited": "Be upbeat and enthusiastic, but still short.",
}


def persona_prompt(name: str) -> str:
    """Resolve a persona name or custom prompt to the final string to ship.

    Resolution order:
      1. Empty / None → ``PERSONAS["default"]`` silently ("no opinion" signal).
      2. A known preset name (`default`, `concise`, `warm`, `terse`, `excited`)
         → that preset's prompt.
      3. Anything else → treated as a raw custom prompt and returned verbatim.
         Logged at INFO so a typo of a preset name (e.g. ``defauult``) surfaces
         in the operator's log stream — the LLM hearing nonsense will make the
         misconfiguration obvious, but the log is the primary signal.

    This keeps the API honest: any string the user puts in
    ``TTS_PERSONA_PROFILE`` is the string the brain actually ships. No
    silent coercion to `default` for near-miss names or short prompts.
    """
    if not name:
        return PERSONAS["default"]
    prompt = PERSONAS.get(name)
    if prompt is not None:
        return prompt
    log.info(
        "persona_custom",
        value=name,
        length=len(name),
        hint="not a known preset — shipping verbatim as a custom prompt",
    )
    return name
