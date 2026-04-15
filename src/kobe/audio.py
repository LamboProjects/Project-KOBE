"""Shared microphone source.

Opening the mic twice (wake + stt) is unreliable on Windows. This module owns the
single InputStream and fans frames out to any number of subscribers. A ring buffer
retains the last few seconds so STT can recover pre-roll audio after a wake event.

Threading model: the `_callback` runs on a PortAudio thread. `_subs` is mutated from
the event-loop thread (subscribe/unsubscribe). We synchronize with a `threading.Lock`
and marshal queue puts back onto the loop thread via `call_soon_threadsafe` — the
actual `put_nowait` therefore runs on the loop thread, so `QueueFull` must be handled
*there*, not at the call site.
"""
from __future__ import annotations

import asyncio
import threading
from collections import deque

import numpy as np
import sounddevice as sd
import structlog

log = structlog.get_logger(__name__)

FRAME_MS = 20  # 20 ms frames = 320 samples at 16 kHz


def _safe_put(q: asyncio.Queue[bytes], pcm: bytes) -> None:
    """Put on the loop thread, drop the oldest frame on overflow.

    Stale audio frames have no value for wake/VAD, so we'd rather keep the pipeline
    flowing than backpressure all the way to the mic callback.
    """
    try:
        q.put_nowait(pcm)
    except asyncio.QueueFull:
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            return
        try:
            q.put_nowait(pcm)
        except asyncio.QueueFull:
            return


class AudioSource:
    """Single owner of the input stream; fans int16 mono PCM frames out to subscribers."""

    def __init__(self, sample_rate: int = 16000, device: int | None = None) -> None:
        self.sample_rate = sample_rate
        self.device = device
        self.frame_samples = int(sample_rate * FRAME_MS / 1000)
        self._subs: tuple[asyncio.Queue[bytes], ...] = ()
        self._subs_lock = threading.Lock()
        self._ring: deque[bytes] = deque(maxlen=int(5_000 / FRAME_MS))  # 5 s of pre-roll
        self._stream: sd.InputStream | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lifecycle_lock = asyncio.Lock()

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("audio_status", status=str(status))
        pcm = (indata[:, 0] * 32767.0).clip(-32768, 32767).astype(np.int16).tobytes()
        self._ring.append(pcm)
        loop = self._loop
        if loop is None:
            return
        # Snapshot under lock; iteration is then race-free.
        with self._subs_lock:
            subs = self._subs
        for q in subs:
            try:
                loop.call_soon_threadsafe(_safe_put, q, pcm)
            except RuntimeError:
                # Loop closed mid-callback (e.g., during shutdown). Skip rather than crash
                # PortAudio's callback thread.
                return

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._stream is not None:
                return
            self._loop = asyncio.get_running_loop()
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=self.frame_samples,
                device=self.device,
                callback=self._callback,
            )
            self._stream.start()
            log.info("audio_started", sample_rate=self.sample_rate, device=self.device)

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            if self._stream is None:
                return
            # Null the loop ref first so the callback can't schedule on a soon-to-close loop.
            self._loop = None
            self._stream.stop()
            self._stream.close()
            self._stream = None
            log.info("audio_stopped")

    def subscribe(self) -> asyncio.Queue[bytes]:
        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)
        with self._subs_lock:
            self._subs = (*self._subs, q)
        return q

    def unsubscribe(self, q: asyncio.Queue[bytes]) -> None:
        with self._subs_lock:
            self._subs = tuple(s for s in self._subs if s is not q)

    def pre_roll(self, seconds: float = 1.0) -> bytes:
        """Return the most recent `seconds` of audio as int16 PCM bytes."""
        frames_needed = int(seconds * 1000 / FRAME_MS)
        frames = list(self._ring)[-frames_needed:]
        return b"".join(frames)


async def run_audio_source(source: AudioSource) -> None:
    await source.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await source.stop()
        raise
