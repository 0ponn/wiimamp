#!/usr/bin/env bash
# Install the launcher + icon so "WiiM Amp" appears in the app grid and can be
# pinned to the dock. The desktop file is named to match the app's ID
# (net.local.WiimAmp) so GNOME associates the running window with it.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
data="${XDG_DATA_HOME:-$HOME/.local/share}"
apps="$data/applications"
icons="$data/icons/hicolor/scalable/apps"
mkdir -p "$apps" "$icons"

install -m644 "$repo/data/net.local.WiimAmp.svg" "$icons/net.local.WiimAmp.svg"

# Bake this checkout's path into Exec's working directory (Path=).
sed "s|^Path=.*|Path=$repo|" "$repo/data/net.local.WiimAmp.desktop" \
    > "$apps/net.local.WiimAmp.desktop"
chmod 644 "$apps/net.local.WiimAmp.desktop"

# Drop the old mismatched launcher if it's lying around.
rm -f "$apps/wiim-amp.desktop"

update-desktop-database "$apps" 2>/dev/null || true
gtk-update-icon-cache -f -t "$data/icons/hicolor" 2>/dev/null || true

echo "Installed. Find 'WiiM Amp' in the app grid (its icon should show)."
echo "Launch it, then right-click its dock icon -> 'Pin to Dash' to keep it on the toolbar."
