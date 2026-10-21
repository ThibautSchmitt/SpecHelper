"""Immutable historical v1.1 defaults, stored as locale data."""

import json
from pathlib import Path

_data = json.loads(Path(__file__).with_name("locales").joinpath("v11.fr.json").read_text())
SKILLS = {slug: tuple(value) for slug, value in _data["skills"].items()}
PROFILES = _data["profiles"]
