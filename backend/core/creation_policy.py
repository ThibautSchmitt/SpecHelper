"""Freeze the configured analysis policy when a business item is created."""

from .models import InstanceSettings


def creation_settings():
    options, _ = InstanceSettings.objects.get_or_create(pk=1)
    return options


def automatic_comparison(options):
    """Missing role capacity queues work; it cannot waive independent review."""
    return True
