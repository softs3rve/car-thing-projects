# Car Thing Projects

By **[softserve](https://github.com/softs3rve)**.

A discontinued **Spotify Car Thing**, revived with
[bridgething](https://bridgething.com) firmware and plugged into a
**Raspberry Pi**, running as a small dashboard: a clock with weather, WiZ
smart-bulb controls, Kasa smart-plug controls, and the **ASP Ticket
Preventer 3000**, a reminder for New York City's alternate side parking
rules.

```
                     ┌──────────────────────────── Cloudflare Worker ───────────┐
iPhone Shortcut ────▶│ ASP Ticket Preventer 3000 (NYC)                          │──▶ Discord alerts
 (on parking)        │ NYC Open Data street + sign lookup, KV, cron             │
                     └─────────────▲────────────────────────────────────────────┘
                                   │ GET /parking/status
Internet ── Raspberry Pi ── USB ── Car Thing (bridgething)
            wiz-bridge             webapp: 1 Clock · 2 Light · 3 Kasa · 4 Parking
            kasa-bridge
            discord-bot ─────────▶ Discord /lights, /kasa
```

## What's here

| Folder | What it is |
|---|---|
| [ticket-preventer-3000](https://github.com/softs3rve/ticket-preventer-3000) (separate repo) | **ASP Ticket Preventer 3000.** NYC street-cleaning reminders: an iPhone Shortcut reports where you parked, a Cloudflare Worker reads the posted ASP signs for that block, and Discord (and optionally the Car Thing) tells you when to move. Works on its own, no Car Thing needed. |
| [`car-thing-webapp/`](car-thing-webapp) | The app on the Car Thing's screen: four views on the four preset buttons, dial controls the lights. |
| [`pi-services/`](pi-services) | Python services on the Pi: WiZ bulb bridge, Kasa plug bridge, Discord bot, and a security watchdog. |
| [`docs/`](docs) | Setup guides: [flash the Car Thing](docs/01-flash-the-car-thing.md), [Raspberry Pi gateway](docs/02-raspberry-pi-gateway.md). |
| [`knowledge-base/`](knowledge-base) | General Car Thing reference (hardware, flashing, recovery) and an AI-assistant skill. |

## Where to start

- **Only want the NYC parking reminder?** Go straight to
  its own repo, [ticket-preventer-3000](https://github.com/softs3rve/ticket-preventer-3000). You need a free
  Cloudflare account and an iPhone (or anything that can send a web request).
- **Building the whole thing:**
  1. [Flash the Car Thing](docs/01-flash-the-car-thing.md)
  2. [Set up the Pi gateway](docs/02-raspberry-pi-gateway.md)
  3. [Install the Pi services](pi-services)
  4. [Deploy the Ticket Preventer](https://github.com/softs3rve/ticket-preventer-3000) (if you park in NYC)
  5. [Install the webapp](car-thing-webapp)

## Your values go in placeholders

Nothing personal is committed: no addresses, coordinates, device IPs, or
secrets. Every value you need to supply is a placeholder. Find them all with:

```bash
grep -rn "REPLACE_WITH_" .
```

The device IPs in the code (`192.168.1.XXX`) and MAC addresses
(`aabbccddeeff`) are placeholders too. `10.42.1.250` and `10.42.1.253` are
not: they're the addresses bridgething's USB link assigns by default.

Keep real secrets out of git. `.gitignore` already excludes `.bridge_secret` and `.discord_bot_token`, but the webapp's
`index.html` holds secrets once you fill it in, so don't commit your filled-in
copy to a public repo.

## Status

A personal project, shared as-is. It runs on one setup: a Car Thing on
bridgething, a Raspberry Pi 3 B+, WiZ bulbs, Kasa plugs, and an iPhone with
CarPlay. Expect to adapt it to yours. Each folder's README says what was and
wasn't tested.

## Credits

Made by **softserve**. Built on bridgething, Thing Labs' tools, NYC Open Data, and a number of open
source libraries and fonts. See [CREDITS.md](CREDITS.md).

Not affiliated with Spotify, bridgething, Thing Labs, or the City of New York.

## License

MIT, copyright softserve. See [LICENSE](LICENSE). Third-party code, fonts,
and data keep their own licenses; see [CREDITS.md](CREDITS.md).
