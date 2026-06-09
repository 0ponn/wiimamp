"""Load the amp host from ~/.config/wiim/config (INI), defaulting to mDNS name."""
import configparser
import os

from wiim.client import DEFAULT_HOST


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "wiim", "config")


def config_host():
    """The explicit host from the config file, or None if not set."""
    cp = configparser.ConfigParser()
    if cp.read(config_path()) and cp.has_option("device", "host"):
        return cp.get("device", "host")
    return None


def load_host():
    """Resolved host for immediate use: config value, else the mDNS fallback.

    mDNS auto-discovery (wiim.discovery) runs separately and overrides this when
    no explicit config host is set.
    """
    return config_host() or DEFAULT_HOST
