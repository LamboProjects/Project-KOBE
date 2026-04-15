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
    log.info("startup", version_config=settings.model_dump(exclude={"openclaw_api_key", "elevenlabs_api_key", "openai_api_key"}))

    bus = Bus()

    # Lazy imports so missing optional deps don't crash startup for unrelated services.
    from kobe.audio import AudioSource, run_audio_source
    from kobe.wake.service import run_wake_service
    from kobe.stt.service import run_stt_service
    from kobe.tts.service import run_tts_service
    from kobe.brain.router import run_brain_service
    from kobe.actions.executor import run_action_executor
    from kobe.mute.service import run_mute_service

    audio = AudioSource(sample_rate=settings.audio_sample_rate, device=settings.audio_input_device)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(run_audio_source(audio), name="audio")
        tg.create_task(run_wake_service(bus, settings, audio), name="wake")
        tg.create_task(run_stt_service(bus, settings, audio), name="stt")
        tg.create_task(run_tts_service(bus, settings), name="tts")
        tg.create_task(run_brain_service(bus, settings), name="brain")
        tg.create_task(run_action_executor(bus, settings), name="actions")
        tg.create_task(run_mute_service(bus, settings), name="mute")


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
