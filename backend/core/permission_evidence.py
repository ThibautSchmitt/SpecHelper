"""Keep fixed runtime permission observations separate from a model's self-report."""

PERMISSION_LIMIT = (
    "A necessary analysis tool was refused by the assistant's permission policy; "
    "related findings remain unverified."
)
TOOL_ERROR_LIMIT = "Antigravity reported an unresolved tool error during this analysis."
KNOWN_TOOLS = {
    "run_command", "view_file", "read_file", "list_dir", "grep_search", "find_by_name",
    "read_url_content", "search_web", "write_to_file", "replace_file_content",
    "multi_replace_file_content", "execute_python", "structured_output", "unknown",
    "ask_permission", "view_code_item", "view_file_outline", "view_content_chunk",
    "command_status", "send_command_input", "task_boundary", "notify_user",
}
KNOWN_ALLOW_RULES = {
    "command(" + command + ")"
    for command in ("git", "rg", "ls", "cat", "sed", "head", "tail", "find", "readlink", "wc", "python3", "curl")
} | {
    "read_file(/workspace)", "read_file(/skills)", "read_file(/context)",
    "read_file(/attachments)", "read_file(/session/schema.json)",
}
KNOWN_DENY_RULES = {"write_file(*)"}


def trace(response):
    """Separate native advertised tools from service-authored grants, with no arbitrary text.

    A native tool list does not prove approval or a completed tool invocation. These
    records describe observations only and cannot grant backend/runtime access.
    """
    result = {}
    snapshot = response.get("permission_snapshot")
    if isinstance(snapshot, dict):
        parsed = {}
        mode = snapshot.get("mode")
        if isinstance(mode, str) and mode in {"request-review", "always-proceed"}:
            parsed["mode"] = mode
        tools = snapshot.get("tools")
        if isinstance(tools, list):
            parsed["tools"] = list(dict.fromkeys(
                value for value in tools[:100]
                if isinstance(value, str) and value in KNOWN_TOOLS
            ))
        result["permission_snapshot"] = parsed
    grants = response.get("permission_grants")
    if isinstance(grants, dict):
        parsed = {}
        for key, known in (("allow", KNOWN_ALLOW_RULES), ("deny", KNOWN_DENY_RULES)):
            rules = grants.get(key)
            if isinstance(rules, list):
                parsed[key] = list(dict.fromkeys(
                    value for value in rules[:100] if isinstance(value, str) and value in known
                ))
        result["permission_grants"] = parsed
    return result


def observation(response):
    """Never retain raw tool arguments, output, permission messages or credentials."""
    records = response.get("permission_events", [])
    events = []
    if isinstance(records, list):
        for row in records[:100]:
            if not isinstance(row, dict) or not isinstance(row.get("status"), str) or row["status"] not in {
                "allowed", "denied", "unknown"
            }:
                continue
            tool = row.get("tool")
            value = {
                "tool": tool if isinstance(tool, str) and tool in KNOWN_TOOLS else "unknown",
                "status": row["status"],
            }
            if value not in events:
                events.append(value)
    raw_limits = response.get("permission_limits", [])
    limits = []
    if isinstance(raw_limits, list) and raw_limits:
        limits = [
            TOOL_ERROR_LIMIT if value == TOOL_ERROR_LIMIT else PERMISSION_LIMIT
            for value in raw_limits[:30]
        ]
    if any(row["status"] == "denied" for row in events):
        limits.append(PERMISSION_LIMIT)
    if response.get("result_status") == "partial" and not limits:
        limits.append(TOOL_ERROR_LIMIT)
    return list(dict.fromkeys(limits)), events


def qualify_report(report, limits):
    """Service-observed refusal cannot be waived by a later model's READY label."""
    if limits:
        report = report.model_copy(deep=True)
        report.blocking = True
        safe = [
            TOOL_ERROR_LIMIT if value == TOOL_ERROR_LIMIT else PERMISSION_LIMIT
            for value in limits[:30]
        ]
        report.limitations = list(dict.fromkeys([*report.limitations, *safe]))
    return report
