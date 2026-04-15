"""Camera + MediaPipe GestureRecognizer orchestration (Phase 5).

A producer thread owns `cv2.VideoCapture` (opened with CAP_DSHOW to avoid the
Windows MSMF open-latency bug) and feeds RGB frames into a LIVE_STREAM
`GestureRecognizer`. MediaPipe delivers results on its own worker thread; from
there we marshal `FrameResult`s onto the asyncio loop via
`run_coroutine_threadsafe` / `call_soon_threadsafe` — mirroring `kobe.audio`.
Heavy deps (cv2, mediapipe, numpy, httpx) are lazy-imported.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from kobe.config import Settings
from kobe.events import WebcamStatus

log = structlog.get_logger(__name__)

OnResult = Callable[["FrameResult"], Awaitable[None] | None]


@dataclass(frozen=True)
class FrameResult:
    """One MediaPipe inference tagged with its capture timestamp.

    `landmarks` is the 21 normalized (x,y,z) coords of hand 0 (empty if no
    hand). `gesture_label` is MediaPipe's raw label — downstream maps it to
    KOBE's semantic vocabulary."""

    timestamp_ms: int
    landmarks: list[tuple[float, float, float]]
    gesture_label: str
    gesture_score: float
    handedness: str  # "Left" | "Right" | ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_model(settings: Settings) -> Path:
    """Resolve the gesture model, downloading on first run.

    Idempotent: returns the path immediately if it exists with non-zero size.
    Otherwise streams the .task from `settings.gesture_model_url` into
    `settings.gesture_model_path` (with `~` expansion). Raises on failure —
    callers degrade gracefully."""
    import httpx  # lazy

    path = Path(settings.gesture_model_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 0:
        return path

    url = settings.gesture_model_url
    log.info("gesture_model_downloading", url=url, dest=str(path))
    tmp = path.with_suffix(path.suffix + ".part")
    bytes_written = 0
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as fh:
                    async for chunk in resp.aiter_bytes(chunk_size=64 * 1024):
                        if chunk:
                            fh.write(chunk)
                            bytes_written += len(chunk)
        tmp.replace(path)
    finally:
        # If the rename never happened, drop the partial. Covers both regular
        # exceptions AND BaseException (e.g. asyncio.CancelledError in 3.11+).
        if tmp.exists() and not path.exists():
            try:
                tmp.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
    log.info("gesture_model_downloaded", bytes=bytes_written, dest=str(path))
    return path


class GestureCamera:
    """Owns the webcam, recognizer, and producer thread.

    The MediaPipe result callback runs on MP's thread — from there we only
    touch `self._loop` via the two threadsafe bridges."""

    _FPS_WINDOW = 30

    def __init__(
        self,
        settings: Settings,
        on_result: OnResult,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._settings = settings
        self._on_result = on_result
        self._loop = loop
        self._on_result_is_coro = inspect.iscoroutinefunction(on_result)

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._cap: Any = None
        self._recognizer: Any = None
        self._running = False
        self._shutting_down: bool = False
        self._lifecycle_lock = threading.Lock()

        self._last_ts_ms: int = 0  # strictly-monotonic per MP's contract
        self._frame_count: int = 0
        self._fps_samples: deque[tuple[int, float]] = deque(maxlen=self._FPS_WINDOW)
        self._last_detail: str = ""
        # Health tracking: flip `connected` offline after ~a third of a second
        # of back-to-back failed reads (camera unplug, driver hiccup, etc.).
        self._consecutive_read_failures: int = 0
        self._healthy: bool = True
        self._offline_after_fails: int = max(10, settings.gesture_camera_fps // 3)

    # ------------------------------------------------------------------ API

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        import cv2  # lazy
        import mediapipe as mp

        with self._lifecycle_lock:
            if self._running:
                return

            model_path = Path(self._settings.gesture_model_path).expanduser()
            if not model_path.is_file():
                raise RuntimeError(
                    f"gesture model not found at {model_path}; call ensure_model() first"
                )

            vision = mp.tasks.vision
            options = vision.GestureRecognizerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
                running_mode=vision.RunningMode.LIVE_STREAM,
                num_hands=self._settings.gesture_num_hands,
                min_hand_detection_confidence=self._settings.gesture_min_detection_confidence,
                min_hand_presence_confidence=self._settings.gesture_min_presence_confidence,
                min_tracking_confidence=self._settings.gesture_min_tracking_confidence,
                result_callback=self._on_mp_result,
            )
            self._recognizer = vision.GestureRecognizer.create_from_options(options)

            cap = cv2.VideoCapture(self._settings.gesture_camera_index, cv2.CAP_DSHOW)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self._settings.gesture_camera_width))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self._settings.gesture_camera_height))
            cap.set(cv2.CAP_PROP_FPS, float(self._settings.gesture_camera_fps))
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1.0)
            except Exception:  # noqa: BLE001 — some backends reject this setter.
                pass

            if not cap.isOpened():
                cap.release()
                self._close_recognizer()
                raise RuntimeError(
                    f"cv2.VideoCapture failed to open camera index "
                    f"{self._settings.gesture_camera_index} via CAP_DSHOW"
                )

            self._cap = cap
            self._stop_event.clear()
            self._last_ts_ms = 0
            self._frame_count = 0
            self._fps_samples.clear()
            self._last_detail = "ok"
            self._consecutive_read_failures = 0
            self._healthy = True
            self._thread = threading.Thread(
                target=self._loop_producer, name="kobe-gesture-cam", daemon=True
            )
            self._running = True
            self._thread.start()
            log.info(
                "gesture_camera_started",
                index=self._settings.gesture_camera_index,
                w=self._settings.gesture_camera_width,
                h=self._settings.gesture_camera_height,
                fps=self._settings.gesture_camera_fps,
            )

    def stop(self) -> None:
        self._shutting_down = True
        with self._lifecycle_lock:
            if not self._running and self._thread is None and self._cap is None:
                return
            self._stop_event.set()
            thread = self._thread
            self._thread = None
            self._running = False

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:  # noqa: BLE001
                pass
            self._cap = None
        self._close_recognizer()
        log.info("gesture_camera_stopped", frames=self._frame_count)

    def _close_recognizer(self) -> None:
        if self._recognizer is None:
            return
        try:
            self._recognizer.close()
        except Exception:  # noqa: BLE001
            pass
        self._recognizer = None

    def stats(self) -> WebcamStatus:
        if not self._healthy:
            detail = f"{self._consecutive_read_failures} consecutive read failures"
        else:
            detail = self._last_detail
        return WebcamStatus(
            connected=self._running and self._healthy,
            fps=self._measured_fps(),
            frame_count=self._frame_count,
            detail=detail,
            timestamp_iso=_now_iso(),
        )

    # -------------------------------------------------------------- internals

    def _measured_fps(self) -> float:
        samples = list(self._fps_samples)
        if len(samples) < 2:
            return 0.0
        first_count, first_t = samples[0]
        last_count, last_t = samples[-1]
        dt = last_t - first_t
        if dt <= 0.0:
            return 0.0
        return float(last_count - first_count) / dt

    def _loop_producer(self) -> None:
        import cv2  # lazy
        import mediapipe as mp
        import numpy as np  # noqa: F401 — mp.Image wants numpy arrays

        cap = self._cap
        recognizer = self._recognizer
        assert cap is not None and recognizer is not None

        while not self._stop_event.is_set():
            try:
                ret, frame = cap.read()
            except Exception as exc:  # noqa: BLE001
                ret, frame = False, None
                self._last_detail = f"frame_read_raised: {exc.__class__.__name__}"
            if not ret or frame is None:
                self._consecutive_read_failures += 1
                if self._consecutive_read_failures >= self._offline_after_fails:
                    self._healthy = False
                    self._last_detail = (
                        f"{self._consecutive_read_failures} consecutive read failures"
                    )
                elif not self._last_detail.startswith("frame_read_raised"):
                    self._last_detail = "frame_read_failed"
                self._stop_event.wait(0.05)
                continue

            # Successful read — reset failure counter and recover health.
            if not self._healthy:
                log.info("webcam_recovered", failures=self._consecutive_read_failures)
                self._healthy = True
            self._consecutive_read_failures = 0

            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            except Exception as exc:  # noqa: BLE001
                self._last_detail = f"convert_failed: {exc.__class__.__name__}"
                continue

            ts_ms = time.perf_counter_ns() // 1_000_000
            if ts_ms <= self._last_ts_ms:
                ts_ms = self._last_ts_ms + 1
            self._last_ts_ms = ts_ms

            try:
                recognizer.recognize_async(mp_image, ts_ms)
            except Exception as exc:  # noqa: BLE001
                self._last_detail = f"recognize_failed: {exc.__class__.__name__}"
                if self._stop_event.is_set():
                    break
                self._stop_event.wait(0.01)
                continue

            self._frame_count += 1
            self._fps_samples.append((self._frame_count, time.perf_counter()))
            self._last_detail = "ok"

    def _on_mp_result(self, result: Any, output_image: Any, timestamp_ms: int) -> None:
        """MediaPipe callback (runs on MP's worker thread). Must never raise —
        exceptions here crash the MediaPipe graph."""
        try:
            if self._shutting_down or self._recognizer is None:
                return
        except Exception:  # noqa: BLE001 — doubly safe against late-callback races
            return

        try:
            landmarks: list[tuple[float, float, float]] = []
            hand_landmarks = getattr(result, "hand_landmarks", None) or []
            if hand_landmarks:
                landmarks = [
                    (float(lm.x), float(lm.y), float(lm.z)) for lm in hand_landmarks[0]
                ]

            label = ""
            score = 0.0
            gestures = getattr(result, "gestures", None) or []
            if gestures and gestures[0]:
                top = gestures[0][0]
                label = str(getattr(top, "category_name", "") or "")
                score = float(getattr(top, "score", 0.0) or 0.0)

            handedness = ""
            hd = getattr(result, "handedness", None) or []
            if hd and hd[0]:
                handedness = str(getattr(hd[0][0], "category_name", "") or "")

            fr = FrameResult(
                timestamp_ms=int(timestamp_ms),
                landmarks=landmarks,
                gesture_label=label,
                gesture_score=score,
                handedness=handedness,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("gesture_callback_parse_failed", error=str(exc))
            return

        loop = self._loop
        if loop is None or loop.is_closed():
            return

        try:
            if self._on_result_is_coro:
                asyncio.run_coroutine_threadsafe(self._on_result(fr), loop)  # type: ignore[arg-type]
            else:
                loop.call_soon_threadsafe(self._on_result, fr)
        except RuntimeError:
            return  # loop shutting down — drop silently
        except Exception as exc:  # noqa: BLE001
            log.warning("gesture_dispatch_failed", error=str(exc))
