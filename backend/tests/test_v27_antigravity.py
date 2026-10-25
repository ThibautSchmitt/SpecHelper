"""Native protocol fixtures exercise provenance, partial permissions and bounded metadata."""

import json
import subprocess
import uuid
from types import SimpleNamespace

import pytest

from runtime.antigravity import (
    MAX_EVENTS,
    PINNED_VERSION,
    REQUIRED_FLAGS,
    classify_failure,
    cli_status,
    discover_models,
    headless_command,
    model_family,
    parse_models,
    parse_run,
    prompt_message,
)


def stream(*, status="SUCCESS", output=None, model="gemini-observed-high", error=None):
    conversation = str(uuid.uuid4())
    result = {
        "conversation_id": conversation,
        "status": status,
        "structured_output": {"summary": "Observed source behavior"} if output is None else output,
    }
    if error:
        result["error"] = error
    events = [
        {
            "event": "init", "conversation_id": conversation,
            "init": {
                "permission_mode": "request-review", "model": model,
                "tools": ["read_file", "run_command"],
            },
        },
        {"event": "result", "result": result},
    ]
    return events


def encode(events):
    return ("\n".join(json.dumps(event) for event in events) + "\n").encode()


def native_oauth_profile():
    return {"auth_method": "consumer", "token": {
        "access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
        "token_type": "Bearer", "expiry": "2099-01-01T00:00:00Z",
    }}


def test_native_personal_profile_uses_actual_filename_and_clean_environment(tmp_path, monkeypatch):
    from runtime.antigravity_auth import (
        metadata_environment,
        oauth_profile_path,
        read_oauth_profile,
    )

    monkeypatch.setenv("GEMINI_API_KEY", "never-inherit")
    monkeypatch.setenv("CLOUD_CODE_URL", "https://untrusted.invalid")
    profile = native_oauth_profile()
    env = metadata_environment(tmp_path, oauth_profile=profile)
    assert "GEMINI_API_KEY" not in env and "CLOUD_CODE_URL" not in env
    assert "modelProvider" not in json.loads((tmp_path / ".gemini/antigravity-cli/settings.json").read_text())
    assert oauth_profile_path(tmp_path) == tmp_path / ".gemini/antigravity-cli/antigravity-oauth-token"
    assert read_oauth_profile(tmp_path) == profile
    assert oauth_profile_path(tmp_path).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("field,value", [
    ("access_token", ""), ("refresh_token", "has\ncontrol"), ("token_type", "Basic"),
    ("expiry", "not-a-date"), ("expiry", "2099-01-01T00:00:00"),
])
def test_native_profile_rejects_malformed_credentials(field, value):
    from runtime.antigravity_auth import validate_oauth_profile

    profile = native_oauth_profile()
    profile["token"][field] = value
    with pytest.raises(ValueError, match="Invalid Antigravity OAuth profile"):
        validate_oauth_profile(profile)


def test_native_profile_read_rejects_links_and_oversized_data(tmp_path):
    from runtime.antigravity_auth import oauth_profile_path, read_oauth_profile

    path = oauth_profile_path(tmp_path)
    path.parent.mkdir(parents=True)
    target = tmp_path / "elsewhere"
    target.write_text(json.dumps(native_oauth_profile()))
    path.symlink_to(target)
    with pytest.raises(OSError):
        read_oauth_profile(tmp_path)
    path.unlink()
    path.write_bytes(b"x" * 65537)
    with pytest.raises(ValueError):
        read_oauth_profile(tmp_path)


def test_analysis_child_contains_only_synthetic_oauth_capability(tmp_path):
    from runtime.antigravity_auth import OAUTH_MODE, prepare_session, read_oauth_profile

    grants = prepare_session(tmp_path, token="broker-capability", auth_mode=OAUTH_MODE)
    profile = read_oauth_profile(tmp_path)
    assert profile["token"]["access_token"] == "broker-capability"
    assert profile["token"]["refresh_token"] == "spechelper-synthetic-refresh"
    config = json.loads((tmp_path / ".gemini/antigravity-cli/settings.json").read_text())
    assert "modelProvider" not in config
    assert grants["deny"] == ["write_file(*)"]


def test_personal_and_api_auth_modes_cannot_mix(tmp_path):
    from runtime.antigravity_auth import metadata_environment

    with pytest.raises(ValueError):
        metadata_environment(tmp_path, api_key="synthetic", oauth_profile=native_oauth_profile())


def test_stream_preserves_actual_conversation_model_and_permission_metadata():
    events = stream()
    result = parse_run(encode(events), expected_model="gemini-observed-high")
    assert result["output"] == events[1]["result"]["structured_output"]
    assert result["session_id"] == events[0]["conversation_id"]
    assert result["model"] == "gemini-observed-high"
    assert result["usage"] == {}  # No invented zero or quota windows.
    assert result["permission_snapshot"] == {
        "mode": "request-review", "tools": ["read_file", "run_command"],
    }
    assert "permission_limits" not in result
    assert "quota_windows" not in result


def test_only_observed_nonnegative_integer_usage_survives():
    events = stream()
    events[-1]["result"]["usage"] = {
        "input_tokens": 123, "output_tokens": 45, "thinking_tokens": True,
        "cache_read_tokens": -2, "total_tokens": 2**80, "unknown": 3,
    }
    result = parse_run(encode(events))
    assert result["usage"] == {"input_tokens": 123, "output_tokens": 45}


@pytest.mark.parametrize("notice", [
    "permission denied for tool run_command",
    "Tool run_command requires approval in headless mode",
    "Command git status was soft-denied",
    "Cannot obtain approval in headless mode",
    "PERMISSION_DENIED: private-source-identifier",
])
def test_zero_exit_soft_refusal_never_becomes_complete(notice):
    result = parse_run(encode(stream()), notice.encode(), 0)
    assert result["output"]
    assert result["result_status"] == "partial"
    assert result["permission_limits"]
    assert "private-source-identifier" not in json.dumps(result)


def test_refusal_in_tool_event_is_partial_without_exposing_command_or_output():
    events = stream()
    events.insert(1, {
        "event": "step_update",
        "step_update": {
            "conversation_id": events[0]["conversation_id"],
            "state": "DONE", "step_type": "tool", "tool_name": "run_command",
            "tool_info": {
                "parameters": {"CommandLine": "cat secret-business-document"},
                "output": "private-provider-value",
                "error": {"type": "permission_denied", "message": "private-error"},
            },
        },
    })
    result = parse_run(encode(events))
    assert result["result_status"] == "partial"
    assert result["events"][1]["tool_error"] is True
    assert "secret-business-document" not in json.dumps(result)
    assert "private-provider-value" not in json.dumps(result)
    assert "private-error" not in json.dumps(result)


def test_refusal_without_usable_output_has_fixed_failure():
    events = stream(status="ERROR", output="", error="permission denied private-value")
    result = parse_run(encode(events))
    assert result["failure"] == {"kind": "PERMISSION_DENIED"}
    assert "output" not in result
    assert "private-value" not in json.dumps(result)


@pytest.mark.parametrize("detail,kind", [
    ("authentication required private-token", "AUTH_ERROR"),
    ("invalid API key private-token", "AUTH_ERROR"),
    ("invalid model selection", "MODEL_UNAVAILABLE"),
    ("unknown model selected", "MODEL_UNAVAILABLE"),
    ("quota_exceeded", "QUOTA_EXHAUSTED"),
    ("RESOURCE_EXHAUSTED", "QUOTA_EXHAUSTED"),
    ("rate limit exceeded", "BUSY"),
    ("permission denied", "PERMISSION_DENIED"),
    ("deadline exceeded", "TIMEOUT"),
    ("unknown private failure", "ERROR"),
])
def test_failure_categories_never_echo_provider_text(detail, kind):
    assert classify_failure(detail) == {"kind": kind}
    if kind not in {"PERMISSION_DENIED", "ERROR"}:
        result = parse_run(encode(stream()), detail.encode())
        assert result["failure"] == {"kind": kind}
        assert "output" not in result


@pytest.mark.parametrize("status", ["ERROR", "CANCELED", "INTERRUPTED", "INVALID", "WAITING", "RUNNING"])
def test_non_success_terminal_states_cannot_publish_output(status):
    result = parse_run(encode(stream(status=status)))
    assert "output" not in result
    assert result["failure"]


def test_model_substitution_is_explicit_failure():
    result = parse_run(encode(stream(model="different-model")), expected_model="selected-model")
    assert result["failure"] == {"kind": "MODEL_UNAVAILABLE"}


def test_unrecognized_status_and_malformed_model_do_not_leak_diagnostics():
    events = stream(model="private provider diagnostic")
    events[-1]["result"]["status"] = "private terminal diagnostic"
    result = parse_run(encode(events))
    assert result["failure"] == {"kind": "ERROR"}
    assert "private" not in json.dumps(result)


def test_nonzero_exit_and_technical_timeout_cannot_look_successful():
    assert "output" not in parse_run(encode(stream()), returncode=1)
    result = parse_run(encode(stream()), timed_out=True)
    assert result["failure"] == {"kind": "TIMEOUT"}
    assert result["timed_out"] is True
    assert "output" not in result


@pytest.mark.parametrize("mutation", [
    "missing_init", "duplicate_init", "duplicate_result", "unknown_event",
    "different_conversation", "invalid_conversation", "malformed_line", "unsafe_permission_mode",
])
def test_protocol_anomalies_fail_closed(mutation):
    events = stream()
    if mutation == "missing_init":
        events.pop(0)
    elif mutation == "duplicate_init":
        events.insert(0, events[0])
    elif mutation == "duplicate_result":
        events.append(events[-1])
    elif mutation == "unknown_event":
        events.insert(1, {"event": "future_type", "future_type": {}})
    elif mutation == "different_conversation":
        events[-1]["result"]["conversation_id"] = str(uuid.uuid4())
    elif mutation == "invalid_conversation":
        events[-1]["result"]["conversation_id"] = "../other-session"
    elif mutation == "unsafe_permission_mode":
        events[0]["init"]["permission_mode"] = "always-proceed"
    encoded = encode(events) + (b"malformed\n" if mutation == "malformed_line" else b"")
    assert "output" not in parse_run(encoded)


def test_oversized_event_stream_fails_without_processing_all_events():
    assert parse_run(b"{}\n" * (MAX_EVENTS + 1)) == {"failure": {"kind": "ERROR"}}


def test_headless_uses_fresh_single_turn_stdin_without_private_prompt_in_argv():
    command = headless_command("gemini-exact-slug-high", timeout=47)
    assert command[command.index("--model") + 1] == "gemini-exact-slug-high"
    assert command[command.index("--print-timeout") + 1] == "47s"
    assert command[command.index("--input-format") + 1] == "stream-json"
    assert not {"-p", "--continue", "--conversation", "--dangerously-skip-permissions"} & set(command)
    private_request = "First line\nSecond line with a quoted \"value\""
    message = prompt_message(private_request)
    assert len(message.splitlines()) == 1
    assert json.loads(message) == {"event": "user", "message": {"content": private_request}}
    assert private_request not in " ".join(command)


@pytest.mark.parametrize("model,timeout", [("", 30), ("bad model", 30), ("-model", 30), ("good-model", 0), ("good-model", 601), ("good-model", True)])
def test_invalid_model_or_resource_bounds_are_rejected(model, timeout):
    with pytest.raises(ValueError):
        headless_command(model, timeout=timeout)


def test_catalog_retains_exact_returned_slugs_and_actual_family():
    value = parse_models(
        b"Available models:\n"
        b"gemini-observed-high       Gemini observed (High)\n"
        b"claude-observed-sonnet     Claude observed Sonnet\n"
        b"custom-model:revision      Custom administered entry\n"
    )
    assert value == [
        {"identifier": "gemini-observed-high", "name": "Gemini observed (High)", "family": "google"},
        {"identifier": "claude-observed-sonnet", "name": "Claude observed Sonnet", "family": "anthropic"},
        {"identifier": "custom-model:revision", "name": "Custom administered entry"},
    ]
    assert model_family("account-display-name") == ""


@pytest.mark.parametrize("catalog", [
    b"authentication required", b"No models available", b"",
    b"my-model First\nmy-model Second\n", b"warning: private-provider-diagnostic\n",
])
def test_catalog_never_invents_entries_on_failure_or_duplicate_identifiers(catalog):
    with pytest.raises(ValueError):
        parse_models(catalog)


def test_cli_preflight_checks_actual_version_and_required_flags(monkeypatch):
    monkeypatch.setattr("runtime.antigravity.shutil.which", lambda *a, **k: "/fixture/agy")
    calls = []

    def invoke(command, **kwargs):
        calls.append(command)
        assert kwargs["env"] == {"HOME": "/fixture/clean", "PATH": "/fixture/bin"}
        return SimpleNamespace(returncode=0, stderr=b"", stdout=(
            PINNED_VERSION.encode() if command[-1] == "--version" else "\n".join(REQUIRED_FLAGS).encode()
        ))

    monkeypatch.setattr("runtime.antigravity.subprocess.run", invoke)
    result = cli_status({"HOME": "/fixture/clean", "PATH": "/fixture/bin"}, expected_version=PINNED_VERSION)
    assert result == {"state": "supported", "reason": "", "version": PINNED_VERSION}
    assert [command[-1] for command in calls] == ["--version", "--help"]


def test_real_linux_help_on_stderr_is_supported(monkeypatch):
    monkeypatch.setattr("runtime.antigravity.shutil.which", lambda *a, **k: "/fixture/agy")

    def invoke(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=PINNED_VERSION.encode() if command[-1] == "--version" else b"",
            stderr="\n".join(REQUIRED_FLAGS).encode() if command[-1] == "--help" else b"",
        )

    monkeypatch.setattr("runtime.antigravity.subprocess.run", invoke)
    assert cli_status({})["state"] == "supported"


def test_real_linux_missing_gemini_key_is_authentication_failure():
    diagnostic = (
        'modelProvider is set to "gemini" in settings.json, '
        'but the GEMINI_API_KEY environment variable is not set'
    )
    assert classify_failure(diagnostic) == {"kind": "AUTH_ERROR"}


@pytest.mark.parametrize("field", ["event", "status"])
def test_malformed_unhashable_protocol_fields_fail_closed(field):
    events = stream()
    if field == "event":
        events[0]["event"] = {"invalid": True}
    else:
        events[-1]["result"]["status"] = {"invalid": True}
    assert parse_run(encode(events))["failure"] == {"kind": "ERROR"}


def test_absent_and_incompatible_cli_have_safe_diagnostics(monkeypatch):
    monkeypatch.setattr("runtime.antigravity.shutil.which", lambda *a, **k: None)
    assert cli_status({})["reason"] == "missing_cli"
    monkeypatch.setattr("runtime.antigravity.shutil.which", lambda *a, **k: "/fixture/agy")
    monkeypatch.setattr("runtime.antigravity.subprocess.run", lambda *a, **k: SimpleNamespace(
        returncode=0, stderr=b"", stdout=b"2.0.0",
    ))
    assert cli_status({})["reason"] == "incompatible_cli"


def test_unreviewed_patch_upgrade_is_not_silently_accepted(monkeypatch):
    monkeypatch.setattr("runtime.antigravity.shutil.which", lambda *a, **k: "/fixture/agy")

    def invoke(command, **kwargs):
        return SimpleNamespace(returncode=0, stderr=b"", stdout=(
            b"1.4.99" if command[-1] == "--version" else "\n".join(REQUIRED_FLAGS).encode()
        ))

    monkeypatch.setattr("runtime.antigravity.subprocess.run", invoke)
    assert cli_status({}) == {
        "state": "unavailable", "reason": "incompatible_cli", "version": "1.4.99",
    }


def test_metadata_discovery_timeout_does_not_return_raw_diagnostics(monkeypatch):
    monkeypatch.setattr("runtime.antigravity.shutil.which", lambda *a, **k: "/fixture/agy")

    def invoke(*args, **kwargs):
        raise subprocess.TimeoutExpired(["private-provider-value"], 1)

    monkeypatch.setattr("runtime.antigravity.subprocess.run", invoke)
    result = discover_models({"HOME": "/fixture/clean"})
    assert result == {
        "state": "error", "reason": "refresh_failed", "items": [],
        "failure": {"kind": "TIMEOUT"},
    }


@pytest.mark.parametrize(("diagnostic", "kind"), [
    (b"invalid_grant", "AUTH_ERROR"),
    (b"RESOURCE_EXHAUSTED", "QUOTA_EXHAUSTED"),
    (b"unknown model", "MODEL_UNAVAILABLE"),
    (b"permission_denied", "PERMISSION_DENIED"),
])
def test_metadata_preflight_preserves_failure_category_without_raw_provider_text(monkeypatch, diagnostic, kind):
    monkeypatch.setattr("runtime.antigravity.shutil.which", lambda *a, **k: "/fixture/agy")
    monkeypatch.setattr(
        "runtime.antigravity.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=1, stderr=diagnostic + b" private-value", stdout=b""),
    )
    result = discover_models({"HOME": "/fixture/clean"})
    assert result["failure"] == {"kind": kind}
    assert "private-value" not in json.dumps(result)


def test_model_discovery_is_metadata_only_and_reports_catalog_not_entitlement(monkeypatch):
    monkeypatch.setattr("runtime.antigravity.shutil.which", lambda *a, **k: "/fixture/agy")

    def invoke(command, **kwargs):
        assert command == ["/fixture/agy", "models"]
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"gemini-observed Model label\n")

    monkeypatch.setattr("runtime.antigravity.subprocess.run", invoke)
    result = discover_models({"HOME": "/fixture/clean"})
    assert result["state"] == "supported"
    assert result["reason"] == "catalog_not_entitlement"
    assert result["items"][0]["identifier"] == "gemini-observed"
