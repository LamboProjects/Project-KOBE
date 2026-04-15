"""Speech-to-text service.

Subscribes to WakeDetected. On each wake, captures pre-roll + live mic audio,
detects end-of-speech via an RMS-energy VAD, and transcribes via faster-whisper.

A simple energy-based VAD sidesteps webrtcvad's C extension (which needs MSVC
build tools on Windows with modern Pythons). `vad_aggressiveness` (0..3) is
reinterpreted as an RMS threshold: higher = treat more frames as silence.
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
    RecordingStarted,
    RecordingStopped,
    TranscriptReady,
    WakeDetected,
)

log = structlog.get_logger(__name__)

FRAME_MS = 20
SAMPLE_WIDTH = 2  # int16
INT16_MAX = 32768.0

# Energy thresholds, in int16 RMS. Tuned conservatively for a desk mic.
# 0 (off) → keep everything voiced; 3 (aggressive) → high floor.
_RMS_THRESHOLDS = {0: 150.0, 1: 300.0, 2: 500.0, 3: 900.0}


def _pcm_bytes_to_float32(pcm: bytes) -> np.ndarray:
    if not pcm:
        return np.zeros(0, dtype=np.float32)
    arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / INT16_MAX
    return arr


def _frame_is_speech(frame: bytes, threshold: float) -> bool:
    """Energy-based VAD. Returns True if the frame's RMS exceeds the threshold."""
    if not frame:
        return False
    pcm = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
    if pcm.size == 0:
        return False
    rms = float(np.sqrt(np.mean(pcm * pcm)))
    return rms > threshold


def _load_model(settings: Settings) -> Any:
    from faster_whisper import WhisperModel

    try:
        log.info(
            "whisper_loading",
            model=settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        t0 = time.monotonic()
        model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        log.info("whisper_loaded", load_s=round(time.monotonic() - t0, 3))
        return model
    except Exception as e:
        log.warning("whisper_cuda_failed", error=str(e))
        t0 = time.monotonic()
        model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
        log.info("whisper_loaded_cpu_fallback", load_s=round(time.monotonic() - t0, 3))
        return model


async def _capture_utterance(
    audio: AudioSource,
    settings: Settings,
    rms_threshold: float,
) -> tuple[bytes, float, str]:
    """Capture one utterance: pre-roll + live frames until silence or max duration."""
    pre = audio.pre_roll(1.0)
    collected = bytearray(pre)

    queue = audio.subscribe()
    # Drain any already-buffered frames so we start fresh on "now".
    while not queue.empty():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    silence_ms = 0
    voiced_ms = 0
    elapsed_ms = 0
    min_voiced_ms = 200  # require some speech before trusting silence
    max_ms = int(settings.max_record_seconds * 1000)
    silence_end_ms = settings.silence_end_ms
    reason = "max_duration"

    start = time.monotonic()
    try:
        while True:
            if elapsed_ms >= max_ms:
                reason = "max_duration"
                break
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            collected.extend(frame)
            elapsed_ms += FRAME_MS

            is_speech = _frame_is_speech(frame, rms_threshold)
            if is_speech:
                voiced_ms += FRAME_MS
                silence_ms = 0
            else:
                silence_ms += FRAME_MS
                if voiced_ms >= min_voiced_ms and silence_ms >= silence_end_ms:
                    reason = "vad_silence"
                    break
    finally:
        audio.unsubscribe(queue)

    duration_s = time.monotonic() - start
    return bytes(collected), duration_s, reason


def _transcribe_sync(model: Any, pcm: bytes) -> str:
    audio_f32 = _pcm_bytes_to_float32(pcm)
    if audio_f32.size == 0:
        return ""
    segments, _info = model.transcribe(
        audio_f32,
        language="en",
        vad_filter=False,
    )
    return "".join(seg.text for seg in segments).strip()


async def _handle_wake(
    event: WakeDetected,
    bus: Bus,
    settings: Settings,
    audio: AudioSource,
    model_ref: dict[str, Any],
    rms_threshold: float,
) -> None:
    rid = event.request_id
    log.info("stt_wake", request_id=rid, keyword=event.keyword)

    await bus.publish(RecordingStarted(request_id=rid))

    if model_ref.get("model") is None:
        model_ref["model"] = await asyncio.to_thread(_load_model, settings)
    model = model_ref["model"]

    pcm, rec_duration_s, reason = await _capture_utterance(audio, settings, rms_threshold)
    await bus.publish(
        RecordingStopped(request_id=rid, duration_s=rec_duration_s, reason=reason)
    )
    log.info(
        "stt_recorded",
        request_id=rid,
        duration_s=round(rec_duration_s, 3),
        reason=reason,
        bytes=len(pcm),
    )

    t0 = time.monotonic()
    try:
        text = await asyncio.to_thread(_transcribe_sync, model, pcm)
    except Exception as e:
        log.exception("stt_transcribe_error", request_id=rid, error=str(e))
        text = ""
    transcribe_s = time.monotonic() - t0

    if not text:
        log.info("stt_empty_transcript", request_id=rid, transcribe_s=round(transcribe_s, 3))
    else:
        log.info(
            "stt_transcript",
            request_id=rid,
            text=text,
            transcribe_s=round(transcribe_s, 3),
        )

    await bus.publish(
        TranscriptReady(request_id=rid, text=text, duration_s=transcribe_s)
    )


async def run_stt_service(bus: Bus, settings: Settings, audio: AudioSource) -> None:
    """Consume WakeDetected events serially and emit transcripts."""
    aggr = max(0, min(3, settings.vad_aggressiveness))
    rms_threshold = _RMS_THRESHOLDS[aggr]
    model_ref: dict[str, Any] = {"model": None}
    queue = bus.subscribe(WakeDetected)
    log.info(
        "stt_service_started",
        vad="energy_rms",
        aggressiveness=aggr,
        rms_threshold=rms_threshold,
    )

    try:
        while True:
            event = await queue.get()
            try:
                await _handle_wake(event, bus, settings, audio, model_ref, rms_threshold)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.exception("stt_handle_wake_error", error=str(e))
    except asyncio.CancelledError:
        log.info("stt_service_cancelled")
        raise
    finally:
        bus.unsubscribe(WakeDetected, queue)
