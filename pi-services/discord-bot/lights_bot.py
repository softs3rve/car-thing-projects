import os
import discord
from discord import app_commands
import aiohttp

# Secrets read from local files, never hardcoded - same pattern as
# wiz_bridge.py's .bridge_secret.
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "..", ".discord_bot_token")) as f:
    BOT_TOKEN = f.read().strip()
with open(os.path.join(HERE, "..", ".bridge_secret")) as f:
    BRIDGE_SECRET = f.read().strip()

BRIDGE = "http://127.0.0.1:8899"
KASA_BRIDGE = "http://127.0.0.1:8912"
HEADERS = {"X-Bridge-Secret": BRIDGE_SECRET, "Content-Type": "application/json"}

# Plug ids as they exist in kasa_bridge.py's KNOWN_PLUGS. Presented as
# Choices (not free text) so there's no typo surface, same reasoning as
# the COLORS choices below.
PLUG_IDS = ["K1", "K2", "K3", "K4"]

# Same palette as the Light webapp's DEFAULT_PRESETS (light-app/index.html)
# - one shared color vocabulary across every surface that controls these
# bulbs, rather than inventing a second one here.
COLORS = {
    "red": (255, 0, 0),
    "orange": (255, 140, 0),
    "yellow": (255, 255, 0),
    "green": (0, 200, 60),
    "blue": (0, 120, 255),
    "purple": (160, 0, 220),
}
# Whites go through the bulbs' dedicated white LEDs (colortemp), not
# rgb=(255,255,255) - wiz_bridge.py notes that RGB white looks weak/near-black
# on this RGBW hardware, which is what the old "white" choice here sent.
# 2700K matches the Light webapp's WHITE_COLORTEMP.
WHITES = {
    "white": 2700,
    "cool white": 5000,
}
COLOR_CHOICES = [app_commands.Choice(name=c, value=c) for c in [*COLORS, *WHITES]]

# Light targets. "all" plus each bulb id in wiz_bridge.py; a bulb /scan
# adds later won't be listed until it's added here too.
LIGHT_IDS = ["L1", "L2", "L3"]
LIGHT_CHOICES = [app_commands.Choice(name="all", value="all")] + [
    app_commands.Choice(name=i, value=i) for i in LIGHT_IDS
]


def color_body(name: str | None) -> dict:
    if name is None:
        return {}
    if name in WHITES:
        return {"colortemp": WHITES[name]}
    r, g, b = COLORS[name]
    return {"r": r, "g": g, "b": b}


def light_path(light: str | None, action: str) -> str:
    return f"/all/{action}" if not light or light == "all" else f"/lights/{light}/{action}"


def light_label(light: str | None) -> str:
    return "All lights" if not light or light == "all" else light

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
lights_group = app_commands.Group(name="lights", description="Control the smart home lights")
kasa_group = app_commands.Group(name="kasa", description="Control the Kasa smart plugs")


async def bridge_post(session: aiohttp.ClientSession, path: str, body: dict, base: str = BRIDGE) -> tuple[bool, str]:
    try:
        async with session.post(base + path, json=body, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                # Surface the bridge's own error text (e.g. an invalid HH:MM
                # from the schedule endpoint) rather than a bare status code.
                try:
                    detail = (await resp.json()).get("error", "")
                except Exception:
                    detail = ""
                return False, f"bridge returned {resp.status}{': ' + detail if detail else ''}"
            return True, ""
    except Exception as e:
        return False, str(e)


@lights_group.command(name="on", description="Turn lights on (all, or one light)")
@app_commands.describe(light="Which light (default: all)")
@app_commands.choices(light=LIGHT_CHOICES)
async def lights_on(interaction: discord.Interaction, light: str | None = None):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        ok, err = await bridge_post(session, light_path(light, "brightness"), {"value": 100})
    await interaction.followup.send(f"💡 {light_label(light)} on" if ok else f"⚠️ Failed: {err}")


@lights_group.command(name="off", description="Turn lights off (all, or one light)")
@app_commands.describe(light="Which light (default: all)")
@app_commands.choices(light=LIGHT_CHOICES)
async def lights_off(interaction: discord.Interaction, light: str | None = None):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        ok, err = await bridge_post(session, light_path(light, "brightness"), {"value": 0})
    await interaction.followup.send(f"🌑 {light_label(light)} off" if ok else f"⚠️ Failed: {err}")


@lights_group.command(name="brightness", description="Set brightness (0-100), all lights or one")
@app_commands.describe(value="Brightness percentage, 0-100", light="Which light (default: all)")
@app_commands.choices(light=LIGHT_CHOICES)
async def lights_brightness(interaction: discord.Interaction, value: app_commands.Range[int, 0, 100], light: str | None = None):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        ok, err = await bridge_post(session, light_path(light, "brightness"), {"value": value})
    await interaction.followup.send(f"🔆 {light_label(light)} brightness {value}%" if ok else f"⚠️ Failed: {err}")


@lights_group.command(name="color", description="Set color, all lights or one")
@app_commands.describe(name="Color name", light="Which light (default: all)")
@app_commands.choices(name=COLOR_CHOICES, light=LIGHT_CHOICES)
async def lights_color(interaction: discord.Interaction, name: str, light: str | None = None):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        ok, err = await bridge_post(session, light_path(light, "set"), color_body(name))
    await interaction.followup.send(f"🎨 {light_label(light)} set to {name}" if ok else f"⚠️ Failed: {err}")


@lights_group.command(name="set", description="Set one light (or all) to a color and brightness in one go")
@app_commands.describe(light="Which light", color="Color (optional)", brightness="Brightness 1-100 (optional)")
@app_commands.choices(light=LIGHT_CHOICES, color=COLOR_CHOICES)
async def lights_set(interaction: discord.Interaction, light: str, color: str | None = None,
                     brightness: app_commands.Range[int, 1, 100] | None = None):
    await interaction.response.defer()
    body = color_body(color)
    if brightness is not None:
        body["brightness"] = brightness
    async with aiohttp.ClientSession() as session:
        ok, err = await bridge_post(session, light_path(light, "set"), body)
    what = " · ".join(x for x in [color, f"{brightness}%" if brightness is not None else None] if x) or "on"
    await interaction.followup.send(f"💡 {light_label(light)} → {what}" if ok else f"⚠️ Failed: {err}")


@lights_group.command(name="schedule", description="Daily on/off times for a light (or all), with optional color + brightness")
@app_commands.describe(
    light="Which light",
    on="Turn-on time, HH:MM (24h) - optional if you only want an off time",
    off="Turn-off time, HH:MM (24h) - optional if you only want an on time",
    color="Color to turn on with (optional)",
    brightness="Brightness to turn on at, 1-100 (optional, default 100)",
)
@app_commands.choices(light=LIGHT_CHOICES, color=COLOR_CHOICES)
async def lights_schedule(interaction: discord.Interaction, light: str, on: str | None = None, off: str | None = None,
                          color: str | None = None, brightness: app_commands.Range[int, 1, 100] | None = None):
    await interaction.response.defer()
    body = {"on": on, "off": off, **color_body(color)}
    if brightness is not None:
        body["brightness"] = brightness
    async with aiohttp.ClientSession() as session:
        ok, err = await bridge_post(session, f"/light-schedules/{'ALL' if light == 'all' else light}", body)
    if not ok:
        await interaction.followup.send(f"⚠️ Failed: {err}")
        return
    parts = [f"on at {on}" if on else None, f"off at {off}" if off else None]
    look = " · ".join(x for x in [color, f"{brightness}%" if brightness is not None else None] if x)
    await interaction.followup.send(
        f"⏰ {light_label(light)}: {', '.join(p for p in parts if p)} (daily){' · ' + look if look else ''}"
    )


@lights_group.command(name="unschedule", description="Clear a light's (or all-lights) daily schedule")
@app_commands.describe(light="Which light")
@app_commands.choices(light=LIGHT_CHOICES)
async def lights_unschedule(interaction: discord.Interaction, light: str):
    await interaction.response.defer()
    target = "ALL" if light == "all" else light
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(f"{BRIDGE}/light-schedules/{target}", headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ok = resp.status == 200
                existed = ok and (await resp.json()).get("existed")
                err = "" if ok else f"bridge returned {resp.status}"
    except Exception as e:
        ok, existed, err = False, False, str(e)
    if not ok:
        await interaction.followup.send(f"⚠️ Failed: {err}")
    else:
        await interaction.followup.send(f"⏰ {light_label(light)} schedule cleared" if existed else f"{light_label(light)} had no schedule")


def fmt_light_schedule(entry: dict) -> str:
    parts = [f"on {entry['on']}" if entry.get("on") else None, f"off {entry['off']}" if entry.get("off") else None]
    if entry.get("colortemp"):
        parts.append(next((n for n, k in WHITES.items() if k == entry["colortemp"]), f"{entry['colortemp']}K"))
    elif entry.get("r") is not None:
        rgb = (entry["r"], entry["g"], entry["b"])
        parts.append(next((n for n, c in COLORS.items() if c == rgb), f"rgb{rgb}"))
    if entry.get("brightness"):
        parts.append(f"{entry['brightness']}%")
    return ", ".join(p for p in parts if p)


@lights_group.command(name="status", description="Show current light status")
async def lights_status(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BRIDGE + "/lights", headers=HEADERS, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                lights = await resp.json()
            async with session.get(BRIDGE + "/light-schedules", headers=HEADERS, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                schedules = await resp.json()
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed: {e}")
        return
    lines = []
    for light in lights:
        sched = schedules.get(light["id"])
        sched_txt = f" · ⏰ {fmt_light_schedule(sched)}" if sched else ""
        if light.get("reachable") is False:
            lines.append(f"**{light['id']}** — unreachable{sched_txt}")
            continue
        state = "on" if light["on"] else "off"
        pct = round(light["brightness"] / 255 * 100)
        rgb = light.get("rgb") or [None]
        color = ""
        if light["on"] and rgb[0] is not None:
            color = ", " + next((n for n, c in COLORS.items() if list(c) == list(rgb)), f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})")
        lines.append(f"**{light['id']}** — {state}, {pct}%{color}{sched_txt}")
    if schedules.get("ALL"):
        lines.append(f"**All lights** · ⏰ {fmt_light_schedule(schedules['ALL'])}")
    await interaction.followup.send("\n".join(lines) or "No lights found")


@kasa_group.command(name="on", description="Turn a Kasa plug on")
@app_commands.describe(plug="Which plug")
@app_commands.choices(plug=[app_commands.Choice(name=p, value=p) for p in PLUG_IDS])
async def kasa_on(interaction: discord.Interaction, plug: str):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        ok, err = await bridge_post(session, f"/plugs/{plug}/on", {}, base=KASA_BRIDGE)
    await interaction.followup.send(f"🔌 {plug} on" if ok else f"⚠️ Failed: {err}")


@kasa_group.command(name="off", description="Turn a Kasa plug off")
@app_commands.describe(plug="Which plug")
@app_commands.choices(plug=[app_commands.Choice(name=p, value=p) for p in PLUG_IDS])
async def kasa_off(interaction: discord.Interaction, plug: str):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        ok, err = await bridge_post(session, f"/plugs/{plug}/off", {}, base=KASA_BRIDGE)
    await interaction.followup.send(f"🔌 {plug} off" if ok else f"⚠️ Failed: {err}")


@kasa_group.command(name="status", description="Show all Kasa plugs and their schedules")
async def kasa_status(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(KASA_BRIDGE + "/plugs", headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                plugs = await resp.json()
            # kasa_bridge now returns each plug's schedule with /plugs.
            schedules = {p["id"]: [p["schedule"]] if p.get("schedule") else [] for p in plugs}
    except Exception as e:
        await interaction.followup.send(f"⚠️ Failed: {e}")
        return
    lines = []
    for p in plugs:
        if p.get("reachable") is False:
            lines.append(f"**{p['id']}** — unreachable")
            continue
        state = "on" if p["on"] else "off"
        rules = schedules.get(p["id"]) or []
        if rules:
            r = rules[0]
            sched = f" · on {r['on_time']}, off {r['off_time']}"
        else:
            sched = " · no schedule"
        lines.append(f"**{p['id']}** ({p['alias']}) — {state}{sched}")
    await interaction.followup.send("\n".join(lines) or "No plugs found")


@kasa_group.command(name="schedule", description="Set a daily on/off schedule for a plug")
@app_commands.describe(plug="Which plug", on="Turn-on time, HH:MM (24h)", off="Turn-off time, HH:MM (24h)")
@app_commands.choices(plug=[app_commands.Choice(name=p, value=p) for p in PLUG_IDS])
async def kasa_schedule(interaction: discord.Interaction, plug: str, on: str, off: str):
    await interaction.response.defer()
    async with aiohttp.ClientSession() as session:
        ok, err = await bridge_post(session, f"/plugs/{plug}/schedule", {"on": on, "off": off}, base=KASA_BRIDGE)
    await interaction.followup.send(
        f"⏰ {plug} scheduled — on at {on}, off at {off} (daily)" if ok else f"⚠️ Failed: {err}"
    )


@kasa_group.command(name="unschedule", description="Clear a plug's schedule")
@app_commands.describe(plug="Which plug")
@app_commands.choices(plug=[app_commands.Choice(name=p, value=p) for p in PLUG_IDS])
async def kasa_unschedule(interaction: discord.Interaction, plug: str):
    await interaction.response.defer()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(f"{KASA_BRIDGE}/plugs/{plug}/schedule", headers=HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ok = resp.status == 200
                err = "" if ok else f"bridge returned {resp.status}"
    except Exception as e:
        ok, err = False, str(e)
    await interaction.followup.send(f"⏰ {plug} schedule cleared" if ok else f"⚠️ Failed: {err}")


tree.add_command(lights_group)
tree.add_command(kasa_group)


@client.event
async def on_ready():
    # Sync to every guild the bot is actually in rather than a global sync
    # (which can take up to an hour to propagate) or a hardcoded guild ID
    # (this bot was only just invited, no ID known ahead of time) - guild
    # syncs are instant, and there's exactly one guild for a personal bot.
    # Commands added via tree.add_command() with no explicit guild scoping
    # are global-scoped in the tree's own bookkeeping - tree.sync(guild=...)
    # only pushes whatever's actually been copied into that guild's bucket,
    # so without copy_global_to first it correctly (if confusingly) syncs
    # zero commands. Confirmed live: tree.get_commands() showed the "lights"
    # group present, but sync(guild=...) alone still returned an empty list
    # both here and via a direct GET against Discord's API afterward.
    for guild in client.guilds:
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        print(f"synced {len(synced)} command(s) to guild: {guild.name} ({guild.id})")
    print(f"logged in as {client.user}")


if __name__ == "__main__":
    client.run(BOT_TOKEN)
