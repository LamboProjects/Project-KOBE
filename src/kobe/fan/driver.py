"""Holographic fan backend abstraction (Phase 7).

65 cm WiFi holographic fans (Chinese white-label, Kiwi-style, Hypervsn clones,
GIWOX, etc.) have no standardised control protocol — every vendor ships its own
mobile app that talks to the device over the local WiFi AP the fan hosts, and
the wire format is generally undocumented. We therefore ship an abstraction:
the `FanBackend` Protocol plus a handful of implementations that let the rest
of the KOBE pipeline (clip renderer → fan service → HUD) run end-to-end even
while the real device driver is still reverse-engineered.

Built-ins
---------

- `NullBackend` — log-only stub used when no device is configured. `push_clip`
  logs and returns True; `health` reports connected=True with detail="stub".
  This keeps the rendering/service/HUD machinery exercised without hardware.

- `FileOutputBackend` — writes each pushed clip to
  `<hologram_output_dir>/<name>_<timestamp>.mp4`, then atomically re-points
  `<hologram_output_dir>/current.mp4` at the new file via `os.replace` (which
  is an atomic rename on both POSIX and Windows). Handy for feeding VLC or a
  test HTML5 player and for capturing rendered clips during development.
  Keeps the 20 most recent files per clip-name on disk.

- `HttpPushBackend` — scaffold for a real WiFi device. The exact handshake is
  vendor-specific; the shape below is the lowest common denominator observed
  across several fans (multipart upload, then a JSON "play" command). The
  user is expected to pcap their device's app and fill in the exact paths /
  field names / any prelude commands below; the skeleton keeps the async
  lifecycle, logging, auth, and timeout contract in place so only the wire
  details need editing.

    POST <url>/upload          multipart/form-data, field=`file`, filename=`current.mp4`
                               Authorization: Bearer <token>  (if token set)
                               -> 200 on success, any other status treated as failure.

    POST <url>/play            JSON body {"name": "<clip-name>", "loop": true|false}
                               Authorization: Bearer <token>
                               -> 200 on success.

    GET  <url>/status          used by `health()` with a 2 s timeout.
                               A 200 response maps to connected=True.

All backends are non-blocking: filesystem work hops onto `asyncio.to_thread`,
HTTP uses `httpx.AsyncClient`. Backends MUST NOT raise from `push_clip` —
they catch internally, log, and return False. `build_backend(settings)`
dispatches on `settings.hologram_backend`; an unknown value falls back to
`NullBackend` with a warning, matching `kobe.vision.backends.build_backend`'s
policy.

Follow-up: when a real fan's pcap is in hand, subclass `HttpPushBackend` as
e.g. `GiwoxBackend` / `KiwiSignBackend` / `HypervsnBackend` and register the
new key in `build_backend`.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import structlog

from kobe.config import Settings

log = structlog.get_logger(__name__)


# --- public types -----------------------------------------------------------

@dataclass(frozen=True)
class BackendHealth:
    """Snapshot of a backend's liveness. `name` mirrors the backend's own
    `name` attribute ("null" / "file" / "http" / vendor key)."""
    name: str
    connected: bool
    detail: str = ""


class FanBackend(Protocol):
    """Anything that can accept a rendered hologram clip and display it.

    `push_clip` returns True on success, False on failure (backends NEVER
    raise for normal failure modes — they catch internally and log). `clear`
    is best-effort (stop display / remove current symlink). `health` is a
    cheap liveness probe used by the fan service to emit `FanBackendStatus`
    events for the HUD.
    """

    name: str

    async def push_clip(
        self,
        path: Path,
        *,
        name: str,
        duration_s: float,
        loop: bool = True,
    ) -> bool: ...

    async def clear(self) -> None: ...

    async def health(self) -> BackendHealth: ...


# --- NullBackend ------------------------------------------------------------

class NullBackend:
    """Log-only stub. Represents 'no device configured yet — pipeline should
    still run so the renderer / service / HUD can be exercised end-to-end.'"""

    name = "null"

    async def push_clip(
        self,
        path: Path,
        *,
        name: str,
        duration_s: float,
        loop: bool = True,
    ) -> bool:
        log.info(
            "fan_push_clip_stub",
            backend=self.name,
            name=name,
            duration_s=round(float(duration_s), 3),
            loop=bool(loop),
            path=str(path),
        )
        return True

    async def clear(self) -> None:
        return None

    async def health(self) -> BackendHealth:
        return BackendHealth(name=self.name, connected=True, detail="stub")

    async def close(self) -> None:
        return None


# --- FileOutputBackend ------------------------------------------------------

class FileOutputBackend:
    """Persists every clip to disk and maintains a `current.mp4` pointer.

    The `current.mp4` swap uses `os.replace`, which is atomic on POSIX and
    Windows (the replacement is either fully visible or not at all — no
    half-written file exposed to a tailing player). Each push also trims the
    per-name rolling window so the output directory stays bounded.
    """

    name = "file"
    RETAIN_PER_NAME = 20

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._output_dir = _resolve_output_dir(settings.hologram_output_dir)
        self._ready = False

    def _ensure_dir(self) -> None:
        if self._ready:
            return
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._ready = True

    async def push_clip(
        self,
        path: Path,
        *,
        name: str,
        duration_s: float,
        loop: bool = True,
    ) -> bool:
        try:
            await asyncio.to_thread(self._push_sync, Path(path), name)
        except FileNotFoundError as exc:
            log.warning("fan_file_source_missing", error=str(exc), path=str(path))
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_file_push_failed", error=str(exc), name=name, path=str(path))
            return False

        log.info(
            "fan_file_push_ok",
            backend=self.name,
            name=name,
            duration_s=round(float(duration_s), 3),
            loop=bool(loop),
            output_dir=str(self._output_dir),
        )
        return True

    def _push_sync(self, src: Path, name: str) -> None:
        self._ensure_dir()
        if not src.is_file():
            raise FileNotFoundError(f"clip source not found: {src}")
        safe_name = _sanitize_name(name)
        stamp = time.strftime("%Y%m%d_%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"
        dest = self._output_dir / f"{safe_name}_{stamp}.mp4"
        shutil.copyfile(src, dest)

        # Atomic swap of the 'current.mp4' pointer. We write the new path to a
        # temp file next to the destination, then `os.replace` it over
        # `current.mp4`. `os.replace` is the only cross-platform atomic rename
        # Python exposes — on Windows, plain `os.rename` fails if the target
        # exists, so this is the correct primitive.
        current = self._output_dir / "current.mp4"
        tmp = self._output_dir / f".current.{os.getpid()}.{stamp}.mp4.tmp"
        try:
            shutil.copyfile(dest, tmp)
            os.replace(tmp, current)
        except Exception:
            # Best-effort cleanup of the temp file if the replace failed.
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise

        self._sweep_retention(safe_name)

    def _sweep_retention(self, safe_name: str) -> None:
        try:
            candidates = sorted(
                (p for p in self._output_dir.glob(f"{safe_name}_*.mp4") if p.is_file()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for stale in candidates[self.RETAIN_PER_NAME :]:
                try:
                    stale.unlink()
                except OSError as exc:
                    log.debug("fan_file_retention_unlink_failed",
                              path=str(stale), error=str(exc))
        except Exception as exc:  # noqa: BLE001
            log.debug("fan_file_retention_failed", error=str(exc))

    async def clear(self) -> None:
        try:
            await asyncio.to_thread(self._clear_sync)
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_file_clear_failed", error=str(exc))

    def _clear_sync(self) -> None:
        self._ensure_dir()
        current = self._output_dir / "current.mp4"
        if current.exists():
            try:
                current.unlink()
            except OSError as exc:
                log.debug("fan_file_clear_unlink_failed", error=str(exc))

    async def health(self) -> BackendHealth:
        return BackendHealth(name=self.name, connected=True, detail=str(self._output_dir))

    async def close(self) -> None:
        return None


# --- HttpPushBackend --------------------------------------------------------

class HttpPushBackend:
    """POST-based scaffold for a real WiFi holographic fan.

    Assumes an HTTP control surface of the shape documented in the module
    docstring. If you own a GIWOX/Kiwi/Hypervsn-style device, pcap the
    vendor app's traffic and adjust the paths / field names / body schema
    below — the async lifecycle (single `httpx.AsyncClient`, Bearer auth,
    timeouts, structured logging, never-raise failure mode) is already in
    place.
    """

    name = "http"
    HEALTH_TIMEOUT_S = 2.0

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._url = (settings.hologram_http_url or "").rstrip("/")
        self._token = settings.hologram_http_auth_token or ""
        self._timeout = float(settings.hologram_http_timeout_s)
        self._client = None  # type: ignore[assignment]
        self._client_lock = asyncio.Lock()

        if not self._url:
            log.warning("fan_http_unconfigured", detail="hologram_http_url is empty")

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def _get_client(self):
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                import httpx  # lazy import so a missing wheel doesn't crash module load
                self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def push_clip(
        self,
        path: Path,
        *,
        name: str,
        duration_s: float,
        loop: bool = True,
    ) -> bool:
        if not self._url:
            log.warning("fan_http_skip_unconfigured", name=name)
            return False

        src = Path(path)
        if not src.is_file():
            log.warning("fan_http_source_missing", path=str(src))
            return False

        try:
            client = await self._get_client()
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_http_client_init_failed", error=str(exc))
            return False

        # Load the clip off-loop — MP4s are small (few MB at 512x512 / 30 fps / a
        # couple of seconds) but reading them still blocks.
        try:
            payload = await asyncio.to_thread(src.read_bytes)
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_http_read_failed", error=str(exc), path=str(src))
            return False

        headers = self._auth_headers()

        # TODO(pcap): vendor may require a session-init or heartbeat call
        # before /upload. Insert it here if your pcap shows one.
        try:
            upload = await client.post(
                f"{self._url}/upload",
                files={"file": ("current.mp4", payload, "video/mp4")},
                headers=headers,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_http_upload_failed",
                        error=str(exc), err_type=exc.__class__.__name__, name=name)
            return False

        if upload.status_code != 200:
            log.warning("fan_http_upload_bad_status",
                        status=upload.status_code, name=name)
            return False

        # TODO(pcap): vendors diverge on the "play" command. Some expect
        # form-encoded, some want the clip name as a path param, some use
        # WebSocket frames. Adjust the body/URL below to match your pcap.
        try:
            play = await client.post(
                f"{self._url}/play",
                json={"name": name, "loop": bool(loop)},
                headers=headers,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("fan_http_play_failed",
                        error=str(exc), err_type=exc.__class__.__name__, name=name)
            return False

        if play.status_code != 200:
            log.warning("fan_http_play_bad_status", status=play.status_code, name=name)
            return False

        log.info(
            "fan_http_push_ok",
            backend=self.name,
            name=name,
            duration_s=round(float(duration_s), 3),
            loop=bool(loop),
            bytes=len(payload),
        )
        return True

    async def clear(self) -> None:
        if not self._url:
            return
        try:
            client = await self._get_client()
            # TODO(pcap): replace with the vendor's actual "stop" command.
            resp = await client.post(f"{self._url}/stop", headers=self._auth_headers())
            if resp.status_code != 200:
                log.debug("fan_http_clear_bad_status", status=resp.status_code)
        except Exception as exc:  # noqa: BLE001
            log.debug("fan_http_clear_failed", error=str(exc))

    async def health(self) -> BackendHealth:
        if not self._url:
            return BackendHealth(name=self.name, connected=False, detail="url not configured")
        try:
            client = await self._get_client()
        except Exception as exc:  # noqa: BLE001
            return BackendHealth(name=self.name, connected=False, detail=str(exc))
        try:
            resp = await client.get(
                f"{self._url}/status",
                headers=self._auth_headers(),
                timeout=self.HEALTH_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001
            return BackendHealth(name=self.name, connected=False, detail=str(exc))

        ok = resp.status_code == 200
        detail = f"HTTP {resp.status_code}"
        return BackendHealth(name=self.name, connected=ok, detail=detail)

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as exc:  # noqa: BLE001
                log.debug("fan_http_close_failed", error=str(exc))
            finally:
                self._client = None


# --- helpers ----------------------------------------------------------------

def _resolve_output_dir(raw_value: str) -> Path:
    """Resolve `hologram_output_dir` like `kobe.profiles.manager._profile_dir`.

    Absolute / user-expanded paths are used verbatim; relative paths are
    anchored to the inferred repo root (parents[3] from this module:
    driver.py -> fan/ -> kobe/ -> src/ -> <root>). This mirrors the pattern
    already used for profile config and the pydantic-settings env-file
    lookup, so the output directory doesn't depend on the process CWD.
    """
    raw = Path(raw_value).expanduser()
    if raw.is_absolute():
        return raw
    repo_root = Path(__file__).resolve().parents[3]
    return (repo_root / raw).resolve()


# Characters that are unsafe in filenames on Windows (NTFS) and most POSIX
# systems we care about. We replace them with underscores.
_UNSAFE_NAME_CHARS = set('<>:"/\\|?*\0')


def _sanitize_name(name: str) -> str:
    cleaned = "".join("_" if ch in _UNSAFE_NAME_CHARS or ord(ch) < 32 else ch
                      for ch in (name or "").strip())
    cleaned = cleaned.strip(". ")  # trailing dots/spaces are illegal on Windows
    return cleaned or "clip"


# --- factory ----------------------------------------------------------------

def build_backend(settings: Settings) -> FanBackend:
    """Pick a backend from config. Unknown / disabled → NullBackend."""
    if settings.hologram_enabled is False:
        log.info("fan_backend_disabled", fallback="null")
        return NullBackend()

    choice = (settings.hologram_backend or "null").strip().lower()

    if choice in ("", "null", "none", "stub"):
        return NullBackend()

    if choice == "file":
        return FileOutputBackend(settings)

    if choice == "http":
        return HttpPushBackend(settings)

    log.warning("fan_backend_unknown", requested=choice, fallback="null")
    return NullBackend()
