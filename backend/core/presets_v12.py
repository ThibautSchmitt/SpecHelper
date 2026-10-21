"""Versioned v1.2 defaults; v1.1 migration defaults remain immutable."""

import json
from copy import deepcopy
from pathlib import Path

from .presets_v11 import PROFILES as V11_PROFILES
from .presets_v11 import SKILLS as SKILLS

PROFILES = deepcopy(V11_PROFILES)
PROFILES["reviewer"]["name"] = "Reviewer / Critic"
PROFILES["writer"]["instructions"] = json.loads(
    Path(__file__).with_name("locales").joinpath("v12.fr.json").read_text()
)["writer_instructions"]
