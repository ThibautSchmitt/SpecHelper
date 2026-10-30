"""Guard incomplete public response text before it crosses a streaming boundary."""

import base64
import re
from urllib.parse import quote


def safe_prefix(text, secrets, redact):
    variants = {
        encoded
        for secret in secrets
        if isinstance(secret, str) and secret
        for encoded in (secret, quote(secret, safe=""), base64.b64encode(secret.encode()).decode())
    }
    trim = 0
    for secret in variants:
        # Withhold suffixes that could become a configured credential in the next frame.
        for size in range(1, min(len(secret), len(text) + 1)):
            if secret.startswith(text[-size:]):
                trim = max(trim, size)
    if trim:
        text = text[:-trim]
    # A credential-bearing URL, token or internal absolute path can arrive in pieces.
    text = re.sub(
        r"(?:\b(?:gh[pousr]_|github_pat_|sk-|AIza)[\w-]*|(?:https?|postgres(?:ql)?):[^\s]*|(?<!\w)/[^\s`)]*)$",
        "",
        text,
    )
    text = redact(text)
    return re.sub(
        r"(?<!\w)(?:/(?:data|sessions|credentials|tmp|private|Users|home|app)(?:/[^\s`),\]]*)?|[A-Za-z]:\\[^\s`),\]]*)",
        "[internal path]",
        text,
    )
