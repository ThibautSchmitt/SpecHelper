"""A historical import path; it is not current user-interface authorization."""


def import_contract(row):
    return {"status": row["status"], "open_claims": row.get("open_claims", 0)}
