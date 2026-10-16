#!/bin/sh
# The Car Thing's root filesystem is an immutable squashfs (A/B slot boot,
# not just "mounted ro for safety" - there is no writable /etc at all), so
# kiosk-cdp-proxy.service (unauthenticated Chromium DevTools on 0.0.0.0:9222
# - found in a 2026-08-09 security audit) can be stopped live but
# cannot be durably disabled from the device itself: its
# /etc/systemd/system/multi-user.target.wants/ symlink survives any
# `systemctl stop`, so a reboot brings it straight back. This timer
# re-closes it within a few minutes of any reboot instead of leaving it
# open indefinitely until someone notices.
if curl -s -m 3 http://10.42.1.250:9222/json/version > /dev/null 2>&1; then
    echo "$(date -u +%FT%TZ) kiosk-cdp-proxy reachable on 9222, stopping it"
    ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new root@10.42.1.250 \
        "systemctl stop kiosk-cdp-proxy.service" 2>&1
fi
