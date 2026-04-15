"""Event types exchanged on the internal bus.

Events are immutable dataclasses. Subscribers receive them via `Bus.subscribe(EventType)`.
Publishers never hold references to subscribers — coupling is by event type only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


def _new_id() -> str:
    return uuid4().hex[:12]


@dataclass(frozen=True, slots=True)
class WakeDetected:
    """A wake word was detected. STT should start recording; TTS should interrupt."""
    keyword: str
    confidence: float
    request_id: str = field(default_factory=_new_id)


@dataclass(frozen=True, slots=True)
class RecordingStarted:
    request_id: str


@dataclass(frozen=True, slots=True)
class RecordingStopped:
    request_id: str
    duration_s: float
    reason: str  # "vad_silence" | "max_duration" | "interrupted"


@dataclass(frozen=True, slots=True)
class TranscriptReady:
    """STT produced a transcript. Brain should consume and route."""
    request_id: str
    text: str
    duration_s: float


@dataclass(frozen=True, slots=True)
class ResponseReady:
    """Brain produced a spoken response. TTS should speak it."""
    request_id: str
    text: str


@dataclass(frozen=True, slots=True)
class ActionRequested:
    """Brain returned an action intent. Executor should run it."""
    request_id: str
    action: str  # e.g. "open_app"
    params: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ActionCompleted:
    request_id: str
    action: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SpeakStarted:
    request_id: str


@dataclass(frozen=True, slots=True)
class SpeakFinished:
    request_id: str
    interrupted: bool = False


@dataclass(frozen=True, slots=True)
class InterruptRequested:
    """Stop current TTS playback (barge-in)."""
    reason: str


@dataclass(frozen=True, slots=True)
class MuteToggled:
    """User toggled mute. Wake service should pause/resume detection."""
    muted: bool


@dataclass(frozen=True, slots=True)
class SystemStatus:
    """Periodic system telemetry for the HUD."""
    foreground_app: str
    cpu_percent: float
    memory_percent: float
    timestamp_iso: str


@dataclass(frozen=True, slots=True)
class PrinterStatus:
    """Bambu P1S live state. Emitted by the printer integration, consumed by HUD + voice."""
    connected: bool
    stage: str  # "idle" | "preparing" | "printing" | "paused" | "finished" | "failed" | "unknown"
    progress_pct: float  # 0..100
    remaining_minutes: int
    nozzle_temp_c: float
    bed_temp_c: float
    filename: str
    timestamp_iso: str


@dataclass(frozen=True, slots=True)
class PrinterAlert:
    """Notable printer transitions (start / complete / fail / pause / resume)."""
    kind: str  # "started" | "completed" | "failed" | "paused" | "resumed"
    message: str
    filename: str = ""


@dataclass(frozen=True, slots=True)
class NowPlayingChanged:
    """Current Spotify playback snapshot. Empty when nothing is active."""
    is_playing: bool
    track: str = ""
    artist: str = ""
    album: str = ""
    progress_ms: int = 0
    duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class ConfirmationRequested:
    """Brain returned a destructive intent. Confirmation manager will speak the prompt,
    listen for the user's yes/no, and emit a regular `ActionRequested` on confirm."""
    request_id: str
    action: str
    params: dict[str, Any]
    prompt: str  # "Cancel the print. Confirm?"


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    """Outcome of a ConfirmationRequested flow. Mostly informational; HUD can show it."""
    request_id: str
    action: str
    confirmed: bool


@dataclass(frozen=True, slots=True)
class VisionRequested:
    """Ask the vision service to capture + analyse the screen.

    `mode` chooses what to capture:
      - `"foreground"` — just the current foreground window (default)
      - `"full"`       — every monitor stitched together
      - `"region"`     — a rectangle given by `region=(x,y,w,h)`
    """
    request_id: str
    question: str
    mode: str = "foreground"
    region: tuple[int, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class GestureDetected:
    """A gesture was recognised from the webcam stream.

    `name` uses KOBE's semantic vocabulary (not MediaPipe's pretrained labels):
    "swipe_left" | "swipe_right" | "point" | "confirm" | "dismiss".
    `raw_label` carries the underlying MediaPipe label (or "swipe"/"shake" for
    the custom motion detectors) for debugging.
    """
    name: str
    confidence: float
    hand: str  # "left" | "right" | "unknown"
    raw_label: str
    timestamp_iso: str


@dataclass(frozen=True, slots=True)
class FanClipPushed:
    """A hologram clip has been rendered and handed to the fan backend.
    `name` is a short clip identifier (`"logo"` / `"printer"` / `"spotify"` /
    `"gesture"` / `"stl"`); `path` is server-local and only populated by
    backends that persist to disk (stripped before HUD relay)."""
    name: str
    duration_s: float
    path: str = ""
    timestamp_iso: str = ""


@dataclass(frozen=True, slots=True)
class FanBackendStatus:
    """Periodic health pulse for the hologram fan backend (not the physical
    fan's own state — that's vendor-proprietary)."""
    backend: str  # "null" | "file" | "http" | custom
    connected: bool
    detail: str = ""
    timestamp_iso: str = ""


@dataclass(frozen=True, slots=True)
class ProfileChanged:
    """User profile was switched (e.g. Lambert → Jasmine). Downstream services
    can re-theme, swap wake words, change TTS voice, etc. For Phase 6 scaffolding
    the main consumer is the HUD; future profile-aware services can subscribe."""
    name: str       # canonical profile id, e.g. "lambert"
    label: str      # display label, e.g. "Lambert"
    timestamp_iso: str


@dataclass(frozen=True, slots=True)
class WebcamStatus:
    """Periodic webcam health snapshot for the HUD."""
    connected: bool
    fps: float
    frame_count: int
    detail: str = ""
    timestamp_iso: str = ""


@dataclass(frozen=True, slots=True)
class VisionResult:
    """Outcome of a VisionRequested. `summary` is the human-readable text the brain
    (or TTS) will speak. `image_path` is populated only when the service was asked
    to persist the screenshot to disk. `mode` is the capture mode actually used
    (foreground / full / region — may differ from the request if foreground fell
    through to full). `context_name` is the per-app context the specialist used
    (vscode, bambu_studio, freecad, …)."""
    request_id: str
    ok: bool
    summary: str
    width: int
    height: int
    backend: str
    image_path: str = ""
    timestamp_iso: str = ""
    mode: str = ""
    context_name: str = ""


# Union of everything — handy for type hints in the bus.
Event = (
    WakeDetected
    | RecordingStarted
    | RecordingStopped
    | TranscriptReady
    | ResponseReady
    | ActionRequested
    | ActionCompleted
    | SpeakStarted
    | SpeakFinished
    | InterruptRequested
    | MuteToggled
    | SystemStatus
    | PrinterStatus
    | PrinterAlert
    | NowPlayingChanged
    | ConfirmationRequested
    | ConfirmationResult
    | VisionRequested
    | VisionResult
    | GestureDetected
    | WebcamStatus
    | ProfileChanged
    | FanClipPushed
    | FanBackendStatus
)
