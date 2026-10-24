"""Plain-language scoped conclusions in immutable exports, without confidence scores."""

from .i18n import translate

STATUS = {
    "supported": "Supported",
    "partial": "Partially supported",
    "contradicted": "Contradicted",
    "unverified": "Unverified",
}


def render_evidence(report, language="en"):
    if not report:
        return ""
    lines = ["## " + translate("Checked conclusions and limits", language), ""]
    database = report.get("database", {})
    state = {
        "not_configured": "No business database is configured. Real records were not checked.",
        "not_checked": "Real business records have not been checked.",
        "unavailable": "The business database could not be checked.",
        "checked": "Database observations apply only to the queried population and time.",
    }
    lines += [translate(state.get(database.get("status"), state["not_checked"]), language), ""]
    for claim in report.get("claims", []):
        lines += ["### " + claim["statement"], "", translate(STATUS[claim["status"]], language), ""]
        scope = claim["scope"]
        for key, label in (
            ("environment", "Environment"),
            ("conditions", "Conditions"),
            ("period", "Observation period"),
            ("population", "Checked population"),
            ("sample_limits", "Observation limits"),
        ):
            value = scope.get(key)
            if value:
                lines += [
                    translate(label, language)
                    + ": "
                    + ("; ".join(value) if isinstance(value, list) else value),
                    "",
                ]
        for item in claim.get("counterexamples", []):
            lines += [translate("Observed exception", language) + ": " + item["description"], ""]
        if claim.get("verification_notes"):
            lines += [
                "\n".join(
                    translate(item, language) for item in claim["verification_notes"].splitlines()
                ),
                "",
            ]
        for source in claim.get("sources", []):
            if source["kind"] == "git":
                lines += [
                    f"{source['repository']} · `{source['commit']}` · `{source['path']}`:{source['line_start']}-{source['line_end']}",
                    "",
                ]
            elif source["kind"] == "web":
                receipt = next(
                    (
                        row
                        for row in report.get("web_references", [])
                        if row["reference_id"] == source["reference_id"]
                    ),
                    None,
                )
                if receipt:
                    lines += [
                        translate("External reference", language) + ": " + receipt["title"],
                        receipt["url"],
                        translate("Consulted on", language) + ": " + receipt["consulted_at"],
                        "SHA-256: " + receipt["sha256"],
                        translate("Reference applicability", language)
                        + ": "
                        + source["applicability_notes"],
                        "",
                    ]
                    for key, label in (
                        ("effective_date", "Effective date"),
                        ("version", "Version"),
                        ("jurisdiction", "Jurisdiction"),
                        ("scope", "Reference scope"),
                    ):
                        if source.get(key):
                            lines += [translate(label, language) + ": " + source[key], ""]
            else:
                receipt = next(
                    (
                        row
                        for row in database.get("checks", [])
                        if row["query_id"] == source["query_id"]
                    ),
                    None,
                )
                if receipt:
                    lines += [
                        translate("Authorized database observation", language)
                        + f": {receipt['query_id']} · {receipt['checked_at']}",
                        "",
                    ]
    for item in [*database.get("limitations", []), *report.get("limitations", [])]:
        lines += ["- " + translate(item, language)]
    return "\n".join(lines).rstrip() + "\n"
