import asyncio
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kasa import Device
from kasa.iot import IotPlug
from kasa.iot.modules.rulemodule import Action, TimeOption
from kasa.protocols.iotprotocol import IotProtocol
from kasa.transports.klaptransport import KlapTransportV2
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)

BIND_ADDR = ("0.0.0.0", 8912)
BRIDGE_SECRET_PATH = os.path.expanduser("~/smart-home/.bridge_secret")

# Same shared secret as wiz_bridge.py. Fail closed on a missing/empty
# file rather than starting unauthenticated.
with open(BRIDGE_SECRET_PATH) as _f:
    BRIDGE_SECRET = _f.read().strip()
if not BRIDGE_SECRET:
    raise SystemExit(f"{BRIDGE_SECRET_PATH} is empty - refusing to start unauthenticated")

# K4 needs a different connect path than the other three - see
# _get_device() below. Real, confirmed reason, not a guess: python-kasa
# 0.10.2's device_factory.py hardcodes "IOT.KLAP" -> KlapTransport (v1)
# unconditionally, regardless of the device's own reported login_version;
# only "SMART.KLAP" (a different device family entirely - Tapo/newer Kasa)
# gets routed to KlapTransportV2. K4's firmware requires v2 even though
# it's IOT-family, so the standard Device.connect() factory path can never
# authenticate it - confirmed against the library's own source, not
# assumed (2026-08-10).
KNOWN_PLUGS = {
    "K1": {"ip": "192.168.1.XXX", "mac": "aabbccddeeff", "klap_v2": False},
    "K2": {"ip": "192.168.1.XXX", "mac": "aabbccddeeff", "klap_v2": False},
    "K3": {"ip": "192.168.1.XXX", "mac": "aabbccddeeff", "klap_v2": False},
    "K4": {"ip": "192.168.1.XXX", "mac": "aabbccddeeff", "klap_v2": True},
}

PER_PLUG_TIMEOUT = 3  # same reasoning as wiz_bridge.py's PER_LIGHT_TIMEOUT -
# one offline/slow plug must not take the other two down with it.

_loop = asyncio.new_event_loop()
_ready = threading.Event()


def _run_loop() -> None:
    asyncio.set_event_loop(_loop)
    _loop.create_task(_poller())
    _ready.set()
    _loop.run_forever()


def _call(coro, timeout=8):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=timeout)


async def _connect(plug_id: str) -> Device:
    info = KNOWN_PLUGS[plug_id]
    if not info["klap_v2"]:
        return await Device.connect(host=info["ip"])
    # K4: bypass the factory entirely (see KNOWN_PLUGS comment above) by
    # constructing the KLAP v2 transport by hand. Confirmed live, twice -
    # once to provision it onto WiFi, once from this exact Pi to control
    # it - not just a theoretical workaround.
    conn = DeviceConnectionParameters(
        device_family=DeviceFamily.IotSmartPlugSwitch,
        encryption_type=DeviceEncryptionType.Klap,
        login_version=2,
    )
    config = DeviceConfig(host=info["ip"], connection_type=conn)
    transport = KlapTransportV2(config=config)
    protocol = IotProtocol(transport=transport)
    dev = IotPlug(info["ip"], config=config, protocol=protocol)
    await dev.update()  # IotPlug isn't auto-updated on construction like Device.connect() does
    return dev


# ── Persistent connections + cached state (2026-09-29) ────────────────────
# This used to open a fresh connection (TCP + KLAP handshake) on EVERY call
# and query all four plugs live per GET /plugs, so one offline plug (K3)
# made every request wait out the full PER_PLUG_TIMEOUT: measured at exactly
# 3.0s per call. The Kasa view then made four more sequential schedule calls
# on top. Now each plug keeps one long-lived Device (a refresh on an open
# one measured ~25ms), a background task keeps _cache fresh, and GET /plugs
# answers from memory with each plug's schedule included. A failing plug's
# Device is dropped and rebuilt on the next attempt, and an unreachable
# plug is only retried every OFFLINE_RETRY so it can't slow the others.
POLL_INTERVAL = 5.0
OFFLINE_RETRY = 30.0
_devices: dict[str, Device] = {}
_locks: dict[str, asyncio.Lock] = {}
_cache: dict[str, dict] = {}
_last_try: dict[str, float] = {}


def _lock(plug_id: str) -> asyncio.Lock:
    if plug_id not in _locks:
        _locks[plug_id] = asyncio.Lock()
    return _locks[plug_id]


async def _drop(plug_id: str) -> None:
    dev = _devices.pop(plug_id, None)
    if dev is not None:
        try:
            await dev.disconnect()
        except Exception:
            pass


async def _get_device(plug_id: str) -> Device:
    """The plug's open Device, freshly updated. Caller holds _lock(plug_id)."""
    dev = _devices.get(plug_id)
    if dev is None:
        dev = await asyncio.wait_for(_connect(plug_id), PER_PLUG_TIMEOUT)
        _devices[plug_id] = dev
    else:
        await asyncio.wait_for(dev.update(), PER_PLUG_TIMEOUT)
    return dev


def _state_from(plug_id: str, dev: Device) -> dict:
    try:
        rules = dev.modules["schedule"].rules
    except Exception:
        rules = []
    return {
        "id": plug_id,
        "alias": dev.alias,
        "ip": KNOWN_PLUGS[plug_id]["ip"],
        "on": bool(dev.features["state"].value),
        "rssi": dev.features["rssi"].value if "rssi" in dev.features else None,
        "schedule": _rule_to_dict(rules[0]) if rules else None,
    }


def _unreachable(plug_id: str) -> dict:
    return {
        "id": plug_id,
        "alias": None,
        "ip": KNOWN_PLUGS[plug_id]["ip"],
        "on": False,
        "rssi": None,
        "schedule": None,
        "reachable": False,
    }


async def _plug_state(plug_id: str) -> dict:
    _last_try[plug_id] = time.monotonic()
    async with _lock(plug_id):
        try:
            state = _state_from(plug_id, await _get_device(plug_id))
        except Exception:
            await _drop(plug_id)
            state = _unreachable(plug_id)
        _cache[plug_id] = state
        return state


async def _poller() -> None:
    while True:
        now = time.monotonic()
        due = [
            pid for pid in KNOWN_PLUGS
            if _cache.get(pid, {}).get("reachable", True)
            or now - _last_try.get(pid, 0) >= OFFLINE_RETRY
        ]
        try:
            await asyncio.gather(*(_plug_state(pid) for pid in due))
        except Exception as e:
            print(f"[poller] {e}")
        await asyncio.sleep(POLL_INTERVAL)


async def _get_all_states() -> list[dict]:
    missing = [pid for pid in KNOWN_PLUGS if pid not in _cache]
    if missing:
        await asyncio.gather(*(_plug_state(pid) for pid in missing))
    return [_cache[pid] for pid in KNOWN_PLUGS]


async def _with_device(plug_id: str, fn):
    """Run fn(dev) on the plug's open Device, retrying once on a fresh
    connection if the kept-alive one has gone stale (KLAP sessions expire),
    then refresh the cache so the next read reflects the change."""
    async with _lock(plug_id):
        try:
            dev = await _get_device(plug_id)
            result = await asyncio.wait_for(fn(dev), PER_PLUG_TIMEOUT * 2)
        except Exception:
            await _drop(plug_id)
            dev = await _get_device(plug_id)
            result = await asyncio.wait_for(fn(dev), PER_PLUG_TIMEOUT * 2)
        try:
            await asyncio.wait_for(dev.update(), PER_PLUG_TIMEOUT)
            _cache[plug_id] = _state_from(plug_id, dev)
        except Exception:
            pass
        return result


async def _set_plug(plug_id: str, on: bool) -> None:
    await _with_device(plug_id, lambda dev: dev.turn_on() if on else dev.turn_off())


def _rule_to_dict(rule) -> dict:
    return {
        "id": rule.id,
        "enabled": bool(rule.enable),
        "on_time": _min_to_hhmm(rule.smin) if rule.sact == Action.TurnOn else None,
        "off_time": _min_to_hhmm(rule.emin) if rule.eact == Action.TurnOff else None,
    }


def _min_to_hhmm(mins: int | None) -> str | None:
    if mins is None or mins < 0:
        return None
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _hhmm_to_min(hhmm: str) -> int:
    m = re.fullmatch(r"([01]?[0-9]|2[0-3]):([0-5][0-9])", hhmm)
    if not m:
        raise ValueError(f"invalid time {hhmm!r}, expected HH:MM")
    return int(m.group(1)) * 60 + int(m.group(2))


async def _get_schedule(plug_id: str) -> list[dict]:
    if plug_id not in _cache:
        await _plug_state(plug_id)
    sched = _cache[plug_id].get("schedule")
    return [sched] if sched else []


async def _set_schedule(plug_id: str, on_time: str, off_time: str) -> dict:
    on_min = _hhmm_to_min(on_time)
    off_min = _hhmm_to_min(off_time)

    async def apply(dev):
        sched = dev.modules["schedule"]
        # Replace rather than accumulate - a repeated POST to the same
        # plug's schedule should update it in place, not pile up duplicate
        # daily rules that'd all fire independently.
        await sched.delete_all_rules()
        return await sched.call(
            "add_rule",
            {
                "name": f"{plug_id}-daily",
                "enable": 1,
                "wday": [1, 1, 1, 1, 1, 1, 1],
                "repeat": 1,
                "sact": Action.TurnOn.value,
                "stime_opt": TimeOption.Enabled.value,
                "smin": on_min,
                "eact": Action.TurnOff.value,
                "etime_opt": TimeOption.Enabled.value,
                "emin": off_min,
            },
        )

    return await _with_device(plug_id, apply)


async def _clear_schedule(plug_id: str) -> None:
    await _with_device(plug_id, lambda dev: dev.modules["schedule"].delete_all_rules())


class Handler(BaseHTTPRequestHandler):
    # Keep-alive + cached CORS preflight: same reasoning as wiz_bridge.py.
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload) -> None:
        body = b"" if status == 204 else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Bridge-Secret")
        self.send_header("Access-Control-Max-Age", "7200")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _authorized(self) -> bool:
        return self.headers.get("X-Bridge-Secret") == BRIDGE_SECRET

    def do_OPTIONS(self) -> None:
        self._send_json(204, {})

    def do_GET(self) -> None:
        try:
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            if self.path == "/plugs":
                self._send_json(200, _call(_get_all_states()))
                return
            m = re.fullmatch(r"/plugs/([A-Za-z0-9]+)/schedule", self.path)
            if m:
                plug_id = m.group(1)
                if plug_id not in KNOWN_PLUGS:
                    self._send_json(404, {"error": "unknown plug"})
                    return
                self._send_json(200, _call(_get_schedule(plug_id)))
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            self._send_json(502, {"error": str(e)})

    def do_POST(self) -> None:
        try:
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            m = re.fullmatch(r"/plugs/([A-Za-z0-9]+)/(on|off)", self.path)
            if m:
                plug_id, action = m.group(1), m.group(2)
                if plug_id not in KNOWN_PLUGS:
                    self._send_json(404, {"error": "unknown plug"})
                    return
                _call(_set_plug(plug_id, action == "on"))
                self._send_json(200, {"ok": True})
                return
            m = re.fullmatch(r"/plugs/([A-Za-z0-9]+)/schedule", self.path)
            if m:
                plug_id = m.group(1)
                if plug_id not in KNOWN_PLUGS:
                    self._send_json(404, {"error": "unknown plug"})
                    return
                body = self._read_json()
                if "on" not in body or "off" not in body:
                    self._send_json(400, {"error": "body must include on and off, e.g. {\"on\": \"07:00\", \"off\": \"23:00\"}"})
                    return
                _call(_set_schedule(plug_id, body["on"], body["off"]))
                self._send_json(200, {"ok": True})
                return
            self._send_json(404, {"error": "not found"})
        except ValueError as e:
            self._send_json(400, {"error": str(e)})
        except Exception as e:
            self._send_json(502, {"error": str(e)})

    def do_DELETE(self) -> None:
        try:
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            m = re.fullmatch(r"/plugs/([A-Za-z0-9]+)/schedule", self.path)
            if m:
                plug_id = m.group(1)
                if plug_id not in KNOWN_PLUGS:
                    self._send_json(404, {"error": "unknown plug"})
                    return
                _call(_clear_schedule(plug_id))
                self._send_json(200, {"ok": True})
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            self._send_json(502, {"error": str(e)})

    def log_message(self, fmt, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    # Started here, not at import time, so _poller exists before the loop runs it.
    threading.Thread(target=_run_loop, daemon=True).start()
    _ready.wait()
    server = ThreadingHTTPServer(BIND_ADDR, Handler)
    server.daemon_threads = True
    print(f"kasa_bridge listening on {BIND_ADDR[0]}:{BIND_ADDR[1]}, plugs={list(KNOWN_PLUGS)}")
    server.serve_forever()
