#!/usr/bin/env bash
# Make the WiiM Amp available as a system audio output via PipeWire RAOP (AirPlay).
#
# Most modern distros (Fedora included) enable RAOP discovery by default, so the
# amp appears automatically and this script does nothing but confirm it. It is
# idempotent and deliberately NEVER loads a second discovery instance — doing so
# makes PipeWire create duplicate IPv4 + IPv6 sinks for the same device.
set -euo pipefail

have_amp()      { pactl list short sinks   2>/dev/null | grep -qi wiim; }
have_discover() { pactl list modules short 2>/dev/null | grep -qi raop-discover; }

if have_amp; then
    echo "WiiM Amp is already a selectable output."
    echo "Pick \"WiiM Amp-FCB2\" under Settings -> Sound -> Output."
    exit 0
fi

if have_discover; then
    echo "AirPlay/RAOP discovery is already enabled, but the amp isn't visible yet."
    echo "Make sure it's powered on and on this network, then check Sound settings."
    exit 0
fi

# Discovery is off: enable it by activating the distro's stock RAOP config.
avail="/usr/share/pipewire/pipewire.conf.avail/50-raop.conf"
dest="${XDG_CONFIG_HOME:-$HOME/.config}/pipewire/pipewire.conf.d"
if [ ! -f "$avail" ]; then
    echo "PipeWire RAOP config not found ($avail)." >&2
    echo "Install your distro's PipeWire AirPlay/RAOP support, then re-run." >&2
    exit 1
fi
mkdir -p "$dest"
ln -sf "$avail" "$dest/50-raop.conf"
systemctl --user restart pipewire pipewire-pulse
echo "Enabled AirPlay/RAOP discovery; waiting for the amp..."
for _ in $(seq 1 10); do
    sleep 1
    if have_amp; then
        echo "Done. Select \"WiiM Amp-FCB2\" under Settings -> Sound -> Output."
        exit 0
    fi
done
echo "Discovery enabled, but no WiiM sink appeared. Is the amp on and on this network?" >&2
exit 1
