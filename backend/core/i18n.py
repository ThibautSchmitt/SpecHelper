"""Small locale catalog shared by artifact rendering and immutable historical seeds."""

import json
from pathlib import Path

FRENCH = json.loads(Path(__file__).with_name("locales").joinpath("fr.json").read_text())
ENGLISH_KEYS = {value: key for key, value in FRENCH.items()}
LEGACY = json.loads(
    Path(__file__).with_name("locales").joinpath("legacy_migrations.fr.json").read_text()
)


def translate(text, language="en", **parameters):
    key = ENGLISH_KEYS.get(text, text)
    value = FRENCH.get(key, key) if language == "fr" else key
    return value.format_map(parameters) if parameters else value


def legacy(text):
    """Keep historical migration data byte-for-byte while source identifiers are English."""
    return LEGACY[text]
