"""Source-first navigation and explicit limits shared by independent analysis roles."""

from copy import deepcopy

from .presets_v16 import PROFILES as PREVIOUS_PROFILES
from .presets_v16 import SKILLS as PREVIOUS_SKILLS

NAVIGATION_INSTRUCTIONS = (
    "Locate before reading: inspect the repository map and relevant manifests, search exact "
    "symbols and callers, then read bounded source ranges at the frozen Git commit. Follow "
    "dependencies, configuration, temporal conditions and alternative execution paths before "
    "generalizing a business rule. Expand exploration whenever missing evidence, a contradiction "
    "or a possible counterexample requires it; token savings never justify omitted review. "
    "Share compact structured claims, exact source references, scope, exceptions and open "
    "questions rather than full files or conversation transcripts. Each public role keeps its "
    "own independent session. An optional structural index only suggests navigation targets: "
    "verify its repository/environment authorization and frozen commit, reopen actual code, "
    "and never use an index hit as proof. Without an authorized matching index, use ordinary "
    "Git/symbol/text navigation. Do not assume a language, framework, domain or preinstalled "
    "indexing service. Do not install tools, execute project code, widen network access or read "
    "another environment to improve navigation. Preserve all central runtime restrictions."
)

VERIFICATION_INSTRUCTIONS = (
    " Decompose decisive claims into subject, quantifier, time, population, conditions and "
    "assumed exceptions. Actively seek cases where the claim fails rather than confirming "
    "only its nominal path. Relate code and data structures before querying an available "
    "read-only database. Prefer bounded existence checks, counts and state/configuration "
    "distributions to large extracts. Distinguish historical anomalies from currently allowed "
    "application behavior. No counterexample found means only none found within the checked "
    "scope. With an absent or inaccessible database, explicitly report that actual data was "
    "not checked. Keep observed facts, interpretations, contradictions, unknowns and human "
    "business decisions separate. Never invent numerical confidence or universal certification."
)

SKILLS = deepcopy(PREVIOUS_SKILLS)
SKILLS["effective-navigation"] = ("Effective source navigation", NAVIGATION_INSTRUCTIONS)
PROFILES = deepcopy(PREVIOUS_PROFILES)
for slug in ("code", "reviewer", "writer"):
    PROFILES[slug]["skills"] = list(
        dict.fromkeys([*PROFILES[slug]["skills"], "effective-navigation"])
    )
PROFILES["code"]["instructions"] += VERIFICATION_INSTRUCTIONS
PROFILES["reviewer"]["instructions"] += VERIFICATION_INSTRUCTIONS
