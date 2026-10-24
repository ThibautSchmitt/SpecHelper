"""Historical importer differs from the current application cancellation path."""


def import_legacy_order(row):
    return {**row, "status": "cancelled", "origin": "legacy_import"}
