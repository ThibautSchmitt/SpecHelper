"""Generic project conventions and on-demand reference exploration."""

from copy import deepcopy

from .presets_v14 import PROFILES as PREVIOUS_PROFILES
from .presets_v14 import SKILLS as PREVIOUS_SKILLS

SKILLS = deepcopy(PREVIOUS_SKILLS)
SKILLS.pop("tryton-coog")
SKILLS["project-conventions"] = (
    "Project conventions and references",
    "Discover the actual stack, installed dependency versions and project conventions from "
    "sources and manifests. Do not assume a framework or API. Consult relevant environment "
    "reference files on demand rather than reading everything. Flag stale or contradictory "
    "documentation; prioritize inspected code for implementation behavior. Separate verified "
    "evidence, inferences, constraints and open questions. Cite paths and baseline SHAs.",
)
PROFILES = deepcopy(PREVIOUS_PROFILES)
for profile in PROFILES.values():
    profile["skills"] = [
        "project-conventions" if slug == "tryton-coog" else slug for slug in profile["skills"]
    ]
