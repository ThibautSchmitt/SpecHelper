"""Require complete artifact prose to follow the request's output language."""

from copy import deepcopy

from .presets_v13 import PROFILES as PREVIOUS_PROFILES
from .presets_v13 import SKILLS as SKILLS

PROFILES = deepcopy(PREVIOUS_PROFILES)
PROFILES["writer"]["instructions"] += (
    " Write all narrative content of ticket.md and goal.md in output_language, including "
    "the title, business explanation, technical guidance, risks and acceptance criteria. "
    "Rephrase source observations in that language even when sources or instructions "
    "are in another language. Preserve filenames, code identifiers, paths, commands and "
    "source quotations. Check language consistency before returning both artifacts."
)
