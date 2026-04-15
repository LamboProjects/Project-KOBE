"""Wake word detection service.

Consumes 20 ms PCM frames from the shared AudioSource, accumulates them into 80 ms
chunks (1280 samples at 16 kHz — OpenWakeWord's native window), and runs inference
in a worker thread. Publishes `WakeDetected` on the bus.

Suppresses detection while muted or while TTS is speaking to avoid self-trigger.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import numpy as np
import structlog

from kobe.audio import AudioSource
from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import (
    MuteToggled,
    RecordingStarted,
    RecordingStopped,
    SpeakFinished,
    SpeakStarted,
    WakeDetected,
)

log = structlog.get_logger(__name__)

# OpenWakeWord expects 80 ms windows at 16 kHz.
CHUNK_SAMPLES = 1280
CHUNK_BYTES = CHUNK_SAMPLES * 2  # int16
DEBOUNCE_S = 2.0

# Models that ship with openwakeword by default. Anything else is treated as a
# user-supplied path; if loading fails we fall back to hey_jarvis.
_BUILTIN_MODELS = {
    "alexa",
    "hey_jarvis",
    "hey_mycroft",
    "hey_rhasspy",
    "timer",
    "weather",
}


def _load_model(model_list: list[str]) -> tuple[Any, list[str]]:
    """Load OpenWakeWord with onnx, fall back to tflite. Returns (model, resolved_names)."""
    from openwakeword.model import Model  # local import: heavy

    # Unknown names (e.g. the not-yet-trained "hey_kobe") get swapped for hey_jarvis.
    resolved: list[str] = []
    for name in model_list:
        if name in _BUILTIN_MODELS or name.endswith((".onnx", ".tflite")):
            resolved.append(name)
        else:
            log.warning(
                "wake_model_not_shipped_fallback",
                requested=name,
                fallback="hey_jarvis",
                hint="Train a custom model or drop an .onnx/.tflite path in wake_models.",
            )
            resolved.append("hey_jarvis")
    # De-dupe while preserving order.
    seen: set[str] = set()
    resolved = [m for m in resolved if not (m in seen or seen.add(m))]

    last_exc: Exception | None = None
    for framework in ("onnx", "tflite"):
        try:
            model = Model(wakeword_models=resolved, inference_framework=framework)
            log.info("wake_model_loaded", framework=framework, models=resolved)
            return model, resolved
        except Exception as e:  # noqa: BLE001 — framework probe
            log.warning("wake_model_load_failed", framework=framework, error=str(e))
            last_exc = e
    raise RuntimeError(f"Failed to load any OpenWakeWord framework: {last_exc}")


async def run_wake_service(bus: Bus, settings: Settings, audio: AudioSource) -> None:
    # Degrade cleanly if OpenWakeWord can't load either backend — otherwise the
    # `RuntimeError` from `_load_model` escapes `run_wake_service`, the
    # `asyncio.TaskGroup` bundles it into an ExceptionGroup, and **every**
    # other service gets cancelled. Failing soft here means the rest of KOBE
    # (HUD / brain / TTS / integrations / vision / gestures / fan) keeps running.
    try:
        model, loaded_names = await asyncio.to_thread(_load_model, settings.wake_model_list)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "wake_service_unavailable",
            error=str(exc),
            hint="install openwakeword, provide a valid wake_models list, "
                 "or set WAKE_ENABLED (future flag) — pipeline continues without wake",
        )
        return

    audio_q = audio.subscribe()
    mute_q = bus.subscribe(MuteToggled)
    speak_start_q = bus.subscribe(SpeakStarted)
    speak_finish_q = bus.subscribe(SpeakFinished)
    recording_start_q = bus.subscribe(RecordingStarted)
    recording_stop_q = bus.subscribe(RecordingStopped)

    muted = False
    speaking = False
    recording = False
    last_detect_ts = 0.0
    buffer = bytearray()

    def _drain_events() -> None:
        nonlocal muted, speaking, recording
        while True:
            try:
                ev = mute_q.get_nowait()
            except asyncio.QueueEmpty:
                break
            muted = ev.muted
            log.info("wake_mute", muted=muted)
        while True:
            try:
                speak_start_q.get_nowait()
            except asyncio.QueueEmpty:
                break
            speaking = True
        while True:
            try:
                speak_finish_q.get_nowait()
            except asyncio.QueueEmpty:
                break
            speaking = False
        while True:
            try:
                recording_start_q.get_nowait()
            except asyncio.QueueEmpty:
                break
            recording = True
        while True:
            try:
                recording_stop_q.get_nowait()
            except asyncio.QueueEmpty:
                break
            recording = False

    log.info("wake_service_started", models=loaded_names, threshold=settings.wake_threshold)

    try:
        while True:
            frame = await audio_q.get()
            _drain_events()

            if muted or speaking or recording:
                # Still consume frames so we don't back up the queue, but skip inference.
                # Suppressing during `recording` prevents a false re-trigger on the
                # user's own utterance while STT is capturing it.
                buffer.clear()
                continue

            buffer.extend(frame)
            if len(buffer) < CHUNK_BYTES:
                continue

            chunk_bytes = bytes(buffer[:CHUNK_BYTES])
            del buffer[:CHUNK_BYTES]
            chunk = np.frombuffer(chunk_bytes, dtype=np.int16)

            try:
                scores = await asyncio.to_thread(model.predict, chunk)
            except Exception as e:  # noqa: BLE001
                log.error("wake_predict_error", error=str(e))
                continue

            now = time.monotonic()
            if now - last_detect_ts < DEBOUNCE_S:
                continue

            best_name = ""
            best_score = 0.0
            for name, score in scores.items():
                s = float(score)
                if s > best_score:
                    best_name = name
                    best_score = s

            if best_score > settings.wake_threshold:
                last_detect_ts = now
                log.info("wake_detected", keyword=best_name, confidence=best_score)
                await bus.publish(WakeDetected(keyword=best_name, confidence=best_score))

    except asyncio.CancelledError:
        log.info("wake_service_cancelled")
        audio.unsubscribe(audio_q)
        bus.unsubscribe(MuteToggled, mute_q)
        bus.unsubscribe(SpeakStarted, speak_start_q)
        bus.unsubscribe(SpeakFinished, speak_finish_q)
        bus.unsubscribe(RecordingStarted, recording_start_q)
        bus.unsubscribe(RecordingStopped, recording_stop_q)
        raise
