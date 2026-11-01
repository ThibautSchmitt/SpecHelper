"""Separate a redundant reply envelope from user-facing Markdown and JSON examples."""

import json
import re


def message_text(text, user_text="", *, partial=False):
    # Explicit structured-data requests and fenced examples are user content.
    # Be conservative: never strip an arbitrary object or an object with extra fields.
    if re.search(r"\bjson\b|```|\{\s*[\"']|\b(?:key|clé|clef)\s+[\"']?message\b", user_text, re.I):
        return text
    for _ in range(3):
        stripped = text.strip()
        if not stripped.startswith("{"):
            break
        try:
            pairs = json.loads(stripped, object_pairs_hook=list)
        except (TypeError, ValueError):
            return "" if partial else text
        if not isinstance(pairs, list) or len(pairs) != 1 or pairs[0][0] != "message":
            break
        inner = pairs[0][1]
        if not isinstance(inner, str) or not inner.strip():
            break
        text = inner
    return text


def normalize_messages(messages, initial_need=""):
    user_text = initial_need
    for message in messages:
        if message["role"] == "user":
            user_text = initial_need + "\n" + message["content"]
        elif message.get("kind") == "discussion_reply":
            message["content"] = message_text(message["content"], user_text)
    return messages
