# Credits

These projects are made by **[softserve](https://github.com/softs3rve)**.
They build on other people's work. Thank you to all of them.

The ASP Ticket Preventer 3000 lives in its own repo,
[ticket-preventer-3000](https://github.com/softs3rve/ticket-preventer-3000),
with its own credits (NYC Open Data, resvg, the Carlito font, Cloudflare).

## Downloaded at setup time

Nothing from other projects is committed here. Scripts and package files fetch them from their
publishers, and `car-thing-webapp/fetch-vendor.sh` copies each license file
next to the files it downloads.

| What | Used by | Source | License |
|---|---|---|---|
| `@bridgething/client`, `@bridgething/lib` | Car Thing webapp | [bridgething](https://github.com/JoeyEamigh/bridgething) | MIT |
| `@msgpack/msgpack` | Car Thing webapp | [msgpack-javascript](https://github.com/msgpack/msgpack-javascript) | ISC |
| `pako` | Car Thing webapp | [nodeca/pako](https://github.com/nodeca/pako) | MIT and Zlib |
| Arimo | Car Thing webapp | [googlefonts/Arimo](https://github.com/googlefonts/Arimo), via [Fontsource](https://fontsource.org) | SIL Open Font License 1.1 |
| Source Code Pro | Car Thing webapp | [adobe-fonts/source-code-pro](https://github.com/adobe-fonts/source-code-pro), via Fontsource | SIL Open Font License 1.1 |
| `pywizlight` | wiz-bridge | [sbidy/pywizlight](https://github.com/sbidy/pywizlight) | MIT |
| `python-kasa` | kasa-bridge | [python-kasa/python-kasa](https://github.com/python-kasa/python-kasa) | GPL-3.0-or-later |
| `discord.py` | discord-bot | [Rapptz/discord.py](https://github.com/Rapptz/discord.py) | MIT |
| `aiohttp` | discord-bot | [aio-libs/aiohttp](https://github.com/aio-libs/aiohttp) | Apache-2.0 and MIT |

## Data and services

- **[Open-Meteo](https://open-meteo.com):** weather on the Car Thing clock
  (data under CC BY 4.0).
- **Discord** webhooks and bot API.

## Firmware, tools, and research

These made the Car Thing usable again. Their code isn't copied here, but this
project depends on their work and their documentation.

- **[bridgething](https://bridgething.com)**
  ([source](https://github.com/JoeyEamigh/bridgething), MIT): the firmware,
  daemon, kiosk runtime, and SDK the webapp runs on. The webapp's knowledge
  of the client protocol came from reading the source bundled with
  bridgething's own launcher.
- **[Thing Labs](https://github.com/ThingLabsOSS)**:
  [superbird-tool](https://github.com/ThingLabsOSS/superbird-tool) (backup
  and restore), [Terbium](https://terbium.app) (browser flasher),
  [thingify.tools](https://thingify.tools), and the
  [carthing.wiki](https://carthing.wiki).
- **[pyamlboot](https://github.com/superna9999/pyamlboot)** (Apache-2.0):
  open implementation of Amlogic's USB boot protocol.
- **[err4o4/spotify-car-thing-reverse-engineering](https://github.com/err4o4/spotify-car-thing-reverse-engineering)**:
  early reverse-engineering of the device.
- **[DeskThing](https://github.com/ItsRiprod/DeskThing)**,
  **[Nocturne](https://usenocturne.com)**, and **LlizardOS**: other Car Thing
  operating systems described in the knowledge base.
- **[Claudius Coenen's Car Thing internet-access
  walkthrough](https://claudiuscoenen.de/spotify-carthing-internet-access)**
  and the **[iFixit custom-firmware
  guide](https://www.ifixit.com/Guide/How+to+Install+Custom+Firmware+onto+Car+Thing/178814)**,
  sources for the knowledge base.

## Trademarks

Spotify and Car Thing are trademarks of Spotify AB. This project is not
affiliated with or endorsed by Spotify, bridgething, Thing Labs, WiZ,
TP-Link, or Discord.
