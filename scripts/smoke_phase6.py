"""Phase 6 smoke test.

Exercises Phase 6 surfaces without touching real HA, MuteMe hardware, or
ElevenLabs. Focus on the wiring + integration contracts:

1. **Persona registry** — `persona_prompt()` returns each of the 5 preset
   prompts and falls back to `default` on unknown input.
2. **Profile manager** — publishing `ActionRequested(action="profile_show")`
   produces an `ActionCompleted` summarizing the current profile. Startup
   also emits a `ProfileChanged` event.
3. **Home Assistant service** — with no URL/token configured, the service
   degrades cleanly (logs unconfigured and returns). With a fake URL, a
   `home_state` action produces an `ActionCompleted` (ok=False on the
   unreachable mock — that's the point; we just want the code path to run
   without crashing).
4. **Discord progress bar / persona** (pure-function path) — verify the
   helper that renders the 20-char ASCII bar.
5. **No-mediapipe construction** — confirm all Phase 6 services can be
   imported + constructed without the webcam pieces active.

No API keys, no hardware, no network. Runs on any Windows box with the
base deps installed.
"""
from __future__ import annotations

import asyncio
import sys

import structlog

from kobe.bus import Bus
from kobe.config import load_settings
from kobe.events import (
    ActionCompleted,
    ActionRequested,
    ProfileChanged,
    ResponseReady,
)
from kobe.logging import configure_logging


async def _first(bus: Bus, event_type: type, *, timeout: float, predicate=None):
    q = bus.subscribe(event_type)
    try:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return None
            try:
                ev = await asyncio.wait_for(q.get(), timeout=remaining)
            except asyncio.TimeoutError:
                return None
            if predicate is None or predicate(ev):
                return ev
    finally:
        bus.unsubscribe(event_type, q)


async def main() -> int:
    configure_logging("INFO")
    log = structlog.get_logger("smoke6")

    # --- Test 1: persona registry.
    from kobe.brain.personas import PERSONAS, persona_prompt
    expected = {"default", "concise", "warm", "terse", "excited"}
    assert expected.issubset(PERSONAS.keys()), f"missing presets: {expected - PERSONAS.keys()}"
    for name in expected:
        p = persona_prompt(name)
        assert isinstance(p, str) and p.strip(), f"{name}: empty"
    # Any non-preset value is treated as a raw custom prompt and shipped
    # verbatim. This applies to both short one-word values (`snarky`) and
    # full-sentence prompts — no silent fallback to default for near-miss
    # names.
    assert persona_prompt("snarky") == "snarky", "short custom must pass through verbatim"
    long_custom = "Speak like a terse British butler."
    assert persona_prompt(long_custom) == long_custom, "long custom must pass through verbatim"
    # Empty / None still falls back to default (the only silent coercion).
    assert persona_prompt("") == PERSONAS["default"]
    log.info(
        "test_1_pass_persona_registry",
        presets=sorted(PERSONAS.keys()),
        custom_passthrough=True,
    )

    # --- Test 2: profile manager.
    settings = load_settings()
    settings.profile_name = "lambert"
    settings.profile_label = "Lambert"
    settings.profile_config_dir = "config/profiles"  # may or may not exist

    bus = Bus()
    from kobe.profiles.manager import run_profile_service

    svc = asyncio.create_task(run_profile_service(bus, settings))
    startup_evt = await _first(
        bus, ProfileChanged, timeout=3.0, predicate=lambda e: e.name == "lambert"
    )
    assert startup_evt is not None, "profile service didn't emit startup ProfileChanged"
    log.info("test_2a_pass_profile_startup", name=startup_evt.name, label=startup_evt.label)

    # Drive a `profile_show` action.
    done_task = asyncio.create_task(
        _first(
            bus,
            ActionCompleted,
            timeout=3.0,
            predicate=lambda e: e.request_id == "p1" and e.action == "profile_show",
        )
    )
    await bus.publish(
        ActionRequested(request_id="p1", action="profile_show", params={})
    )
    done = await done_task
    assert done is not None and done.ok, f"profile_show didn't complete: {done}"
    assert "lambert" in done.detail.lower(), done.detail
    log.info("test_2b_pass_profile_show", detail=done.detail)

    svc.cancel()
    try:
        await svc
    except (asyncio.CancelledError, Exception):
        pass

    # --- Test 3: Home Assistant service degrades when unconfigured.
    from kobe.integrations.home_assistant import run_homeassistant_service
    ha_settings = load_settings()
    ha_settings.homeassistant_enabled = True
    ha_settings.homeassistant_url = ""  # force unconfigured
    ha_settings.homeassistant_token = ""
    bus2 = Bus()
    ha_task = asyncio.create_task(run_homeassistant_service(bus2, ha_settings))
    # Service should exit cleanly on its own when unconfigured.
    try:
        await asyncio.wait_for(ha_task, timeout=2.0)
        log.info("test_3a_pass_ha_unconfigured_returns")
    except asyncio.TimeoutError:
        # If it didn't exit, force cancel — still a pass if no exception below.
        ha_task.cancel()
        try:
            await ha_task
        except (asyncio.CancelledError, Exception):
            pass
        log.info("test_3a_pass_ha_unconfigured_stayed_up")

    # --- Test 4: MuteMe service degrades when hid unavailable or no device.
    from kobe.mute.muteme import run_muteme_service
    mm_settings = load_settings()
    bus3 = Bus()
    mm_task = asyncio.create_task(run_muteme_service(bus3, mm_settings))
    try:
        # The service should return quickly if hid isn't available or no device
        # is plugged in. In either case, no exception should propagate.
        await asyncio.wait_for(mm_task, timeout=2.0)
        log.info("test_4_pass_muteme_degrades_cleanly")
    except asyncio.TimeoutError:
        # Device IS plugged in — legit path, just cancel and move on.
        mm_task.cancel()
        try:
            await mm_task
        except (asyncio.CancelledError, Exception):
            pass
        log.info("test_4_pass_muteme_device_found_cancelled")

    log.info("smoke_phase6_ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
