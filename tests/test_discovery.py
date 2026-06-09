import unittest

from wiim.discovery import is_wiim


class TestIsWiim(unittest.TestCase):
    def test_name_match(self):
        self.assertTrue(is_wiim("9EB8B4C2BCB2@WiiM Amp-FCB2", []))

    def test_txt_am_match(self):
        self.assertTrue(is_wiim("somebox", ["am=WiiM Amp", "vs=366.0"]))

    def test_txt_linkplay_match(self):
        self.assertTrue(is_wiim("box", ["manufacturer=LinkPlay Technology Inc."]))

    def test_no_match(self):
        self.assertFalse(is_wiim("Living Room HomePod", ["am=AirPort"]))

    def test_empty(self):
        self.assertFalse(is_wiim("", []))


if __name__ == "__main__":
    unittest.main()
