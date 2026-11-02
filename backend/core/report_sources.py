"""Audience-specific presentation of recorded sources; no inference or query execution."""

import re

from .i18n import translate


def _text(value):
    """Keep source metadata from introducing Markdown structure or executable HTML."""
    return (
        re.sub(r"([\\`*_{}\[\]()<>#!|])", r"\\\1", str(value)).replace("\n", " ").replace("\r", " ")
    )


def _quote(value):
    return "\n".join("> " + line for line in _text(value).splitlines())


def _code(value, language=""):
    # A source may itself contain fenced Markdown. Never let it escape its block.
    runs = [len(match.group()) for match in re.finditer(r"`+", value)]
    fence = "`" * max(3, max(runs, default=0) + 1)
    return f"{fence}{language}\n{value}\n{fence}"


def render_sources(sources, kind, language="en"):
    """Code supports business conclusions too, but raw code/SQL belongs in technical exports."""
    records = [
        source
        for source in sources
        if source.get("kind") != "sql" or source.get("status") == "checked"
    ]
    if not records:
        return ""

    def tr(value, **parameters):
        return translate(value, language, **parameters)

    lines = [
        "## " + tr("Recorded sources"),
        "",
        tr(
            "These sources belong to the selected answer version. A recorded source does not by itself verify a conclusion; the verification statuses and limits above still apply."
        ),
        "",
    ]
    technical = kind in {"technical", "mixed"}
    for index, source in enumerate(records, 1):
        source_kind = source.get("kind")
        label = {
            "git": "Source code",
            "sql": "Database check",
            "web": "Web reference",
            "document": "Document",
        }.get(source_kind)
        if not label:
            continue
        title = source.get("title") or tr(label)
        if source_kind == "git" and not technical:
            title = tr("Source code") + " · " + source.get("repository", "")
        lines += [f"### {index}. {_text(title)}", ""]
        if source_kind == "git":
            if technical:
                location = f"{source.get('repository', '')} · {source.get('commit', '')}"
                if source.get("line_start"):
                    location += f" · {source['line_start']}–{source.get('line_end') or source['line_start']}"
                lines += [_text(location), ""]
            elif source.get("excerpt"):
                lines += [
                    tr(
                        "The source excerpt and frozen Git reference are available in the technical report."
                    ),
                    "",
                ]
        elif source_kind == "sql":
            if source.get("row_count") is not None:
                lines += [tr("Rows returned: {count}", count=source["row_count"]), ""]
            if source.get("truncated"):
                lines += [tr("The recorded query result was truncated."), ""]
            if not source.get("sql"):
                lines += [tr("The executed query text was not retained."), ""]
            elif technical:
                lines += [_code(source.get("sql", ""), "sql"), ""]
            else:
                lines += [
                    tr(
                        "The executed query is available in the technical report. Returned row counts do not describe the whole business population."
                    ),
                    "",
                ]
        if source.get("url"):
            # Collector already validates public URLs and application download paths.
            url = (
                source["url"]
                .replace("<", "%3C")
                .replace(">", "%3E")
                .replace("\n", "")
                .replace("\r", "")
            )
            lines += [f"[{_text(tr('Open source'))}](<{url}>)", ""]
        if source.get("version") is not None:
            lines += [tr("Document version: {version}", version=source["version"]), ""]
        for applicability in source.get("applicability", []):
            for key, label in (
                ("applicability_notes", "Reference applicability"),
                ("effective_date", "Effective date"),
                ("version", "Version"),
                ("jurisdiction", "Jurisdiction"),
                ("scope", "Reference scope"),
            ):
                if applicability.get(key):
                    lines += [tr(label) + ": " + _text(applicability[key]), ""]
        excerpt = source.get("excerpt", "")
        if excerpt and (technical or source_kind == "web" and not source.get("note")):
            lines += [
                _code(excerpt)
                if technical
                else _quote(excerpt[:1200] + ("…" if len(excerpt) > 1200 else "")),
                "",
            ]
        if source_kind == "document" and not technical and source.get("url"):
            lines += [
                tr(
                    "The retained document is available from its source link; its preview is included in the technical report."
                ),
                "",
            ]
        if source.get("note"):
            lines += [tr(source["note"]), ""]
    return "\n".join(lines).rstrip() + "\n"
