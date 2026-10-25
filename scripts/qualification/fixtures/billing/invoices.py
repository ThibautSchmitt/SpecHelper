"""Fictional invoice constraints; no actual tax or insurance rule is asserted."""


def refundable(invoice, settings):
    return (
        invoice["status"] == "paid"
        and invoice["dispute_open"] is False
        and invoice["paid_on"] >= settings["refund_policy_effective_from"]
    )


def cancellation_fee(contract, settings):
    if contract["status"] == "draft":
        return 0
    return settings["active_cancellation_fee"]
