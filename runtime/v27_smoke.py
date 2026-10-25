"""Real Antigravity binary and Linux sandbox, with synthetic Gemini transport only."""

import concurrent.futures
import json
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx

from runtime import server
from runtime.antigravity import PINNED_VERSION, cli_status, discover_models, parse_run
from runtime.antigravity_auth import metadata_environment
from runtime.vault import write

MODEL = "gemini-3.8-flash-medium"
SECRET = "fixture-v27-explicit-key-never-real"


def run_probe(root):
    server.DATA, server.SESSIONS, server.CREDENTIALS = (
        root / "data", root / "sessions", root / "credentials"
    )
    server.SESSIONS.mkdir()
    observations = []
    captured_tools = []
    native_tools = []
    checks = {}

    def create(case, with_credentials=True):
        request_id, identity_id = uuid.uuid4(), uuid.uuid4()
        workspace = server.DATA / "analysis-workspaces" / str(request_id)
        workspace.mkdir(parents=True)
        (workspace / "evidence.txt").write_text("v27 synthetic source evidence")
        (workspace / "symbolic-target-for-qualification.txt").write_text("Synthetic linked source")
        (workspace / "source-link").symlink_to("symbolic-target-for-qualification.txt")
        workspace.chmod(0o777)
        (workspace / "evidence.txt").chmod(0o666)
        (server.DATA / "requests" / str(request_id) / "attachments").mkdir(parents=True)
        if with_credentials:
            write(
                server.CREDENTIALS / "identities" / str(identity_id) / "antigravity/auth.json",
                json.dumps({"auth_mode": "gemini_api_key", "api_key": SECRET}).encode(),
            )
        return server.RunIn(
            request_id=request_id, attempt_id=uuid.uuid4(), identity_id=identity_id,
            agent="antigravity", model=MODEL, workspace=str(workspace),
            prompt=f"Controlled transport fixture: {case}. Return the required object after the tool.",
            schema={
                "type": "object", "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"], "additionalProperties": False,
            },
            timeout=30,
        )

    def response(parts, streaming):
        # Token values are synthetic fixture fields, never real measured AI usage.
        value = {
            "candidates": [{
                "content": {"role": "model", "parts": parts},
                "finishReason": "STOP", "index": 0,
            }],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4, "totalTokenCount": 14},
        }
        if streaming:
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"},
                content=("data: " + json.dumps(value) + "\n\n").encode(),
            )
        return httpx.Response(200, json=value)

    state = {"case": "read"}
    ready, release = {}, {}
    original_client = httpx.Client

    def upstream(request):
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers.get("x-goog-api-key") == SECRET
        body = json.loads(request.content)
        observations.append(request.url.path)
        if not body.get("tools"):
            return response([{"text": "Synthetic CLI fixture"}], True)
        replies = [
            part["functionResponse"] for content in body.get("contents", [])
            for part in content.get("parts", []) if part.get("functionResponse")
        ]
        captured_tools.extend(replies)
        case = state["case"]
        if case == "cancel":
            label = "first" if "fixture: first." in json.dumps(body.get("contents", [])) else "second"
            ready[label].set()
            assert release[label].wait(12), "Cancellation fixture failed to release."
            return response([{"functionCall": {"name": "finish", "args": {"ok": True}}}], True)
        if not replies:
            if case == "read":
                calls = [
                    {"name": "read_file", "args": {"Path": "/workspace/evidence.txt"}},
                    {"name": "read_file", "args": {"Path": "/skills/v27-procedure/v2.md"}},
                    {"name": "read_file", "args": {"Path": "/session/schema.json"}},
                    {"name": "run_command", "args": {
                        "CommandLine": "readlink /workspace/source-link",
                        "WaitMsBeforeAsync": 1000, "toolSummary": "Read source link metadata",
                    }},
                ]
            elif case == "deny":
                calls = [{"name": "run_command", "args": {
                    "CommandLine": "echo forbidden-auto-approval",
                    "WaitMsBeforeAsync": 1000, "toolSummary": "Permission probe",
                }}]
            else:
                if case == "write":
                    command = "python3 /workspace/guard_probe.py"
                elif case == "sql":
                    command = (
                        "curl -s -X POST http://127.0.0.1:8090/database "
                        "-H 'Content-Type: application/json' -d '{\"sql\":\"DELETE FROM fixture_records\"}'"
                    )
                else:
                    raise AssertionError("Unknown fixture case.")
                calls = [{"name": "run_command", "args": {
                    "CommandLine": command, "WaitMsBeforeAsync": 1000, "toolSummary": "Read-only boundary probe",
                }}]
            return response([{"functionCall": call} for call in calls], True)
        return response([{"functionCall": {"name": "finish", "args": {"ok": True}}}], True)

    def client(*args, **kwargs):
        return original_client(*args, transport=httpx.MockTransport(upstream), **kwargs)

    def capture_parse(stdout, *args, **kwargs):
        for line in stdout.decode(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            detail = event.get("step_update", {})
            if detail.get("state") == "DONE" and isinstance(detail.get("tool_info"), dict):
                native_tools.append(detail["tool_info"])
        return parse_run(stdout, *args, **kwargs)

    with tempfile.TemporaryDirectory(prefix="agy-metadata-") as home:
        environment = metadata_environment(home, SECRET)
        actual_cli = cli_status(environment)
        assert actual_cli["state"] == "supported" and actual_cli["version"] == PINNED_VERSION
        models = discover_models(environment)
        assert models["state"] == "supported"
        assert MODEL in {item["identifier"] for item in models["items"]}
        checks["real_binary_version"] = PINNED_VERSION
        checks["real_catalog_models"] = len(models["items"])

    with tempfile.TemporaryDirectory(prefix="agy-missing-auth-") as home:
        missing_cli = subprocess.run(
            ["agy", "-p", "Reply with the word fixture.", "--output-format", "stream-json"],
            env=metadata_environment(home), capture_output=True, timeout=10, check=False,
        )
        assert missing_cli.returncode != 0
        assert parse_run(missing_cli.stdout, missing_cli.stderr, missing_cli.returncode)["failure"]["kind"] == "AUTH_ERROR"
        checks["native_headless_missing_auth_explicit"] = True

    missing = create("missing", with_credentials=False)
    assert server.run(missing)["failure"]["kind"] == "AUTH_ERROR"
    checks["missing_auth_explicit"] = True

    with patch("runtime.broker.httpx.Client", client), patch("runtime.antigravity.parse_run", capture_parse):
        unknown = create("unknown")
        unknown.model = "unknown-model-not-a-fallback"
        assert server.run(unknown)["failure"]["kind"] == "MODEL_UNAVAILABLE"
        assert not observations
        checks["unknown_model_no_substitution"] = True

        read = create("read")
        read.skill_definitions = [{
            "slug": "v27-procedure", "name": "Read-only procedure", "version": 2,
            "objective": "Inspect scoped source evidence.",
            "instructions": "v27 skill marker: preserve source conditions.",
            "required_capabilities": ["read_sources"],
        }]
        result = server.run(read)
        assert result.get("output") == {"ok": True}, result
        assert "v27 synthetic source evidence" in json.dumps(captured_tools)
        assert "v27 skill marker" in json.dumps(captured_tools)
        assert "properties" in json.dumps(captured_tools)
        assert "symbolic-target-for-qualification.txt" in json.dumps(captured_tools)
        assert "read_file(/session/schema.json)" in result["permission_grants"]["allow"]
        assert "read_file(/session)" not in result["permission_grants"]["allow"]
        assert result["loaded_skills"][0]["slug"] == "v27-procedure", result
        assert result["permission_snapshot"]["mode"] == "request-review"
        assert "command(git)" in result["permission_grants"]["allow"]
        first_sid = result["session_id"]
        read.session_id = uuid.UUID(first_sid)
        second = server.run(read)
        assert second.get("output") == {"ok": True} and second["session_id"] != first_sid
        checks["native_structured_output_and_actual_source_skill_reads"] = True
        checks["native_read_of_exact_structured_output_schema"] = True
        checks["native_readlink_scoped_source_navigation"] = True
        checks["no_implicit_conversation_reuse"] = True

        state["case"] = "deny"
        captured_tools.clear()
        denied = server.run(create("deny"))
        assert denied.get("failure", {}).get("kind") == "PERMISSION_DENIED", denied
        assert any(item.get("status") == "SUCCESS" for item in denied["events"]), denied
        assert "output" not in denied
        checks["native_success_envelope_with_soft_denial_is_rejected"] = True

        state["case"] = "write"
        captured_tools.clear()
        write_attempt = create("write")
        (Path(write_attempt.workspace) / "guard_probe.py").write_text(
            "from pathlib import Path\nimport os, socket\n"
            "assert os.getuid() == 10001\nassert not Path('/credentials').exists()\n"
            "try:\n    Path('/workspace/evidence.txt').write_text('forbidden')\n"
            "except OSError:\n    print('SOURCE_WRITE_DENIED')\n"
            "else:\n    raise AssertionError('source writable')\n"
            "assert socket.socket().connect_ex(('1.1.1.1',443)) != 0\n"
        )
        refused = server.run(write_attempt)
        assert "SOURCE_WRITE_DENIED" in json.dumps(native_tools), refused
        assert (Path(write_attempt.workspace) / "evidence.txt").read_text() == "v27 synthetic source evidence"
        checks["actual_cli_source_write_and_arbitrary_network_denied"] = True

        state["case"] = "sql"
        captured_tools.clear()
        sql = create("sql")
        sql.database = {"host": "unused.invalid", "database": "fixture", "user": "reader", "password": "fixture"}
        with patch.object(server, "query", side_effect=AssertionError("Rejected SQL must never reach PostgreSQL")):
            rejected = server.run(sql)
        assert rejected.get("database_checks"), rejected
        assert rejected["database_checks"][0]["status"] == "rejected", rejected
        assert "Read-only query rejected" in json.dumps(native_tools), rejected
        checks["actual_cli_sql_write_rejected_before_database"] = True

        state["case"] = "cancel"
        ready = {label: threading.Event() for label in ("first", "second")}
        release = {label: threading.Event() for label in ("first", "second")}
        first, second = create("first"), create("second")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            a = executor.submit(server.run, first)
            b = executor.submit(server.run, second)
            assert ready["first"].wait(10) and ready["second"].wait(10)
            cancelled = server.cancel_run(server.CancelRunIn(
                request_id=first.request_id, attempt_id=first.attempt_id,
            ))
            assert cancelled["stopped"] is True, cancelled
            release["first"].set()
            release["second"].set()
            assert a.result(timeout=10).get("cancelled") is True
            assert b.result(timeout=10).get("output") == {"ok": True}
        checks["exact_cancellation_preserves_other_native_conversation"] = True

    # The parser must never turn an interrupted invocation into success.
    assert parse_run(b"", timed_out=True)["timed_out"] is True
    return checks


def main():
    with tempfile.TemporaryDirectory(prefix="spechelper-v27-smoke-") as directory:
        checks = run_probe(Path(directory))
    print(json.dumps({
        "checks": checks,
        "scope": "real pinned CLI/Bubblewrap with synthetic Gemini responses; no real provider inference or billing",
    }, indent=2))


if __name__ == "__main__":
    main()
