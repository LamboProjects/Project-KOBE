"""Vision backend protocol + built-in stubs and real implementations.

A backend is anything that turns a `Screenshot` + natural-language question
into a short text summary. Phase 6 ships two real backends (OpenClaw HTTP,
OpenAI gpt-4o-mini) plus the foundation `NullBackend` for tests.

Backends MUST NOT block the event loop — the synchronous OpenAI SDK call is
wrapped in `asyncio.to_thread`, OpenClaw uses `httpx.AsyncClient`. All real
backends must catch their own failures and return a fallback string so the
TTS layer always has something to say.
"""
from __future__ import annotations

import asyncio
import base64
from typing import Protocol
from uuid import uuid4

import structlog

from kobe.config import Settings
from kobe.vision.capture import Screenshot

log = structlog.get_logger(__name__)


class VisionBackend(Protocol):
    """One-shot image-plus-question answerer. Async so real backends can be
    streamed without blocking the event loop.

    Returns `(ok, text)`. Backends MUST NOT raise for normal failure modes
    (timeout, HTTP error, missing key, decode error) — they catch internally
    and return `(False, descriptive_fallback)`. The service uses `ok` to
    populate `VisionResult.ok` and to mark the `ActionCompleted` correctly,
    while still having a TTS-friendly string in `text` to speak.
    """

    name: str

    async def analyse(self, shot: Screenshot, question: str) -> tuple[bool, str]:
        ...


class NullBackend:
    """Foundation stub: describes the screenshot without any model call."""

    name = "null"

    async def analyse(self, shot: Screenshot, question: str) -> tuple[bool, str]:
        win = f' "{shot.window_title}"' if shot.window_title else ""
        text = (
            f"Screen vision backend is not configured yet. "
            f"Captured a {shot.width}x{shot.height} {shot.mode} screenshot{win}. "
            f"Your question was: {question.strip() or '(none)'}."
        )
        # The null stub is a deliberate "captured but no model" — that's a successful
        # capture from the pipeline's perspective, so ok=True. Real backends flip ok=False
        # when the network/SDK call fails.
        return True, text


def encode_jpeg(shot: Screenshot, quality: int, max_edge: int) -> bytes:
    """Encode a Screenshot as a JPEG byte string.

    BGRA (mss native) → RGB → optional LANCZOS downscale → JPEG.

    Downscale only when `max(width, height) > max_edge`; preserve aspect ratio.
    Pillow is lazy-imported so an unrelated import failure can't kill the
    service at module load.
    """
    from PIL import Image  # lazy import
    from io import BytesIO

    img = Image.frombuffer(
        "RGBA", (shot.width, shot.height), shot.pixels, "raw", "BGRA", 0, 1
    ).convert("RGB")

    long_edge = max(shot.width, shot.height)
    if max_edge > 0 and long_edge > max_edge:
        scale = max_edge / float(long_edge)
        new_w = max(1, int(round(shot.width * scale)))
        new_h = max(1, int(round(shot.height * scale)))
        img = img.resize((new_w, new_h), Image.LANCZOS)

    buf = BytesIO()
    q = max(1, min(int(quality), 95))
    img.save(buf, format="JPEG", quality=q, optimize=True)
    return buf.getvalue()


class OpenClawBackend:
    """POSTs the screenshot + question to the user's OpenClaw VPS endpoint.

    Multipart form-data: `agent`, `request_id`, `question` fields plus an
    `image` file part. Bearer-token authenticated. Per-call HTTPX client to
    keep Phase 6 simple — see follow-up note about pooling.
    """

    name = "openclaw"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        base = settings.openclaw_api_url.rstrip("/")
        path = settings.openclaw_vision_path
        if not path.startswith("/"):
            path = "/" + path
        self._endpoint = f"{base}{path}"

    async def analyse(self, shot: Screenshot, question: str) -> tuple[bool, str]:
        import httpx  # lazy import

        s = self._settings
        try:
            jpeg = await asyncio.to_thread(
                encode_jpeg, shot, s.vision_jpeg_quality, s.vision_max_edge_px
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("openclaw_encode_failed", error=str(exc))
            return False, f"Vision call to OpenClaw failed: encode error ({exc})"

        log.info(
            "vision_payload_encoded",
            backend=self.name,
            jpeg_bytes=len(jpeg),
            w=shot.width,
            h=shot.height,
        )

        request_id = uuid4().hex[:12]
        files = {"image": ("screen.jpg", jpeg, "image/jpeg")}
        data = {
            "agent": s.openclaw_agent,
            "request_id": request_id,
            "question": question or "",
        }
        headers = {"Authorization": f"Bearer {s.openclaw_api_key}"}
        timeout = float(s.openclaw_vision_timeout_s)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    self._endpoint, data=data, files=files, headers=headers
                )
        except httpx.TimeoutException:
            log.warning("openclaw_timeout", endpoint=self._endpoint, timeout=timeout)
            return False, "Vision call to OpenClaw failed: request timed out."
        except httpx.HTTPError as exc:
            log.warning("openclaw_network_error", error=str(exc))
            return False, f"Vision call to OpenClaw failed: network error ({exc.__class__.__name__})."
        except Exception as exc:  # noqa: BLE001
            log.warning("openclaw_unexpected_error", error=str(exc))
            return False, f"Vision call to OpenClaw failed: {exc.__class__.__name__}."

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:120].replace("\n", " ")
            log.warning(
                "openclaw_bad_status",
                status=resp.status_code,
                body_preview=body_preview,
            )
            return False, f"Vision call to OpenClaw failed: HTTP {resp.status_code}."

        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("openclaw_bad_json", error=str(exc))
            return False, "Vision call to OpenClaw failed: invalid JSON response."

        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            log.warning("openclaw_missing_text", payload_keys=list(payload) if isinstance(payload, dict) else None)
            return False, "Vision call to OpenClaw failed: response missing 'text'."
        return True, text.strip()


class OpenAIBackend:
    """Calls OpenAI's `chat.completions` with an image_url data URL.

    Uses `gpt-4o-mini` by default (cheap, vision-capable). The SDK is
    synchronous, so we hop to a thread to avoid blocking the event loop.
    """

    name = "openai"

    SYSTEM_PROMPT = "Answer in 1–2 short sentences. Be specific."
    MAX_REPLY_CHARS = 500

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # NOTE: client is constructed per-call to keep failure paths simple
        # (see follow-up note in the report). Caching the OpenAI() instance
        # on self would be a tiny throughput win at the cost of a shutdown
        # contract.

    async def analyse(self, shot: Screenshot, question: str) -> tuple[bool, str]:
        try:
            from openai import OpenAI  # lazy import
        except Exception as exc:  # noqa: BLE001
            log.warning("openai_import_failed", error=str(exc))
            return False, "Vision call to OpenAI failed: SDK import error."

        s = self._settings
        try:
            jpeg = await asyncio.to_thread(
                encode_jpeg, shot, s.vision_jpeg_quality, s.vision_max_edge_px
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("openai_encode_failed", error=str(exc))
            return False, f"Vision call to OpenAI failed: encode error ({exc})."

        log.info(
            "vision_payload_encoded",
            backend=self.name,
            jpeg_bytes=len(jpeg),
            w=shot.width,
            h=shot.height,
        )

        b64 = base64.b64encode(jpeg).decode("ascii")
        prompt = (question or "").strip() or "Describe what's on the screen."
        model = s.openai_vision_model or "gpt-4o-mini"

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ]

        def _call() -> str:
            client = OpenAI(api_key=s.openai_api_key)
            resp = client.chat.completions.create(model=model, messages=messages)
            content = resp.choices[0].message.content or ""
            return content.strip()

        try:
            text = await asyncio.to_thread(_call)
        except Exception as exc:  # noqa: BLE001
            log.warning("openai_call_failed", error=str(exc), model=model)
            return False, f"Vision call to OpenAI failed: {exc.__class__.__name__}."

        if not text:
            return False, "Vision call to OpenAI failed: empty reply."
        if len(text) > self.MAX_REPLY_CHARS:
            text = text[: self.MAX_REPLY_CHARS].rstrip() + "..."
        return True, text


def build_backend(settings: Settings) -> VisionBackend:
    """Pick a backend from config. Unknown or unconfigured → NullBackend."""
    choice = (settings.vision_backend or "null").strip().lower()

    if choice in ("", "null", "none", "stub"):
        return NullBackend()

    if choice == "openai":
        if not settings.openai_api_key:
            log.warning(
                "vision_backend_unconfigured",
                requested="openai",
                fallback="null",
                missing="openai_api_key",
            )
            return NullBackend()
        return OpenAIBackend(settings)

    if choice == "openclaw":
        if not settings.openclaw_api_url or not settings.openclaw_api_key:
            log.warning(
                "vision_backend_unconfigured",
                requested="openclaw",
                fallback="null",
                missing=[
                    name
                    for name, val in (
                        ("openclaw_api_url", settings.openclaw_api_url),
                        ("openclaw_api_key", settings.openclaw_api_key),
                    )
                    if not val
                ],
            )
            return NullBackend()
        return OpenClawBackend(settings)

    log.warning(
        "vision_backend_unknown",
        requested=choice,
        fallback="null",
    )
    return NullBackend()
