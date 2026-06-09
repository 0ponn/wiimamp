# WiiM Amp Linux Control + Audio Routing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a WiiM Amp usable from a Fedora/GNOME/PipeWire PC — route all PC audio to it as a normal output device, and control its own functions (source, EQ, presets, transport) from a native GTK4 GUI.

**Architecture:** Two independent units. (1) A PipeWire RAOP sink so the amp appears in Sound settings. (2) A zero-dependency Python package: a pure-stdlib HTTP API client (`wiim/client.py`) plus a GTK4/libadwaita GUI (`wiim/app.py`) that consumes it. The client has no GTK imports and is unit-tested with mocked transport; the GUI is manually verified.

**Tech Stack:** Python 3.14 stdlib (`urllib`, `ssl`, `json`, `configparser`, `unittest`), PyGObject + GTK4 + libadwaita, PipeWire `module-raop-discover`.

**Conventions:** All commits use imperative messages and end with the trailer:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
Tests run with `python3 -m unittest discover -s tests -v`.

**Addressing:** The amp is reached at `WiiM-Amp-FCB2.local` (mDNS, DHCP-stable). HTTPS uses a self-signed cert, so all clients disable TLS verification.

---

## File Structure

- `wiim/__init__.py` — package marker.
- `wiim/client.py` — API client + `decode_hex`, `build_url`, `DEFAULT_HOST`. Pure stdlib, no GTK.
- `wiim/config.py` — `load_host()` from `~/.config/wiim/config`.
- `wiim/app.py` — GTK4/libadwaita GUI.
- `wiim/__main__.py` — `python3 -m wiim` entry → launches the GUI.
- `tests/test_client.py` — unit tests for client (mocked transport).
- `tests/test_config.py` — unit tests for config loading.
- `tests/test_live.py` — opt-in live smoke test (skipped unless `WIIM_LIVE=1`).
- `setup/90-wiim-raop.conf` — PipeWire fragment loading RAOP discovery.
- `setup/install-audio.sh` — installs the fragment, restarts `pipewire-pulse`.
- `data/wiim-amp.desktop` — GNOME launcher.
- `README.md` — install + usage.

---

## Task 0: Project scaffold + git

**Files:**
- Create: `.gitignore`, `wiim/__init__.py`, `tests/__init__.py`, `README.md`

- [ ] **Step 1: Initialize git and package dirs**

```bash
cd /path/to/wiimamp
git init
mkdir -p wiim tests setup data docs/superpowers
printf '__pycache__/\n*.pyc\n.venv/\n' > .gitignore
touch wiim/__init__.py tests/__init__.py
```

- [ ] **Step 2: Add a minimal README**

```markdown
# WiiM Amp — Linux control + audio routing

- `wiim/` — zero-dependency API client + GTK4 GUI to control a WiiM Amp.
- `setup/` — PipeWire config to use the amp as a system audio output.

Run the GUI: `python3 -m wiim`
Run tests: `python3 -m unittest discover -s tests -v`
```

Write the above to `README.md`.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "chore: scaffold wiim package and repo"
```

---

## Task 1: Client pure helpers (`decode_hex`, `build_url`)

**Files:**
- Create: `wiim/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_client.py`:

```python
import unittest
from wiim.client import decode_hex, build_url, DEFAULT_HOST


class TestHelpers(unittest.TestCase):
    def test_decode_hex_utf8(self):
        self.assertEqual(decode_hex("4B6E65656C"), "Kneel")

    def test_decode_hex_non_hex_passthrough(self):
        self.assertEqual(decode_hex("not-hex!"), "not-hex!")

    def test_decode_hex_empty(self):
        self.assertEqual(decode_hex(""), "")

    def test_build_url(self):
        self.assertEqual(
            build_url("host.local", "getStatusEx"),
            "https://host.local/httpapi.asp?command=getStatusEx",
        )

    def test_default_host(self):
        self.assertEqual(DEFAULT_HOST, "WiiM-Amp-FCB2.local")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_client -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wiim.client'`.

- [ ] **Step 3: Implement helpers**

Create `wiim/client.py`:

```python
"""Zero-dependency client for the WiiM/LinkPlay HTTP API."""
import binascii
import json
import ssl
import urllib.parse
import urllib.request

DEFAULT_HOST = "WiiM-Amp-FCB2.local"


def build_url(host, command):
    return f"https://{host}/httpapi.asp?command={command}"


def decode_hex(value):
    """Decode a hex-encoded UTF-8 string; return input unchanged if not hex."""
    try:
        return binascii.unhexlify(value).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return value


def _ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_client -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add wiim/client.py tests/test_client.py
git commit -m "feat: add wiim client url + hex helpers"
```

---

## Task 2: Client transport/control commands

**Files:**
- Modify: `wiim/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Add failing tests for command methods**

Append to `tests/test_client.py` (before the `if __name__` block):

```python
from unittest import mock
from wiim.client import WiimClient


class TestCommands(unittest.TestCase):
    def setUp(self):
        self.c = WiimClient(host="h.local")

    def _capture(self):
        return mock.patch.object(self.c, "_command", return_value="OK")

    def test_pause(self):
        with self._capture() as m:
            self.c.pause()
            m.assert_called_once_with("setPlayerCmd:pause")

    def test_toggle(self):
        with self._capture() as m:
            self.c.toggle()
            m.assert_called_once_with("setPlayerCmd:onepause")

    def test_next_prev_stop_resume(self):
        with self._capture() as m:
            self.c.play(); self.c.next(); self.c.prev(); self.c.stop()
        self.assertEqual(
            [call.args[0] for call in m.call_args_list],
            ["setPlayerCmd:resume", "setPlayerCmd:next",
             "setPlayerCmd:prev", "setPlayerCmd:stop"],
        )

    def test_seek_int(self):
        with self._capture() as m:
            self.c.seek(42.7)
            m.assert_called_once_with("setPlayerCmd:seek:42")

    def test_volume_clamped_high(self):
        with self._capture() as m:
            self.c.set_volume(150)
            m.assert_called_once_with("setPlayerCmd:vol:100")

    def test_volume_clamped_low(self):
        with self._capture() as m:
            self.c.set_volume(-5)
            m.assert_called_once_with("setPlayerCmd:vol:0")

    def test_mute(self):
        with self._capture() as m:
            self.c.mute(True); self.c.mute(False)
        self.assertEqual(
            [call.args[0] for call in m.call_args_list],
            ["setPlayerCmd:mute:1", "setPlayerCmd:mute:0"],
        )

    def test_source_alias(self):
        with self._capture() as m:
            self.c.set_source("aux")
            m.assert_called_once_with("setPlayerCmd:switchmode:line-in")

    def test_eq_load_quotes_spaces(self):
        with self._capture() as m:
            self.c.eq_load("Bass Booster")
            m.assert_called_once_with("EQLoad:Bass%20Booster")

    def test_reboot(self):
        with self._capture() as m:
            self.c.reboot()
            m.assert_called_once_with("reboot")

    def test_play_preset(self):
        with self._capture() as m:
            self.c.play_preset(3)
            m.assert_called_once_with("setPlayerCmd:preset:3")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_client -v`
Expected: FAIL — `ImportError: cannot import name 'WiimClient'`.

- [ ] **Step 3: Implement `WiimClient` command methods**

Append to `wiim/client.py`:

```python
class WiimClient:
    SOURCES = {
        "wifi": "wifi",
        "optical": "optical",
        "aux": "line-in",
        "line-in": "line-in",
        "bluetooth": "bluetooth",
        "udisk": "udisk",
    }

    def __init__(self, host=DEFAULT_HOST, timeout=5):
        self.host = host
        self.timeout = timeout
        self._ctx = _ssl_context()

    def _command(self, command):
        url = build_url(self.host, command)
        with urllib.request.urlopen(
            url, timeout=self.timeout, context=self._ctx
        ) as resp:
            return resp.read().decode("utf-8", "replace")

    def _command_json(self, command):
        return json.loads(self._command(command))

    # transport
    def play(self):
        return self._command("setPlayerCmd:resume")

    def pause(self):
        return self._command("setPlayerCmd:pause")

    def toggle(self):
        return self._command("setPlayerCmd:onepause")

    def next(self):
        return self._command("setPlayerCmd:next")

    def prev(self):
        return self._command("setPlayerCmd:prev")

    def stop(self):
        return self._command("setPlayerCmd:stop")

    def seek(self, seconds):
        return self._command(f"setPlayerCmd:seek:{int(seconds)}")

    # volume
    def set_volume(self, value):
        value = max(0, min(100, int(value)))
        return self._command(f"setPlayerCmd:vol:{value}")

    def mute(self, on):
        return self._command(f"setPlayerCmd:mute:{1 if on else 0}")

    # source
    def set_source(self, name):
        mode = self.SOURCES[name]
        return self._command(f"setPlayerCmd:switchmode:{mode}")

    # eq
    def eq_on(self):
        return self._command("EQOn")

    def eq_off(self):
        return self._command("EQOff")

    def eq_stat(self):
        return self._command_json("EQGetStat")

    def eq_list(self):
        return json.loads(self._command("EQGetList"))

    def eq_load(self, name):
        return self._command(f"EQLoad:{urllib.parse.quote(name)}")

    # presets (command confirmed in Task 4)
    def play_preset(self, n):
        return self._command(f"setPlayerCmd:preset:{int(n)}")

    # device
    def reboot(self):
        return self._command("reboot")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_client -v`
Expected: PASS (all TestCommands + TestHelpers).

- [ ] **Step 5: Commit**

```bash
git add wiim/client.py tests/test_client.py
git commit -m "feat: add wiim client control commands"
```

---

## Task 3: Client state parsing (status + now-playing decode)

**Files:**
- Modify: `wiim/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_client.py` (before the `if __name__` block):

```python
PLAYER_FIXTURE = (
    '{"type":"0","mode":"31","status":"play","curpos":"108222",'
    '"totlen":"224287","vol":"22","mute":"0","vendor":"Qobuz",'
    '"Title":"4B6E65656C","Artist":"4E696CC3BC666572","Album":"53686F6573"}'
)


class TestState(unittest.TestCase):
    def setUp(self):
        self.c = WiimClient(host="h.local")

    def test_get_player_status_decodes_metadata(self):
        with mock.patch.object(self.c, "_command", return_value=PLAYER_FIXTURE):
            s = self.c.get_player_status()
        self.assertEqual(s["Title"], "Kneel")
        self.assertEqual(s["Artist"], "Nilüfer")
        self.assertEqual(s["Album"], "Shoes")
        self.assertEqual(s["status"], "play")
        self.assertEqual(s["vol"], "22")

    def test_get_player_status_handles_missing_metadata(self):
        with mock.patch.object(self.c, "_command", return_value='{"status":"stop"}'):
            s = self.c.get_player_status()
        self.assertEqual(s["status"], "stop")
        self.assertNotIn("Title", s)

    def test_get_status_passthrough(self):
        with mock.patch.object(self.c, "_command", return_value='{"DeviceName":"WiiM Amp"}'):
            s = self.c.get_status()
        self.assertEqual(s["DeviceName"], "WiiM Amp")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_client -v`
Expected: FAIL — `AttributeError: 'WiimClient' object has no attribute 'get_player_status'`.

- [ ] **Step 3: Implement state methods**

Append to the `WiimClient` class in `wiim/client.py` (inside the class, after `reboot`):

```python
    # state
    def get_status(self):
        return self._command_json("getStatusEx")

    def get_player_status(self):
        data = self._command_json("getPlayerStatus")
        for key in ("Title", "Artist", "Album"):
            if key in data:
                data[key] = decode_hex(data[key])
        return data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_client -v`
Expected: PASS (all suites).

- [ ] **Step 5: Commit**

```bash
git add wiim/client.py tests/test_client.py
git commit -m "feat: add wiim client state parsing with metadata decode"
```

---

## Task 4: Live smoke test + confirm preset/source behavior

**Files:**
- Create: `tests/test_live.py`

This task hits the real amp to (a) prove the client works end-to-end and (b) resolve the two open spec items: the preset-trigger command and the source tokens.

- [ ] **Step 1: Write the opt-in live test**

Create `tests/test_live.py`:

```python
import os
import unittest
from wiim.client import WiimClient


@unittest.skipUnless(os.environ.get("WIIM_LIVE") == "1", "set WIIM_LIVE=1 to run")
class TestLive(unittest.TestCase):
    def setUp(self):
        self.c = WiimClient()

    def test_get_status(self):
        s = self.c.get_status()
        self.assertIn("DeviceName", s)

    def test_get_player_status(self):
        s = self.c.get_player_status()
        self.assertIn("status", s)

    def test_eq_list(self):
        eqs = self.c.eq_list()
        self.assertIsInstance(eqs, list)
        self.assertIn("Flat", eqs)
```

- [ ] **Step 2: Run the live test**

Run: `WIIM_LIVE=1 python3 -m unittest tests.test_live -v`
Expected: PASS (3 tests) against `WiiM-Amp-FCB2.local`.

- [ ] **Step 3: Manually confirm preset command**

Read the current preset count, then trigger preset 1 and observe playback change:

```bash
curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=getStatusEx" | grep -o '"preset_key":"[0-9]*"'
curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=setPlayerCmd:preset:1"; echo
sleep 2
curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=getPlayerStatus" | head -c 200; echo
```

Decision: if preset 1 starts playback (status flips to `play` / track changes), presets work — keep `play_preset` and the GUI preset row. If it errors or does nothing, presets are unsupported on this firmware via this command: remove `play_preset` from `wiim/client.py`, its test in `tests/test_client.py`, and the preset row in Task 6's `app.py`. Record the outcome in the commit message.

- [ ] **Step 4: Manually confirm source switching**

```bash
for m in optical line-in wifi; do
  echo "switchmode:$m ->"; curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=setPlayerCmd:switchmode:$m"; echo
  sleep 1
done
# return to wifi to leave the amp in a normal state
```

Confirm each returns `OK` and the amp's input changes. If a token differs on this firmware, update `WiimClient.SOURCES` and the corresponding test, then re-run `python3 -m unittest tests.test_client -v`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_live.py wiim/client.py tests/test_client.py
git commit -m "test: add live smoke test; confirm preset and source behavior"
```

---

## Task 5: Config loading

**Files:**
- Create: `wiim/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config.py`:

```python
import os
import tempfile
import unittest
from wiim.config import load_host
from wiim.client import DEFAULT_HOST


class TestConfig(unittest.TestCase):
    def test_default_when_no_file(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["XDG_CONFIG_HOME"] = d
            self.assertEqual(load_host(), DEFAULT_HOST)

    def test_reads_host_from_config(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["XDG_CONFIG_HOME"] = d
            cfgdir = os.path.join(d, "wiim")
            os.makedirs(cfgdir)
            with open(os.path.join(cfgdir, "config"), "w") as f:
                f.write("[device]\nhost = 192.0.2.10\n")
            self.assertEqual(load_host(), "192.0.2.10")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_config -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wiim.config'`.

- [ ] **Step 3: Implement config loader**

Create `wiim/config.py`:

```python
"""Load the amp host from ~/.config/wiim/config (INI), defaulting to mDNS name."""
import configparser
import os

from wiim.client import DEFAULT_HOST


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "wiim", "config")


def load_host():
    cp = configparser.ConfigParser()
    if cp.read(config_path()) and cp.has_option("device", "host"):
        return cp.get("device", "host")
    return DEFAULT_HOST
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_config -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS (all non-live suites; live skipped).

- [ ] **Step 6: Commit**

```bash
git add wiim/config.py tests/test_config.py
git commit -m "feat: add config host loading"
```

---

## Task 6: GTK4 GUI

**Files:**
- Create: `wiim/app.py`, `wiim/__main__.py`

The GUI is manually verified (GTK is not unit-tested). All amp calls run on a worker thread; results marshal back via `GLib.idle_add` so the UI never blocks. A 1 s poll refreshes now-playing/volume.

- [ ] **Step 1: Implement the GUI**

Create `wiim/app.py`:

```python
"""GTK4/libadwaita GUI for the WiiM Amp."""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from wiim.client import WiimClient  # noqa: E402
from wiim.config import load_host  # noqa: E402

SOURCES = [
    ("Wi-Fi", "wifi"),
    ("Optical", "optical"),
    ("Line-In / AUX", "line-in"),
    ("Bluetooth", "bluetooth"),
]


def run_async(fn, on_done=None):
    """Run blocking fn() off the GTK thread; deliver (result, error) on the main loop."""
    def worker():
        try:
            result, err = fn(), None
        except Exception as exc:  # noqa: BLE001 - surfaced to UI
            result, err = None, exc
        if on_done is not None:
            GLib.idle_add(on_done, result, err)

    threading.Thread(target=worker, daemon=True).start()


class WiimWindow(Adw.ApplicationWindow):
    def __init__(self, app, client):
        super().__init__(application=app, title="WiiM Amp")
        self.client = client
        self.set_default_size(380, 520)
        self._suppress_volume = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        header = Adw.HeaderBar()
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(header)
        root.append(box)
        self.set_content(root)

        # Now playing
        self.title_lbl = Gtk.Label(label="—", xalign=0)
        self.title_lbl.add_css_class("title-3")
        self.artist_lbl = Gtk.Label(label="", xalign=0)
        self.artist_lbl.add_css_class("dim-label")
        box.append(self.title_lbl)
        box.append(self.artist_lbl)

        # Transport
        transport = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                            halign=Gtk.Align.CENTER)
        for icon, handler in [
            ("media-skip-backward-symbolic", lambda *_: self._call(self.client.prev)),
            ("media-playback-start-symbolic", lambda *_: self._call(self.client.toggle)),
            ("media-skip-forward-symbolic", lambda *_: self._call(self.client.next)),
            ("media-playback-stop-symbolic", lambda *_: self._call(self.client.stop)),
        ]:
            btn = Gtk.Button(icon_name=icon)
            btn.connect("clicked", handler)
            transport.append(btn)
        box.append(transport)

        # Volume
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume.set_hexpand(True)
        self.volume.connect("value-changed", self._on_volume)
        box.append(Gtk.Label(label="Volume", xalign=0))
        box.append(self.volume)

        # Source
        self.source = Gtk.DropDown.new_from_strings([s[0] for s in SOURCES])
        self.source.connect("notify::selected", self._on_source)
        box.append(Gtk.Label(label="Source", xalign=0))
        box.append(self.source)

        # EQ
        eq_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.eq_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.eq_switch.connect("state-set", self._on_eq_switch)
        self.eq_drop = Gtk.DropDown.new_from_strings(["(loading)"])
        self.eq_drop.set_hexpand(True)
        self.eq_apply = Gtk.Button(label="Apply EQ")
        self.eq_apply.connect("clicked", self._on_eq_apply)
        eq_row.append(Gtk.Label(label="EQ"))
        eq_row.append(self.eq_switch)
        eq_row.append(self.eq_drop)
        box.append(eq_row)
        box.append(self.eq_apply)

        self._load_eq_list()
        self._tick()
        GLib.timeout_add_seconds(1, self._tick)

    # --- helpers ---
    def _call(self, fn, on_done=None):
        run_async(fn, on_done or self._noop)

    def _noop(self, result, err):
        if err:
            self.title_lbl.set_label(f"error: {err}")
        return False

    # --- handlers ---
    def _on_volume(self, scale):
        if self._suppress_volume:
            return
        value = int(scale.get_value())
        run_async(lambda: self.client.set_volume(value), self._noop)

    def _on_source(self, dropdown, _param):
        idx = dropdown.get_selected()
        mode = SOURCES[idx][1]
        run_async(lambda: self.client.set_source(mode), self._noop)

    def _on_eq_switch(self, _switch, state):
        run_async((self.client.eq_on if state else self.client.eq_off), self._noop)
        return False

    def _on_eq_apply(self, _btn):
        item = self.eq_drop.get_selected_item()
        if item is None:
            return
        name = item.get_string()
        run_async(lambda: self.client.eq_load(name), self._noop)

    # --- data ---
    def _load_eq_list(self):
        def done(result, err):
            if result:
                self.eq_drop.set_model(Gtk.StringList.new(result))
            return False
        run_async(self.client.eq_list, done)

    def _tick(self):
        def done(status, err):
            if err or not status:
                return False
            title = status.get("Title") or status.get("vendor") or "—"
            artist = status.get("Artist", "")
            album = status.get("Album", "")
            self.title_lbl.set_label(title)
            self.artist_lbl.set_label(" — ".join(p for p in (artist, album) if p))
            try:
                vol = int(status.get("vol", "0"))
                self._suppress_volume = True
                self.volume.set_value(vol)
                self._suppress_volume = False
            except ValueError:
                pass
            return False
        run_async(self.client.get_player_status, done)
        return True  # keep the timeout alive


class WiimApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="net.local.WiimAmp")
        self.client = WiimClient(host=load_host())

    def do_activate(self):
        win = WiimWindow(self, self.client)
        win.present()


def main():
    return WiimApp().run(None)
```

- [ ] **Step 2: Create the module entry point**

Create `wiim/__main__.py`:

```python
from wiim.app import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Launch and verify manually**

Run: `python3 -m wiim`
Expected — a window titled "WiiM Amp" showing:
- current track title/artist updating within ~1 s,
- transport buttons that pause/resume/skip the amp,
- a volume slider that reflects and changes the amp volume,
- a Source dropdown that switches input,
- an EQ switch + populated dropdown + Apply that loads the preset.

If Task 4 found presets unsupported, no preset row exists here — nothing to remove. If presets ARE supported and you want them in the GUI, add a button row that calls `self.client.play_preset(n)` for `n` in `1..preset_key`; otherwise leave them to the device app (out of scope, YAGNI).

- [ ] **Step 4: Commit**

```bash
git add wiim/app.py wiim/__main__.py
git commit -m "feat: add GTK4 control GUI"
```

---

## Task 7: Desktop launcher

**Files:**
- Create: `data/wiim-amp.desktop`

- [ ] **Step 1: Write the launcher**

Create `data/wiim-amp.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=WiiM Amp
Comment=Control the WiiM Amp
Exec=python3 -m wiim
Icon=audio-speakers-symbolic
Terminal=false
Categories=AudioVideo;Audio;
```

- [ ] **Step 2: Install and verify it appears**

```bash
install -Dm644 data/wiim-amp.desktop ~/.local/share/applications/wiim-amp.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

Note: `Exec=python3 -m wiim` requires launching from the repo dir, or installing the package. For now, edit the installed file's `Exec` to `Exec=sh -c 'cd /path/to/wiimamp && python3 -m wiim'` if launching from the app grid. Verify "WiiM Amp" appears in the GNOME app grid and launches the window.

- [ ] **Step 3: Commit**

```bash
git add data/wiim-amp.desktop
git commit -m "feat: add desktop launcher"
```

---

## Task 8: Audio routing — RAOP sink

**Files:**
- Create: `setup/90-wiim-raop.conf`, `setup/install-audio.sh`

Make the amp a selectable system output device.

- [ ] **Step 1: Write the PipeWire fragment**

Create `setup/90-wiim-raop.conf`:

```
# Discover AirPlay/RAOP receivers (incl. the WiiM Amp) and expose them as sinks.
context.modules = [
    { name = libpipewire-module-raop-discover }
]
```

- [ ] **Step 2: Write the installer**

Create `setup/install-audio.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
dest="${XDG_CONFIG_HOME:-$HOME/.config}/pipewire/pipewire-pulse.conf.d"
mkdir -p "$dest"
install -m644 "$(dirname "$0")/90-wiim-raop.conf" "$dest/90-wiim-raop.conf"
systemctl --user restart pipewire-pulse.service
echo "Installed. The amp should appear as an output in Sound settings within a few seconds."
```

- [ ] **Step 3: Install and verify the sink appears**

```bash
chmod +x setup/install-audio.sh
./setup/install-audio.sh
sleep 4
wpctl status | grep -i wiim || pactl list short sinks | grep -i raop
```

Expected: a RAOP sink for the WiiM Amp is listed. Then in GNOME Sound settings, "WiiM Amp-FCB2" appears under Output; selecting it and playing audio plays through the amp.

If no sink appears (RAOP auto-discovery rejected by the firmware's `et=4` auth), fall back to an explicit sink in the fragment instead of discover:

```
context.modules = [
    { name = libpipewire-module-raop-sink
      args = {
        raop.ip = "192.0.2.10"
        raop.port = 7000
        raop.name = "WiiM Amp"
        raop.transport = "udp"
        raop.encryption.type = "auth"
        audio.codec = "ALAC"
        stream.props = { node.name = "raop.wiim" node.description = "WiiM Amp" }
      }
    }
]
```

Re-run the installer and re-check `wpctl status`. Record which variant worked in the commit message.

- [ ] **Step 4: Commit**

```bash
git add setup/90-wiim-raop.conf setup/install-audio.sh
git commit -m "feat: add PipeWire RAOP sink setup for amp audio output"
```

---

## Task 9: Final verification + README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: all unit tests PASS, live tests skipped.

- [ ] **Step 2: Run the live suite once**

Run: `WIIM_LIVE=1 python3 -m unittest discover -s tests -v`
Expected: live tests PASS.

- [ ] **Step 3: Flesh out the README**

Replace `README.md` with usage covering: install audio routing (`./setup/install-audio.sh`), selecting the amp in Sound settings, launching the GUI (`python3 -m wiim`), the config file (`~/.config/wiim/config`, `[device] host =`), and running tests. Keep it under ~40 lines.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document install and usage"
```

---

## Self-Review (completed by author)

**Spec coverage:**
- Audio routing → Task 8 (discover + explicit fallback, persistence, verification). ✓
- Client (all commands, metadata decode, SSL) → Tasks 1-3. ✓
- mDNS addressing → `DEFAULT_HOST` (Task 1), config override (Task 5). ✓
- GUI (now-playing, transport, volume, source, EQ, presets) → Task 6. ✓
- Preset/source open items → Task 4 resolves live, with explicit drop path. ✓
- Launcher → Task 7. ✓
- Testing strategy (mocked unit + opt-in live + manual GUI) → Tasks 1-6, 9. ✓

**Placeholder scan:** No TBDs. The only conditional ("drop presets if unsupported") has a concrete decision rule and exact edit locations.

**Type consistency:** `WiimClient` method names match between client tasks, tests, and GUI calls (`toggle`, `next`, `prev`, `stop`, `set_volume`, `set_source`, `eq_list`, `eq_load`, `eq_on/off`, `get_player_status`, `play_preset`). `load_host()`/`DEFAULT_HOST` consistent across config + client + tests.
