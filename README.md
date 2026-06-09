# WiiM Amp — Linux control + audio routing

Use a WiiM Amp from a Linux PC (no official Linux app): route all PC audio to it
as a normal output device, and control its inputs/EQ/presets/transport from a
small GTK4 GUI. Zero Python dependencies beyond PyGObject/GTK (already on GNOME).

## 1. Audio routing — use the amp as PC speakers

On most modern distros (Fedora included) PipeWire enables AirPlay/RAOP discovery
by default, so the amp **already** shows up in **Settings → Sound → Output** as
**"WiiM Amp-FCB2"** with no setup. Select it (system-wide or per-app in the
volume mixer) and all audio plays through the amp, lossless. No Apple device
involved — your PC is the sender. Latency is ~1-2s (fine for music; not for
lip-synced video).

If the amp does *not* appear, enable discovery with:

```bash
./setup/install-audio.sh
```

This is idempotent: it confirms the amp is available, and only enables RAOP
discovery if it's off. It never adds a second discovery instance (that would
create duplicate IPv4/IPv6 sinks for the same device).

## 2. Control GUI

```bash
python3 -m wiim
```

**Player window:** now-playing, a draggable seek bar, transport
(prev/play-pause/next/stop), mute, shuffle/repeat, volume, source switch
(Wi-Fi / Optical / Line-In / Bluetooth), EQ on-off + preset picker, and amp
presets (1-12).

**Settings** (gear button → preferences window): device info (name, firmware,
IP, MAC, Wi-Fi + signal, internet), connection status, a sleep timer, Play URL
(stream any audio URL), and reboot.

Install the launcher + app icon (so it shows in the app grid and can be pinned
to the dock):

```bash
./setup/install-app.sh
```

Then launch "WiiM Amp" from the app grid and right-click its dock icon → **Pin
to Dash**.

## Configuration

The amp is addressed at `WiiM-Amp-FCB2.local` (mDNS, survives IP changes). To
point at a different device, create `~/.config/wiim/config`:

```ini
[device]
host = 192.0.2.10
```

## Development

- `wiim/client.py` — stdlib-only HTTP API client (no third-party deps).
- `wiim/app.py` — GTK4/libadwaita GUI.
- Run tests: `python3 -m unittest discover -s tests -v`
- Live tests against the real amp: `WIIM_LIVE=1 python3 -m unittest discover -s tests -v`
