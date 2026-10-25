"""Fictional contract rules used only by the qualification corpus."""


def can_cancel(contract, settings):
    if contract["status"] == "draft":
        return True
    if contract["status"] != "active" or contract["open_claims"] > 0:
        return False
    return bool(settings["allow_active_cancellation"])


def can_renew(contract, settings):
    return contract["status"] == "active" and settings["renewal_enabled"]
