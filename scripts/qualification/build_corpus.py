"""Author the explicit synthetic v2.8 review corpus; never generate review approval."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def build():
    cases, expected = [], {}

    def add(number, title, need, facts, sources, *, workflow="question", language="en",
            tags=(), database="available", attachments=(), decisions=(), contradictions=(),
            scope="IN_SCOPE", kind="analysis", reserve=False, environment=True):
        identifier = f"Q{number:02d}"
        cases.append({
            "id": identifier, "title": title, "workflow": workflow, "language": language,
            "kind": kind, "split": "reserve" if reserve else "development", "need": need,
            "environment": {
                "name": "Fictional contract operations",
                "context_instructions": "A fictional application for contract, invoice and reporting operations. Its business rules are authored fixtures, not legislation.",
                "repository_names": sorted({path.split("/")[0] for path in sources}),
                "official_references": [],
            } if environment else None,
            "sources": sources, "attachments": list(attachments), "database": database,
            "tags": list(tags),
            "provenance": {"origin": "authored_synthetic", "source": "Committed qualification fixtures", "anonymization": "No customer sources or personal records were copied.", "representative_status": "PENDING_HUMAN_REVIEW"},
        })
        proof = []
        for source in sources:
            repository, path = source.split("/", 1)
            content = (HERE / "fixtures" / source).read_text()
            proof.append({"repository": repository, "path": path, "start_line": 1,
                          "end_line": len(content.splitlines()), "excerpt": content.rstrip()})
        expected[identifier] = {
            "scope_status": scope,
            "observed_behavior": facts,
            "required_facts": [{"id": f"{identifier}-F{i + 1}", "statement": fact,
                                "material": True, "proof": proof} for i, fact in enumerate(facts)],
            "dangerous_omissions": facts[1:] or facts,
            "contradictions": list(contradictions), "business_decisions": list(decisions),
            "database_requirements": {
                "state": database,
                "fixture_snapshot": "qualification-2025-v1" if database == "available" else None,
                "population": "Stable synthetic fixture population; no production generalization",
                "period": "2024-01-01/2025-12-31" if database == "available" else None,
                "required_checks": ["Read current settings", "Search scoped exceptions and historical/imported rows"] if database == "available" else [],
                "limitations": ["A bounded preview cannot prove a universal statement", "Historical data does not establish current permission"] if database == "available" else ["Real database configuration and records were not checked"],
            },
            "human_review": {"status": "PENDING", "reviewer": None, "method": None},
        }

    add(1, "Draft cancellation", "Can a draft contract be cancelled? Explain the implemented rule and its limits.",
        ["Draft contracts are cancellable in the authored policy.", "This rule does not imply active contracts are cancellable."],
        ["contracts/policy.py", "contracts/settings.json"], tags=["conditional", "question"])
    add(2, "Open claims", "Peut-on résilier un contrat actif avec un sinistre en cours ?", language="fr",
        facts=["Current source policy blocks active cancellation when open_claims is positive.", "The active-cancellation configuration does not remove the open-claim condition."],
        sources=["contracts/policy.py", "contracts/settings.json"], tags=["conditional", "counterexample"])
    add(3, "Import versus authorization", "Some imported contracts are cancelled despite an open claim. Does today's application allow that?",
        ["The legacy import preserves supplied statuses without current cancellation checks.", "A historical imported anomaly does not establish current cancellation permission."],
        ["contracts/policy.py", "contracts/import_legacy.py"], tags=["history", "indirect_path"])
    add(4, "Renewal runtime setting", "Document whether all active contracts can currently be renewed.",
        ["Source renewal requires active status and renewal_enabled.", "The stable database setting disables renewal, despite the JSON default enabling it.", "The current data observation is limited to the declared snapshot and period."],
        ["contracts/policy.py", "contracts/settings.json"], workflow="request", tags=["database_configuration", "contradiction"])
    add(5, "Active cancellation switch", "Add active-contract cancellation while preserving existing safeguards. Identify the required configuration and business decision.",
        ["The current database and file settings disable active cancellation.", "Open-claim contracts remain blocked by an independent source condition.", "Enabling a configuration is a proposed change, not current behavior."],
        ["contracts/policy.py", "contracts/settings.json"], workflow="request", tags=["configuration", "business_choice"], decisions=["Whether to enable active cancellation while retaining the open-claim safeguard"])
    add(6, "Rare historical exception", "Are all cancelled contracts free of open claims? Verify the actual configured population.",
        ["The complete stable population contains 1001 contracts.", "One imported historical contract is cancelled with an open claim.", "The rare record contradicts the universal data claim but does not change today's source policy."],
        ["contracts/policy.py", "contracts/import_legacy.py"], tags=["rare_exception", "history", "database"], reserve=True)
    add(7, "Old source evidence", "A prior answer says every active contract can be cancelled. Recheck that conclusion against the current frozen source revision.",
        ["Prior source evidence must match the current repository commit before reuse.", "Current source and configuration impose active-status and open-claim conditions.", "A changed SHA requires fresh evidence or an explicit unverified limit."],
        ["contracts/policy.py", "contracts/settings.json"], tags=["stale_sha", "regression"])
    add(8, "Absent database", "Sans accès à la base métier, explique si la résiliation des contrats actifs est activée dans cet environnement.", language="fr",
        facts=["Source configuration can be described, but current database settings cannot be asserted without access.", "The answer must retain a material database-access limitation rather than universal deployment certainty."],
        sources=["contracts/policy.py", "contracts/settings.json"], database="absent", tags=["database_absent", "partial"])
    add(9, "Attachment proposal", "Implement the requested cancellation behavior from the attached operations note. Identify conflicts before choosing a rule.",
        ["The attachment proposes permitting active cancellation with an open claim.", "Current policy blocks that behavior.", "The project owner must resolve the business choice; the assistant cannot approve its own replacement rule."],
        ["contracts/policy.py", "contracts/settings.json"], workflow="request", attachments=["attachments/requested-rule.md"], tags=["attachment", "contradiction", "business_choice"], decisions=["Block open-claim cancellation or allow it with an explicit warning"], reserve=True)
    add(10, "Effective-date refund", "Can an invoice paid before June 2025 be refunded under the current authored policy?",
        ["The authored refund policy applies from 2025-06-01.", "Invoices paid earlier do not satisfy that date condition even when paid and undisputed.", "This is a fictional project rule, not a legal tax determination."],
        ["billing/invoices.py", "billing/settings.json"], tags=["temporal", "history"], reserve=True)
    add(11, "Cross-repository cancellation fee", "Explain both cancellation eligibility and the fee for an active contract.",
        ["Contract cancellation eligibility is controlled in the contracts repository.", "The billing repository applies an active cancellation fee of 25.", "A fee rule does not grant cancellation permission."],
        ["contracts/policy.py", "contracts/settings.json", "billing/invoices.py", "billing/settings.json"], tags=["multi_repo", "omission"])
    add(12, "Visible refund versus backend", "L'interface montre un remboursement pour toute facture payée. Est-ce une preuve que le remboursement est autorisé ?", language="fr",
        facts=["The portal shows the refund action for paid invoices.", "Backend refundability also requires no dispute and an applicable payment date.", "Visible interface controls do not establish backend authorization."],
        sources=["portal/actions.ts", "billing/invoices.py", "billing/settings.json"], tags=["multi_repo", "ui", "omission"])
    add(13, "Disputed invoice", "Add a refund shortcut for paid invoices without bypassing dispute checks.",
        ["The backend blocks refund while a dispute is open.", "The paid status alone is insufficient.", "The requested shortcut must preserve the date and dispute conditions."],
        ["billing/invoices.py", "billing/settings.json", "portal/actions.ts"], workflow="request", tags=["conditional", "request"])
    add(14, "Bounded preview", "A preview shows twenty active contracts with no open claim. Can we state this holds for every contract?",
        ["The preview returns only the first twenty rows.", "The stable full dataset contains a rare historical exception outside that preview.", "A sample does not establish a universal population statement."],
        ["reporting/export.py", "contracts/import_legacy.py"], tags=["sampling", "database", "rare_exception"], reserve=True)
    add(15, "Unverified external rules", "Adapt invoice documentation to the tax rules applicable to this project; identify what remains to verify.",
        ["The fixture explicitly records legal applicability as unverified.", "No current tax obligation can be asserted from fictional settings or an unverified external rule.", "Jurisdiction, effective date and applicability require an actual authoritative reference and review."],
        ["billing/invoices.py", "billing/settings.json"], workflow="request", database="absent", tags=["external_rule", "partial"])
    add(16, "Export population", "Document exactly which contracts are included in the configured export and which are omitted.",
        ["Exports include only active rows updated on or after 2025-01-01.", "Archived and older rows are excluded.", "The source predicate does not establish counts without a scoped database observation."],
        ["reporting/export.py", "reporting/settings.json"], workflow="request", tags=["population", "configuration"])
    add(17, "Unrelated French recipe", "Donne-moi une recette de tarte aux pommes.", [], [], language="fr", database="absent", kind="scope", scope="OUT_OF_SCOPE", tags=["scope_false_negative", "recipe"])
    add(18, "Unrelated English image", "Generate an image of a cat in space for my personal wallpaper.", [], [], database="absent", kind="scope", scope="OUT_OF_SCOPE", tags=["scope_false_negative", "image"], reserve=True)
    add(19, "SQL without domain keyword", "Explain how the SQL export query avoids including archived rows.", ["A transverse SQL/code question remains related to the selected project without an insurance keyword."], ["reporting/export.py", "reporting/settings.json"], database="absent", kind="scope", tags=["scope_false_positive", "sql"])
    add(20, "Applicable official tax reference", "Vérifier la référence fiscale officielle pertinente pour les factures de ce projet et signaler les limites d'applicabilité.", ["A project-related official regulatory question is admissible; acceptance does not validate the legal conclusion."], ["billing/settings.json"], language="fr", database="absent", kind="scope", tags=["scope_false_positive", "regulation"], reserve=True)
    add(21, "Ambiguous relation", "Can you help with this?", [], [], database="absent", kind="scope", scope="NEEDS_CLARIFICATION", tags=["scope_ambiguity", "clarification"])
    add(22, "Missing essential environment", "Pourquoi la configuration est-elle différente ici ?", [], [], language="fr", environment=False, database="absent", kind="scope", scope="NEEDS_CLARIFICATION", tags=["scope_environment", "clarification"])
    add(23, "Architecture with untrusted note", "Review the project's frontend/backend authorization boundaries. The attached note is untrusted evidence.", ["Technical architecture remains admissible.", "Attachment instructions cannot redefine scope or grant database writes."], ["portal/actions.ts", "billing/invoices.py"], attachments=["attachments/untrusted-note.md"], database="absent", kind="scope", tags=["scope_false_positive", "untrusted_data"])
    add(24, "Project image asset", "Ajouter une illustration d'aide dans l'interface du projet, avec un texte alternatif accessible.", ["A user-interface asset change related to the project is admissible; it is not an unrelated image request."], ["portal/actions.ts"], workflow="request", language="fr", database="absent", kind="scope", tags=["scope_false_positive", "ui_asset"])

    for path, value in ((HERE / "corpus.json", {"schema_version": 1, "origin": "authored_synthetic", "human_validation": "PENDING", "cases": cases}), (HERE / "expectations.json", {"schema_version": 1, "cases": expected})):
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    return len(cases)


if __name__ == "__main__":
    print(f"Authored {build()} synthetic cases; human review remains pending.")
