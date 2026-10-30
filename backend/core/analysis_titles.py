"""Deterministic presentation titles; business needs and results stay unchanged."""

import re


def analysis_title(value):
    if value.display_title:
        return value.display_title
    first_line = next((line.strip() for line in value.need.splitlines() if line.strip()), "")
    text = re.split(r"(?<=[.!?])\s+", first_line, maxsplit=1)[0]
    text = " ".join(text.split())
    if len(text) <= 80:
        return text
    prefix = text[:80].rsplit(" ", 1)[0]
    return (prefix or text[:80]).rstrip(" ,:;-") + "…"
