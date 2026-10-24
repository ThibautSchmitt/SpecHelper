"""Synthetic order cancellation policy; no business source is included."""


def cancellation_allowed(order, settings):
    if order["status"] != "open":
        return False
    if order["kind"] == "subscription" and settings["block_active_services"]:
        return order["active_services"] == 0
    return True
