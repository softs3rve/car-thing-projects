# Car Thing Operational Reference

Exact commands and procedures for flashing, backing up, ADB, internet access, and
recovery. Pairs with [SKILL.md](SKILL.md) and the wiki
([../../wiki/carthing-wiki.md](../../carthing-wiki.md)). Community-derived —
verify against [carthing.wiki](https://carthing.wiki) before destructive steps.

---

## 0. Enter USB burn mode (do this first for any flashing)

- **Hold preset buttons 1 and 4, then plug in USB-C.** Keep holding for a few
  seconds.
- **Success = black screen** and the device enumerates as `1b8e:c003
  Amlogic, Inc.` (GX-CHIP).
- Verify on the host:
  - Linux/macOS: `lsusb | grep 1b8e` (macOS: `system_profiler SPUSBDataType | grep -i amlogic`)
  - superbird-tool: `python superbird_tool.py --find_device`

---

## 1. Flashing with Terbium (recommended)

Browser flasher at **[terbium.app](https://terbium.app)** — Chrome/Chromium/Edge.

Drivers:
```powershell
# Windows (admin PowerShell) — install WinUSB
irm https://driver.terbium.app/get | iex
```
```bash
# Linux — install udev rules
curl -fsSL https://terbium.app/install-rules | bash
# macOS — nothing needed
```

Steps:
1. Download firmware from **[thingify.tools](https://thingify.tools)**
   (`x.x.x-thinglabs.zip`) and **extract it**.
2. Open **terbium.app**; enter burn mode (buttons 1+4 while plugging in).
3. Select **GX-CHIP** at the prompt; after reconnect, select the **Amlogic, Inc.**
   device again.
4. **Restore Local Folder** → pick the extracted folder → **Select** to flash.
5. Trouble? Press **F12** for logs.

---

## 2. superbird-tool (backups, restores, advanced)

Install:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install git+https://github.com/superna9999/pyamlboot
# macOS: brew install libusb   (Apple Silicon may need pyusb from master)
# Windows: use Zadig to bind WinUSB/libusb to the GX-CHIP device (fiddly)
git clone https://github.com/ThingLabsOSS/superbird-tool && cd superbird-tool
```

Discovery:
```bash
python superbird_tool.py --find_device
```

**Back up everything before your first flash** (slow, ~110 min — expected):
```bash
python superbird_tool.py --dump_device ./carthing-backup
# single partition:
python superbird_tool.py --dump_partition bootloader ./bootloader.bin
```

Restore:
```bash
python superbird_tool.py --restore_device ./carthing-backup      # ~11 min
python superbird_tool.py --restore_partition bootloader ./bootloader.bin
```

Boot a temporary ADB kernel (no permanent flash):
```bash
python superbird_tool.py --boot_adb_kernel A     # or B
```

Burn-mode / boot config:
```bash
python superbird_tool.py --enable_burn_mode          # burn mode every boot
python superbird_tool.py --enable_burn_mode_button   # hold button 4 at boot
python superbird_tool.py --disable_avb2 A            # lock to one slot
python superbird_tool.py --disable_charger_check
```

u-boot environment:
```bash
python superbird_tool.py --get_env env.txt
python superbird_tool.py --send_env env.txt
python superbird_tool.py --restore_stock_env
```

Stability flags on timeouts (and power-cycle between attempts):
```bash
python superbird_tool.py --restore_device ./backup --slow_burn
python superbird_tool.py --restore_device ./backup --slower_burn
```

---

## 3. DeskThing (custom OS on top)

- Install the **server** from **deskthing.app/releases** (don't clone `main`).
  Needs Node.js 25+ if building from source.
- In the app: **Clients** tab → **refresh ADB** → **Settings** → enable
  **Auto Detect ADB**, **Use Global ADB**, **Auto Config**.
- The device runs a Chromium client that talks to the desktop server over ADB/IPC.

Alternative OSes: **Nocturne** (usenocturne.com), **LlizardOS** (llizard.com).

---

## 4. ADB cheatsheet

```bash
adb devices                          # confirm the device is seen
adb shell                            # shell on the device
adb shell mount -o remount,rw /      # make rootfs writable
adb push local /path/on/device       # copy to device
adb pull /path/on/device local       # copy from device
adb shell date -s "`date +'%Y-%m-%d %H:%M'`"   # set the clock
```

---

## 5. Internet access

**Pick by goal:** DeskThing apps → no device internet needed (server tethers over
ADB). Real system-wide internet while tethered → **g_ether + NAT** (below).
Standalone/in-car → **ESP32-S3 dongle**. Browser-only quick hack → SOCKS proxy.

### RECOMMENDED — g_ether USB Ethernet + host NAT (real, system-wide)
Device = `172.16.42.2/24` (usb0), host = `172.16.42.1/24`. Use a **Linux/Pi host**
(macOS CDC-ethernet gadget support is poor). SSH: `ssh root@172.16.42.2` (pw `buildroot`).

On the host (Pi/Linux):
```bash
# Optional stable iface name (Linux g_ether gadget = 0525:a4a2)
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
On the Car Thing (`adb shell` or ssh):
```bash
ip addr add 172.16.42.2/24 dev usb0    # if firmware didn't already
ip link set usb0 up
ip route add default via 172.16.42.1
echo 'nameserver 1.1.1.1' > /etc/resolv.conf   # DNS
```

### Standalone — ESP32-S3 USB-NCM dongle
An ESP32-S3 presents as a **USB-NCM adapter** bridging Wi-Fi to the device's USB
(Car Thing acts as USB host). See the `esp32-wifi-ncm` dir in
[err4o4/spotify-car-thing-reverse-engineering](https://github.com/err4o4/spotify-car-thing-reverse-engineering).

### Legacy — SOCKS proxy + adb reverse (Chromium only)
```bash
adb reverse tcp:1080 tcp:1080     # host runs a Dante SOCKS proxy on :1080
```
Launch Chromium with `--proxy-server="socks5://127.0.0.1:1080"` (persist in
`/etc/supervisord.conf`). Set clock + `mount -o remount,rw /` first. Source:
[claudiuscoenen.de](https://claudiuscoenen.de/spotify-carthing-internet-access).
Only proxies apps you configure — superseded by g_ether for anything system-wide.

---

## 6. Recovery / unbrick

The Amlogic ROM burn mode is **un-brickable** — this is the safety net.

1. Re-enter burn mode (buttons **1 + 4** while plugging in).
2. Reflash a known-good firmware with **Terbium**, or restore your dump:
   ```bash
   python superbird_tool.py --restore_device ./carthing-backup
   ```
3. Bad bootloader env → `python superbird_tool.py --restore_stock_env`.

---

## 7. Partition names (AVB2 A/B)

`bootloader`, `fip_a`, `fip_b`, `env`, `logo`, `recovery`, `misc`, `boot_a`,
`boot_b`, `system_a`, `system_b`, `cache`, `settings`, `data` — eMMC at
`/dev/mmcblk2`, rootfs ext4 (Buildroot).
