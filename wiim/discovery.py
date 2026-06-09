"""Find a WiiM/LinkPlay device on the LAN via Avahi (mDNS) over D-Bus.

Zero third-party deps: Gio ships with PyGObject. Browses _raop._tcp (every WiiM
advertises AirPlay) and returns the first matching device's .local hostname, so
the amp doesn't have to be hardcoded. Falls back gracefully (returns None) if
Avahi isn't available or nothing is found.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

AVAHI = "org.freedesktop.Avahi"
IF_UNSPEC = -1
PROTO_INET = 0  # IPv4 only — avoids duplicate IPv6 link-local hits
SERVICE_TYPE = "_raop._tcp"


def is_wiim(name, txt):
    """True if an mDNS service (name + TXT 'key=value' list) is a WiiM/LinkPlay device."""
    if "wiim" in (name or "").lower():
        return True
    for entry in txt:
        e = entry.lower()
        if e.startswith("am=") and "wiim" in e:
            return True
        if "linkplay" in e:
            return True
    return False


def _txt_to_strings(txt_aay):
    out = []
    for b in txt_aay:
        try:
            out.append(bytes(b).decode("utf-8", "replace"))
        except (TypeError, ValueError):
            pass
    return out


def discover_wiim(timeout=2.0):
    """Hostname (e.g. 'WiiM-Amp-FCB2.local') of the first WiiM found, or None.

    Safe to call from a worker thread: runs in its own main context.
    """
    ctx = GLib.MainContext.new()
    ctx.push_thread_default()
    found = {"host": None}
    try:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            reply = bus.call_sync(
                AVAHI, "/", AVAHI + ".Server", "ServiceBrowserNew",
                GLib.Variant("(iissu)", (IF_UNSPEC, PROTO_INET, SERVICE_TYPE, "local", 0)),
                GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error:
            return None
        browser_path = reply.unpack()[0]
        loop = GLib.MainLoop.new(ctx, False)

        def on_item_new(conn, sender, path, iface, signal, params):
            interface, protocol, name, stype, domain, _flags = params.unpack()
            try:
                res = bus.call_sync(
                    AVAHI, "/", AVAHI + ".Server", "ResolveService",
                    GLib.Variant("(iisssiu)",
                                 (interface, protocol, name, stype, domain, PROTO_INET, 0)),
                    None, Gio.DBusCallFlags.NONE, -1, None)
            except GLib.Error:
                return
            vals = res.unpack()
            host, txt = vals[5], _txt_to_strings(vals[9])
            if is_wiim(name, txt):
                found["host"] = host
                loop.quit()

        sub = bus.signal_subscribe(
            AVAHI, AVAHI + ".ServiceBrowser", "ItemNew", browser_path, None,
            Gio.DBusSignalFlags.NONE, on_item_new)
        source = GLib.timeout_source_new(int(timeout * 1000))
        source.set_callback(lambda *_: (loop.quit(), GLib.SOURCE_REMOVE)[1])
        source.attach(ctx)
        loop.run()
        source.destroy()
        bus.signal_unsubscribe(sub)
        try:
            bus.call_sync(AVAHI, browser_path, AVAHI + ".ServiceBrowser", "Free",
                          None, None, Gio.DBusCallFlags.NONE, -1, None)
        except GLib.Error:
            pass
    finally:
        ctx.pop_thread_default()
    return found["host"]
