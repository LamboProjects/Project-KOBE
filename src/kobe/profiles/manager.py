"""Multi-profile scaffold (Phase 6).

Tracks the currently active KOBE profile (e.g. ``lambert`` / ``jasmine``) and
publishes ``ProfileChanged`` so downstream services (HUD today, voice/wake
pickers in later phases) can re-theme without a pipeline restart.

This is a **scaffold**: overrides loaded from ``config/profiles/<name>.env``
are parsed and kept on the in-memory ``Profile.overrides`` dict so we can log
them and surface them via ``profile_show``, but they are NOT yet merged back
into the running ``Settings``. Phase 7 will wire specific fields (wake_models,
elevenlabs_voice_id, tts_persona_profile, ...) through the running pipeline.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import (
    ActionCompleted,
    ActionRequested,
    ProfileChanged,
)

log = structlog.get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Profile:
    """A single persona/voice/wake-word profile."""

    name: str                       # canonical id, lowercase, e.g. "lambert"
    label: str                      # display label, e.g. "Lambert"
    env_file: Path | None           # profile-scoped overrides file; may not exist
    overrides: dict[str, str] = field(default_factory=dict)


# --- dotenv parsing ---------------------------------------------------------

def _parse_dotenv(path: Path) -> dict[str, str]:
    """Tiny dotenv parser: ``KEY=value`` per line, ``#`` comments, blank lines
    ignored; surrounding single/double quotes stripped. Never raises — malformed
    lines are logged and skipped so a typo can't kill the service."""
    out: dict[str, str] = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("profile_env_read_error", path=str(path), error=str(exc))
        return out
    for lineno, line in enumerate(raw.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # Strip trailing inline comment (only when preceded by whitespace).
        if " #" in s:
            s = s.split(" #", 1)[0].rstrip()
        if "=" not in s:
            log.warning("profile_env_malformed", path=str(path), line=lineno)
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if not key:
            log.warning("profile_env_empty_key", path=str(path), line=lineno)
            continue
        out[key] = val
    return out


# --- profile I/O ------------------------------------------------------------

def _profile_dir(settings: Settings) -> Path:
    """Resolve `settings.profile_config_dir` against a stable base path.

    Matches `kobe.config`'s env-file resolution: an absolute or
    user-expanded path is used verbatim; a relative path is resolved
    against the inferred repo root (two levels up from this module) so
    the active profile directory doesn't depend on the process working
    directory. Falls back to CWD only if the repo-relative path doesn't
    exist AND the CWD-relative one does — mirroring the pydantic-settings
    layered lookup pattern we use for `config/.env`.
    """
    raw = Path(settings.profile_config_dir).expanduser()
    if raw.is_absolute():
        return raw
    # Repo root = parents[3] from this file: manager.py → profiles/ → kobe/ → src/ → <root>.
    # Matches `kobe/config.py`'s `REPO_ROOT = Path(__file__).resolve().parents[2]`
    # (config.py is one level shallower).
    repo_root = Path(__file__).resolve().parents[3]
    repo_relative = (repo_root / raw).resolve()
    cwd_relative = (Path.cwd() / raw).resolve()
    if repo_relative.is_dir():
        return repo_relative
    if cwd_relative.is_dir():
        return cwd_relative
    # Neither exists yet — return the repo-relative path so any future write
    # (or the informative "only <current>" in profile_list) has a stable target.
    return repo_relative


def _env_file_for(settings: Settings, name: str) -> Path:
    return _profile_dir(settings) / f"{name.lower()}.env"


def _load_profile(settings: Settings, name: str, label: str) -> Profile:
    env_file = _env_file_for(settings, name)
    exists = env_file.is_file()
    overrides = _parse_dotenv(env_file) if exists else {}
    log.info(
        "profile_loaded" if exists else "profile_loaded_no_overrides",
        name=name, label=label, env_file=str(env_file),
        keys=sorted(overrides.keys()),
    )
    return Profile(
        name=name.lower(),
        label=label,
        env_file=env_file if exists else None,
        overrides=overrides,
    )


def _list_available(settings: Settings) -> list[str]:
    d = _profile_dir(settings)
    if not d.is_dir():
        return []
    return sorted(p.stem.lower() for p in d.glob("*.env") if p.is_file())


# --- action handlers --------------------------------------------------------

async def _handle_switch(bus: Bus, settings: Settings, current: Profile,
                         params: dict) -> tuple[Profile, bool, str]:
    raw_name = params.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return current, False, "profile_switch requires a 'name' string"
    name = raw_name.strip().lower()
    raw_label = params.get("label")
    label = raw_label if isinstance(raw_label, str) and raw_label.strip() else name.capitalize()

    new_profile = _load_profile(settings, name, label)
    await bus.publish(
        ProfileChanged(name=new_profile.name, label=new_profile.label, timestamp_iso=_now_iso())
    )
    # Note: we deliberately do NOT publish a `ResponseReady` here. In the
    # real OpenClaw flow the brain already publishes `ResponseReady` from
    # the model's `text` *before* dispatching `profile_switch`, so an extra
    # spoken acknowledgement would double-speak the user. The HUD profile
    # tag and the `ActionCompleted` detail (consumed by the HUD relay) are
    # the only feedback channels for this action — by design.
    detail = f"Switched to {new_profile.label} ({new_profile.name})"
    if new_profile.env_file is None:
        detail += " (no overrides file)"
    else:
        detail += f" with {len(new_profile.overrides)} override(s)"
    return new_profile, True, detail


def _handle_list(settings: Settings, current: Profile) -> tuple[bool, str]:
    names = _list_available(settings)
    if not names:
        return True, f"only {current.name}"
    return True, ", ".join(names)


def _handle_show(current: Profile) -> tuple[bool, str]:
    return True, f"Current profile: {current.label} ({current.name})"


# --- service entry point ----------------------------------------------------

async def run_profile_service(bus: Bus, settings: Settings) -> None:
    """Consume profile_* actions, maintain the active Profile, and announce changes."""
    current = _load_profile(settings, settings.profile_name, settings.profile_label)

    # Subscribe first so we never miss a `profile_*` action that races the
    # startup `ProfileChanged` publish.
    action_q = bus.subscribe(ActionRequested)

    # Other TaskGroup members (notably the HUD) may not have subscribed to
    # `ProfileChanged` yet when we start up. Yield once + a small delay so
    # their bus.subscribe() calls have a chance to run — without this, the
    # HUD's snapshot keeps `profile: null` until the user manually triggers
    # a switch. The delay is deliberately small (50 ms) so it doesn't stall
    # real startup latency noticeably.
    await asyncio.sleep(0.05)
    await bus.publish(
        ProfileChanged(name=current.name, label=current.label, timestamp_iso=_now_iso())
    )
    log.info(
        "profile_service_started",
        name=current.name,
        label=current.label,
        config_dir=str(_profile_dir(settings)),
    )
    try:
        while True:
            event: ActionRequested = await action_q.get()
            if not event.action.startswith("profile_"):
                continue
            try:
                if event.action == "profile_switch":
                    current, ok, detail = await _handle_switch(
                        bus, settings, current, event.params or {}
                    )
                elif event.action == "profile_list":
                    ok, detail = _handle_list(settings, current)
                elif event.action == "profile_show":
                    ok, detail = _handle_show(current)
                else:
                    log.debug("profile_action_ignored", action=event.action)
                    continue
                await bus.publish(
                    ActionCompleted(
                        request_id=event.request_id,
                        action=event.action,
                        ok=ok,
                        detail=detail,
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.error(
                    "profile_action_error",
                    action=event.action,
                    request_id=event.request_id,
                    error=str(exc),
                )
                await bus.publish(
                    ActionCompleted(
                        request_id=event.request_id,
                        action=event.action,
                        ok=False,
                        detail=f"error: {exc}",
                    )
                )
    except asyncio.CancelledError:
        log.info("profile_service_cancelled")
        raise
    finally:
        bus.unsubscribe(ActionRequested, action_q)
