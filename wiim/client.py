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
        return self._command(f"setPlayerCmd:seek:{max(0, int(seconds))}")

    # volume
    def set_volume(self, value):
        value = max(0, min(100, int(value)))
        return self._command(f"setPlayerCmd:vol:{value}")

    def mute(self, on):
        return self._command(f"setPlayerCmd:mute:{1 if on else 0}")

    # source
    def set_source(self, name):
        mode = self.SOURCES.get(name)
        if mode is None:
            raise ValueError(f"unknown source {name!r}, valid: {list(self.SOURCES)}")
        return self._command(f"setPlayerCmd:switchmode:{mode}")

    # eq
    def eq_on(self):
        return self._command("EQOn")

    def eq_off(self):
        return self._command("EQOff")

    def eq_stat(self):
        return self._command_json("EQGetStat")

    def eq_list(self):
        return self._command_json("EQGetList")

    def eq_load(self, name):
        return self._command(f"EQLoad:{urllib.parse.quote(name)}")

    # presets (command confirmed in Task 4)
    def play_preset(self, n):
        return self._command(f"setPlayerCmd:preset:{int(n)}")

    # device
    def reboot(self):
        return self._command("reboot")

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

    # state
    def get_status(self):
        return self._command_json("getStatusEx")

    def get_player_status(self):
        data = self._command_json("getPlayerStatus")
        for key in ("Title", "Artist", "Album"):
            if key in data:
                data[key] = decode_hex(data[key])
        return data
