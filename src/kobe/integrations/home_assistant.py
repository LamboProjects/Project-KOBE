"""Home Assistant smart-home integration (Phase 6).

Subscribes to `ActionRequested` and translates `home_*` intents into REST calls
against a user-supplied Home Assistant instance. The brain is responsible for
picking the right `entity_id` — we do no mDNS or device discovery here.

All REST calls go through a single reused `httpx.AsyncClient` so HA sees us as
one well-behaved keep-alive peer. Failures (HTTP, timeout, non-2xx) are logged
and surfaced as `ActionCompleted(ok=False, detail=...)` — they never raise into
the bus.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from kobe.bus import Bus
from kobe.config import Settings
from kobe.events import ActionCompleted, ActionRequested

log = structlog.get_logger(__name__)

_DETAIL_MAX = 160

# Named action -> (HTTP method, path-template, allowed extra params).
# entity_id is always passed through in the JSON body (POST) or URL (GET).
_LIGHT_ON_PARAMS = {"brightness_pct", "rgb_color", "color_temp_kelvin", "transition"}
_LIGHT_OFF_PARAMS = {"transition"}

_HANDLED_NAMED: set[str] = {
    "home_light_on",
    "home_light_off",
    "home_light_toggle",
    "home_switch_on",
    "home_switch_off",
    "home_scene_activate",
    "home_state",
}


def _truncate(s: str, limit: int = _DETAIL_MAX) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "\u2026"


def _build_service_body(
    action: str, params: dict[str, Any]
) -> tuple[str, str, dict[str, Any]] | None:
    """Return (domain, service, body) for a named action, or None if invalid."""
    entity_id = params.get("entity_id")
    if not entity_id:
        return None
    body: dict[str, Any] = {"entity_id": entity_id}

    if action == "home_light_on":
        for key in _LIGHT_ON_PARAMS:
            if key in params and params[key] is not None:
                body[key] = params[key]
        return "light", "turn_on", body
    if action == "home_light_off":
        for key in _LIGHT_OFF_PARAMS:
            if key in params and params[key] is not None:
                body[key] = params[key]
        return "light", "turn_off", body
    if action == "home_light_toggle":
        return "light", "toggle", body
    if action == "home_switch_on":
        return "switch", "turn_on", body
    if action == "home_switch_off":
        return "switch", "turn_off", body
    if action == "home_scene_activate":
        return "scene", "turn_on", body
    return None


def _summarise_state(payload: dict[str, Any]) -> str:
    """Build a short human phrase like `Desk lamp is on at 80%` from a state blob."""
    attrs = payload.get("attributes") or {}
    friendly = attrs.get("friendly_name") or payload.get("entity_id") or "entity"
    state = str(payload.get("state", "unknown"))
    extra = ""
    # Light brightness 0..255 -> percent
    brightness = attrs.get("brightness")
    if state == "on" and isinstance(brightness, (int, float)):
        pct = max(0, min(100, round(float(brightness) / 255.0 * 100)))
        extra = f" at {pct}%"
    # Climate / sensor — surface current temperature if present
    elif "temperature" in attrs and attrs["temperature"] is not None:
        extra = f" ({attrs['temperature']}\u00b0)"
    elif "current_temperature" in attrs and attrs["current_temperature"] is not None:
        extra = f" ({attrs['current_temperature']}\u00b0)"
    return f"{friendly} is {state}{extra}"


async def _call_service(
    client: httpx.AsyncClient,
    base: str,
    domain: str,
    service: str,
    body: dict[str, Any],
) -> tuple[bool, str]:
    url = f"{base}/api/services/{domain}/{service}"
    try:
        resp = await client.post(url, json=body)
    except httpx.TimeoutException as exc:
        return False, f"timeout: {exc}"
    except httpx.HTTPError as exc:
        return False, f"http_error: {exc}"
    if resp.status_code in (200, 201):
        entity = body.get("entity_id", "?")
        return True, f"{domain}.{service} ok ({entity})"
    preview = resp.text[:120].replace("\n", " ")
    return False, f"status {resp.status_code}: {preview}"


async def _get_state(
    client: httpx.AsyncClient, base: str, entity_id: str
) -> tuple[bool, str]:
    url = f"{base}/api/states/{entity_id}"
    try:
        resp = await client.get(url)
    except httpx.TimeoutException as exc:
        return False, f"timeout: {exc}"
    except httpx.HTTPError as exc:
        return False, f"http_error: {exc}"
    if resp.status_code != 200:
        preview = resp.text[:120].replace("\n", " ")
        return False, f"status {resp.status_code}: {preview}"
    try:
        payload = resp.json()
    except ValueError as exc:
        return False, f"bad_json: {exc}"
    if not isinstance(payload, dict):
        return False, "bad_json: not an object"
    return True, _summarise_state(payload)


async def _handle_action(
    client: httpx.AsyncClient, base: str, req: ActionRequested
) -> tuple[bool, str]:
    params = dict(req.params or {})
    action = req.action

    if action == "home_state":
        entity_id = params.get("entity_id")
        if not entity_id:
            return False, "missing entity_id"
        return await _get_state(client, base, entity_id)

    if action in _HANDLED_NAMED:
        built = _build_service_body(action, params)
        if built is None:
            return False, "missing entity_id"
        domain, service, body = built
        return await _call_service(client, base, domain, service, body)

    # Generic pass-through: brain supplies service/domain/data directly.
    domain = params.get("domain")
    service = params.get("service")
    data = params.get("data")
    if not domain or not service:
        return False, "missing domain/service for generic home_* action"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return False, "data must be an object"
    return await _call_service(client, base, str(domain), str(service), data)


async def _probe(client: httpx.AsyncClient, base: str) -> None:
    """One-shot health check. Log on ready/unreachable; do not raise."""
    try:
        resp = await client.get(f"{base}/api/")
    except httpx.HTTPError as exc:
        log.warning("homeassistant_unreachable", error=str(exc))
        return
    if resp.status_code == 200:
        log.info("homeassistant_ready", url=base)
    elif resp.status_code == 401:
        log.warning("homeassistant_unreachable", status=401, reason="bad_token")
    else:
        log.warning(
            "homeassistant_unreachable",
            status=resp.status_code,
            preview=resp.text[:80].replace("\n", " "),
        )


async def run_homeassistant_service(bus: Bus, settings: Settings) -> None:
    """Run the Home Assistant action executor until cancelled.

    When unconfigured we don't exit the TaskGroup — instead we run a tiny
    stub that subscribes to `ActionRequested` and replies to any `home_*`
    with a clear `ActionCompleted(ok=False, "…not configured")`. Otherwise
    those actions would go to nobody (no executor owns them) and the user
    would hear silence instead of a concrete failure.
    """
    if (
        not settings.homeassistant_enabled
        or not settings.homeassistant_url
        or not settings.homeassistant_token
    ):
        log.info("homeassistant_unconfigured")
        q = bus.subscribe(ActionRequested)
        try:
            while True:
                ev = await q.get()
                if not ev.action.startswith("home_"):
                    continue
                await bus.publish(
                    ActionCompleted(
                        request_id=ev.request_id,
                        action=ev.action,
                        ok=False,
                        detail=(
                            "Home Assistant is not configured — set "
                            "HOMEASSISTANT_URL and HOMEASSISTANT_TOKEN."
                        ),
                    )
                )
        except asyncio.CancelledError:
            raise
        finally:
            bus.unsubscribe(ActionRequested, q)
            log.info("homeassistant_stub_stopped")
        return

    base = settings.homeassistant_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.homeassistant_token}",
        "Content-Type": "application/json",
    }

    client = httpx.AsyncClient(
        timeout=settings.homeassistant_timeout_s,
        verify=settings.homeassistant_verify_tls,
        headers=headers,
    )

    q = bus.subscribe(ActionRequested)
    try:
        await _probe(client, base)
        log.info(
            "homeassistant_service_started",
            url=base,
            verify_tls=settings.homeassistant_verify_tls,
        )
        while True:
            req = await q.get()
            action = req.action
            if not action.startswith("home_"):
                continue  # Not ours — executor owns it.
            log.info(
                "homeassistant_action",
                action=action,
                params=req.params,
                request_id=req.request_id,
            )
            try:
                ok, detail = await _handle_action(client, base, req)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - never raise into the bus
                ok = False
                detail = f"error: {exc}"
                log.warning(
                    "homeassistant_action_error",
                    action=action,
                    error=str(exc),
                )
            if not ok:
                log.warning(
                    "homeassistant_action_failed",
                    action=action,
                    detail=detail,
                )
            await bus.publish(
                ActionCompleted(
                    request_id=req.request_id,
                    action=action,
                    ok=ok,
                    detail=_truncate(detail),
                )
            )
    except asyncio.CancelledError:
        log.info("homeassistant_service_cancelled")
        raise
    finally:
        bus.unsubscribe(ActionRequested, q)
        await client.aclose()
        log.info("homeassistant_service_stopped")
