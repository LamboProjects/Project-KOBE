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

from pydantic import Field
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

    # Logging
    log_level: str = "INFO"

    @property
    def wake_model_list(self) -> list[str]:
        return [m.strip() for m in self.wake_models.split(",") if m.strip()]


def load_settings() -> Settings:
    return Settings()
