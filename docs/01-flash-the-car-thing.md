# 1. Flash the Car Thing with bridgething

The Spotify Car Thing was discontinued and remotely disabled by Spotify in
December 2024. Inside it's a small Amlogic Linux computer with a 800×480
touchscreen, four preset buttons, a dial, and a back button. Community
firmware brings it back.

This repo uses **[bridgething](https://bridgething.com)**: open firmware with
a Rust daemon and a kiosk browser that runs web apps. Follow bridgething's own
install page, which is the source of truth:
**<https://bridgething.com/install>**. The summary below is for orientation.

## Before you start: back up

Make a full backup of the device first. It's slow but it's your personal
restore image.

Using [superbird-tool](https://github.com/ThingLabsOSS/superbird-tool), with
the device in burn mode (next section):

```bash
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install git+https://github.com/pyusb/pyusb   # only on Apple Silicon Macs
python3 -m pip install git+https://github.com/superna9999/pyamlboot
git clone https://github.com/ThingLabsOSS/superbird-tool
cd superbird-tool
python3 superbird_tool.py --find_device
python3 superbird_tool.py --dump_device ../my-car-thing-backup/
```

On macOS, install libusb first (`brew install libusb`). superbird-tool's
README has the Linux and Windows steps. The dump takes
around 110 minutes; don't interrupt it. Keep the dump private and out of
any git repo (it's a full image of your device).

## Burn mode

Hold **preset buttons 1 and 4** while plugging in the USB-C cable. The screen
stays **black**: that's success. The device now shows up over USB as
`1b8e:c003` ("GX-CHIP"), ready to flash. This mode is in the chip's ROM, so
the device is very hard to brick: if a flash fails, re-enter burn mode and
try again.

## Flash bridgething

From bridgething's install page (stable channel):

- **In the browser:** open [Terbium](https://terbium.app) with bridgething's
  stable manifest preset (the link is on the install page). Needs a
  Chromium-based browser (Chrome, Edge) for WebUSB.
- **From the command line:** `cargo install flashthing-cli`. macOS needs
  libusb; Linux needs a udev rule.

Then pair bridgething's companion app (iOS, Android, or desktop), as the
install page describes.

## If it goes wrong

- Most flashing failures are the **cable or USB port**. Try another USB-C
  cable, another port, or another computer. Some AMD 5000-series USB
  controllers are reported to fail.
- Re-enter burn mode and reflash.
- Restore your dump: `python3 superbird_tool.py --restore_device ../my-car-thing-backup/`.
- bridgething [troubleshooting docs](https://bridgething.com/docs/troubleshooting)
  and the [Thing Labs wiki](https://carthing.wiki).

## Shell access

Once bridgething is running and connected over USB (see the next guide), the
device is reachable over SSH at `root@10.42.1.250`. Its root filesystem is
read-only; webapps go in `/var/bridgething/webapps/`, which is writable.

More background (hardware, other firmware options like DeskThing, recovery
details) is in [../knowledge-base/carthing-wiki.md](../knowledge-base/carthing-wiki.md).

Next: [02-raspberry-pi-gateway.md](02-raspberry-pi-gateway.md)
