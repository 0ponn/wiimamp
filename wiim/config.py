"""Load the amp host from ~/.config/wiim/config (INI), defaulting to mDNS name."""
import configparser
import os

from wiim.client import DEFAULT_HOST


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "wiim", "config")


def load_host():
    cp = configparser.ConfigParser()
    if cp.read(config_path()) and cp.has_option("device", "host"):
        return cp.get("device", "host")
    return DEFAULT_HOST
