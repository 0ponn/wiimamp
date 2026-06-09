import os
import tempfile
import unittest
from wiim.config import load_host
from wiim.client import DEFAULT_HOST


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.addCleanup(os.environ.pop, "XDG_CONFIG_HOME", None)

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


if __name__ == "__main__":
    unittest.main()
