"""Redact known credentials at the response boundary without rewriting stored history."""

import json

from django.http import HttpResponse, JsonResponse

from .sensitive_data import configured_secrets, redact


class BoundaryResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.prepare(request)
        if request.path == "/api" or request.path.startswith("/api/"):
            response["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
            response["Referrer-Policy"] = "no-referrer"
        return response

    def prepare(self, request):
        if request.path.startswith("/api/") and request.content_type == "application/json":
            try:
                if int(request.META.get("CONTENT_LENGTH") or "0") > 1024 * 1024:
                    return JsonResponse({"detail": "Request too large."}, status=413)
            except ValueError:
                return JsonResponse({"detail": "Invalid request length."}, status=400)
        response = self.get_response(request)
        if not request.path.startswith("/api/") or request.path.startswith("/api/access/"):
            return response
        content_type = response.get("Content-Type", "").split(";", 1)[0]
        if content_type not in {"application/json", "text/markdown", "text/plain"}:
            return response
        try:
            secrets = configured_secrets()
            if response.streaming:
                # Exported text is bounded by runtime output limits, never arbitrary files.
                data = bytearray()
                for chunk in response.streaming_content:
                    data.extend(chunk)
                    if len(data) > 2 * 1024 * 1024:
                        return JsonResponse({"detail": "The export exceeds the response limit."}, status=413)
                replacement = HttpResponse(bytes(data), status=response.status_code)
                for key, value in response.items():
                    replacement[key] = value
                response.close()
                response = replacement
            text = response.content.decode("utf-8")
            value = json.loads(text) if content_type == "application/json" else text
            # Connector usernames are deliberately public/editable metadata. A short
            # password equal to the username must not corrupt subsequent form saves.
            identifiers = ("username",) if request.path.startswith("/api/ticket-connectors") else ()
            value = redact(value, secrets, public_identifiers=identifiers)
            response.content = json.dumps(value, ensure_ascii=False).encode() if content_type == "application/json" else value.encode()
            response["Content-Length"] = str(len(response.content))
        except (ValueError, UnicodeError):
            return JsonResponse({"detail": "The response could not be safely prepared."}, status=500)
        return response
