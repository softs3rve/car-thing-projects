import asyncio
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pywizlight import discovery, wizlight, PilotBuilder

BIND_ADDR = ("0.0.0.0", 8899)
SCENES_PATH = os.path.expanduser("~/smart-home/scenes.json")
LIGHTS_PATH = os.path.expanduser("~/smart-home/lights.json")
APP_STATE_PATH = os.path.expanduser("~/smart-home/app_state.json")
BRIDGE_SECRET_PATH = os.path.expanduser("~/smart-home/.bridge_secret")
LIGHT_SCHEDULES_PATH = os.path.expanduser("~/smart-home/light_schedules.json")

# This bridge used to accept any request from anyone who could reach it -
# no key, no token. Confirmed during a security audit: bound to 0.0.0.0,
# reachable from the whole Tailscale tailnet (and would be from the whole
# home WiFi too, if this network didn't happen to have client isolation).
# Read once at startup rather than per-request; a missing/empty file means
# every request is rejected (fail closed, not fail open on misconfiguration).
with open(BRIDGE_SECRET_PATH) as _f:
    BRIDGE_SECRET = _f.read().strip()
if not BRIDGE_SECRET:
    raise SystemExit(f"{BRIDGE_SECRET_PATH} is empty - refusing to start unauthenticated")

# known lights at startup: id -> {ip, mac}. More are added at runtime by /scan,
# and persisted to LIGHTS_PATH so a bridge restart doesn't forget them.
KNOWN_LIGHTS = {
    "L1": {"ip": "192.168.1.XXX", "mac": "aabbccddeeff"},
    "L2": {"ip": "192.168.1.XXX", "mac": "aabbccddeeff"},
}

_loop = asyncio.new_event_loop()
_lights: dict[str, wizlight] = {}
_ready = threading.Event()

# Per-light write sequencing. ThreadingHTTPServer gives each request its own
# thread, and _call() blocks that thread on a real UDP round trip (with
# pywizlight retries) via a shared asyncio loop - nothing about that pipeline
# guarantees a command finishes SENDING in the order it was logically issued.
# A brightness command that hits a lost UDP packet and retries can finish
# AFTER a newer command that had no trouble, silently overwriting the bulb
# back to a stale value - this was the client's reversal-blip symptom
# (rapid direction changes are exactly when two opposite-value commands are
# most likely in flight at once), just one layer down: the two client-side
# fixes in the Light webapp (2026-08-06) protect the on-screen DISPLAY from
# stale data, not the bulb itself. Same fix, same layer: a monotonic
# sequence per light, checked immediately before the actual send - if a
# newer command for the same light has been issued since this one started,
# this one is stale and is dropped rather than allowed to overwrite it.
_write_seq_lock = threading.Lock()
_write_seq: dict[str, int] = {}


def _next_write_seq(light_id: str) -> int:
    with _write_seq_lock:
        n = _write_seq.get(light_id, 0) + 1
        _write_seq[light_id] = n
        return n


def _is_latest_write(light_id: str, seq: int) -> bool:
    with _write_seq_lock:
        latest = _write_seq.get(light_id, 0)
        if latest != seq:
            print(f"[write-seq] {light_id} seq={seq} DROPPED - superseded by seq={latest}")
        return latest == seq


def _load_extra_lights() -> dict:
    if os.path.exists(LIGHTS_PATH):
        with open(LIGHTS_PATH) as f:
            return json.load(f)
    return {}


def _save_extra_lights(extra: dict) -> None:
    with open(LIGHTS_PATH, "w") as f:
        json.dump(extra, f, indent=2)


def _next_light_id() -> str:
    n = 1
    while f"L{n}" in _lights:
        n += 1
    return f"L{n}"


def _run_loop() -> None:
    asyncio.set_event_loop(_loop)
    for light_id, info in KNOWN_LIGHTS.items():
        _lights[light_id] = wizlight(info["ip"], mac=info["mac"])
    # Persisted overrides always win over the hardcoded KNOWN_LIGHTS seed -
    # once /scan has re-discovered a bulb at a new IP (see below), LIGHTS_PATH
    # is the real-world source of truth, even for an id that also exists in
    # KNOWN_LIGHTS.
    for light_id, info in _load_extra_lights().items():
        _lights[light_id] = wizlight(info["ip"], mac=info["mac"])
    _loop.create_task(_poller())
    _loop.create_task(_scheduler())
    _ready.set()
    _loop.run_forever()


def _call(coro, timeout=8):
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=timeout)


async def _get_light_state(light_id: str) -> dict:
    bulb = _lights[light_id]
    state = (await bulb.updateState())[0]
    is_on = state.get_state()
    return {
        "id": light_id,
        "ip": bulb.ip,
        "on": is_on,
        # The bulb RETAINS its last brightness internally even while off
        # (turn_off() doesn't reset it) - reporting that retained value here
        # would make every client (Light's slider, the dial-anywhere script
        # on Clock/Parking) resume from wherever it was before being turned
        # off, rather than genuinely starting from zero. Report 0 while off
        # so "off" and "brightness 0" are the same state everywhere, and
        # turning the dial back up from off lands on the lowest step (5%)
        # instead of jumping back to the old pre-off level.
        "brightness": state.get_brightness() if is_on else 0,
        "rgb": state.get_rgb(),
    }


# Queried concurrently with a per-bulb cap. Serially, a single unreachable
# bulb costs ~13s of pywizlight retries on its own - more than _call's whole
# 8s budget - so one bulb switched off at the wall made GET /lights fail
# outright. Now an unresponsive bulb is reported as unreachable instead of
# taking the rest of the response down with it.
PER_LIGHT_TIMEOUT = 2.5

# ── Cached state (2026-09-29) ─────────────────────────────────────────────
# GET /lights used to query every bulb live, so ONE offline bulb (L3) made
# every request wait out the full PER_LIGHT_TIMEOUT: measured at exactly
# 2.50s per call, every call, which is the "slow to connect" the Car Thing
# showed each time the Light view opened. Now a background task on the
# shared loop keeps _cache fresh and every read is answered from memory.
# Reachable bulbs are re-polled every POLL_INTERVAL; an unreachable one is
# only retried every OFFLINE_RETRY so it can't slow the loop for the rest.
POLL_INTERVAL = 3.0
OFFLINE_RETRY = 30.0
_cache: dict[str, dict] = {}
_last_try: dict[str, float] = {}
# Set on every write. A poll that STARTED before the most recent write to
# that bulb is discarded, so a read already in flight can't overwrite the
# optimistic post-write state with the bulb's pre-write values.
_last_write_at: dict[str, float] = {}


def _unreachable(light_id: str) -> dict:
    return {
        "id": light_id,
        "ip": _lights[light_id].ip,
        "on": False,
        "brightness": 0,
        "rgb": [None, None, None],
        "reachable": False,
    }


async def _poll_one(light_id: str) -> None:
    started = time.monotonic()
    _last_try[light_id] = started
    try:
        state = await asyncio.wait_for(_get_light_state(light_id), PER_LIGHT_TIMEOUT)
    except Exception:
        state = _unreachable(light_id)
    if _last_write_at.get(light_id, 0) > started:
        return
    _cache[light_id] = state


async def _poll_due() -> None:
    now = time.monotonic()
    due = [
        light_id for light_id in list(_lights)
        if _cache.get(light_id, {}).get("reachable", True)
        or now - _last_try.get(light_id, 0) >= OFFLINE_RETRY
    ]
    await asyncio.gather(*(_poll_one(light_id) for light_id in due))


async def _poller() -> None:
    while True:
        try:
            await _poll_due()
        except Exception as e:
            print(f"[poller] {e}")
        await asyncio.sleep(POLL_INTERVAL)


async def _get_all_states() -> list[dict]:
    # Anything not polled yet (first request after startup, or a bulb /scan
    # just added) is fetched once live; everything else is instant.
    missing = [light_id for light_id in _lights if light_id not in _cache]
    if missing:
        await asyncio.gather(*(_poll_one(light_id) for light_id in missing))
    return [_cache[light_id] for light_id in list(_lights) if light_id in _cache]


def _note_write(light_id: str, action: str, body: dict) -> None:
    """Optimistically update the cache after a successful write, so the next
    read reflects it immediately instead of up to POLL_INTERVAL later."""
    _last_write_at[light_id] = time.monotonic()
    entry = dict(_cache.get(light_id) or _unreachable(light_id))
    entry.pop("reachable", None)  # a successful write proves it's reachable
    if body.get("on") is False:
        action = "off"
    if action == "off":
        entry["on"], entry["brightness"] = False, 0
    elif action == "on":
        entry["on"] = True
    if "value" in body and action == "brightness":
        v = max(0, min(100, int(body["value"])))
        entry["on"], entry["brightness"] = v > 0, round(v * 255 / 100)
    if "brightness" in body and body["brightness"] is not None:
        v = max(0, min(100, int(body["brightness"])))
        entry["on"], entry["brightness"] = v > 0, round(v * 255 / 100)
    if action == "color" or ("r" in body and body.get("r") is not None):
        entry["on"], entry["rgb"] = True, [int(body["r"]), int(body["g"]), int(body["b"])]
    if action == "colortemp" or body.get("colortemp") is not None:
        entry["on"], entry["rgb"] = True, [None, None, None]
    _cache[light_id] = entry


# Cross-app "which app was active before Clock took over" handoff. Deliberately
# NOT using bridgething's own client.doc surface for this: its docs describe doc
# values as scoped "for the active webapp", which reads as per-app-id storage -
# meaning Light's write and Clock's later read could land in two different
# buckets and silently never connect. Untestable from here without the device,
# so routing through this bridge (already the direct-fetch server both apps
# talk to) sidesteps the ambiguity entirely with state this project controls.
def _load_app_state() -> dict:
    if os.path.exists(APP_STATE_PATH):
        with open(APP_STATE_PATH) as f:
            return json.load(f)
    return {"lastActiveApp": None}


def _save_app_state(state: dict) -> None:
    with open(APP_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def _load_scenes() -> dict:
    if os.path.exists(SCENES_PATH):
        with open(SCENES_PATH) as f:
            return json.load(f)
    return {}


def _save_scenes(scenes: dict) -> None:
    with open(SCENES_PATH, "w") as f:
        json.dump(scenes, f, indent=2)


async def _scan() -> dict:
    found = await discovery.discover_lights(broadcast_space="255.255.255.255", wait_time=6.0)
    mac_to_id = {bulb.mac: light_id for light_id, bulb in _lights.items()}
    extra = _load_extra_lights()
    new_ids = []
    updated_ids = []
    changed = False
    for b in found:
        existing_id = mac_to_id.get(b.mac)
        if existing_id is not None:
            # Already-registered bulb (matched by MAC) showing up at a
            # different IP than we have on file - a DHCP lease change after
            # reconnecting, e.g. after being unplugged/off WiFi a while.
            # The old version of this function deduped purely on "have we
            # seen this MAC before" and skipped touching anything once it
            # had, which is exactly why a bulb could reconnect, answer this
            # same broadcast scan, and still stay "unreachable" forever -
            # nothing ever refreshed its stored IP. Update in place instead.
            if _lights[existing_id].ip != b.ip:
                _lights[existing_id] = wizlight(b.ip, mac=b.mac)
                extra[existing_id] = {"ip": b.ip, "mac": b.mac}
                updated_ids.append(existing_id)
                changed = True
            continue
        light_id = _next_light_id()
        _lights[light_id] = wizlight(b.ip, mac=b.mac)
        mac_to_id[b.mac] = light_id
        extra[light_id] = {"ip": b.ip, "mac": b.mac}
        new_ids.append(light_id)
        changed = True
    if changed:
        _save_extra_lights(extra)
    return {"new": new_ids, "updated": updated_ids}


# Builds the raw pywizlight awaitable for a "set an absolute value" action,
# without dispatching it - shared by the single-light path (_apply, wrapped
# in the synchronous _call()) and the all-lights path below (dispatched
# concurrently via asyncio.gather on the same shared loop).
def _build_set_coro(bulb: wizlight, action: str, body: dict):
    if action == "brightness":
        value = max(0, min(100, int(body["value"])))
        if value == 0:
            # turn_on(PilotBuilder(brightness=0)) still explicitly turns the
            # bulb ON - WiZ firmware clamps 0 up to some minimum visible
            # floor rather than actually going dark, so dialing all the way
            # down left it dimly lit instead of off. Zero means off.
            return bulb.turn_off()
        brightness_255 = round(value * 255 / 100)
        return bulb.turn_on(PilotBuilder(brightness=brightness_255))
    elif action == "color":
        r, g, b = int(body["r"]), int(body["g"]), int(body["b"])
        return bulb.turn_on(PilotBuilder(rgb=(r, g, b)))
    elif action == "colortemp":
        # true white uses the bulb's dedicated white LEDs via colortemp -
        # sending rgb=(255,255,255) only drives the color channels, which
        # on this RGBW hardware looks weak/near-black instead of white
        value = max(1000, min(10000, int(body["value"])))
        return bulb.turn_on(PilotBuilder(colortemp=value))
    elif action == "set":
        # One command carrying any mix of brightness + color/colortemp, so
        # "L1 red at 40%" is a single UDP send, not two racing ones. Used by
        # the Discord bot's per-light commands and the light schedules.
        if body.get("on") is False:
            return bulb.turn_off()
        kwargs = {}
        if body.get("brightness") is not None:
            value = max(0, min(100, int(body["brightness"])))
            if value == 0:
                return bulb.turn_off()
            kwargs["brightness"] = round(value * 255 / 100)
        if body.get("colortemp") is not None:
            kwargs["colortemp"] = max(1000, min(10000, int(body["colortemp"])))
        elif body.get("r") is not None:
            kwargs["rgb"] = (int(body["r"]), int(body["g"]), int(body["b"]))
        return bulb.turn_on(PilotBuilder(**kwargs)) if kwargs else bulb.turn_on()
    raise ValueError(f"unknown action {action}")


# "/all/*" used to apply to each light SEQUENTIALLY in a plain for loop, each
# a full blocking UDP round trip (with pywizlight retries) via _call(). Any
# single bulb having a bad moment raised, and since do_POST's try/except
# wraps the whole loop, one flaky bulb turned into a 502 for the ENTIRE
# batch - the client saw "bridge unreachable" and the other two bulbs' state
# was left ambiguous even though their own commands may have been fine.
# Reported symptom this was traced from: real 502s on POST /all/brightness
# in the journal, immediately correlated with the Light app's "some clicks
# do nothing" complaint. Now dispatched concurrently (same pattern as
# _get_all_states' concurrency fix earlier) with each light's failure
# caught and logged individually - one bad bulb no longer takes the other
# two down with it, and three-bulb writes are ~3x faster besides.
def _toggle_action(action: str, body: dict) -> str:
    if action == "toggle":
        return "on" if body.get("_toggled_to") else "off"
    return action


async def _apply_all_async(action: str, body: dict) -> None:
    async def do_one(light_id: str) -> None:
        write_body = body
        if action == "toggle":
            # This state read used to sit outside the try/except below - an
            # unreachable bulb raising here (not just from the actual
            # turn_on/turn_off send) escaped uncaught out of gather() and
            # 502'd the whole batch, reintroducing exactly the "one bad
            # bulb takes the others down" bug this function exists to
            # prevent, just for toggle specifically. Confirmed live:
            # POST /all/toggle 502'd in the journal while a third bulb was
            # offline, even though brightness/color/colortemp were
            # unaffected.
            # Toggle reads the cached state now (see _poller) instead of a
            # live round trip first.
            is_on = (_cache.get(light_id) or {}).get("on", False)
            coro = _lights[light_id].turn_off() if is_on else _lights[light_id].turn_on()
            write_body = {**body, "_toggled_to": not is_on}
        else:
            seq = _next_write_seq(light_id)
            coro = _build_set_coro(_lights[light_id], action, body)
            if not _is_latest_write(light_id, seq):
                return
        await coro
        _note_write(light_id, _toggle_action(action, write_body), write_body)

    async def one(light_id: str) -> None:
        started = time.monotonic()
        try:
            # Same PER_LIGHT_TIMEOUT cap the read path already uses. Without
            # this, one slow/offline bulb's pywizlight retries can eat the
            # outer _call()'s whole 8s budget on their own - the shared
            # asyncio Future from run_coroutine_threadsafe just times out
            # instead of ever reaching the except below to be caught and
            # logged, 502ing the entire batch again even with the fix above.
            await asyncio.wait_for(do_one(light_id), PER_LIGHT_TIMEOUT)
            # Successes are logged with their latency too, not just
            # failures: the owner reports L3 intermittently not following
            # the other two, and a failure-only log can't distinguish "L3
            # errored" from "L3 succeeded but took 2.4s while L1/L2 took
            # 200ms". A handful of lines per command, not a hot loop.
            print(f"[/all/{action}] {light_id} ok in {(time.monotonic() - started) * 1000:.0f}ms")
        except Exception as e:
            print(f"[/all/{action}] {light_id} FAILED after {(time.monotonic() - started) * 1000:.0f}ms (other lights unaffected): {e}")

    # Skip bulbs the poller already knows are offline: otherwise every
    # all-lights write (every dial tick) waits PER_LIGHT_TIMEOUT on them
    # before answering. The poller retries them every OFFLINE_RETRY, so a
    # bulb that comes back rejoins "all" on its own within ~30s.
    targets = [light_id for light_id in _lights if (_cache.get(light_id) or {}).get("reachable", True)]
    await asyncio.gather(*(one(light_id) for light_id in targets))



# ── Light schedules (2026-09-29) ──────────────────────────────────────────
# WiZ bulbs keep their own schedules in WiZ's cloud app, not anywhere
# reachable over the local UDP API, so on/off times for these bulbs have to
# be run from here instead. One daily schedule per target ("ALL" or a light
# id), replaced on re-save - same model as kasa_bridge.py's per-plug rule.
# Times are the Pi's local time (America/New_York, confirmed via timedatectl).
# Entry: {"on": "HH:MM"|None, "off": "HH:MM"|None, "brightness": 0-100|None,
#         "r"/"g"/"b" or "colortemp": optional look applied at the ON time}
SCHEDULE_CHECK_SECONDS = 15
_HHMM = re.compile(r"([01]?[0-9]|2[0-3]):([0-5][0-9])")
_sched_lock = threading.Lock()
_fired: set[tuple[str, str, str]] = set()  # (target, "on"/"off", "YYYY-MM-DD HH:MM")


def _norm_hhmm(value):
    if value in (None, ""):
        return None
    m = _HHMM.fullmatch(str(value).strip())
    if not m:
        raise ValueError(f"invalid time {value!r}, expected HH:MM (24h)")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _load_light_schedules() -> dict:
    if os.path.exists(LIGHT_SCHEDULES_PATH):
        with open(LIGHT_SCHEDULES_PATH) as f:
            return json.load(f)
    return {}


def _save_light_schedules(schedules: dict) -> None:
    with open(LIGHT_SCHEDULES_PATH, "w") as f:
        json.dump(schedules, f, indent=2)


async def _run_scheduled(target: str, which: str, entry: dict) -> None:
    ids = list(_lights) if target == "ALL" else [target]
    if which == "off":
        body = {"on": False}
    else:
        body = {k: entry[k] for k in ("brightness", "r", "g", "b", "colortemp") if entry.get(k) is not None}
        body.setdefault("brightness", 100)
    for light_id in ids:
        if light_id not in _lights:
            continue
        try:
            await asyncio.wait_for(_build_set_coro(_lights[light_id], "set", body), PER_LIGHT_TIMEOUT)
            _note_write(light_id, "set", body)
            print(f"[schedule] {target} {which} -> {light_id} ok")
        except Exception as e:
            print(f"[schedule] {target} {which} -> {light_id} FAILED: {e}")


async def _scheduler() -> None:
    while True:
        try:
            now = datetime.now()
            stamp = now.strftime("%Y-%m-%d %H:%M")
            hhmm = now.strftime("%H:%M")
            with _sched_lock:
                schedules = _load_light_schedules()
            for target, entry in schedules.items():
                for which in ("on", "off"):
                    key = (target, which, stamp)
                    if entry.get(which) == hhmm and key not in _fired:
                        _fired.add(key)
                        await _run_scheduled(target, which, entry)
            # Only this minute's keys matter for de-duplication.
            _fired.intersection_update({k for k in _fired if k[2] == stamp})
        except Exception as e:
            print(f"[scheduler] {e}")
        await asyncio.sleep(SCHEDULE_CHECK_SECONDS)


def _set_light_schedule(target: str, body: dict) -> dict:
    target = "ALL" if target.upper() == "ALL" else target
    if target != "ALL" and target not in _lights:
        raise KeyError(target)
    entry = {"on": _norm_hhmm(body.get("on")), "off": _norm_hhmm(body.get("off"))}
    if not entry["on"] and not entry["off"]:
        raise ValueError("give at least one of on / off, e.g. {\"on\": \"07:00\", \"off\": \"23:00\"}")
    if body.get("brightness") is not None:
        entry["brightness"] = max(1, min(100, int(body["brightness"])))
    if body.get("colortemp") is not None:
        entry["colortemp"] = max(1000, min(10000, int(body["colortemp"])))
    elif body.get("r") is not None:
        entry.update(r=int(body["r"]), g=int(body["g"]), b=int(body["b"]))
    with _sched_lock:
        schedules = _load_light_schedules()
        schedules[target] = entry
        _save_light_schedules(schedules)
    return schedules


def _clear_light_schedule(target: str) -> bool:
    target = "ALL" if target.upper() == "ALL" else target
    with _sched_lock:
        schedules = _load_light_schedules()
        existed = schedules.pop(target, None) is not None
        _save_light_schedules(schedules)
    return existed

# ── Car Thing screen backlight ────────────────────────────────────────────
# Lives here rather than as its own service ON the Car Thing, for a real
# reason: the Car Thing has no Python, no Node, no Perl, and its BusyBox
# `nc` is client-only (no -l listen mode), so it genuinely cannot host any
# local HTTP service at all - checked directly, not assumed. Its backlight
# sysfs node is also root-only. So the webapps (which already call this
# bridge for lights) call it here too, and the Pi drives the actual write
# over the passwordless SSH path it already has to the Car Thing.
CARTHING_HOST = "root@10.42.1.250"
BRIGHTNESS_PATH = "/sys/class/backlight/backlight/brightness"
DIM_BRIGHTNESS = 20        # of 160 max (device's own max_brightness)
NORMAL_BRIGHTNESS = 71     # the device's real default, read off it live


def _set_carthing_brightness(value: int) -> None:
    subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
         "-o", "StrictHostKeyChecking=accept-new", CARTHING_HOST,
         f"echo {int(value)} > {BRIGHTNESS_PATH}"],
        check=True, capture_output=True, timeout=10,
    )


async def _apply_scene_async(entries: list[dict]) -> list[dict]:
    # Concurrent with the same per-bulb cap as everything else - this used
    # to be a serial loop of _call()s, so one offline bulb 502'd the scene.
    async def one(entry: dict) -> None:
        light_id = entry["id"]
        if light_id not in _lights or entry.get("reachable") is False:
            return
        bulb = _lights[light_id]
        if entry["on"]:
            if entry["rgb"][0] is not None:
                coro = bulb.turn_on(PilotBuilder(brightness=entry["brightness"], rgb=tuple(entry["rgb"])))
            else:
                coro = bulb.turn_on(PilotBuilder(brightness=entry["brightness"]))
        else:
            coro = bulb.turn_off()
        try:
            await asyncio.wait_for(coro, PER_LIGHT_TIMEOUT)
            _last_write_at[light_id] = time.monotonic()
            await _poll_one(light_id)
        except Exception as e:
            print(f"[scene] {light_id} FAILED: {e}")

    await asyncio.gather(*(one(e) for e in entries))
    return await _get_all_states()


class Handler(BaseHTTPRequestHandler):
    # Keep-alive: the Car Thing's Chromium reuses one connection instead of
    # a fresh TCP handshake per request. Requires every response to carry an
    # accurate Content-Length, which _send_json always does.
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload) -> None:
        # A 204 must have no body - sending "{}" with it (the old behavior)
        # desyncs a kept-alive HTTP/1.1 connection.
        body = b"" if status == 204 else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Bridge-Secret")
        # The X-Bridge-Secret header makes EVERY request (GETs included)
        # need a CORS preflight, so each call used to be two round trips.
        # Let the browser cache the preflight (Chromium caps this at 2h).
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

    # Checked at the top of do_GET/do_POST, not do_OPTIONS - a CORS
    # preflight never carries the app's own headers (that's the whole
    # point of preflight), so it can't be gated the same way. The real
    # request right behind it still is.
    def _authorized(self) -> bool:
        return self.headers.get("X-Bridge-Secret") == BRIDGE_SECRET

    def do_OPTIONS(self) -> None:
        self._send_json(204, {})

    def do_GET(self) -> None:
        try:
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            if self.path == "/lights":
                self._send_json(200, _call(_get_all_states()))
            elif self.path == "/scenes":
                self._send_json(200, _load_scenes())
            elif self.path == "/state/last-active-app":
                self._send_json(200, _load_app_state())
            elif self.path == "/light-schedules":
                with _sched_lock:
                    self._send_json(200, _load_light_schedules())
            else:
                self._send_json(404, {"error": "not found"})
        except Exception as e:
            self._send_json(502, {"error": str(e)})

    def do_POST(self) -> None:
        try:
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            if self.path == "/scan":
                scan_result = _call(_scan(), timeout=10)
                self._send_json(200, {**scan_result, "lights": _call(_get_all_states())})
                return

            if self.path in ("/screen/dim", "/screen/undim"):
                value = DIM_BRIGHTNESS if self.path.endswith("/dim") else NORMAL_BRIGHTNESS
                _set_carthing_brightness(value)
                self._send_json(200, {"ok": True, "brightness": value})
                return

            # Both branches below used to re-fetch fresh state (another full
            # UDP round trip per bulb) just to put it in the response body -
            # but every caller in all three webapps (Light's toggle/
            # brightness/color/colortemp, and the dial-anywhere script on
            # Clock/Parking) discards that response and does its own
            # separate refresh() afterward regardless. That made every
            # single dial tick pay for two full round trips (set, then an
            # unread get) instead of one, and was the real source of the
            # reported lag under fast/sustained input. Acknowledge
            # immediately instead; nothing currently reads the old body.
            m = re.fullmatch(r"/lights/([A-Za-z0-9]+)/(toggle|brightness|color|colortemp|set)", self.path)
            if m:
                light_id, action = m.group(1), m.group(2)
                if light_id not in _lights:
                    self._send_json(404, {"error": f"unknown light {light_id}"})
                    return
                self._apply(light_id, action, self._read_json())
                self._send_json(200, {"ok": True})
                return

            m = re.fullmatch(r"/all/(toggle|brightness|color|colortemp|set)", self.path)
            if m:
                action = m.group(1)
                body = self._read_json()
                _call(_apply_all_async(action, body))
                self._send_json(200, {"ok": True})
                return

            m = re.fullmatch(r"/light-schedules/([A-Za-z0-9]+)", self.path)
            if m:
                try:
                    self._send_json(200, _set_light_schedule(m.group(1), self._read_json()))
                except KeyError:
                    self._send_json(404, {"error": f"unknown light {m.group(1)}"})
                except ValueError as e:
                    self._send_json(400, {"error": str(e)})
                return

            if self.path == "/state/last-active-app":
                body = self._read_json()
                state = {"lastActiveApp": body.get("id")}
                _save_app_state(state)
                self._send_json(200, state)
                return

            if self.path == "/scenes":
                scenes = _load_scenes()
                body = self._read_json()
                name = (body.get("name") or "").strip()
                if not name:
                    n = len(scenes) + 1
                    while f"Scene {n}" in scenes:
                        n += 1
                    name = f"Scene {n}"
                snapshot = _call(_get_all_states())
                scenes[name] = snapshot
                _save_scenes(scenes)
                self._send_json(200, {"name": name, "scenes": scenes})
                return

            m = re.fullmatch(r"/scenes/([^/]+)/apply", self.path)
            if m:
                name = m.group(1)
                scenes = _load_scenes()
                if name not in scenes:
                    self._send_json(404, {"error": f"unknown scene {name}"})
                    return
                self._send_json(200, _call(_apply_scene_async(scenes[name])))
                return

            self._send_json(404, {"error": "not found"})
        except Exception as e:
            self._send_json(502, {"error": str(e)})

    def do_DELETE(self) -> None:
        try:
            if not self._authorized():
                self._send_json(401, {"error": "unauthorized"})
                return
            m = re.fullmatch(r"/light-schedules/([A-Za-z0-9]+)", self.path)
            if m:
                self._send_json(200, {"ok": True, "existed": _clear_light_schedule(m.group(1))})
                return
            self._send_json(404, {"error": "not found"})
        except Exception as e:
            self._send_json(502, {"error": str(e)})

    def _apply(self, light_id: str, action: str, body: dict) -> None:
        bulb = _lights[light_id]
        if action == "toggle":
            is_on = (_cache.get(light_id) or {}).get("on", False)
            _call(bulb.turn_off() if is_on else bulb.turn_on())
            _note_write(light_id, "off" if is_on else "on", body)
        elif action in ("brightness", "color", "colortemp", "set"):
            seq = _next_write_seq(light_id)
            coro = _build_set_coro(bulb, action, body)
            if not _is_latest_write(light_id, seq):
                return  # superseded by a newer command for this light - drop it
            _call(coro)
            _note_write(light_id, "off" if action == "set" and (body.get("on") is False or body.get("brightness") == 0) else action, body)

    def log_message(self, fmt, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    # Started here rather than at import time: the loop's startup tasks
    # (_poller, _scheduler) are defined further down the module than the
    # old import-time start, and must exist before the loop runs them.
    threading.Thread(target=_run_loop, daemon=True).start()
    _ready.wait()
    server = ThreadingHTTPServer(BIND_ADDR, Handler)
    server.daemon_threads = True
    print(f"wiz_bridge listening on {BIND_ADDR[0]}:{BIND_ADDR[1]}, lights={list(KNOWN_LIGHTS)}")
    server.serve_forever()
