"""GTK4/libadwaita GUI for the WiiM Amp."""
import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

STYLE_PATH = os.path.join(os.path.dirname(__file__), "style.css")

from wiim.client import WiimClient, decode_hex  # noqa: E402
from wiim.config import load_host  # noqa: E402
from wiim.mpris import MprisController  # noqa: E402

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
    LOOP_SET = {0: 0, 1: -1, 2: 1, 3: 2}   # dropdown index -> loopmode value
    LOOP_READ = {0: 1, 1: 2, 2: 3, 3: 3, 4: 0}  # getPlayerStatus.loop -> dropdown index

    def __init__(self, app, client):
        super().__init__(application=app, title="WiiM Amp")
        self.client = client
        self.set_default_size(380, 560)
        self._poll_in_flight = False
        self._suppress_source = True
        self._vol_timer = 0
        self._pending_vol = 0
        try:
            self.mpris = MprisController()
        except Exception:  # noqa: BLE001 - no session bus / no players
            self.mpris = None
        self._mpris_active = False

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        header = Adw.HeaderBar()
        gear = Gtk.Button(icon_name="emblem-system-symbolic")
        gear.connect("clicked", self._open_settings)
        header.pack_end(gear)
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
            ("media-skip-backward-symbolic", lambda *_: self._transport("previous", self.client.prev)),
            ("media-playback-start-symbolic", lambda *_: self._transport("play_pause", self.client.toggle)),
            ("media-skip-forward-symbolic", lambda *_: self._transport("next", self.client.next)),
            ("media-playback-stop-symbolic", lambda *_: self._transport("stop", self.client.stop)),
        ]:
            btn = Gtk.Button(icon_name=icon)
            btn.connect("clicked", handler)
            transport.append(btn)
            if icon == "media-playback-start-symbolic":
                self.playpause_btn = btn
        box.append(transport)

        # Mode row: mute + shuffle/repeat
        self._suppress_mute = False
        self._suppress_loop = True
        mode_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8,
                           halign=Gtk.Align.CENTER)
        self.mute_btn = Gtk.ToggleButton(icon_name="audio-volume-muted-symbolic")
        self.mute_btn.connect("toggled", self._on_mute)
        self.loop_drop = Gtk.DropDown.new_from_strings(
            ["No repeat", "Repeat all", "Repeat one", "Shuffle"])
        self.loop_drop.connect("notify::selected", self._on_loop)
        mode_row.append(self.mute_btn)
        mode_row.append(self.loop_drop)
        box.append(mode_row)

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

        # Volume (change-value fires on commit/scroll, not every drag pixel)
        self.volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume.set_hexpand(True)
        self.volume.connect("change-value", self._on_volume)
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

        # Presets
        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.preset_spin = Gtk.SpinButton.new_with_range(1, 12, 1)
        preset_play = Gtk.Button(label="Play preset")
        preset_play.connect("clicked", self._on_preset)
        preset_row.append(Gtk.Label(label="Preset"))
        preset_row.append(self.preset_spin)
        preset_row.append(preset_play)
        box.append(preset_row)

        self._load_eq_list()
        self._load_presets()
        self._tick()
        self._tick_source = GLib.timeout_add_seconds(1, self._tick)

    # --- helpers ---
    def _call(self, fn, on_done=None):
        run_async(fn, on_done or self._noop)

    def _transport(self, mpris_method, amp_fn):
        # Control the PC's media player if one is active (it owns AirPlay transport);
        # otherwise fall back to the amp's own playback.
        if self.mpris and self.mpris.active():
            try:
                getattr(self.mpris, mpris_method)()
            except Exception as exc:  # noqa: BLE001
                self._noop(None, exc)
        else:
            run_async(amp_fn, self._noop)

    def _noop(self, result, err):
        if err:
            self.title_lbl.set_label(f"error: {err}")
        return False

    # --- handlers ---
    def _on_volume(self, scale, scroll_type, value):
        self._pending_vol = max(0, min(100, int(value)))
        if self._vol_timer:
            GLib.source_remove(self._vol_timer)
        self._vol_timer = GLib.timeout_add(200, self._flush_volume)
        return False  # let the scale update its displayed value

    def _flush_volume(self):
        self._vol_timer = 0
        run_async(lambda: self.client.set_volume(self._pending_vol), self._noop)
        return False  # one-shot

    def _on_source(self, dropdown, _param):
        if self._suppress_source:
            return
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

    def _on_seek(self, scale, scroll_type, value):
        # No known duration -> seeking is meaningless (and would restart the track).
        if self._suppress_seek or self._duration_s <= 0:
            return False
        if self.mpris and self.mpris.active():
            self.mpris.set_position_s(int(value))
        else:
            run_async(lambda: self.client.seek(int(value)), self._noop)
        return False

    def _on_mute(self, btn):
        if self._suppress_mute:
            return
        active = btn.get_active()
        btn.set_icon_name(
            "audio-volume-muted-symbolic" if active else "audio-volume-high-symbolic")
        run_async(lambda: self.client.mute(active), self._noop)

    def _on_loop(self, dropdown, _param):
        if self._suppress_loop:
            return
        n = self.LOOP_SET.get(dropdown.get_selected(), 0)
        run_async(lambda: self.client.set_loop_mode(n), self._noop)

    def _on_preset(self, _btn):
        n = int(self.preset_spin.get_value())
        run_async(lambda: self.client.play_preset(n), self._noop)

    # --- data ---
    def _load_eq_list(self):
        def done(result, err):
            if result:
                self.eq_drop.set_model(Gtk.StringList.new(result))
            return False
        run_async(self.client.eq_list, done)

    def _load_presets(self):
        def done(status, err):
            if status:
                try:
                    n = int(status.get("preset_key", "0"))
                except (ValueError, TypeError):
                    n = 0
                if n > 0:
                    self.preset_spin.set_range(1, n)
            return False
        run_async(self.client.get_status, done)

    def _set_playing_icon(self, is_playing):
        self.playpause_btn.set_icon_name(
            "media-playback-pause-symbolic" if is_playing
            else "media-playback-start-symbolic")

    def _set_seek(self, cur, dur):
        self._duration_s = dur
        seekable = dur > 0
        self.seek.set_sensitive(seekable)
        self._suppress_seek = True
        self.seek.set_range(0, max(dur, 1))
        self.seek.set_value(min(cur, max(dur, 1)))
        self._suppress_seek = False
        if seekable:
            self.pos_lbl.set_label(f"{cur//60}:{cur%60:02d} / {dur//60}:{dur%60:02d}")
        else:
            self.pos_lbl.set_label("live · no duration")

    def _tick(self):
        # The PC media player (local, fast) drives now-playing + seek when present,
        # since that's the audio actually streaming to the amp over AirPlay.
        snap = None
        if self.mpris:
            try:
                snap = self.mpris.snapshot()
            except Exception:  # noqa: BLE001
                snap = None
        self._mpris_active = snap is not None
        if snap:
            self.title_lbl.set_label(snap["title"] or snap["player"])
            self.artist_lbl.set_label(snap["artist"] or snap["album"])
            self._set_seek(snap["position_s"], snap["length_s"])
            self._set_playing_icon(snap["status"] == "Playing")

        if self._poll_in_flight:
            return True
        self._poll_in_flight = True

        def done(status, err):
            self._poll_in_flight = False
            self._suppress_source = False  # first poll done; user changes now honored
            if err or not status:
                return False
            if not self._mpris_active:  # amp is the source of truth for now-playing
                title = status.get("Title") or status.get("vendor") or "—"
                artist = status.get("Artist", "")
                album = status.get("Album", "")
                self.title_lbl.set_label(title)
                self.artist_lbl.set_label(" — ".join(p for p in (artist, album) if p))
                self._set_playing_icon(status.get("status") == "play")
                try:
                    self._set_seek(int(status.get("curpos", "0")) // 1000,
                                   int(status.get("totlen", "0")) // 1000)
                except ValueError:
                    pass
            try:
                self.volume.set_value(int(status.get("vol", "0")))
            except ValueError:
                pass
            muted = status.get("mute") == "1"
            self._suppress_mute = True
            self.mute_btn.set_active(muted)
            self._suppress_mute = False
            self.mute_btn.set_icon_name(
                "audio-volume-muted-symbolic" if muted else "audio-volume-high-symbolic")
            try:
                idx = self.LOOP_READ.get(int(status.get("loop", "4")), 0)
                self._suppress_loop = True
                self.loop_drop.set_selected(idx)
                self._suppress_loop = False
            except ValueError:
                pass
            return False

        run_async(self.client.get_player_status, done)
        return True  # keep the timeout alive

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
                    if key == "essid":
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

    def do_close_request(self):
        if self._tick_source:
            GLib.source_remove(self._tick_source)
            self._tick_source = 0
        if self._vol_timer:
            GLib.source_remove(self._vol_timer)
            self._vol_timer = 0
        return False  # proceed with close


class WiimApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="net.local.WiimAmp")
        self.client = WiimClient(host=load_host())

    def do_activate(self):
        self._apply_eink_style()
        # Reuse the existing window on re-activation instead of opening another.
        win = self.props.active_window or WiimWindow(self, self.client)
        win.present()

    def _apply_eink_style(self):
        if getattr(self, "_styled", False):
            return
        self._styled = True
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        provider = Gtk.CssProvider()
        provider.load_from_path(STYLE_PATH)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER)


def main():
    return WiimApp().run(None)
