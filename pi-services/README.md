# Raspberry Pi services

Small Python services that run on the Raspberry Pi the Car Thing is plugged
into. The Car Thing webapp and a Discord bot call them over HTTP.

| Folder | Port | What it does |
|---|---|---|
| [`wiz-bridge/`](wiz-bridge) | 8899 | Controls WiZ smart bulbs on your network; runs daily light schedules; dims the Car Thing's screen |
| [`kasa-bridge/`](kasa-bridge) | 8912 | Controls TP-Link Kasa smart plugs; writes on/off schedules into the plugs themselves |
| [`discord-bot/`](discord-bot) | none | `/lights` and `/kasa` slash commands in your Discord server |
| [`cdp-watchdog/`](cdp-watchdog) | none | Timer that closes an unauthenticated debugging port on the Car Thing if a reboot reopens it |

You don't need all of them. The webapp's Light view needs `wiz-bridge`, the
Kasa view needs `kasa-bridge`, and screen dimming goes through `wiz-bridge`.

## Layout on the Pi

The unit files assume user `admin` and this layout. If your username or
paths differ, edit `User=`, `WorkingDirectory=`, and `ExecStart=` in each
`.service` file.

```
/home/admin/smart-home/
├── .bridge_secret          # shared secret, chmod 600
├── .discord_bot_token      # Discord bot token, chmod 600
├── venv/                   # wiz-bridge's virtualenv
├── wiz_bridge.py
├── kasa/venv/              # kasa-bridge's virtualenv
├── kasa_bridge.py
├── close_cdp_proxy.sh
└── discord-bot/
    ├── venv/
    └── lights_bot.py
```

## 1. The shared secret

Every request to the bridges must carry an `X-Bridge-Secret` header. Both
bridges refuse to start without the file.

```bash
mkdir -p ~/smart-home
openssl rand -hex 24 > ~/smart-home/.bridge_secret
chmod 600 ~/smart-home/.bridge_secret
```

Put the same value in `BRIDGE_SECRET` in the webapp's `index.html`.

## 2. wiz-bridge

Edit `KNOWN_LIGHTS` in `wiz_bridge.py` with your bulbs' local IP and MAC
addresses (your router's device list, or the WiZ app's device info, shows
them). You can also leave it empty and `POST /scan` to discover bulbs by
broadcast; found bulbs are saved to `~/smart-home/lights.json`. Also update
`LIGHT_IDS` in `discord-bot/lights_bot.py` to match.

```bash
cp wiz-bridge/wiz_bridge.py ~/smart-home/
python3 -m venv ~/smart-home/venv
~/smart-home/venv/bin/pip install -r wiz-bridge/requirements.txt

sudo cp wiz-bridge/wiz-bridge.service /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/wiz-bridge.service.d
sudo cp wiz-bridge/10-logging.conf /etc/systemd/system/wiz-bridge.service.d/
sudo systemctl daemon-reload
sudo systemctl enable --now wiz-bridge
```

Endpoints: `GET /lights` (answers from a cache that a background poller
keeps fresh, so an offline bulb doesn't stall it), `POST /lights/<id>/set`
and `/lights/all/set` (on/off, brightness, RGB color or color temperature in
one call), `GET /light-schedules`, `POST|DELETE /light-schedules/<id>` (or
`ALL`), `GET|POST /scenes`,
`POST /scan`, `POST /screen/dim` and `/screen/undim`.

WiZ keeps its own schedules in its cloud app, which the local API can't
reach, so **light schedules are run by this bridge** and don't fire while
the Pi is off.

**Screen dimming** runs `ssh root@10.42.1.250 "echo N >
/sys/class/backlight/backlight/brightness"` from the Pi. It needs the Pi to
reach the Car Thing over SSH without a password prompt (see the security
note below).

## 3. kasa-bridge

Edit `KNOWN_PLUGS` in `kasa_bridge.py` with your plugs' IPs and MACs, and
update `PLUG_IDS` in `discord-bot/lights_bot.py` to match. Set `klap_v2:
True` only for a plug whose firmware needs KLAP v2 (python-kasa 0.10.2
can't detect that for older Kasa plugs; if a plug won't authenticate with
`False`, try `True`).

```bash
cp kasa-bridge/kasa_bridge.py ~/smart-home/
python3 -m venv ~/smart-home/kasa/venv
~/smart-home/kasa/venv/bin/pip install -r kasa-bridge/requirements.txt
sudo cp kasa-bridge/kasa-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kasa-bridge
```

Endpoints: `GET /plugs` (state plus schedules), `POST /plugs/<id>/on|off`,
`GET|POST|DELETE /plugs/<id>/schedule`. Schedules are written into each plug's
own scheduler, so they keep working when the Pi is off.

## 4. discord-bot

1. In the [Discord Developer Portal](https://discord.com/developers/applications):
   **New Application → Bot → Reset Token**, and copy the token.
2. **OAuth2 → URL Generator**: scopes `bot` and `applications.commands`.
   Open the generated URL and add the bot to your server.
3. On the Pi:

```bash
printf '%s' 'PASTE_TOKEN_HERE' > ~/smart-home/.discord_bot_token
chmod 600 ~/smart-home/.discord_bot_token
mkdir -p ~/smart-home/discord-bot
cp discord-bot/lights_bot.py ~/smart-home/discord-bot/
python3 -m venv ~/smart-home/discord-bot/venv
~/smart-home/discord-bot/venv/bin/pip install -r discord-bot/requirements.txt
sudo cp discord-bot/discord-lights-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now discord-lights-bot
```

Commands: `/lights on|off|brightness|color|set|schedule|unschedule|status`
(all lights or one) and `/kasa on|off|schedule|unschedule|status`. The bot
syncs its commands to every server it's in when it starts, so they show up
right away.

## 5. cdp-watchdog

On the tested bridgething version, a service on the Car Thing
(`kiosk-cdp-proxy`) exposes Chromium's remote-debugging protocol on port
9222 to anyone who can reach the Car Thing, with no password. Through it,
someone could read the page, including the secrets in `index.html`. It can be
stopped, but the Car Thing's root filesystem is read-only, so it can't be
disabled and comes back after every reboot. This timer checks every 5
minutes and stops it again.

```bash
cp cdp-watchdog/close_cdp_proxy.sh ~/smart-home/
chmod +x ~/smart-home/close_cdp_proxy.sh
sudo cp cdp-watchdog/close-cdp-proxy.service cdp-watchdog/close-cdp-proxy.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now close-cdp-proxy.timer
```

Check whether your firmware version still has this service first:
`ssh root@10.42.1.250 "systemctl status kiosk-cdp-proxy"`.

## Security notes

- **Car Thing SSH.** On the tested bridgething version, `root@10.42.1.250`
  accepted SSH with no authentication at all. That's what makes the screen
  dimming and the watchdog work without setting up keys, and it also means
  anyone who can reach that address controls the device. Keep the Car
  Thing's USB subnet off any wider network (don't route it onto your Wi-Fi or
  a VPN you share).
- **Bridges listen on all interfaces** (`0.0.0.0`) so the Car Thing can reach
  them. The shared secret is what protects them. Since that secret is also
  in the webapp's page source, anyone who can read the page can control your
  lights and plugs.
- Use a fresh random secret here. Don't reuse it for anything else.

## Credits

- [pywizlight](https://github.com/sbidy/pywizlight) (MIT)
- [python-kasa](https://github.com/python-kasa/python-kasa) (GPL-3.0-or-later)
- [discord.py](https://github.com/Rapptz/discord.py) (MIT) and
  [aiohttp](https://github.com/aio-libs/aiohttp) (Apache-2.0 and MIT)

These are installed from PyPI by `requirements.txt`; none of their code is
copied into this repo. See [../CREDITS.md](../CREDITS.md).
