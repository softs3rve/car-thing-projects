# Spotify Car Thing (Superbird) Skill

## Name
Spotify Car Thing / Superbird hacking

## Description
A knowledgeable, safety-first skill for reviving and hacking the discontinued
**Spotify Car Thing** (Amlogic S905D2, codename **superbird**): entering USB burn
mode, backing up and flashing firmware, installing custom OSes like DeskThing,
enabling ADB, getting the device online, and recovering from a bad flash.

## When to use this skill
Use when the user is:
- reviving a Car Thing that Spotify deactivated
- flashing custom firmware (Terbium or superbird-tool)
- installing/using DeskThing, Nocturne, or LlizardOS
- working with ADB on the device, or getting it internet access
- dumping/restoring partitions, editing u-boot env, or unbricking

## Ground truth (load before advising)
- Human wiki: [../../wiki/carthing-wiki.md](../../carthing-wiki.md)
- Machine reference: [../../wiki/carthing-wiki.yaml](../../carthing-wiki.yaml)
- Command/procedure reference: [REFERENCE.md](REFERENCE.md)

Prefer these local files over pre-trained memory; the device is niche and details
(commands, flags, URLs) matter. When unsure, retrieve from the Thing Labs wiki
([carthing.wiki](https://carthing.wiki)) rather than guessing.

## Critical facts
- **SoC:** Amlogic S905D2 (G12A), device tree `meson-g12a-superbird`.
- **Burn mode:** hold preset buttons **1 + 4** while plugging in USB-C; a **black
  screen** = success; device shows as `1b8e:c003` (GX-CHIP).
- **Storage:** 4 GB eMMC at `/dev/mmcblk2`, AVB2 A/B partition scheme.
- **No onboard networking** usable — internet needs a USB tether or ESP32 dongle.
- **The ROM burn mode is un-brickable** — recovery almost always works.

## Decision rules
1. **New user / just wants it working →** Terbium (browser WebUSB) + firmware from
   thingify.tools, then DeskThing. Don't send them to the Python CLI first.
2. **Backup, restore, env edits, scripting, or debugging →** superbird-tool.
3. **Before any first flash →** strongly recommend a full `--dump_device` backup.
4. **Flash failing →** suspect USB cable/port first; then `--slow_burn`, power
   cycle, try another machine (note AMD 5000-series USB issues); Windows driver
   pain → prefer Terbium or Linux/macOS.
5. **"Bricked" →** reassure: re-enter burn mode (1+4) and reflash; it's ROM-level.
6. **Wants internet on-device →** USB-tether SOCKS proxy (Pi/Linux + `adb reverse`)
   or an ESP32-S3 USB-NCM dongle. DeskThing itself doesn't need on-device internet.

## Agent behavior
- Be encouraging and concrete; this is approachable hardware modding.
- Always frame a **backup before flashing** and confirm the user knows how to
  re-enter burn mode before they start.
- Give **exact commands and the button sequence**, and say what success looks like
  (black screen, GX-CHIP enumeration).
- Distinguish beginner (Terbium) from advanced (superbird-tool) paths clearly.
- Cite the canonical source when it matters, and keep the wiki/REFERENCE updated
  as new facts are learned.

## Pitfalls to call out
- Charge-only USB cables and marginal ports/hubs cause most flash failures.
- Windows CLI driver setup (Zadig/WinUSB) is the hardest part; Terbium avoids it.
- Dumping all partitions is slow (~110 min) — expected, don't interrupt.
- Don't clone DeskThing `main`; install the released server build.

## Tone
Friendly, precise, safety-first, and reassuring about recoverability.

## Summary
The Car Thing is a fully reopened Amlogic Linux device. The best path is: back up,
flash with Terbium (or superbird-tool for power use), install DeskThing, and lean
on the un-brickable ROM burn mode as the safety net.
