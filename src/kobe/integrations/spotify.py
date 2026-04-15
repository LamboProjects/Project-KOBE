"""Spotify integration — voice-driven playback control and now-playing telemetry.

Two concurrent loops run inside `run_spotify_service`:

1. **Action handler** — consumes `ActionRequested` events whose `action` is one
   of `spotify_play`, `spotify_pause`, `spotify_next`, `spotify_previous`,
   `spotify_volume`. Each maps 1:1 to a spotipy call (wrapped in
   `asyncio.to_thread` so we never block the event loop), and every handled
   action emits an `ActionCompleted`.

2. **Now-playing poller** — every `settings.spotify_poll_interval_s` it calls
   `sp.current_playback()` and publishes a `NowPlayingChanged` event *only* when
   the track id or playing state has changed since the last emission, so the
   HUD can diff cheaply and the bus isn't spammed.

OAuth / first-run note
----------------------
On first launch, `spotipy.SpotifyOAuth` will open the user's default browser to
complete the authorization code flow and listen on `spotify_redirect_uri` for
the callback. The resulting token is cached under `config/.spotify-cache`
relative to the current working directory; subsequent runs refresh silently
without prompting. If the service is running somewhere headless, perform the
first-run auth interactively once to populate the cache, then copy it over.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import spotipy
import structlog
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import ActionCompleted, ActionRequested, NowPlayingChanged

log = structlog.get_logger(__name__)

_SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
_CACHE_PATH = Path("config") / ".spotify-cache"
_HANDLED_ACTIONS = {
    "spotify_play",
    "spotify_pause",
    "spotify_next",
    "spotify_previous",
    "spotify_volume",
}


def _build_client(settings: Settings) -> spotipy.Spotify:
    """Construct a Spotipy client backed by a cached OAuth token."""
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    auth = SpotifyOAuth(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        redirect_uri=settings.spotify_redirect_uri,
        scope=_SCOPES,
        cache_path=str(_CACHE_PATH),
        open_browser=True,
    )
    return spotipy.Spotify(auth_manager=auth)


def _snapshot(playback: dict[str, Any] | None) -> tuple[NowPlayingChanged, str]:
    """Translate a `current_playback()` dict into a `NowPlayingChanged` + track id key."""
    if not playback or not playback.get("item"):
        return NowPlayingChanged(is_playing=False), ""
    item = playback["item"]
    track_id = item.get("id") or item.get("uri") or ""
    artists = ", ".join(a.get("name", "") for a in item.get("artists", []) if a.get("name"))
    album = (item.get("album") or {}).get("name", "")
    event = NowPlayingChanged(
        is_playing=bool(playback.get("is_playing")),
        track=item.get("name", ""),
        artist=artists,
        album=album,
        progress_ms=int(playback.get("progress_ms") or 0),
        duration_ms=int(item.get("duration_ms") or 0),
    )
    return event, track_id


async def _dispatch_action(
    sp: spotipy.Spotify, action: str, params: dict[str, Any]
) -> None:
    """Run the spotipy call for `action` off-thread. Raises on failure."""
    if action == "spotify_play":
        uri = params.get("uri")
        if uri:
            await asyncio.to_thread(sp.start_playback, uris=[uri])
        else:
            await asyncio.to_thread(sp.start_playback)
    elif action == "spotify_pause":
        await asyncio.to_thread(sp.pause_playback)
    elif action == "spotify_next":
        await asyncio.to_thread(sp.next_track)
    elif action == "spotify_previous":
        await asyncio.to_thread(sp.previous_track)
    elif action == "spotify_volume":
        level = int(params.get("level", 50))
        level = max(0, min(100, level))
        await asyncio.to_thread(sp.volume, level)


async def _action_loop(bus: Bus, sp: spotipy.Spotify) -> None:
    async with bus.stream(ActionRequested) as q:
        while True:
            req = await q.get()
            if req.action not in _HANDLED_ACTIONS:
                continue
            log.info("spotify_action", action=req.action, params=req.params, request_id=req.request_id)
            ok = True
            detail = ""
            try:
                await _dispatch_action(sp, req.action, req.params or {})
            except SpotifyException as exc:
                ok = False
                detail = f"spotify_error: {exc.msg or str(exc)}"
                log.warning("spotify_action_failed", action=req.action, error=detail)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - surface any other failure as ok=False
                ok = False
                detail = f"error: {exc}"
                log.warning("spotify_action_error", action=req.action, error=detail)
            await bus.publish(
                ActionCompleted(
                    request_id=req.request_id,
                    action=req.action,
                    ok=ok,
                    detail=detail,
                )
            )


async def _now_playing_loop(bus: Bus, sp: spotipy.Spotify, interval: float) -> None:
    """Publish NowPlayingChanged on every poll while a track is playing, so the HUD
    progress bar keeps advancing; only suppress publishes when nothing is playing
    and the state hasn't changed since the last emission.
    """
    last_key: tuple[str, bool] | None = None
    while True:
        try:
            playback = await asyncio.to_thread(sp.current_playback)
            event, track_id = _snapshot(playback)
            key = (track_id, event.is_playing)
            # Always publish while playing so `progress_ms` stays fresh in the HUD.
            # When paused or empty, only publish on state change to avoid bus chatter.
            if event.is_playing or key != last_key:
                await bus.publish(event)
                if key != last_key:
                    log.debug(
                        "now_playing_changed",
                        track=event.track,
                        artist=event.artist,
                        is_playing=event.is_playing,
                    )
                last_key = key
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - poller must never crash the service
            log.warning("spotify_poll_failed", error=str(exc))
        await asyncio.sleep(interval)


async def run_spotify_service(bus: Bus, settings: Settings) -> None:
    """Run the Spotify control + telemetry service until cancelled."""
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        log.info("spotify_unconfigured")
        return

    try:
        sp = await asyncio.to_thread(_build_client, settings)
        # Sanity-check auth: triggers browser OAuth on first run.
        playback = await asyncio.to_thread(sp.current_playback)
        log.info(
            "spotify_service_started",
            has_active_device=bool(playback),
            poll_interval_s=settings.spotify_poll_interval_s,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - fail-soft on init
        log.error("spotify_init_failed", error=str(exc))
        return

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_action_loop(bus, sp))
            tg.create_task(_now_playing_loop(bus, sp, settings.spotify_poll_interval_s))
    except asyncio.CancelledError:
        log.info("spotify_service_cancelled")
        raise
