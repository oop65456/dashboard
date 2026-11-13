"""Loads API keys without ever printing them.

Where keys come from, first match wins:
  1. Environment variables (this is how GitHub Actions passes its Secrets in).
  2. The .env file in this project folder.
This project never reads files outside its own folder.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # the signal-dashboard folder

KEY_NAMES = ["APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "TWELVEDATA_API_KEY",
             "COINGECKO_API_KEY", "FRED_API_KEY", "FINNHUB_API_KEY", "GITHUB_TOKEN", "DASHBOARD_PASSPHRASE"]


def _read_env_file(path):
    """Read NAME=value lines from a .env file into a dict (comments and blank lines skipped)."""
    values = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:                                       # an empty "NAME=" doesn't count as set
            values[name.strip()] = value
    return values


def load():
    """Put every key found into os.environ without overwriting ones already set."""
    for name, value in _read_env_file(ROOT / ".env").items():
        os.environ.setdefault(name, value)


def get(name):
    """Return a key's value, or None if it isn't set anywhere."""
    value = os.environ.get(name, "").strip()
    return value or None


def secrets():
    """All key values currently set, so error messages can be scrubbed before printing."""
    return [v for v in (get(n) for n in KEY_NAMES) if v]


def scrub(text):
    """Replace any key value inside a message with ***, e.g. a URL that carried ?apikey=..."""
    text = str(text)
    for value in secrets():
        text = text.replace(value, "***")
    return text
