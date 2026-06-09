"""Control the PC's active media player over MPRIS (D-Bus via Gio).

The amp can't control an AirPlay stream's transport — the PC (sender) owns it.
So the GUI's transport/now-playing/seek act on whatever's playing on the PC
(Firefox, Spotify, VLC, ...) through this controller, with the amp as fallback.
No third-party deps: Gio ships with PyGObject.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

BUS_PREFIX = "org.mpris.MediaPlayer2."
OBJ_PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS_IFACE = "org.freedesktop.DBus.Properties"


def format_metadata(meta, status, position_us):
    """Pure: MPRIS metadata dict + status + position(microseconds) -> display fields."""
    title = meta.get("xesam:title") or ""
    artists = meta.get("xesam:artist") or []
    if isinstance(artists, (list, tuple)):
        artist = ", ".join(a for a in artists if a)
    else:
        artist = str(artists)
    album = meta.get("xesam:album") or ""
    length_s = int(meta.get("mpris:length") or 0) // 1_000_000
    position_s = int(position_us or 0) // 1_000_000
    return {
        "title": title,
        "artist": artist,
        "album": album,
        "length_s": length_s,
        "position_s": position_s,
        "status": status,
        "trackid": meta.get("mpris:trackid"),
    }


class MprisController:
    """Thin wrapper over the session bus targeting the active MPRIS player."""

    def __init__(self):
        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    def list_players(self):
        reply = self._bus.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus",
            "org.freedesktop.DBus", "ListNames", None,
            GLib.VariantType("(as)"), Gio.DBusCallFlags.NONE, -1, None)
        return [n for n in reply.unpack()[0] if n.startswith(BUS_PREFIX)]

    def _get(self, name, prop):
        reply = self._bus.call_sync(
            name, OBJ_PATH, PROPS_IFACE, "Get",
            GLib.Variant("(ss)", (PLAYER_IFACE, prop)),
            GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, -1, None)
        return reply.unpack()[0]

    def _status(self, name):
        try:
            return self._get(name, "PlaybackStatus")
        except GLib.Error:
            return ""

    def active(self):
        """Bus name of the player to control: a Playing one if any, else the first."""
        names = self.list_players()
        if not names:
            return None
        playing = [n for n in names if self._status(n) == "Playing"]
        return (playing or names)[0]

    def _call(self, name, method, params=None):
        self._bus.call_sync(name, OBJ_PATH, PLAYER_IFACE, method, params,
                            None, Gio.DBusCallFlags.NONE, -1, None)

    def play_pause(self):
        n = self.active()
        if n:
            self._call(n, "PlayPause")

    def next(self):
        n = self.active()
        if n:
            self._call(n, "Next")

    def previous(self):
        n = self.active()
        if n:
            self._call(n, "Previous")

    def stop(self):
        n = self.active()
        if n:
            self._call(n, "Stop")

    def set_position_s(self, seconds):
        n = self.active()
        if not n:
            return
        snap = self.snapshot(n)
        tid = snap and snap.get("trackid")
        if not tid:
            return
        try:
            self._call(n, "SetPosition",
                       GLib.Variant("(ox)", (tid, int(seconds) * 1_000_000)))
        except GLib.Error:
            pass  # player doesn't support seeking (e.g. Firefox)

    def snapshot(self, name=None):
        """Current player state, or None if no player is available."""
        name = name or self.active()
        if not name:
            return None
        try:
            meta = self._get(name, "Metadata")
            status = self._status(name)
            pos = self._get(name, "Position")
        except GLib.Error:
            return None
        snap = format_metadata(meta if isinstance(meta, dict) else {}, status, pos)
        snap["player"] = name[len(BUS_PREFIX):]
        return snap
