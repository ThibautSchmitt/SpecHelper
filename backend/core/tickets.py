SECTIONS = {
    "context": "Context",
    "business_need": "Business need",
    "current_behavior": "Current behavior",
    "expected_behavior": "Expected behavior",
    "decisions": "Questions and decisions",
    "acceptance_criteria": "Acceptance criteria",
    "proposed_solution": "Proposed solution",
    "technical_analysis": "Technical analysis",
    "components": "Affected components / files / models",
    "database_impact": "Database impact",
    "risks": "Risks and considerations",
    "tests": "Expected tests",
}


def render_ticket(ticket, request):
    lines = ["# " + ticket["title"], ""]
    for key, label in SECTIONS.items():
        value = ticket[key]
        lines += [
            "## " + label,
            "",
            value if isinstance(value, str) else "\n".join("- " + item for item in value),
            "",
        ]
    lines += ["## Baseline Git", ""]
    lines += [f"- {r['repository']} · {r['branch']} · `{r['sha']}`" for r in request.baseline]
    lines += [
        "",
        "## Database",
        "",
        request.database_snapshot.get("name", "None"),
        "",
        "## Attachments",
        "",
    ]
    lines += ["- " + a.name for a in request.attachments.all()] or ["None"]
    return "\n".join(lines) + "\n"
