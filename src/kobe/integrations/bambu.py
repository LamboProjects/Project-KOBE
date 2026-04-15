"""Bambu Lab P1S LAN MQTT integration.

Acts as both a state poller (subscribes to `device/{serial}/report` and fans out
`PrinterStatus` / `PrinterAlert` events) and an action handler (pause/resume/cancel
and a status-summary action).

Protocol reference (public LAN MQTT, no cloud):
  - TLS port 8883, self-signed cert → verification is disabled.
  - Auth: username "bblp", password = LAN access code.
  - Subscribe topic: device/{serial}/report
  - Publish topic:   device/{serial}/request
  - Report payload is a JSON object; when it carries a "print" object we treat that
    as a status push. Fields of interest:
      gcode_state: "IDLE" | "PREPARE" | "RUNNING" | "PAUSE" | "FINISH" | "FAILED"
      mc_percent: 0..100
      mc_remaining_time: int minutes
      nozzle_temper / bed_temper: floats (Celsius)
      subtask_name: currently-printing filename
  - Control commands are published as:
      {"print": {"sequence_id": "<n>", "command": "pause"|"resume"|"stop"}}
    and a full-state request as:
      {"pushing": {"sequence_id": "<n>", "command": "pushall"}}

paho-mqtt is synchronous; we let it run its own network thread via `loop_start()`
and marshal everything back to the asyncio loop with `run_coroutine_threadsafe`.
"""
from __future__ import annotations

import asyncio
import json
import ssl
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import structlog
from paho.mqtt.client import CallbackAPIVersion, Client, MQTTv311

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import ActionCompleted, ActionRequested, PrinterAlert, PrinterStatus

log = structlog.get_logger(__name__)


_STAGE_MAP = {
    "IDLE": "idle",
    "PREPARE": "preparing",
    "RUNNING": "printing",
    "PAUSE": "paused",
    "FINISH": "finished",
    "FAILED": "failed",
}

_HANDLED_ACTIONS = {
    "bambu_pause_print": "pause",
    "bambu_resume_print": "resume",
    "bambu_cancel_print": "stop",
    "bambu_status": "status",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _State:
    """Mutable shared state between the MQTT thread and asyncio tasks.

    `next_seq` has three potential callers: paho's network thread
    (`_on_connect`), the asyncio keepalive, and action handlers. Guard the
    non-atomic `self.seq += 1` with a `threading.Lock`.
    """
    connected: bool = False
    last_status: PrinterStatus | None = None
    last_stage: str | None = None  # raw gcode_state value we've already handled
    seq: int = 0
    seq_lock: threading.Lock = field(default_factory=threading.Lock)

    def next_seq(self) -> str:
        with self.seq_lock:
            self.seq += 1
            return str(self.seq)


def _parse_status(print_obj: dict[str, Any], connected: bool) -> PrinterStatus | None:
    """Map a 'print' sub-object from a report payload to a PrinterStatus.

    Bambu pushes incremental diffs: most fields may be missing in any given message.
    We only emit a status when at least one interesting field is present, and fall
    back to prior values via `_State.last_status` in the caller.
    """
    if not isinstance(print_obj, dict):
        return None
    interesting = {"gcode_state", "mc_percent", "mc_remaining_time",
                   "nozzle_temper", "bed_temper", "subtask_name"}
    if not interesting.intersection(print_obj.keys()):
        return None

    raw_stage = str(print_obj.get("gcode_state") or "").upper()
    stage = _STAGE_MAP.get(raw_stage, "unknown" if raw_stage else "unknown")

    def _num(key: str, default: float = 0.0) -> float:
        val = print_obj.get(key, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def _int(key: str, default: int = 0) -> int:
        val = print_obj.get(key, default)
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    return PrinterStatus(
        connected=connected,
        stage=stage,
        progress_pct=max(0.0, min(100.0, _num("mc_percent"))),
        remaining_minutes=max(0, _int("mc_remaining_time")),
        nozzle_temp_c=_num("nozzle_temper"),
        bed_temp_c=_num("bed_temper"),
        filename=str(print_obj.get("subtask_name") or ""),
        timestamp_iso=_now_iso(),
    )


def _alert_for_transition(prev_raw: str | None, new_raw: str, filename: str) -> PrinterAlert | None:
    """Return a PrinterAlert iff `new_raw` represents a meaningful transition."""
    if not new_raw or new_raw == prev_raw:
        return None
    if new_raw in ("PREPARE", "RUNNING"):
        # Only fire "started" when moving from an inactive stage, not on every RUNNING tick.
        if prev_raw in (None, "IDLE", "FINISH", "FAILED"):
            return PrinterAlert(kind="started",
                                message=f"Print started: {filename}" if filename else "Print started",
                                filename=filename)
        if prev_raw == "PAUSE" and new_raw == "RUNNING":
            return PrinterAlert(kind="resumed", message="Print resumed", filename=filename)
        return None
    if new_raw == "PAUSE" and prev_raw != "PAUSE":
        return PrinterAlert(kind="paused", message="Print paused", filename=filename)
    if new_raw == "FINISH":
        return PrinterAlert(kind="completed",
                            message=f"Print completed: {filename}" if filename else "Print completed",
                            filename=filename)
    if new_raw == "FAILED":
        return PrinterAlert(kind="failed",
                            message=f"Print failed: {filename}" if filename else "Print failed",
                            filename=filename)
    return None


def _status_detail(st: PrinterStatus | None) -> str:
    if st is None:
        return "No printer status yet."
    if not st.connected:
        return "Printer is offline."
    if st.stage in ("idle", "finished"):
        return f"Printer is {st.stage}."
    parts = [f"Stage {st.stage}", f"{st.progress_pct:.0f}% complete"]
    if st.remaining_minutes > 0:
        parts.append(f"{st.remaining_minutes} min remaining")
    if st.filename:
        parts.append(f"file {st.filename}")
    return ", ".join(parts) + "."


async def run_bambu_service(bus: Bus, settings: Settings) -> None:
    """Run the Bambu P1S LAN MQTT integration until cancelled."""
    host = (settings.bambu_host or "").strip()
    serial = (settings.bambu_serial or "").strip()
    access_code = (settings.bambu_access_code or "").strip()

    if not settings.bambu_enabled or not host or not serial or not access_code:
        log.info("bambu_disabled_or_unconfigured",
                 enabled=settings.bambu_enabled,
                 has_host=bool(host),
                 has_serial=bool(serial),
                 has_access_code=bool(access_code))
        return

    loop = asyncio.get_running_loop()
    state = _State()
    report_topic = f"device/{serial}/report"
    request_topic = f"device/{serial}/request"

    client = Client(
        CallbackAPIVersion.VERSION2,
        client_id=f"kobe-{uuid4().hex[:12]}",
        protocol=MQTTv311,
    )
    client.username_pw_set("bblp", access_code)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    async def _publish_status_and_alert(st: PrinterStatus, new_raw: str, prev_raw: str | None) -> None:
        state.last_status = st
        await bus.publish(st)
        alert = _alert_for_transition(prev_raw, new_raw, st.filename)
        if alert is not None:
            await bus.publish(alert)

    def _marshal(coro) -> None:
        """Schedule a coroutine on the asyncio loop from the MQTT thread."""
        try:
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as exc:  # noqa: BLE001
            log.warning("bambu_marshal_failed", error=str(exc))

    def _publish_request(payload: dict[str, Any]) -> bool:
        try:
            info = client.publish(request_topic, json.dumps(payload), qos=0)
            return info.rc == 0
        except Exception as exc:  # noqa: BLE001
            log.warning("bambu_publish_failed", error=str(exc))
            return False

    def _on_connect(_client: Client, _userdata: Any, _flags: Any, reason_code: Any, _props: Any = None) -> None:
        rc = getattr(reason_code, "value", reason_code)
        if rc != 0:
            log.warning("bambu_connect_failed", reason=str(reason_code))
            return
        log.info("bambu_connected", host=host, serial=serial)
        state.connected = True
        try:
            client.subscribe(report_topic, qos=0)
        except Exception as exc:  # noqa: BLE001
            log.warning("bambu_subscribe_failed", error=str(exc))
        _publish_request({"pushing": {"sequence_id": state.next_seq(), "command": "pushall"}})

    def _on_disconnect(_client: Client, _userdata: Any, *args: Any, **_kwargs: Any) -> None:
        state.connected = False
        log.warning("bambu_disconnected", args=[str(a) for a in args])
        # Paho will auto-reconnect because we use loop_start + reconnect_delay_set.
        # Publish a disconnected snapshot so the HUD and `bambu_status` don't keep
        # claiming the printer is online with stale data.
        prev = state.last_status
        if prev is None:
            offline = PrinterStatus(
                connected=False,
                stage="unknown",
                progress_pct=0.0,
                remaining_minutes=0,
                nozzle_temp_c=0.0,
                bed_temp_c=0.0,
                filename="",
                timestamp_iso=_now_iso(),
            )
        else:
            offline = PrinterStatus(
                connected=False,
                stage=prev.stage,
                progress_pct=prev.progress_pct,
                remaining_minutes=prev.remaining_minutes,
                nozzle_temp_c=prev.nozzle_temp_c,
                bed_temp_c=prev.bed_temp_c,
                filename=prev.filename,
                timestamp_iso=_now_iso(),
            )
        state.last_status = offline
        _marshal(bus.publish(offline))

    def _on_message(_client: Client, _userdata: Any, msg: Any) -> None:
        try:
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            log.debug("bambu_bad_payload", error=str(exc))
            return
        print_obj = payload.get("print") if isinstance(payload, dict) else None
        if not isinstance(print_obj, dict):
            return
        st = _parse_status(print_obj, connected=state.connected)
        if st is None:
            return
        # Merge with prior status so incremental diffs still produce a complete snapshot.
        prev = state.last_status
        if prev is not None:
            st = PrinterStatus(
                connected=st.connected,
                stage=st.stage if st.stage != "unknown" else prev.stage,
                progress_pct=st.progress_pct if "mc_percent" in print_obj else prev.progress_pct,
                remaining_minutes=(st.remaining_minutes
                                   if "mc_remaining_time" in print_obj else prev.remaining_minutes),
                nozzle_temp_c=st.nozzle_temp_c if "nozzle_temper" in print_obj else prev.nozzle_temp_c,
                bed_temp_c=st.bed_temp_c if "bed_temper" in print_obj else prev.bed_temp_c,
                filename=st.filename or prev.filename,
                timestamp_iso=st.timestamp_iso,
            )
        new_raw = str(print_obj.get("gcode_state") or "").upper() or (state.last_stage or "")
        prev_raw = state.last_stage
        if new_raw:
            state.last_stage = new_raw
        _marshal(_publish_status_and_alert(st, new_raw, prev_raw))

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message

    async def _connect_with_retry() -> None:
        delay = 1.0
        while True:
            try:
                await asyncio.to_thread(client.connect, host, 8883, 60)
                client.loop_start()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("bambu_initial_connect_failed", error=str(exc), retry_in_s=delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60.0)

    async def _keepalive() -> None:
        interval = max(1.0, float(settings.bambu_poll_interval_s))
        while True:
            await asyncio.sleep(interval)
            if state.connected:
                _publish_request({"pushing": {"sequence_id": state.next_seq(), "command": "pushall"}})

    async def _handle_actions() -> None:
        async with bus.stream(ActionRequested) as q:
            while True:
                ev = await q.get()
                cmd = _HANDLED_ACTIONS.get(ev.action)
                if cmd is None:
                    continue  # not ours
                if cmd == "status":
                    await bus.publish(ActionCompleted(
                        request_id=ev.request_id,
                        action=ev.action,
                        ok=state.last_status is not None,
                        detail=_status_detail(state.last_status),
                    ))
                    continue
                if not state.connected:
                    await bus.publish(ActionCompleted(
                        request_id=ev.request_id,
                        action=ev.action,
                        ok=False,
                        detail="Printer not connected.",
                    ))
                    continue
                payload = {"print": {"sequence_id": state.next_seq(), "command": cmd}}
                ok = await asyncio.to_thread(_publish_request, payload)
                await bus.publish(ActionCompleted(
                    request_id=ev.request_id,
                    action=ev.action,
                    ok=ok,
                    detail=f"Sent {cmd}." if ok else f"Failed to send {cmd}.",
                ))

    log.info("bambu_service_starting", host=host, serial=serial,
             poll_interval_s=settings.bambu_poll_interval_s)

    await _connect_with_retry()
    keepalive_task = asyncio.create_task(_keepalive(), name="bambu.keepalive")
    actions_task = asyncio.create_task(_handle_actions(), name="bambu.actions")
    try:
        await asyncio.gather(keepalive_task, actions_task)
    except asyncio.CancelledError:
        log.info("bambu_service_cancelled")
        raise
    finally:
        for t in (keepalive_task, actions_task):
            if not t.done():
                t.cancel()
        try:
            await asyncio.to_thread(client.loop_stop)
        except Exception as exc:  # noqa: BLE001
            log.debug("bambu_loop_stop_failed", error=str(exc))
        try:
            await asyncio.to_thread(client.disconnect)
        except Exception as exc:  # noqa: BLE001
            log.debug("bambu_disconnect_failed", error=str(exc))
        log.info("bambu_service_stopped")
