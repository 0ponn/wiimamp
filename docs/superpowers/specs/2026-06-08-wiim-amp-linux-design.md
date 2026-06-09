# WiiM Amp ↔ Linux PC — Design

Date: 2026-06-08
Status: approved (pending spec review)

## Goal

Make a WiiM Amp fully usable from a Linux (Fedora/GNOME, PipeWire) PC, where no
official Linux app exists. Two outcomes:

1. **Use the amp as PC speakers** — any PC audio plays through it, selectable in
   normal sound settings.
2. **Control the amp's own functions** the OS can't reach (input source, presets,
   device EQ, reboot) from a native desktop GUI.

## Target environment (verified 2026-06-08)

- Device: WiiM Amp-FCB2, firmware Linkplay.5.2.814734, UUID AABBCCDDEEFF00112233445566.
- Stable address: `WiiM-Amp-FCB2.local` (mDNS via Avahi; resolves to 192.0.2.10,
  survives DHCP changes). Used everywhere instead of a hardcoded IP.
- Audio stack: PipeWire 1.6.6, PulseAudio compat. `module-raop-sink` /
  `module-raop-discover` installed. Avahi running.
- Amp advertises `_raop._tcp` on port 7000, `cn=0,1` (PCM+ALAC), `et=0,4` (none+auth).
- GTK4 + libadwaita + PyGObject present.
- Python 3.14.
- HTTP API is HTTPS with a self-signed cert (clients must skip verification).

## Deliverable 1 — Audio routing (RAOP sink)

Make the amp a standard selectable output device.

- **Mechanism:** PipeWire `module-raop-discover`. Avahi finds the amp; PipeWire
  creates a sink named after the device. It appears in GNOME Sound settings and
  `pavucontrol` as an output; selectable system-wide or per-app; its volume slider
  drives the amp.
- **Persistence:** drop a config fragment in
  `~/.config/pipewire/pipewire-pulse.conf.d/` (e.g. `90-wiim-raop.conf`) loading
  `module-raop-discover`, so the sink is present on every login. No systemd unit.
- **Quality/latency:** lossless ALAC, ~1-2 s buffered latency. Acceptable for music
  and general audio. Known limitation: video lip-sync. Bluetooth fallback is **out of
  scope** until/unless that limitation is actually hit (YAGNI).
- **Verification:** manual — sink appears in `wpctl status` / Sound settings; audio
  plays through the amp. Not unit-testable.

Rejected: DLNA (file playback only, not live system audio); Bluetooth as primary
(lower quality; RAOP is the better default on this stack).

## Deliverable 2 — Control GUI

Native GNOME app for the amp's own functions.

### Architecture — two units

**a. `wiim/client.py` — API client (pure Python, stdlib only)**

- HTTPS GET to `https://WiiM-Amp-FCB2.local/httpapi.asp?command=...` via `urllib`,
  using an `ssl` context with verification disabled (self-signed cert).
- One method per documented command. Surface:
  - State: `get_status()` (getStatusEx), `get_player_status()` (getPlayerStatus).
  - Transport: `play/pause/toggle/next/prev/stop/seek(sec)`.
  - Volume: `set_volume(0-100)`, `mute(bool)`.
  - Source: `set_source(name)` → `setPlayerCmd:switchmode:<wifi|optical|line-in|bluetooth|udisk>`.
  - EQ: `eq_on/eq_off/eq_list/eq_load(name)`.
  - Preset: `play_preset(n)` — command string not in the provided API excerpt;
    confirm the exact form against the device during implementation (likely
    `setPlayerCmd:preset:<n>` / `MCUKeyShortClick:<n>`). If unconfirmable, drop
    presets from the GUI rather than ship a guess.
  - Device: `reboot()`.
- **Metadata decode:** `Title`/`Artist`/`Album` in getPlayerStatus are hex-encoded
  UTF-8; decode for display. `vendor` gives the active service. `status`, `vol`,
  `mute`, `curpos`, `totlen`, `mode` parsed for transport/now-playing state.
- No GTK imports here — fully testable in isolation.

**b. `wiim/app.py` — GTK4/libadwaita GUI**

- Single `Adw.ApplicationWindow`:
  - Now-playing: decoded title/artist/album, service (vendor), position/duration.
  - Transport row: prev / play-pause / next / stop.
  - Volume slider + mute toggle (reflects + sets amp volume).
  - Source dropdown: Wi-Fi, Optical, Line-In/AUX, Bluetooth.
  - EQ: on/off switch + dropdown populated from `eq_list()` + apply.
  - Presets: buttons `1..preset_key` (preset_key read from getStatusEx), if the
    preset command is confirmed.
- **Threading:** client HTTP calls block; run them on a worker thread, marshal
  results back with `GLib.idle_add`. UI never blocks.
- **Polling:** `GLib.timeout` ~1 s refreshes now-playing/volume/status.
- **Config:** `~/.config/wiim/config` (INI) with `host = WiiM-Amp-FCB2.local`
  default; override for a different device.
- **Launcher:** a `.desktop` entry so it appears in the GNOME app grid.

### Dependencies

- Client: stdlib only.
- GUI: PyGObject + GTK4 + libadwaita (already installed). No pip packages.

### Testing

- `client.py`: unit tests with captured fixtures — URL construction per command,
  hex metadata decode, response parsing, SSL-context creation. HTTP mocked; no device
  needed. One opt-in live smoke test against the amp.
- `app.py`: manual verification (toggle source, set volume, load EQ, see now-playing
  update).

## Out of scope (explicit)

GUI volume here is redundant with OS sound settings once the RAOP sink exists — kept
only because it's trivial. No multiroom grouping, no Bluetooth setup automation, no
preset *management* (only triggering), no system-tray applet (awkward on GNOME).

## Open items to resolve during implementation

1. Confirm the preset-trigger command against the live device; drop presets if not
   confirmable.
2. Confirm `switchmode` source tokens behave as documented on this firmware
   (esp. line-in vs aux naming).
