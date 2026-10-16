# Car Thing webapp

One page with four views that runs full-screen on a Spotify Car Thing
running [bridgething](https://bridgething.com) firmware (800×480 screen):

| Button | View | Needs |
|---|---|---|
| 1 | **Clock** with weather | Internet (weather comes from [Open-Meteo](https://open-meteo.com), no API key) |
| 2 | **Light**: WiZ bulbs, color and brightness | `wiz-bridge` on the Pi |
| 3 | **Kasa**: smart plugs on/off and schedules | `kasa-bridge` on the Pi |
| 4 | **Parking**: [ASP Ticket Preventer 3000](https://github.com/softs3rve/ticket-preventer-3000) (NYC) | Your Ticket Preventer Worker |

Turning the dial adjusts the WiZ lights from any view. The screen dims when
idle (the dimming is done by `wiz-bridge` over SSH, because the Car Thing
can't host a service of its own). In the hour before a street-cleaning
window, the page switches itself to the Parking view.

All four views live in one page and switch by showing and hiding sections,
so changing views is instant. (They used to be four separate bridgething
webapps; each switch was a full page reload that took around 5 seconds.)

## Files

| File | What it is |
|---|---|
| `index.html` | The whole app: markup, CSS, and plain JavaScript, no build step |
| `manifest.json` | bridgething webapp manifest. `id` must be a UUID and must match the install directory name |
| `icon.svg` | Launcher icon |
| `uuid-shim.js` | Tiny stand-in for the npm `uuid` package (only the three functions the bridgething SDK uses) |
| `fetch-vendor.sh` | Downloads the third-party files below |

`vendor/` and `fonts/` are not in this repo; `fetch-vendor.sh` downloads them
from npm with their license files:

- `@bridgething/client` and `@bridgething/lib` (MIT), the bridgething SDK
- `@msgpack/msgpack` (ISC) and `pako` (MIT and Zlib), SDK dependencies
- Arimo Bold and Source Code Pro (SIL Open Font License), via Fontsource

## Setup

### 1. Fill in your values

Open `index.html` and search for `REPLACE_WITH_`:

| Constant | Set it to |
|---|---|
| `BRIDGE_SECRET` | The same random string as `~/smart-home/.bridge_secret` on the Pi (see [../pi-services](../pi-services)) |
| `PARKING_WORKER_BASE` | Your Ticket Preventer Worker URL, no trailing slash |
| `PARKING_KEY` | Your Ticket Preventer shared secret |
| `latitude=` / `longitude=` in the Open-Meteo URL | Your location for weather, to 2 or 3 decimal places |

The addresses `10.42.1.253` (the Pi) and `10.42.1.250` (the Car Thing) are
what bridgething's USB network link assigns by default; leave them unless
yours differ.

**These values are visible to anyone who can read the page source** (it's
client-side JavaScript in a kiosk browser). Don't reuse them anywhere else.

### 2. Fetch the third-party files

Needs Node.js:

```bash
sh car-thing-webapp/fetch-vendor.sh
```

### 3. Give the app its own id (optional)

`manifest.json` ships with a fixed UUID. To make your own: `uuidgen | tr
A-Z a-z`, then paste it into `manifest.json`'s `id`.

### 4. Copy it onto the Car Thing

bridgething loads side-loaded webapps from `/var/bridgething/webapps/<id>/`,
where `<id>` is the manifest `id` without dashes (that's how the directories
were named on the tested device). The Car Thing has no `rsync`, so use `scp`
from a machine that can reach it (the Pi, in this repo's setup):

```bash
ID=62a82a066cfe42f594147d7783261227   # manifest id, dashes removed
ssh root@10.42.1.250 "mkdir -p /var/bridgething/webapps/$ID"
scp -r car-thing-webapp/. root@10.42.1.250:/var/bridgething/webapps/$ID/
ssh root@10.42.1.250 "systemctl restart bridgething.service && systemctl restart chromium-kiosk.service"
```

Copying from a Mac can bring macOS `._*` files along. Remove them (BusyBox
`find` has no `-delete`):

```bash
ssh root@10.42.1.250 "find /var/bridgething/webapps/$ID -name '._*' -exec rm {} \;"
```

Open it from bridgething's launcher. To remove a webapp, delete its
directory and restart the two services.

## Tested with

- bridgething firmware on a Car Thing connected to a Raspberry Pi 3 B+ over
  USB, with WiZ bulbs and Kasa plugs on the same network as the Pi.
- On the device, with an older bridgething SDK (`@bridgething/lib` 0.8.0)
  copied from a working webapp. `fetch-vendor.sh` pins the current npm
  versions (client and lib 0.12.1). The page only constructs the SDK client,
  so the version change should be harmless, but that combination hasn't been
  run on a device yet.
- Not tested without the Pi bridges. If you only want the Parking view,
  expect the Light and Kasa views to show errors and idle dimming not to
  work.

## Hardware notes

- **Avoid looping background video.** An earlier version played an ambient
  video behind the clock. The Car Thing's hardware decoder kept a kernel
  thread busy (load average about 2.5 on an idle CPU) and cost about 50 MB of
  its 512 MB of RAM. The current page uses a plain black background.
- **Physical buttons** arrive as keyboard events: presets 1 to 4 as `"1"` to
  `"4"`, dial press as `Enter`, dial turns as wheel events. The back button
  never reaches the page; bridgething intercepts it.

## Credits

- [bridgething](https://github.com/JoeyEamigh/bridgething) (MIT): firmware,
  daemon, and the `@bridgething/client` SDK this page uses.
- [Open-Meteo](https://open-meteo.com): weather data (CC BY 4.0).
- [@msgpack/msgpack](https://github.com/msgpack/msgpack-javascript) (ISC),
  [pako](https://github.com/nodeca/pako) (MIT and Zlib).
- [Arimo](https://github.com/googlefonts/Arimo) and [Source Code
  Pro](https://github.com/adobe-fonts/source-code-pro) (SIL Open Font
  License 1.1), via [Fontsource](https://fontsource.org).

See [../CREDITS.md](../CREDITS.md) for the whole repo.
