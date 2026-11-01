"""Pseudonymous browser attribution inside a shared, access-controlled instance."""

import hashlib
import uuid

from django.core import signing

COOKIE = "spechelper_conversation_owner"
SALT = "spechelper.conversation-owner.v1"
AGE = 365 * 24 * 3600


def identify(request):
    try:
        raw = signing.loads(request.COOKIES.get(COOKIE, ""), salt=SALT, max_age=AGE)
        raw = str(uuid.UUID(raw))
    except (signing.BadSignature, ValueError, TypeError):
        raw = str(uuid.uuid4())
        request.new_discussion_cookie = signing.dumps(raw, salt=SALT)
    request.discussion_actor = hashlib.sha256(raw.encode()).hexdigest()


def actor(request):
    if not hasattr(request, "discussion_actor"):
        identify(request)
    return request.discussion_actor


def visible(request, queryset):
    """Instance access is checked by middleware; browser cookies do not hide records.

    Retain legacy ownership metadata for history without treating it as an access
    boundary. The instance is shared by its authorized visitors, not multi-tenant.
    """
    return queryset
