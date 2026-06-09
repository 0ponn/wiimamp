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

    def test_seek_clamps_negative(self):
        with self._capture() as m:
            self.c.seek(-5)
            m.assert_called_once_with("setPlayerCmd:seek:0")

    def test_eq_list_parses(self):
        with mock.patch.object(self.c, "_command", return_value='["Flat","Rock"]'):
            self.assertEqual(self.c.eq_list(), ["Flat", "Rock"])

    def test_source_invalid_raises(self):
        with self.assertRaises(ValueError):
            self.c.set_source("hdmi")

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


if __name__ == "__main__":
    unittest.main()
