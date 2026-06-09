import unittest

from wiim.mpris import format_metadata


class TestFormatMetadata(unittest.TestCase):
    def test_full(self):
        meta = {
            "xesam:title": "Song",
            "xesam:artist": ["A", "B"],
            "xesam:album": "Alb",
            "mpris:length": 240_000_000,
            "mpris:trackid": "/org/x/1",
        }
        d = format_metadata(meta, "Playing", 60_000_000)
        self.assertEqual(d["title"], "Song")
        self.assertEqual(d["artist"], "A, B")
        self.assertEqual(d["album"], "Alb")
        self.assertEqual(d["length_s"], 240)
        self.assertEqual(d["position_s"], 60)
        self.assertEqual(d["status"], "Playing")
        self.assertEqual(d["trackid"], "/org/x/1")

    def test_empty(self):
        d = format_metadata({}, "Stopped", 0)
        self.assertEqual(d["title"], "")
        self.assertEqual(d["artist"], "")
        self.assertEqual(d["album"], "")
        self.assertEqual(d["length_s"], 0)
        self.assertEqual(d["position_s"], 0)
        self.assertIsNone(d["trackid"])

    def test_artist_string_fallback(self):
        d = format_metadata({"xesam:artist": "Solo"}, "Paused", 0)
        self.assertEqual(d["artist"], "Solo")


if __name__ == "__main__":
    unittest.main()
