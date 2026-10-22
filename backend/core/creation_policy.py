"""Freeze the configured analysis policy when a business item is created."""

from .models import AIConnection, InstanceSettings
from .providers import identity_for


def creation_settings():
    options, _ = InstanceSettings.objects.get_or_create(pk=1)
    return options


def automatic_comparison(options):
    """Capacity waits do not silently downgrade a configured independent analysis."""
    if not options.allow_confrontation:
        return False
    for connection in AIConnection.objects.filter(enabled=True, status="CONNECTED"):
        if "counter_analyst" in connection.roles and identity_for(connection).status == "CONNECTED":
            return True
    return False
