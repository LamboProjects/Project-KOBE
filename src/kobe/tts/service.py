"""Text-to-speech service.

Consumes `ResponseReady` events, synthesizes audio with ElevenLabs (primary) or
OpenAI TTS (fallback), and plays through sounddevice. Supports barge-in via
`InterruptRequested` and `WakeDetected`.

ElevenLabs SDK: targets `elevenlabs>=1.0` (post-rewrite) client API —
`ElevenLabs(api_key=...).text_to_speech.convert(...)` returning an iterator of
PCM byte chunks. Output format `pcm_16000` yields raw 16 kHz, 16-bit mono PCM.
"""
from __future__ import annotations

import asyncio
import io
from typing import Any

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import (
    InterruptRequested,
    ResponseReady,
    SpeakFinished,
    SpeakStarted,
    WakeDetected,
)

log = structlog.get_logger(__name__)

# Playback chunk size in frames (samples). ~50 ms at 16 kHz lets the
# interrupt flag be checked often enough for responsive barge-in.
_PLAYBACK_CHUNK_FRAMES = 800
_SAMPLE_WIDTH_BYTES = 2  # int16


async def run_tts_service(bus: Bus, settings: Settings) -> None:
    """Run the TTS service until cancelled."""
    stop_flag = asyncio.Event()
    speaking = asyncio.Event()  # Set only while audio is actually being written to the output device.
    response_q = bus.subscribe(ResponseReady)
    interrupt_q = bus.subscribe(InterruptRequested)
    wake_q = bus.subscribe(WakeDetected)

    interrupt_task = asyncio.create_task(
        _watch_interrupts(interrupt_q, wake_q, stop_flag, speaking),
        name="tts-interrupt-watcher",
    )

    log.info("tts_service_started")
    try:
        while True:
            event = await response_q.get()
            # Clear any stale stop signal from before this utterance.
            stop_flag.clear()
            await _handle_response(event, bus, settings, stop_flag, speaking)
    except asyncio.CancelledError:
        log.info("tts_service_cancelled")
        stop_flag.set()
        raise
    finally:
        interrupt_task.cancel()
        try:
            await interrupt_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.warning("interrupt_watcher_error", error=str(exc))
        bus.unsubscribe(ResponseReady, response_q)
        bus.unsubscribe(InterruptRequested, interrupt_q)
        bus.unsubscribe(WakeDetected, wake_q)
        log.info("tts_service_stopped")


async def _watch_interrupts(
    interrupt_q: asyncio.Queue,
    wake_q: asyncio.Queue,
    stop_flag: asyncio.Event,
    speaking: asyncio.Event,
) -> None:
    """Set the stop flag whenever an interrupt or wake event fires — but only while speaking.

    Wake events during recording / idle are unrelated to TTS and must not poison the
    stop_flag for the *next* utterance. By gating on `speaking`, we only honor
    barge-in signals that arrive mid-playback.
    """

    async def _drain(q: asyncio.Queue, label: str) -> None:
        try:
            while True:
                ev = await q.get()
                if speaking.is_set():
                    log.info("tts_interrupt", source=label, event=type(ev).__name__)
                    stop_flag.set()
                else:
                    log.debug("tts_interrupt_ignored", source=label, reason="not_speaking")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("interrupt_drain_error", source=label, error=str(exc))

    async with asyncio.TaskGroup() as tg:
        tg.create_task(_drain(interrupt_q, "interrupt"))
        tg.create_task(_drain(wake_q, "wake"))


async def _handle_response(
    event: ResponseReady,
    bus: Bus,
    settings: Settings,
    stop_flag: asyncio.Event,
    speaking: asyncio.Event,
) -> None:
    await bus.publish(SpeakStarted(request_id=event.request_id))
    log.info("tts_speak_started", request_id=event.request_id, chars=len(event.text))

    interrupted = False
    text = event.text.strip()
    if not text:
        await bus.publish(SpeakFinished(request_id=event.request_id, interrupted=False))
        return

    speaking.set()
    try:
        played = False

        # Primary: ElevenLabs
        if settings.elevenlabs_api_key:
            try:
                interrupted = await _speak_elevenlabs(text, settings, stop_flag)
                played = True
            except Exception as exc:
                log.warning("elevenlabs_failed", error=str(exc))

        # Fallback: OpenAI
        if not played and settings.openai_api_key:
            try:
                interrupted = await _speak_openai(text, settings, stop_flag)
                played = True
            except Exception as exc:
                log.warning("openai_tts_failed", error=str(exc))

        if not played:
            log.warning(
                "tts_no_provider_available",
                request_id=event.request_id,
                reason="no_api_keys_or_all_failed",
            )
    except asyncio.CancelledError:
        interrupted = True
        raise
    except Exception as exc:
        log.exception("tts_unexpected_error", error=str(exc))
    finally:
        speaking.clear()
        await bus.publish(
            SpeakFinished(request_id=event.request_id, interrupted=interrupted)
        )
        log.info(
            "tts_speak_finished",
            request_id=event.request_id,
            interrupted=interrupted,
        )


# ---------------------------------------------------------------------------
# ElevenLabs path
# ---------------------------------------------------------------------------


async def _speak_elevenlabs(
    text: str, settings: Settings, stop_flag: asyncio.Event
) -> bool:
    """Synthesize with ElevenLabs and play. Returns True if interrupted."""
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)

    def _collect() -> bytes:
        iterator = client.text_to_speech.convert(
            voice_id=settings.elevenlabs_voice_id,
            model_id=settings.elevenlabs_model_id,
            text=text,
            output_format="pcm_16000",
        )
        chunks: list[bytes] = []
        for chunk in iterator:
            if chunk:
                chunks.append(chunk)
        return b"".join(chunks)

    pcm = await asyncio.to_thread(_collect)
    if not pcm:
        log.warning("elevenlabs_empty_audio")
        return False
    return await _play_pcm16(pcm, sample_rate=16000, settings=settings, stop_flag=stop_flag)


# ---------------------------------------------------------------------------
# OpenAI fallback
# ---------------------------------------------------------------------------


async def _speak_openai(
    text: str, settings: Settings, stop_flag: asyncio.Event
) -> bool:
    """Synthesize with OpenAI TTS (wav) and play. Returns True if interrupted."""
    import openai

    client = openai.OpenAI(api_key=settings.openai_api_key)

    def _fetch() -> bytes:
        resp = client.audio.speech.create(
            model=settings.openai_tts_model,
            voice=settings.openai_tts_voice,
            input=text,
            response_format="wav",
        )
        # New SDK returns an object with `.read()` or `.content`.
        if hasattr(resp, "read"):
            try:
                return resp.read()
            except Exception:
                pass
        if hasattr(resp, "content"):
            return resp.content  # type: ignore[no-any-return]
        return bytes(resp)  # best effort

    wav_bytes = await asyncio.to_thread(_fetch)
    if not wav_bytes:
        log.warning("openai_tts_empty_audio")
        return False

    import soundfile as sf
    import numpy as np

    def _decode() -> tuple[Any, int]:
        data, sr = sf.read(io.BytesIO(wav_bytes), dtype="int16", always_2d=False)
        return data, sr

    data, sr = await asyncio.to_thread(_decode)
    if hasattr(data, "ndim") and data.ndim > 1:
        # Mix down to mono by averaging channels.
        data = data.mean(axis=1).astype(np.int16)  # type: ignore[attr-defined]
    pcm = bytes(memoryview(data.tobytes()))
    return await _play_pcm16(pcm, sample_rate=int(sr), settings=settings, stop_flag=stop_flag)


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------


async def _play_pcm16(
    pcm: bytes,
    sample_rate: int,
    settings: Settings,
    stop_flag: asyncio.Event,
) -> bool:
    """Play raw int16 mono PCM through sounddevice. Returns True if interrupted."""
    import numpy as np
    import sounddevice as sd

    audio = np.frombuffer(pcm, dtype=np.int16)
    if audio.size == 0:
        return False

    device = settings.audio_output_device
    interrupted = False

    def _play_blocking() -> bool:
        nonlocal interrupted
        stream = sd.RawOutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device,
            blocksize=_PLAYBACK_CHUNK_FRAMES,
        )
        stream.start()
        try:
            total = audio.size
            offset = 0
            chunk = _PLAYBACK_CHUNK_FRAMES
            while offset < total:
                if stop_flag.is_set():
                    interrupted = True
                    break
                end = min(offset + chunk, total)
                stream.write(audio[offset:end].tobytes())
                offset = end
        finally:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        return interrupted

    try:
        return await asyncio.to_thread(_play_blocking)
    except asyncio.CancelledError:
        stop_flag.set()
        raise
    except Exception as exc:
        log.warning("playback_failed", error=str(exc))
        return False
