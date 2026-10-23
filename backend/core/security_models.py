"""Shared-team access sessions, bounded request accounting and content-free audit."""

from django.db import models


class AccessSession(models.Model):
    token_hash = models.CharField(max_length=64, primary_key=True)
    credential_version = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)


class SecurityBucket(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window = models.BigIntegerField(default=0)
    count = models.PositiveIntegerField(default=0)
    leases = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)


class SecurityEvent(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.CharField(max_length=64)
    action = models.CharField(max_length=32)
    resource = models.CharField(max_length=40)
    status = models.PositiveSmallIntegerField()
