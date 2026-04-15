"""Screen capture primitives.

Single-screenshot API; no streaming. The service layer decides when/what to
capture and hands a `Screenshot` to whichever `VisionBackend` is configured.

On Windows we use `mss` for fast BGRA grabs (zero-copy-ish) and `pygetwindow`
to resolve the foreground window rectangle. Pillow is only used for optional
PNG encoding when the service wants to persist an image.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import structlog

log = structlog.get_logger(__name__)

Mode = Literal["foreground", "full", "region"]


@dataclass(frozen=True)
class Screenshot:
    """Raw captured image. `pixels` is BGRA bytes of shape (height*width*4)."""
    pixels: bytes
    width: int
    height: int
    mode: str  # "foreground" | "full" | "region"
    captured_at_iso: str
    window_title: str = ""  # populated for "foreground" mode

    @property
    def size_bytes(self) -> int:
        return len(self.pixels)


def _foreground_rect() -> tuple[int, int, int, int, str] | None:
    """Return `(left, top, width, height, title)` of the foreground window.

    Returns `None` when no foreground window is resolvable (e.g. the desktop
    itself has focus). Isolated so the service can fall through to full-screen.
    """
    try:
        import pygetwindow  # local import: optional dep path
    except ImportError as exc:
        log.debug("capture_pygetwindow_missing", error=str(exc))
        return None
    try:
        win = pygetwindow.getActiveWindow()
    except Exception as exc:  # noqa: BLE001 - pygetwindow raises bare Exception on Win
        log.debug("capture_active_window_error", error=str(exc))
        return None
    if win is None:
        return None
    title = getattr(win, "title", "") or ""
    try:
        left = int(getattr(win, "left", 0))
        top = int(getattr(win, "top", 0))
        width = int(getattr(win, "width", 0))
        height = int(getattr(win, "height", 0))
    except Exception:  # noqa: BLE001
        return None
    if width <= 0 or height <= 0:
        return None
    return left, top, width, height, title


def capture(
    mode: Mode = "foreground",
    region: tuple[int, int, int, int] | None = None,
) -> Screenshot:
    """Capture a screenshot synchronously. Callers should wrap in `asyncio.to_thread`."""
    import mss  # local import; mss opens a handle per-instance

    # Validate region early — if the caller asked for a region but didn't give
    # one (e.g. a bad `ActionRequested` payload), fail loudly rather than
    # silently widening capture to every monitor. That widening would be a
    # privacy leak: the user asked for a box, we captured their whole desktop.
    if mode == "region":
        if region is None or len(region) != 4:
            raise ValueError(
                "mode='region' requires a valid (x, y, width, height) tuple"
            )
        x, y, w, h = region
        if w <= 0 or h <= 0:
            raise ValueError(f"mode='region' got non-positive size: width={w}, height={h}")

    title = ""
    with mss.mss() as sct:
        if mode == "region" and region is not None:
            left, top, width, height = region
            bbox = {"left": left, "top": top, "width": width, "height": height}
        elif mode == "foreground":
            fg = _foreground_rect()
            if fg is None:
                # Degrade silently to full-screen rather than raise.
                log.info("capture_foreground_fallback_to_full")
                mode = "full"
                bbox = sct.monitors[0]
            else:
                left, top, width, height, title = fg
                bbox = {"left": left, "top": top, "width": width, "height": height}
        else:
            # Full = the "all monitors" virtual display. mss.monitors[0] spans
            # every physical screen.
            bbox = sct.monitors[0]
            mode = "full"

        raw = sct.grab(bbox)
        # mss returns BGRA; keep it that way. Backends will convert if they need RGB.
        pixels = bytes(raw.bgra)
        width, height = int(raw.width), int(raw.height)

    return Screenshot(
        pixels=pixels,
        width=width,
        height=height,
        mode=mode,
        captured_at_iso=datetime.now(timezone.utc).isoformat(),
        window_title=title,
    )


def save_png(shot: Screenshot, directory: str | Path) -> str:
    """Persist a Screenshot as PNG. Returns the written path."""
    from PIL import Image

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = shot.captured_at_iso.replace(":", "").replace("-", "").replace(".", "")
    fname = f"{stamp}_{shot.mode}_{shot.width}x{shot.height}.png"
    path = directory / fname

    # BGRA → RGBA for Pillow.
    img = Image.frombuffer(
        "RGBA", (shot.width, shot.height), shot.pixels, "raw", "BGRA", 0, 1
    )
    img.save(path, format="PNG", optimize=False)
    return str(path)
