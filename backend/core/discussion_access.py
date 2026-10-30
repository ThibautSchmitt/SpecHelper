"""Browser-scoped conversation ownership without introducing application accounts."""

import hashlib
import uuid

from django.core import signing
from django.db.models import Q

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
    return queryset.filter(
        ~Q(discussion_state__has_key="private")
        | Q(discussion_state__private=False)
        | Q(discussion_state__owner=actor(request))
    )
