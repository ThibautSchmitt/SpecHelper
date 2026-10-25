"""Scoped export from a read-only fixture population."""


def exportable(row, settings):
    return row["status"] == "active" and row["updated_on"] >= settings["export_from"]


def preview(rows):
    return rows[:20]
