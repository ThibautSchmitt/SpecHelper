"""Bounded public work observations; never relay CLI diagnostics or reasoning."""

import hashlib
import json
import os
import shlex
from datetime import UTC, datetime

MAX_LINE = 1024 * 1024
MAX_EVENTS = 24


def command_operation(command):
    try:
        parts = shlex.split(command) if isinstance(command, str) else []
        if parts and os.path.basename(parts[0]) in {"bash", "sh", "zsh"} and "-lc" in parts:
            parts = shlex.split(parts[parts.index("-lc") + 1])
        name = os.path.basename(parts[0]) if parts else ""
    except (ValueError, IndexError):
        name = ""
    return {
        "rg": "search",
        "grep": "search",
        "find": "search",
        "ls": "search",
        "cat": "read",
        "sed": "read",
        "head": "read",
        "tail": "read",
        "git": "git",
    }.get(name, "command")


def tool_operation(name, arguments=None):
    if name in {"Bash", "run_command", "exec_command", "shell", "shell_command"}:
        arguments = arguments if isinstance(arguments, dict) else {}
        return command_operation(
            arguments.get("command", arguments.get("CommandLine", arguments.get("cmd", "")))
        )
    return {
        "Read": "read",
        "read_file": "read",
        "read_text_file": "read",
        "Grep": "search",
        "Glob": "search",
        "list_directory": "search",
        "search_files": "search",
        "WebFetch": "reference",
        "WebSearch": "reference",
        "update_plan": "plan",
        "TodoWrite": "plan",
    }.get(name, "tool")


def string_field(text, path):
    """Read only an explicitly allowed JSON string, including a valid incomplete prefix."""
    decoder = json.JSONDecoder()

    def whitespace(position):
        while position < len(text) and text[position].isspace():
            position += 1
        return position

    def field(position, keys):
        position = whitespace(position)
        if position >= len(text) or text[position] != "{":
            return ""
        position += 1
        while True:
            position = whitespace(position)
            key, position = decoder.raw_decode(text, position)
            position = whitespace(position)
            if text[position] != ":":
                return ""
            position = whitespace(position + 1)
            if key == keys[0]:
                if len(keys) > 1:
                    return field(position, keys[1:])
                if text[position] != '"':
                    return ""
                start = position + 1
                position = start
                while position < len(text):
                    character = text[position]
                    if character == '"':
                        return json.loads(text[start - 1 : position + 1])
                    if character == "\\":
                        width = 6 if text[position : position + 2] == "\\u" else 2
                        if position + width > len(text):
                            break
                        position += width
                    else:
                        position += 1
                result = json.loads('"' + text[start:position] + '"')
                while result and 0xD800 <= ord(result[-1]) < 0xE000:
                    result = result[:-1]
                return result
            _, position = decoder.raw_decode(text, position)
            position = whitespace(position)
            if text[position] != ",":
                return ""
            position += 1

    try:
        value = field(0, path.split("."))
        value.encode("utf-8")
        return value[:12000]
    except (ValueError, IndexError, UnicodeError):
        return ""


class Observer:
    """Normalize only documented public tool lifecycles and selected response fields."""

    def __init__(self, provider, emit, preview_field=""):
        self.provider, self.emit, self.preview_field = provider, emit, preview_field
        self.events, self.sequence, self.activity = [], 0, "preparing"
        self.preview, self.buffer, self.blocks, self.seen = "", "", {}, set()

    def snapshot(self):
        self.sequence += 1
        self.emit(
            {
                "type": "progress",
                "sequence": self.sequence,
                "activity": self.activity,
                "events": self.events.copy(),
                "preview": self.preview,
            }
        )

    def operation(self, identifier, operation, state):
        if state not in {"running", "done", "error"}:
            return
        identifier = hashlib.sha256(str(identifier).encode()).hexdigest()[:20]
        old = next((e for e in self.events if e["id"] == identifier), None)
        if old and (old["state"] == state or old["state"] != "running"):
            return
        event = {
            "id": identifier,
            "operation": old["operation"]
            if old and operation in {"command", "tool"}
            else operation,
            "state": state,
            "observed_at": datetime.now(UTC).isoformat(),
        }
        self.events = (
            [event if e["id"] == identifier else e for e in self.events]
            if old
            else (self.events + [event])[-MAX_EVENTS:]
        )
        self.activity = operation if state == "running" else "processing"
        self.snapshot()

    def response(self, text):
        if self.preview_field and isinstance(text, str):
            value = string_field(text[:MAX_LINE], self.preview_field)
            if value and value != self.preview:
                self.preview, self.activity = value, "writing"
                self.snapshot()

    def feed(self, line):
        if len(line) > MAX_LINE:
            return
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                return
            self.event(value)
        except (ValueError, TypeError, KeyError, AttributeError):
            return

    def event(self, value):
        kind = value.get("type")
        if self.provider == "codex":
            item = value.get("item", {})
            if kind in {"item.started", "item.updated", "item.completed"} and isinstance(
                item, dict
            ):
                category = item.get("type")
                state = (
                    "error"
                    if item.get("status") == "failed"
                    or (kind == "item.completed" and item.get("exit_code") not in {None, 0})
                    else "done"
                    if kind == "item.completed"
                    else "running"
                )
                identifier = item.get("id")
                if identifier and category == "command_execution":
                    self.operation(identifier, command_operation(item.get("command")), state)
                elif identifier and category in {"mcp_tool_call", "web_search", "todo_list"}:
                    self.operation(
                        identifier,
                        {"web_search": "reference", "todo_list": "plan"}.get(
                            category, tool_operation(item.get("tool"))
                        ),
                        state,
                    )
                elif category == "agent_message":
                    self.response(item.get("text"))
            elif kind == "turn.started":
                self.activity = "processing"
                self.snapshot()
        elif self.provider == "claude":
            if kind == "stream_event":
                event = value.get("event", {})
                index = event.get("index", 0)
                if event.get("type") == "message_start":
                    self.blocks.clear()
                elif event.get("type") == "content_block_start":
                    block = event.get("content_block", {})
                    self.blocks.pop(index, None)
                    if block.get("type") in {"text", "tool_use"}:
                        self.blocks[index] = {
                            "id": block.get("id", f"block-{index}-{self.sequence}"),
                            "type": block.get("type"),
                            "name": block.get("name"),
                            "json": "",
                        }
                    if block.get("type") == "tool_use" and block.get("name") != "StructuredOutput":
                        self.operation(
                            block.get("id"), tool_operation(block.get("name")), "running"
                        )
                elif event.get("type") == "content_block_delta":
                    block = self.blocks.get(index, {})
                    delta = event.get("delta", {})
                    text = (
                        delta.get("partial_json")
                        if block.get("name") == "StructuredOutput"
                        else delta.get("text")
                        if block.get("type") == "text"
                        else None
                    )
                    if isinstance(text, str) and len(block.get("json", "")) < MAX_LINE:
                        block["json"] = (block.get("json", "") + text)[:MAX_LINE]
                        self.response(block["json"])
            elif kind in {"assistant", "user"}:
                for block in value.get("message", {}).get("content", []):
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        if block.get("name") == "StructuredOutput":
                            self.response(json.dumps(block.get("input", {})))
                        else:
                            self.operation(
                                block.get("id"),
                                tool_operation(block.get("name"), block.get("input")),
                                "running",
                            )
                    elif block.get("type") == "tool_result":
                        identifier = hashlib.sha256(
                            str(block.get("tool_use_id")).encode()
                        ).hexdigest()[:20]
                        previous = next((e for e in self.events if e["id"] == identifier), None)
                        if previous:
                            self.operation(
                                block["tool_use_id"],
                                previous["operation"],
                                "error" if block.get("is_error") else "done",
                            )
            elif kind == "result":
                self.response(json.dumps(value.get("structured_output", {})))
        elif self.provider == "antigravity":
            if value.get("event") == "step_update":
                step = value.get("step_update", {})
                if step.get("step_type") == "tool" and step.get("tool_name"):
                    state = {
                        "RUNNING": "running",
                        "DONE": "done",
                        "ERROR": "error",
                        "FAILED": "error",
                    }.get(step.get("state"))
                    identifier = step.get("step_id", step.get("id"))
                    if identifier:
                        self.operation(
                            identifier,
                            tool_operation(
                                step["tool_name"], step.get("tool_info", {}).get("parameters")
                            ),
                            state,
                        )
                    else:
                        # Older CLI versions omit step IDs; collapse repeated observations.
                        signature = hashlib.sha256(
                            json.dumps(step, sort_keys=True).encode()
                        ).hexdigest()
                        if len(self.seen) < 4096 and signature not in self.seen:
                            self.seen.add(signature)
                            self.operation(signature, tool_operation(step["tool_name"]), state)
            elif value.get("event") == "result":
                self.response(json.dumps(value.get("result", {}).get("structured_output", {})))


class Tail:
    """Read the captured JSONL without moving the child process's write offset."""

    def __init__(self, stream, observer):
        self.fd, self.observer, self.offset, self.pending = stream.fileno(), observer, 0, b""
        self.dropping = False

    def read(self):
        content = os.pread(self.fd, 262144, self.offset)
        self.offset += len(content)
        self.pending += content
        while b"\n" in self.pending:
            line, self.pending = self.pending.split(b"\n", 1)
            if not self.dropping:
                self.observer.feed(line)
            self.dropping = False
        if len(self.pending) > MAX_LINE:
            self.pending = b""
            self.dropping = True
        return len(content)

    def finish(self):
        while self.read():
            pass
        if self.pending and not self.dropping:
            self.observer.feed(self.pending)
            self.pending = b""
