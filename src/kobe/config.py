"""Runtime configuration loaded from config/.env and environment variables.

Env file resolution order (first existing wins):
  1. `KOBE_ENV_FILE` environment variable (explicit override)
  2. `./config/.env` relative to current working directory
  3. `<repo_root>/config/.env` inferred from this module's path (dev/editable install)
  4. `~/.config/kobe/.env`
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str | None:
    candidates: list[Path] = []
    override = os.environ.get("KOBE_ENV_FILE")
    if override:
        candidates.append(Path(override))
    candidates.append(Path.cwd() / "config" / ".env")
    # In an editable install, parents[2] is the repo root; in a wheel install it will
    # point into site-packages and that candidate simply won't exist — which is fine.
    candidates.append(Path(__file__).resolve().parents[2] / "config" / ".env")
    candidates.append(Path.home() / ".config" / "kobe" / ".env")
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenClaw brain
    openclaw_api_url: str = "http://localhost:8000"
    openclaw_api_key: str = ""
    openclaw_agent: str = "main"
    openclaw_timeout_s: float = 30.0

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel (default)
    elevenlabs_model_id: str = "eleven_turbo_v2_5"
    # Phase 6 persona tuning — passed verbatim into ElevenLabs `VoiceSettings`
    # if the SDK exposes them. Stability 0..1, similarity_boost 0..1,
    # style 0..1, use_speaker_boost bool.
    elevenlabs_stability: float = 0.55
    elevenlabs_similarity_boost: float = 0.75
    elevenlabs_style: float = 0.15
    elevenlabs_use_speaker_boost: bool = True
    # Named persona preset the brain prepends to OpenClaw calls.
    # "default" | "concise" | "warm" | "terse" | "excited" | custom.
    tts_persona_profile: str = "default"

    # OpenAI (TTS fallback)
    openai_api_key: str = ""
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "nova"

    # Whisper (STT)
    whisper_model: str = "base.en"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "int8_float16"

    # Wake word
    wake_threshold: float = 0.5
    wake_models: str = "hey_jarvis"  # comma-separated; stand-in until custom "Hey KOBE" model is trained

    # Audio
    audio_input_device: int | None = None
    audio_output_device: int | None = None
    audio_sample_rate: int = 16000

    # VAD / recording limits
    vad_aggressiveness: int = 2  # 0..3, webrtcvad
    max_record_seconds: float = 15.0
    silence_end_ms: int = 800

    # Mute
    mute_hotkey: str = "ctrl+alt+k"

    # HUD
    hud_host: str = "127.0.0.1"
    hud_port: int = 8765
    hud_enabled: bool = True

    # System status polling
    system_status_interval_s: float = 2.0

    # Bambu Lab P1S (LAN MQTT)
    bambu_host: str = ""  # printer IP on the local network
    bambu_serial: str = ""  # printer serial (printed on the label under the bed)
    bambu_access_code: str = ""  # LAN access code from the printer UI
    bambu_poll_interval_s: float = 5.0
    bambu_enabled: bool = True

    # Spotify
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://127.0.0.1:8888/callback"
    spotify_poll_interval_s: float = 5.0

    # Discord alerts
    discord_webhook_url: str = ""

    # Confirmation flow
    confirmation_timeout_s: float = 12.0
    confirmation_yes_words: str = "yes,yeah,yep,confirm,confirmed,do it,go ahead,sure"
    confirmation_no_words: str = "no,nope,cancel,stop,nevermind,never mind,abort"

    # Gesture control (Phase 5)
    # Logitech C922 over MediaPipe Tasks API GestureRecognizer (LIVE_STREAM).
    gesture_enabled: bool = True
    gesture_camera_index: int = 0
    gesture_camera_width: int = 640
    gesture_camera_height: int = 480
    gesture_camera_fps: int = 30
    # Path the gesture recognizer model lives at on disk. If missing it's
    # auto-downloaded from the canonical Google Storage URL on first run.
    gesture_model_path: str = "~/.cache/kobe/gesture_recognizer.task"
    gesture_model_url: str = (
        "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/"
        "gesture_recognizer/float16/1/gesture_recognizer.task"
    )
    # MediaPipe inference thresholds (per the official guide defaults +
    # research recommendations).
    gesture_min_detection_confidence: float = 0.6
    gesture_min_tracking_confidence: float = 0.5
    gesture_min_presence_confidence: float = 0.5
    gesture_min_score: float = 0.6
    gesture_num_hands: int = 1
    # Static-gesture debounce: top label must win N_required of N_window frames.
    gesture_static_window: int = 6
    gesture_static_required: int = 5
    # Swipe motion detection (normalized image coords, 0..1).
    gesture_swipe_window: int = 10
    gesture_swipe_lookback: int = 5
    gesture_swipe_dx_threshold: float = 0.18
    gesture_swipe_dy_max: float = 0.08
    gesture_swipe_required_frames: int = 3
    # Cooldown between same-name detections, milliseconds.
    gesture_cooldown_ms: int = 1200

    # Screen vision
    vision_enabled: bool = True
    # Which backend analyses the screenshot. "null" = foundation stub (no model call).
    # Real backends: "openclaw" | "openai". Unconfigured backends fall back to null.
    vision_backend: str = "null"
    vision_save_screenshots: bool = False
    vision_screenshot_dir: str = "scratch/vision"
    vision_max_capture_seconds: float = 5.0
    # JPEG quality for over-the-wire transport (smaller payload than PNG).
    vision_jpeg_quality: int = 80
    # Cap the long edge before encoding so we don't ship a 4K screenshot to the API.
    vision_max_edge_px: int = 1568
    # OpenAI vision model (cheap default).
    openai_vision_model: str = "gpt-4o-mini"
    # OpenClaw vision endpoint path appended to openclaw_api_url.
    openclaw_vision_path: str = "/v1/vision"
    openclaw_vision_timeout_s: float = 30.0

    @property
    def confirmation_yes_list(self) -> list[str]:
        return [w.strip().lower() for w in self.confirmation_yes_words.split(",") if w.strip()]

    @property
    def confirmation_no_list(self) -> list[str]:
        return [w.strip().lower() for w in self.confirmation_no_words.split(",") if w.strip()]

    # Home Assistant (Phase 6 smart home)
    homeassistant_enabled: bool = True
    homeassistant_url: str = ""  # e.g. http://192.168.1.10:8123
    homeassistant_token: str = ""  # long-lived access token
    homeassistant_timeout_s: float = 10.0
    homeassistant_verify_tls: bool = True  # flip False for self-signed LAN certs

    # MuteMe Mini physical button (Phase 6)
    muteme_enabled: bool = True
    muteme_poll_ms: int = 20  # blocking read timeout; state-change driven, 50 Hz ceiling

    # Multi-profile (Phase 6 scaffold)
    profile_name: str = "lambert"
    profile_label: str = "Lambert"
    profile_config_dir: str = "config/profiles"

    # Discord richer alerts (Phase 6)
    discord_include_snapshot: bool = True  # include live progress/temps in PrinterAlert embed
    discord_digest_interval_hours: float = 0.0  # 0 disables periodic digest

    # Logging
    log_level: str = "INFO"

    @property
    def wake_model_list(self) -> list[str]:
        return [m.strip() for m in self.wake_models.split(",") if m.strip()]


def load_settings() -> Settings:
    return Settings()
