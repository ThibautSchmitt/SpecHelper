from urllib.parse import urlsplit

from django.conf import settings
from django.http import JsonResponse


class SameOriginMiddleware:
    """No application accounts; reject browser cross-site writes at the instance boundary."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.get_host()  # Enforce ALLOWED_HOSTS for reads as well as writes.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            if request.headers.get("Sec-Fetch-Site") == "cross-site":
                return JsonResponse({"detail": "Origin denied"}, status=403)
            if origin and origin not in settings.TRUSTED_ORIGINS:
                if urlsplit(origin).netloc != request.get_host():
                    return JsonResponse({"detail": "Origin denied"}, status=403)
        return self.get_response(request)
