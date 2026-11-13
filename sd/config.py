"""Reads config.json (which symbols to watch)."""
import json

from .env import ROOT


def load():
    return json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
