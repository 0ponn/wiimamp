"""Live smoke test for WiiM Amp via real network requests.

Only runs when WIIM_LIVE=1 is set. These are read-only queries that do not
change the amp's state.

To run:
  WIIM_LIVE=1 python3 -m unittest tests.test_live -v

To skip (default):
  python3 -m unittest tests.test_live -v
"""

import os
import unittest
from wiim.client import WiimClient


@unittest.skipUnless(os.environ.get("WIIM_LIVE") == "1", "set WIIM_LIVE=1 to run")
class TestLive(unittest.TestCase):
    """Live smoke tests against real WiiM Amp (read-only)."""

    def setUp(self):
        self.c = WiimClient()

    def test_get_status(self):
        """Fetch device status; confirm DeviceName present."""
        s = self.c.get_status()
        self.assertIn("DeviceName", s)

    def test_get_player_status(self):
        """Fetch player status; confirm status field present."""
        s = self.c.get_player_status()
        self.assertIn("status", s)

    def test_eq_list(self):
        """Fetch EQ presets; confirm Flat is available."""
        eqs = self.c.eq_list()
        self.assertIsInstance(eqs, list)
        self.assertIn("Flat", eqs)


if __name__ == "__main__":
    unittest.main()
