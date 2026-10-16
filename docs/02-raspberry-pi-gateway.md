# 2. Raspberry Pi gateway

The Car Thing has no usable Wi-Fi of its own. Here, a Raspberry Pi gives it
an internet connection over USB and runs the services in
[../pi-services](../pi-services). Tested with a **Raspberry Pi 3 Model B+**
(1 GB RAM) running Raspberry Pi OS.

```
Internet ── Wi-Fi/Ethernet ── Raspberry Pi ── USB ── Car Thing (bridgething)
                              10.42.1.253            10.42.1.250
                              NAT + pi-services      kiosk webapp
```

## 1. Power

Give the Car Thing its own power. In the original build, the Car Thing kept
resetting in a loop when it drew power from the Pi 3 B+'s USB port alone;
a separate, stronger power source fixed it. If the link keeps dropping,
check power before debugging software.

## 2. Plug the Car Thing into the Pi

Use one of the Pi's USB-A ports. With bridgething, the Car Thing shows up as
a **USB NCM** network device and runs its own DHCP server on the link:

- Pi side: interface `usb0`, gets `10.42.1.253` by DHCP automatically
- Car Thing side: `10.42.1.250`
- Subnet: `10.42.1.248/29`

Check with `ip addr show usb0`. If yours differ, use your addresses below
and in the webapp's `index.html`.

(Older Car Thing guides describe a different scheme, `172.16.42.x` with
`g_ether`. That isn't what bridgething uses.)

## 3. Share the Pi's internet with the Car Thing

Replace `wlan0` with `eth0` if the Pi is on Ethernet.

```bash
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -A POSTROUTING -s 10.42.1.248/29 -o wlan0 -j MASQUERADE
sudo iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A FORWARD -s 10.42.1.248/29 -j ACCEPT
```

To keep this after a reboot (standard Debian approach):

```bash
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-carthing-nat.conf
sudo apt install iptables-persistent   # offers to save the current rules
```

## 4. Give the Car Thing a default route

In the original build, the Pi side worked but the Car Thing had no default
route, so it couldn't reach the internet. Fix it at runtime:

```bash
ssh root@10.42.1.250 "ip route add default via 10.42.1.253 dev uncm0"
```

The persistent fix used there was a systemd-networkd drop-in on the Car
Thing, `/etc/systemd/network/11-usb-ncm.network.d/50-default-route.conf`:

```ini
[Route]
Gateway=10.42.1.253
```

Test from the Car Thing: `ssh root@10.42.1.250 "ping -c 3 1.1.1.1"`.

## 5. Install the services and the webapp

- [../pi-services](../pi-services): lights, plugs, Discord bot, watchdog
- [../car-thing-webapp](../car-thing-webapp): the on-screen app

## Notes

- **RAM.** 1 GB is tight on a Pi 3 B+. The services here are small Python
  processes; check `free -h` before adding anything heavy.
- **Remote access.** You'll want SSH to the Pi from your computer. To reach
  the Car Thing from elsewhere, one option is a VPN like Tailscale on the Pi
  advertising `10.42.1.0/24` as a subnet route. Read the security notes in
  [../pi-services/README.md](../pi-services/README.md#security-notes) first:
  on the tested firmware the Car Thing accepts root SSH with no password, so
  only do this on a network that's yours alone.
