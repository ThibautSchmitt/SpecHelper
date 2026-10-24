"""Informative requirements inferred from declarative procedures, never permissions."""

import re
import unicodedata

BUILTIN_CAPABILITIES = {
    "attachment-analysis": {"read_attachments"},
    "codebase-navigation": {"read_sources"},
    "effective-navigation": {"read_sources"},
    "impact-analysis": {"read_sources"},
    "minimal-change": {"read_sources"},
    "project-conventions": {"read_sources"},
    "postgres-readonly-analysis": {"read_database"},
}
CAPABILITIES = {
    "read_sources",
    "read_attachments",
    "read_database",
    "read_web",
    "structured_output",
}


def inferred_capabilities(value):
    """Conservatively identify named resources; absence never enables a tool.

    Existing valid requirements remain restrictive metadata. The runtime decides
    access independently, including when natural language cannot be classified.
    """
    result = set(value.get("required_capabilities", [])) & CAPABILITIES
    result |= BUILTIN_CAPABILITIES.get(value.get("slug", ""), set())
    text = " ".join(str(value.get(key, "")) for key in ("name", "objective", "instructions"))
    text = "".join(
        c for c in unicodedata.normalize("NFKD", text).casefold() if not unicodedata.combining(c)
    )
    for capability, pattern in {
        "read_database": r"\b(?:sql|postgres(?:ql)?|database|base de donnees)\b",
        "read_sources": r"\b(?:source code|project sources|repository|repositories|code source|depot|depots)\b",
        "read_attachments": r"\b(?:attachments?|pieces? jointes?|screenshots?|captures? d.ecran)\b",
        "read_web": r"\b(?:web[- ]fetch|official (?:web )?sources|official documentation|sources officielles|documentation officielle)\b",
    }.items():
        if re.search(pattern, text):
            result.add(capability)
    return sorted(result)


def normalize_skill(payload):
    """Skills use both supported adapters; authoring contains no manual assignment."""
    return payload.model_copy(
        update={
            "compatibility": [],
            "required_capabilities": inferred_capabilities(payload.model_dump()),
        }
    )
