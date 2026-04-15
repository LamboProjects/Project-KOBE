"""Entry point. Wires every service to the bus and runs them together.

Each service exposes an async `run(bus, settings)` coroutine. Missing credentials are
surfaced as warnings — the runtime still starts so smoke-testing is possible without
every backend configured.
"""
from __future__ import annotations

import asyncio

import typer

from kobe.bus import Bus
from kobe.config import load_settings
from kobe.logging import configure_logging

app = typer.Typer(no_args_is_help=False, add_completion=False)


async def _run_all() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    import structlog
    log = structlog.get_logger("kobe")
    log.info(
        "startup",
        version_config=settings.model_dump(
            exclude={
                "openclaw_api_key",
                "elevenlabs_api_key",
                "openai_api_key",
                # Phase 3: Bambu LAN access code acts as an MQTT password.
                "bambu_access_code",
                # Phase 3: Spotify client secret is a long-lived app secret.
                "spotify_client_secret",
                # Phase 3: Discord webhook URL contains the posting token.
                "discord_webhook_url",
                # Phase 6: long-lived HA bearer token can fully control the home.
                "homeassistant_token",
            },
        ),
    )

    bus = Bus()

    # Lazy imports so missing optional deps don't crash startup for unrelated services.
    from kobe.audio import AudioSource, run_audio_source
    from kobe.wake.service import run_wake_service
    from kobe.stt.service import run_stt_service
    from kobe.tts.service import run_tts_service
    from kobe.brain.router import run_brain_service
    from kobe.actions.executor import run_action_executor
    from kobe.actions.confirmation import run_confirmation_service
    from kobe.mute.service import run_mute_service
    from kobe.hud.backend import run_hud_server
    from kobe.system.status import run_system_status_service
    from kobe.integrations.bambu import run_bambu_service
    from kobe.integrations.spotify import run_spotify_service
    from kobe.integrations.steam import run_steam_service
    from kobe.integrations.discord import run_discord_service
    from kobe.automation.windows_ctrl import run_windows_automation_service
    from kobe.vision.service import run_vision_service
    from kobe.gestures.service import run_gesture_service
    from kobe.integrations.home_assistant import run_homeassistant_service
    from kobe.mute.muteme import run_muteme_service
    from kobe.profiles.manager import run_profile_service
    from kobe.fan.service import run_fan_service

    audio = AudioSource(sample_rate=settings.audio_sample_rate, device=settings.audio_input_device)

    async with asyncio.TaskGroup() as tg:
        # Phase 1 core
        tg.create_task(run_audio_source(audio), name="audio")
        tg.create_task(run_wake_service(bus, settings, audio), name="wake")
        tg.create_task(run_stt_service(bus, settings, audio), name="stt")
        tg.create_task(run_tts_service(bus, settings), name="tts")
        tg.create_task(run_brain_service(bus, settings), name="brain")
        tg.create_task(run_action_executor(bus, settings), name="actions")
        tg.create_task(run_mute_service(bus, settings), name="mute")
        # Phase 2 HUD + telemetry
        tg.create_task(run_hud_server(bus, settings), name="hud")
        tg.create_task(run_system_status_service(bus, settings), name="system-status")
        # Phase 3 integrations
        tg.create_task(run_confirmation_service(bus, settings), name="confirmation")
        tg.create_task(run_bambu_service(bus, settings), name="bambu")
        tg.create_task(run_spotify_service(bus, settings), name="spotify")
        tg.create_task(run_steam_service(bus, settings), name="steam")
        tg.create_task(run_discord_service(bus, settings), name="discord")
        tg.create_task(run_windows_automation_service(bus, settings), name="windows-automation")
        # Phase 4 foundation (vision capture + backend stub)
        tg.create_task(run_vision_service(bus, settings), name="vision")
        # Phase 5 (webcam + MediaPipe gesture recognition)
        tg.create_task(run_gesture_service(bus, settings), name="gestures")
        # Phase 6 (polish — smart home, physical button, profiles)
        tg.create_task(run_homeassistant_service(bus, settings), name="home-assistant")
        tg.create_task(run_muteme_service(bus, settings), name="muteme")
        tg.create_task(run_profile_service(bus, settings), name="profiles")
        # Phase 7 (holographic fan)
        tg.create_task(run_fan_service(bus, settings), name="fan")


@app.command()
def run() -> None:
    """Start the KOBE voice pipeline."""
    try:
        asyncio.run(_run_all())
    except KeyboardInterrupt:
        pass


def cli() -> None:
    app()


if __name__ == "__main__":
    cli()
