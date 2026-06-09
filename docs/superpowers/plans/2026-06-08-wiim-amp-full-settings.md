# WiiM Amp — Full API Settings (GUI v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Expose every controllable command in the WiiM HTTP API doc through the GUI: loop/shuffle, seek bar, mute, Play URL, sleep timer, reboot, device info, connection status. (No alarms, no timeSync, no playlist — explicitly out of scope.)

**Architecture:** Extend the existing stdlib `WiimClient` with the missing commands (TDD, mocked transport), live-confirm each against the device, then grow the GTK4 GUI: add seek/mute/shuffle to the player window and a gear-button `Adw.PreferencesWindow` for device-level settings.

**Tech Stack:** Python 3.14 stdlib, PyGObject/GTK4/libadwaita.

**Conventions:** Commits imperative + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Tests: `python3 -m unittest discover -s tests -v`.

---

## Command → control map (the full remaining doc surface)

| Command | Client method | GUI |
|---|---|---|
| `setPlayerCmd:loopmode:n` | `set_loop_mode(n)` | Player: Shuffle/Repeat dropdown |
| `setPlayerCmd:mute:n` | `mute(on)` (exists) | Player: mute toggle button |
| `setPlayerCmd:seek:sec` | `seek(sec)` (exists) | Player: draggable seek bar |
| `setPlayerCmd:play:url` | `play_url(url)` | Settings: Play URL entry |
| `setShutdown:sec` | `set_shutdown(sec)` | Settings: sleep timer set/cancel |
| `getShutdown` | `get_shutdown()` | Settings: countdown display |
| `reboot` | `reboot()` (exists) | Settings: Reboot button |
| `wlanGetConnectState` | `get_connection_state()` | Settings: connection status line |
| `getStatusEx` | `get_status()` (exists) | Settings: device info panel |

Loop semantics (asymmetric GET vs SET in the doc):
- SET via `loopmode`: `0`=sequence/no-loop, `1`=single-loop, `2`=shuffle-loop, `-1`=sequence-loop.
- GET via `getPlayerStatus.loop`: `0`=loop-all, `1`=single, `2`=shuffle-loop, `3`=shuffle-no-loop, `4`=no-shuffle-no-loop.
- GUI dropdown options + the loopmode value they SET: "No repeat"=0, "Repeat all"=-1, "Repeat one"=1, "Shuffle"=2.

---

## Task 1: Client — new commands (TDD)

**Files:** Modify `wiim/client.py`; Modify `tests/test_client.py`.

- [ ] **Step 1: Add failing tests** (append to `TestCommands` in `tests/test_client.py`):

```python
    def test_set_loop_mode(self):
        with self._capture() as m:
            self.c.set_loop_mode(-1)
            m.assert_called_once_with("setPlayerCmd:loopmode:-1")

    def test_play_url(self):
        with self._capture() as m:
            self.c.play_url("http://host/stream.mp3")
            m.assert_called_once_with("setPlayerCmd:play:http://host/stream.mp3")

    def test_set_shutdown(self):
        with self._capture() as m:
            self.c.set_shutdown(600)
            m.assert_called_once_with("setShutdown:600")

    def test_set_shutdown_cancel(self):
        with self._capture() as m:
            self.c.set_shutdown(-1)
            m.assert_called_once_with("setShutdown:-1")

    def test_get_shutdown(self):
        with mock.patch.object(self.c, "_command", return_value="600"):
            self.assertEqual(self.c.get_shutdown(), 600)

    def test_get_shutdown_nonnumeric(self):
        with mock.patch.object(self.c, "_command", return_value="\n"):
            self.assertEqual(self.c.get_shutdown(), 0)

    def test_get_connection_state(self):
        with mock.patch.object(self.c, "_command", return_value="OK\n"):
            self.assertEqual(self.c.get_connection_state(), "OK")
```

- [ ] **Step 2: Run, confirm fail.** `python3 -m unittest tests.test_client -v` → errors (methods missing).

- [ ] **Step 3: Implement** (append inside `WiimClient`, after `reboot`):

```python
    # loop / shuffle
    def set_loop_mode(self, n):
        return self._command(f"setPlayerCmd:loopmode:{int(n)}")

    # play arbitrary stream URL
    def play_url(self, url):
        return self._command(f"setPlayerCmd:play:{url}")

    # sleep timer / shutdown
    def set_shutdown(self, sec):
        return self._command(f"setShutdown:{int(sec)}")

    def get_shutdown(self):
        try:
            return int(self._command("getShutdown").strip())
        except (ValueError, AttributeError):
            return 0

    # wifi connection state: PROCESS | PAIRFAIL | FAIL | OK
    def get_connection_state(self):
        return self._command("wlanGetConnectState").strip()
```

- [ ] **Step 4: Run, confirm pass.** Full `python3 -m unittest discover -s tests` → all green, 3 live skipped.

- [ ] **Step 5: Commit** `feat: add loop, play-url, shutdown, connection-state to client`.

---

## Task 2: Live-confirm new commands (careful — shutdown must never fire)

**Files:** none (manual probing; update client/tests only if a command misbehaves).

- [ ] **Step 1: Read-only first.**
```bash
curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=wlanGetConnectState"; echo
curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=getShutdown"; echo
```
Expect a state token (e.g. `OK`) and a number (likely `0`).

- [ ] **Step 2: Loop mode (harmless; restore after).** Capture current `loop` from getPlayerStatus, set each loopmode, confirm `OK`, then restore:
```bash
for n in 1 2 -1 0; do printf 'loopmode:%s -> ' "$n"; curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=setPlayerCmd:loopmode:$n"; echo; done
```
All should return `OK`. Leave it on the value matching the user's prior state if known, else `0`.

- [ ] **Step 3: Shutdown — SET THEN IMMEDIATELY CANCEL.** Never leave a timer armed:
```bash
curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=setShutdown:600"; echo
curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=getShutdown"; echo   # expect ~600
curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=setShutdown:-1"; echo # CANCEL
curl -sk "https://WiiM-Amp-FCB2.local/httpapi.asp?command=getShutdown"; echo   # expect 0
```
Verify the final getShutdown is `0` (timer cancelled). If `getShutdown` does not reflect the set value, note the actual behavior; the GUI countdown reads whatever this returns.

- [ ] **Step 4: Skip live play_url** (would hijack playback). Trust the command form.

- [ ] **Step 5:** If any command returned something other than expected, adjust `WiimClient` + tests and re-run the suite. Commit only if code changed: `test: confirm loop/shutdown/connection behavior on firmware`.

---

## Task 3: GUI player additions (seek bar, mute, shuffle/repeat)

**Files:** Modify `wiim/app.py`.

Add to the player window, below transport / near volume. All calls via `run_async`. Seek bar uses the same suppress-during-poll pattern as volume.

- [ ] **Step 1: Add widgets in `__init__`** (after the transport row, before Volume):

```python
        # Seek bar
        self._suppress_seek = False
        self._duration_s = 0
        self.seek = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.seek.set_hexpand(True)
        self.seek.set_draw_value(False)
        self.seek.connect("change-value", self._on_seek)
        self.pos_lbl = Gtk.Label(label="0:00 / 0:00", xalign=0)
        self.pos_lbl.add_css_class("dim-label")
        box.append(self.seek)
        box.append(self.pos_lbl)
```

In the transport row list, add a mute and a shuffle/repeat control AFTER the stop button by appending a second row:

```python
        # Mode row: mute + shuffle/repeat
        mode_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                           halign=Gtk.Align.CENTER)
        self.mute_btn = Gtk.ToggleButton(icon_name="audio-volume-muted-symbolic")
        self.mute_btn.connect("toggled", self._on_mute)
        self.loop_drop = Gtk.DropDown.new_from_strings(
            ["No repeat", "Repeat all", "Repeat one", "Shuffle"])
        self.loop_drop.connect("notify::selected", self._on_loop)
        self._suppress_loop = True
        mode_row.append(self.mute_btn)
        mode_row.append(self.loop_drop)
        box.append(mode_row)
```

(Place the `mode_row` block right after the transport row is appended.)

- [ ] **Step 2: Add handlers** (with the other `_on_*` handlers):

```python
    LOOP_SET = {0: 0, 1: -1, 2: 1, 3: 2}  # dropdown index -> loopmode value
    # getPlayerStatus.loop -> dropdown index
    LOOP_READ = {0: 1, 1: 2, 2: 3, 3: 3, 4: 0}

    def _on_seek(self, scale, scroll_type, value):
        if self._suppress_seek or self._duration_s <= 0:
            return False
        run_async(lambda: self.client.seek(int(value)), self._noop)
        return False

    def _on_mute(self, btn):
        run_async(lambda: self.client.mute(btn.get_active()), self._noop)

    def _on_loop(self, dropdown, _param):
        if self._suppress_loop:
            return
        n = self.LOOP_SET.get(dropdown.get_selected(), 0)
        run_async(lambda: self.client.set_loop_mode(n), self._noop)
```

- [ ] **Step 3: Update `_tick` done()** to refresh seek + mute + loop from status (add inside the existing `done`, after the volume update):

```python
            try:
                cur = int(status.get("curpos", "0")) // 1000
                dur = int(status.get("totlen", "0")) // 1000
                self._duration_s = dur
                self._suppress_seek = True
                self.seek.set_range(0, max(dur, 1))
                self.seek.set_value(min(cur, max(dur, 1)))
                self._suppress_seek = False
                self.pos_lbl.set_label(f"{cur//60}:{cur%60:02d} / {dur//60}:{dur%60:02d}")
            except ValueError:
                pass
            self.mute_btn.set_active(status.get("mute") == "1")
            try:
                idx = self.LOOP_READ.get(int(status.get("loop", "4")), 0)
                self._suppress_loop = True
                self.loop_drop.set_selected(idx)
                self._suppress_loop = False
            except ValueError:
                pass
```

(`_suppress_loop` starts True in `__init__`; the first poll sets it appropriately. Keep the existing `_suppress_source=False` line.)

- [ ] **Step 4: Smoke test + commit.** `python3 -c "import wiim.app; print('ok')"`; full suite green. Commit `feat: add seek bar, mute, shuffle/repeat to player`.

---

## Task 4: GUI settings window (gear → Adw.PreferencesWindow)

**Files:** Modify `wiim/app.py`.

Add a gear button to the header bar opening an `Adw.PreferencesWindow` with groups: Device info, Sleep timer, Playback (Play URL), and a Reboot action. All reads via `run_async`.

- [ ] **Step 1: Add a gear button** to the `Adw.HeaderBar` in `__init__`:

```python
        gear = Gtk.Button(icon_name="emblem-system-symbolic")
        gear.connect("clicked", self._open_settings)
        header.pack_end(gear)
```

- [ ] **Step 2: Implement the settings window** (new method on `WiimWindow`):

```python
    def _open_settings(self, _btn):
        win = Adw.PreferencesWindow(transient_for=self, modal=True)
        win.set_title("WiiM Amp Settings")
        page = Adw.PreferencesPage()
        win.add(page)

        # Device info (filled async)
        info = Adw.PreferencesGroup(title="Device")
        self._info_rows = {}
        for key, label in [("DeviceName", "Name"), ("firmware", "Firmware"),
                           ("apcli0", "IP"), ("MAC", "MAC"),
                           ("essid", "Wi-Fi"), ("RSSI", "Signal (dBm)"),
                           ("internet", "Internet")]:
            row = Adw.ActionRow(title=label, subtitle="…")
            self._info_rows[key] = row
            info.add(row)
        conn_row = Adw.ActionRow(title="Connection", subtitle="…")
        self._info_rows["_conn"] = conn_row
        info.add(conn_row)
        page.add(info)

        # Sleep timer
        sleep = Adw.PreferencesGroup(title="Sleep timer")
        self._sleep_row = Adw.ActionRow(title="Shutdown in", subtitle="off")
        spin = Gtk.SpinButton.new_with_range(1, 600, 5)
        spin.set_valign(Gtk.Align.CENTER)
        set_btn = Gtk.Button(label="Set (min)", valign=Gtk.Align.CENTER)
        set_btn.connect("clicked", lambda *_: self._set_sleep(int(spin.get_value())))
        cancel_btn = Gtk.Button(label="Cancel", valign=Gtk.Align.CENTER)
        cancel_btn.connect("clicked", lambda *_: self._set_sleep(0, cancel=True))
        self._sleep_row.add_suffix(spin)
        self._sleep_row.add_suffix(set_btn)
        self._sleep_row.add_suffix(cancel_btn)
        sleep.add(self._sleep_row)
        page.add(sleep)

        # Playback: Play URL
        play = Adw.PreferencesGroup(title="Playback")
        url_row = Adw.EntryRow(title="Stream URL")
        play_btn = Gtk.Button(label="Play", valign=Gtk.Align.CENTER)
        play_btn.connect("clicked", lambda *_: self._play_url(url_row.get_text()))
        url_row.add_suffix(play_btn)
        play.add(url_row)
        page.add(play)

        # Reboot
        danger = Adw.PreferencesGroup()
        reboot_row = Adw.ActionRow(title="Reboot device")
        reboot_btn = Gtk.Button(label="Reboot", valign=Gtk.Align.CENTER)
        reboot_btn.add_css_class("destructive-action")
        reboot_btn.connect("clicked", lambda *_: run_async(self.client.reboot, self._noop))
        reboot_row.add_suffix(reboot_btn)
        danger.add(reboot_row)
        page.add(danger)

        self._refresh_settings()
        win.present()

    def _refresh_settings(self):
        def info_done(status, err):
            if status:
                for key, row in self._info_rows.items():
                    if key == "_conn":
                        continue
                    val = status.get(key, "—")
                    if key == "essid":  # hex-encoded SSID
                        val = decode_hex(val)
                    row.set_subtitle(str(val))
            return False
        run_async(self.client.get_status, info_done)

        def conn_done(state, err):
            if "_conn" in self._info_rows:
                self._info_rows["_conn"].set_subtitle(state or str(err))
            return False
        run_async(self.client.get_connection_state, conn_done)

        def sleep_done(sec, err):
            if sec and sec > 0:
                self._sleep_row.set_subtitle(f"{sec // 60} min {sec % 60} s")
            else:
                self._sleep_row.set_subtitle("off")
            return False
        run_async(self.client.get_shutdown, sleep_done)

    def _set_sleep(self, minutes, cancel=False):
        sec = -1 if cancel else minutes * 60
        run_async(lambda: self.client.set_shutdown(sec),
                  lambda r, e: (self._refresh_settings(), False)[1])

    def _play_url(self, url):
        if url.strip():
            run_async(lambda: self.client.play_url(url.strip()), self._noop)
```

Note: `decode_hex` must be importable in `app.py` — add `decode_hex` to the existing `from wiim.client import ...` line.

- [ ] **Step 3: Smoke test + commit.** `python3 -c "import wiim.app; print('ok')"`; full suite green. Commit `feat: add settings window (device info, sleep timer, play URL, reboot)`.

---

## Task 5: Live GUI verification + docs

**Files:** Modify `README.md`.

- [ ] **Step 1:** Launch `python3 -m wiim`; confirm: seek bar tracks/scrubs, mute toggles, shuffle/repeat changes, gear opens settings, device info populates, sleep-timer set shows a countdown then Cancel returns it to "off", Play URL plays a test stream. (Do not leave a sleep timer armed.)
- [ ] **Step 2:** Update README feature list to mention the settings window and new player controls.
- [ ] **Step 3:** Commit `docs: document GUI settings window and new controls`.

---

## Self-Review
- Coverage: every remaining doc command (loopmode, mute, seek, play:url, setShutdown, getShutdown, reboot, wlanGetConnectState, getStatusEx) maps to a task. Alarms/timeSync/playlist intentionally excluded per user.
- Safety: shutdown live-test always cancels (Task 2 Step 3).
- Consistency: new method names (`set_loop_mode`, `play_url`, `set_shutdown`, `get_shutdown`, `get_connection_state`) used identically in tests and GUI. `decode_hex` imported where used.
