# Spotify Car Thing ("Superbird") Hacking Wiki

A practical, human-readable knowledge base for reviving and hacking the
discontinued **Spotify Car Thing** (codename **superbird**). Companion to the
machine-readable [carthing-wiki.yaml](carthing-wiki.yaml) and the agent skill in
[../skills/spotify-carthing/SKILL.md](skills/spotify-carthing/SKILL.md).

> **Update this wiki whenever knowledge changes:** bump `Last updated` and add
> a dated note to the Changelog.

Last updated: 2026-09-29

> Everything here is community-reverse-engineered. It's legal to modify hardware
> you own — this is e-waste rescue, not piracy — but you flash at your own risk.
> The good news: the Amlogic ROM burn mode makes the device **very hard to truly
> brick** (see [Recovery](#recovery--unbricking)).

---

## What the Car Thing is

A small dashboard companion Spotify sold (2022–2023), then **remotely bricked in
December 2024**. Under the hood it's a capable little Amlogic Linux computer, and
the community (chiefly **Thing Labs**) has fully reopened it.

### Hardware at a glance

| Part | Detail |
|---|---|
| SoC | **Amlogic S905D2** (G12A family); device tree `meson-g12a-superbird` |
| RAM | 512 MB DDR |
| Storage | 4 GB **eMMC** at `/dev/mmcblk2` |
| Display | 3.4" LCD touchscreen, 800×480 |
| Inputs | 4 preset buttons (1–4), rotary dial (turn + press), back button |
| I/O | **USB-C only** — the single path for power, flashing, and ADB |
| Networking | No usable onboard Wi-Fi/BT; internet needs a USB tether or add-on dongle |

In **burn mode** the SoC enumerates over USB as `1b8e:c003 Amlogic, Inc.`
("GX-CHIP"). That identity is your signal the device is ready to be imaged.

---

## The two things that unlock everything

### 1. USB burn mode (buttons 1 + 4)

**Hold preset buttons 1 and 4 while plugging in the USB-C cable.** The screen
stays **black** — that black screen is success, not a failure. The device is now
in Amlogic's ROM-level USB download mode, ready for a flasher to talk to it.

This ROM mode lives in silicon and can almost always be re-entered, which is why
the device is so hard to permanently brick.

### 2. ADB (the shell into the device)

Custom firmwares expose **ADB over USB**, and `superbird-tool --boot_adb_kernel`
can boot a temporary ADB-capable kernel without flashing anything. Once ADB is
up you get a root-ish Linux shell: `adb shell`, `adb push/pull`, `adb reverse`,
and `mount -o remount,rw /` to make the rootfs writable.

---

## Choosing your path

There are two flashing toolchains. Most people should start with **Terbium**.

### Terbium — the easy path (recommended)

[terbium.app](https://terbium.app) is a **browser** flasher (WebUSB) that
reimplements Amlogic's USB Boot protocol — no CLI, no Python. Use Chrome,
Chromium, or Edge (Safari/Firefox lack the needed WebUSB + File System Access
APIs).

**Flash flow:**
1. Download the latest firmware from **[thingify.tools](https://thingify.tools)**
   (an `x.x.x-thinglabs.zip`) and **extract it**.
2. Open **terbium.app**.
3. Enter burn mode (buttons **1 + 4** while plugging in).
4. Pick the **GX-CHIP** device in the browser prompt; after it reconnects, pick
   the **"Amlogic, Inc."** device again.
5. Click **Restore Local Folder** → choose the extracted firmware folder → grant
   access → **Select** to flash.

**Drivers:** Windows needs WinUSB — run in admin PowerShell:
`irm https://driver.terbium.app/get | iex`. Linux needs udev rules:
`curl -fsSL https://terbium.app/install-rules | bash`. macOS needs nothing.
Press **F12** in the browser for flashing logs if something stalls.

### superbird-tool — the power path

[ThingLabsOSS/superbird-tool](https://github.com/ThingLabsOSS/superbird-tool) is
a cross-platform **Python CLI** built on `pyamlboot`. Use it for **backups,
restores, u-boot env edits, and scripting** — anything Terbium doesn't do.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install git+https://github.com/superna9999/pyamlboot
# macOS: brew install libusb first. Windows: use Zadig for WinUSB (fiddly).
```

Key commands (full list in
[../skills/spotify-carthing/REFERENCE.md](skills/spotify-carthing/REFERENCE.md)):

| Command | Does |
|---|---|
| `--find_device` | Detect the device and its current mode |
| `--dump_device OUT/` | **Back up all partitions** (slow: ~110 min) |
| `--restore_device IN/` | Flash all partitions back (~11 min) |
| `--boot_adb_kernel A` | Boot a temporary ADB kernel (no permanent change) |
| `--enable_burn_mode_button` | Let button 4 trigger burn mode at boot |
| `--get_env` / `--send_env` / `--restore_stock_env` | Read/write/reset u-boot env |

> **Do a full `--dump_device` before your first flash.** It's slow (~110 min) but
> it's your personal, guaranteed restore image.

---

## What to install: the custom OSes

Flashing lays down a base firmware; the experience on top is a custom OS:

- **[DeskThing](https://deskthing.app)** — the flagship. A **desktop server app**
  (Node.js 25+) pairs with a **Chromium client on the device** over ADB/IPC, and
  streams community apps: Spotify playback + album art, local media, Discord,
  weather, and more. Install the server from **deskthing.app/releases** (don't
  clone `main`), then in the app: **Clients → refresh ADB → Settings →** enable
  **Auto Detect ADB**, **Use Global ADB**, **Auto Config**.
- **[Nocturne](https://usenocturne.com)** — an alternative custom OS.
- **[LlizardOS](https://llizard.com)** — another alternative OS.

Because DeskThing talks to a desktop app over ADB, it doesn't strictly need
general internet **on the device**. Standalone browsing does — see below.

---

## Getting the device online

The Car Thing has no usable onboard networking, so internet arrives over its USB
port. **Pick by goal — the most efficient option is often "none needed":**

| Your goal | Best method | Why |
|---|---|---|
| Run **DeskThing** apps (Spotify, weather…) | **No device internet** — DeskThing's desktop server fetches data and pushes it over the ADB/USB link | Fewest moving parts |
| Real **system-wide** internet while tethered | **g_ether USB Ethernet + host NAT** | One cable, all apps + DNS, not just a browser |
| **Standalone** / in-car, no host PC | **ESP32-S3 USB-NCM Wi-Fi dongle** | Self-contained; no computer nearby |
| Quick, browser-only | SOCKS proxy + `adb reverse` (legacy) | App-level only, more fiddly |

### Recommended: g_ether USB Ethernet + host NAT

The custom kernel's USB gadget can present a **real Ethernet interface** over USB.
The device comes up at **`172.16.42.2/24`**, the host at **`172.16.42.1/24`**, and
the host simply NATs its own uplink — giving the Car Thing genuine, system-wide
internet (DNS and all). Use a **Linux host / Raspberry Pi** (macOS's USB
CDC-Ethernet gadget support is poor). SSH in with `ssh root@172.16.42.2`
(password `buildroot`).

**On the host (Pi/Linux):**
```bash
# Optional: give the gadget iface a stable name (Linux g_ether = 0525:a4a2)
echo 'SUBSYSTEM=="net", ATTRS{idVendor}=="0525", ATTRS{idProduct}=="a4a2", NAME="usb_ether"' \
  | sudo tee /etc/udev/rules.d/99-usb-ether.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

sudo ip addr add 172.16.42.1/24 dev usb_ether
sudo ip link set usb_ether up

sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -A POSTROUTING -s 172.16.42.0/24 -j MASQUERADE
sudo iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A FORWARD -s 172.16.42.0/24 -j ACCEPT
```

**On the Car Thing** (`adb shell` or `ssh root@172.16.42.2`):
```bash
ip addr add 172.16.42.2/24 dev usb0     # if the firmware didn't already
ip link set usb0 up
ip route add default via 172.16.42.1
echo 'nameserver 1.1.1.1' > /etc/resolv.conf   # DNS — the piece the blog omits
```

### Standalone: ESP32-S3 USB-NCM Wi-Fi dongle

For an in-car/always-on build with **no host**, err4o4's `esp32-wifi-ncm` turns an
**ESP32-S3 into a USB-NCM network adapter** that bridges Wi-Fi to the Car Thing's
USB (the Car Thing acts as USB host). More build effort, but fully self-contained.

### Legacy: SOCKS proxy + `adb reverse`

The original 2023 method
([claudiuscoenen.de](https://claudiuscoenen.de/spotify-carthing-internet-access)):
a Pi runs a **Dante SOCKS proxy** on 1080, you bridge with
`adb reverse tcp:1080 tcp:1080`, and launch Chromium with
`--proxy-server="socks5://127.0.0.1:1080"`. It only proxies apps you configure
(Chromium), so it's superseded by g_ether for anything system-wide.

---

## Recovery / unbricking

The mental model: **the Amlogic ROM burn mode is un-brickable.** If a flash goes
wrong, you almost always just re-enter burn mode and try again.

1. **Re-enter burn mode** (buttons 1 + 4) and **reflash a known-good firmware**
   with Terbium.
2. **Restore your own dump**: `superbird-tool --restore_device your_dump/`.
3. **Fix a bad bootloader env**: `superbird-tool --restore_stock_env`.

---

## Pitfalls worth knowing before you start

- **USB cable/port matters a lot.** Flaky flashes are usually cable/port. Try a
  C-to-C cable and different ports/hubs.
- **AMD 5000-series USB controllers** have been reported to fail — use another
  machine or a powered hub.
- On timeouts, add **`--slow_burn`/`--slower_burn`** and **power-cycle** the
  device before retrying.
- **Windows is the hard platform** for the CLI (driver pain). Prefer **Terbium**,
  or use **Linux/macOS** for superbird-tool.
- **Dumping is slow (~110 min).** Expected — don't interrupt it.
- **Once it's running a kiosk webapp: a looping background `<video>` is
  expensive.** Measured on bridgething firmware (2026-09-29): with one
  800x480 ambient video playing, the CPU was 93% idle but the load average
  sat around 2.5, because the Amlogic decoder's `vdec_recycle` kernel thread
  stays in uninterruptible sleep (`D`), which counts toward load. Free RAM
  was ~14MB of 447MB, with ~122MB swapped. Removing the video: load ~0.9,
  available RAM 71MB → 121MB, swap 73MB. Rapidly re-creating video elements
  can also exhaust the decoder's buffer pool and freeze rendering
  (seen 2026-08-11). Prefer a static background on this device.

---

## Glossary

- **superbird** — Amlogic's codename for the Car Thing.
- **burn mode** — Amlogic USB ROM download/flash mode used for imaging.
- **GX-CHIP** — the device's USB identity while in burn mode (`1b8e:c003`).
- **FIP** — Firmware Image Package (ARM Trusted Firmware bootloader bundle); see
  `superbird-fip-tools`.
- **u-boot** — the bootloader; `superbird-uboot` is the mainline port.
- **AVB2** — Android Verified Boot 2.0 (A/B slotted verified boot).
- **Buildroot** — the embedded Linux userland on the device.
- **ADB** — Android Debug Bridge (USB shell/debugging).
- **pyamlboot** — open Python implementation of Amlogic's USB boot protocol.

---

## Sources & repositories

**Thing Labs (main hub):** [github.com/ThingLabsOSS](https://github.com/ThingLabsOSS) · wiki: [carthing.wiki](https://carthing.wiki)

| Repo | Purpose |
|---|---|
| [superbird-tool](https://github.com/ThingLabsOSS/superbird-tool) | Flash/dump/modify toolkit (Python/pyamlboot) |
| [superbird-webapp](https://github.com/ThingLabsOSS/superbird-webapp) | Reconstructed stock webapp source |
| [superbird-uboot](https://github.com/ThingLabsOSS/superbird-uboot) | Mainline u-boot port (S905D2/G12A) |
| [superbird-fip-tools](https://github.com/ThingLabsOSS/superbird-fip-tools) | Rebuild/flash signed FIP images |
| [wiki-astro](https://github.com/ThingLabsOSS/wiki-astro) / [wiki](https://github.com/ThingLabsOSS/wiki) | Wiki content |
| [firmware-updates](https://github.com/ThingLabsOSS/firmware-updates) | OTA firmware pulls |
| [peek-carthing](https://github.com/ThingLabsOSS/peek-carthing) | Hardware inventory / live MMIO state |

**Other:** [err4o4/spotify-car-thing-reverse-engineering](https://github.com/err4o4/spotify-car-thing-reverse-engineering) ·
[DeskThing](https://github.com/ItsRiprod/DeskThing) ·
[iFixit custom-firmware guide](https://www.ifixit.com/Guide/How+to+Install+Custom+Firmware+onto+Car+Thing/178814) ·
[Internet-access walkthrough](https://claudiuscoenen.de/spotify-carthing-internet-access) ·
[thingify.tools](https://thingify.tools) · [terbium.app](https://terbium.app)

---

## Changelog

- **2026-09-29:** Added a pitfall: a looping background `<video>` in a kiosk
  webapp keeps the hardware decoder thread in `D` state (load ~2.5 on an idle
  CPU) and costs ~50MB of the device's scarce RAM; measured before/after on
  bridgething. Mirrored into the YAML.
- **2026-08-01** — Expanded **internet access** into a goal-based decision map and
  added the recommended **g_ether USB-Ethernet + host NAT** build (device
  172.16.42.2 / host 172.16.42.1, `root`/`buildroot`, exact iptables + DNS),
  clarified DeskThing needs no device internet, and demoted the SOCKS proxy to a
  legacy/browser-only fallback. Also mirrored into the YAML and skill REFERENCE.
- **2026-08-01** — Initial wiki assembled from Thing Labs (superbird-tool,
  org repos, carthing.wiki), iFixit guide, err4o4 reverse-engineering, DeskThing,
  and the claudiuscoenen internet-access walkthrough.
