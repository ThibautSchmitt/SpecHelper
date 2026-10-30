"""Observed progress is bounded, fenced, private and never promoted to evidence."""

import copy
import json
from uuid import uuid4

import httpx
import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from core.agent import runtime_call
from core.models import AnalysisRun, Job, Request, RequestMessage, StepExecution
from core.progress_text import safe_prefix
from core.sensitive_data import redact
from core.work_progress import Recorder, snapshot
from runtime.progress import Observer, string_field

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "text,path,expected",
    [
        ('{"message":"Hello', "message", "Hello"),
        ('{"message":"A \\"quote\\" and \\u00e9', "message", 'A "quote" and é'),
        ('{"message":"A \\uD83D', "message", "A "),
        ('{"message":"A \\uD83D\\uDE00', "message", "A 😀"),
        ('{"private":"message: hidden", "answer":{"summary":"Public', "answer.summary", "Public"),
        ('{"private":{"message":"Hidden"},"message":"Visible"}', "message", "Visible"),
        ('{"thinking":"Hidden"}', "message", ""),
        ("not JSON", "message", ""),
        ('{"message":"Incomplete \\u0', "message", "Incomplete "),
    ],
)
def test_only_selected_user_response_string_is_decoded(text, path, expected):
    assert string_field(text, path) == expected


def test_codex_tool_lifecycle_never_exports_reasoning_commands_or_paths():
    frames = []
    observer = Observer("codex", lambda frame: frames.append(copy.deepcopy(frame)), "message")
    observer.feed(
        json.dumps(
            {
                "type": "item.started",
                "item": {
                    "id": "call-secret",
                    "type": "command_execution",
                    "command": "rg private-needle /credentials/private",
                },
            }
        )
    )
    observer.feed(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "call-secret",
                    "type": "command_execution",
                    "status": "completed",
                    "exit_code": 0,
                    "aggregated_output": "PRIVATE OUTPUT",
                },
            }
        )
    )
    observer.feed(
        json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "thinking", "type": "reasoning", "text": "PRIVATE REASONING"},
            }
        )
    )
    event = frames[-1]["events"][0]
    assert event["operation"] == "search" and event["state"] == "done"
    assert len(frames[-1]["events"]) == 1
    assert all(
        marker not in json.dumps(frames)
        for marker in ("private-needle", "/credentials", "PRIVATE", "call-secret")
    )
    sequence = observer.sequence
    observer.feed(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "call-secret",
                    "type": "command_execution",
                    "status": "completed",
                    "exit_code": 0,
                },
            }
        )
    )
    assert observer.sequence == sequence


def test_failed_tools_are_never_successful_and_private_plan_text_is_omitted():
    frames = []
    observer = Observer("codex", frames.append)
    for index in range(35):
        observer.feed(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": str(index),
                        "type": "command_execution",
                        "command": "cat hidden.txt",
                        "status": "failed",
                        "exit_code": 1,
                    },
                }
            )
        )
    assert len(frames[-1]["events"]) == 24
    assert all(event["state"] == "error" for event in frames[-1]["events"])
    observer.feed(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "plan",
                    "type": "todo_list",
                    "items": [{"text": "PRIVATE HYPOTHESIS"}],
                },
            }
        )
    )
    assert "PRIVATE" not in json.dumps(frames)


def test_claude_partial_messages_only_stream_the_explicit_public_field():
    frames = []
    observer = Observer("claude", lambda frame: frames.append(copy.deepcopy(frame)), "message")
    observer.event(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking"},
            },
        }
    )
    observer.event(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "PRIVATE REASONING"},
            },
        }
    )
    assert not frames
    observer.event(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "read-1",
                        "name": "Read",
                        "input": {"file_path": "/data/private.py"},
                    }
                ]
            },
        }
    )
    observer.event({"type": "stream_event", "event": {"type": "content_block_stop", "index": 0}})
    assert frames[-1]["events"][0]["state"] == "running"
    observer.event(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "read-1", "content": "PRIVATE SOURCE"}
                ]
            },
        }
    )
    assert frames[-1]["events"][0]["state"] == "done"
    observer.event(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "tool_use", "name": "StructuredOutput", "id": "output"},
            },
        }
    )
    for part in ['{"message":"An ', "answer", '"}']:
        observer.event(
            {
                "type": "stream_event",
                "event": {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "input_json_delta", "partial_json": part},
                },
            }
        )
    assert [frame["preview"] for frame in frames if frame["preview"]] == ["An ", "An answer"]
    assert all(
        marker not in json.dumps(frames) for marker in ("PRIVATE", "/data/", "StructuredOutput")
    )


def test_antigravity_uses_observed_steps_and_never_relabels_model_text_as_work():
    frames = []
    observer = Observer("antigravity", frames.append, "message")
    observer.event(
        {
            "event": "step_update",
            "step_update": {
                "step_id": "x",
                "step_type": "model",
                "state": "RUNNING",
                "text": "PRIVATE THOUGHTS",
            },
        }
    )
    assert not frames
    for state in ["RUNNING", "DONE", "DONE"]:
        observer.event(
            {
                "event": "step_update",
                "step_update": {
                    "step_id": "read-1",
                    "step_type": "tool",
                    "tool_name": "read_file",
                    "state": state,
                    "tool_info": {
                        "parameters": {"path": "/private/hidden"},
                        "output": "PRIVATE SOURCE",
                    },
                },
            }
        )
    assert len(frames[-1]["events"]) == 1 and frames[-1]["events"][0]["state"] == "done"
    assert "PRIVATE" not in json.dumps(frames) and "/private" not in json.dumps(frames)


def test_partial_credentials_never_appear_in_released_prefixes():
    secret = uuid4().hex
    for length in range(1, len(secret)):
        value = safe_prefix(
            "Hello " + secret[:length], [secret], lambda text: redact(text, [secret])
        )
        assert value == "Hello "
    assert "[REDACTED]" in safe_prefix(
        "Hello " + secret + " end", [secret], lambda text: redact(text, [secret])
    )
    assert "sk-test" not in safe_prefix("Answer sk-test", [], lambda text: redact(text, []))
    assert "/credentials" not in safe_prefix(
        "Read /credentials/hidden then continue", [], lambda text: redact(text, [])
    )


def prepared(client, environment):
    value = client.post(
        "/api/analyses",
        {"environment_id": environment.pk, "need": "Explain the SQL export."},
        content_type="application/json",
    ).json()
    request = Request.objects.get(pk=value["id"])
    attempt = str(uuid4())
    job = Job.objects.create(
        kind="discussion",
        target=str(request.pk),
        status="RUNNING",
        payload={"attempt_id": attempt, "revision": 1, "private_snapshot": "HIDDEN MANIFEST"},
    )
    payload = {
        "request_id": str(request.pk),
        "attempt_id": attempt,
        "agent": "codex",
        "schema": {"properties": {"message": {"type": "string"}}},
    }
    return request, job, payload


def frame(sequence=1, preview=""):
    return {
        "type": "progress",
        "sequence": sequence,
        "activity": "read",
        "preview": preview,
        "events": [
            {
                "id": "a" * 20,
                "operation": "read",
                "state": "running",
                "observed_at": "2026-10-30T10:00:00+00:00",
            }
        ],
    }


def test_history_cursor_and_ownership_without_loading_the_conversation(client, environment):
    value, job, payload = prepared(client, environment)
    recorder = Recorder.for_payload(payload)
    before = snapshot(value)
    recorder.receive(frame())
    current = snapshot(value)
    assert before["progress_token"] == current["progress_token"]
    assert before["progress_cursor"] != current["progress_cursor"]
    RequestMessage.objects.create(
        request=value,
        role="assistant",
        kind="discussion_reply",
        content="HIDDEN LONG HISTORY" * 1000,
    )
    endpoint = f"/api/analyses/{value.pk}/progress"
    with CaptureQueriesContext(connection) as queries:
        response = client.get(endpoint)
    assert response.status_code == 200 and len(queries) <= 10
    with CaptureQueriesContext(connection) as projection_queries:
        snapshot(value)
    assert len(projection_queries) <= 3
    assert "HIDDEN" not in response.content.decode()
    assert len(response.content) < 10000
    cursor = response.json()["progress_cursor"]
    assert client.get(endpoint, {"cursor": cursor}).json() == {
        "unchanged": True,
        "progress_cursor": cursor,
    }
    assert Client().get(endpoint).status_code == 404
    reopened = Client()
    reopened.cookies = client.cookies.copy()
    assert reopened.get(endpoint).json()["work_progress"][0]["phases"][0]["events"]


def test_cancelled_or_superseded_execution_cannot_write_late_progress(client, environment):
    value, job, payload = prepared(client, environment)
    recorder = Recorder.for_payload(payload)
    recorder.receive(frame())
    Job.objects.filter(pk=job.pk).update(status="CANCELLED")
    recorder.receive(frame(2, "Late output"))
    recorder.flush(closed=True)
    public = snapshot(value)["work_progress"][0]
    assert not public["phases"][0]["active"] and not public["phases"][0]["preview"]
    assert public["phases"][0]["events"][0]["state"] == "unknown"
    job.refresh_from_db()
    assert job.progress["phases"][0]["sequence"] == 1


def test_deep_observations_do_not_enter_role_evidence_or_frozen_context(client, environment):
    value, discussion_job, _ = prepared(client, environment)
    job = Job.objects.create(kind="analysis", target=str(value.pk), status="RUNNING")
    run = AnalysisRun.objects.create(
        request=value,
        job=job,
        number=1,
        orchestration={"outputs": {"analyst": {"summary": "Initial facts"}}},
        context_snapshot={"human": "Confirmed context"},
    )
    step = StepExecution.objects.create(
        job=job,
        checkpoint="counter_independent",
        public_role="counter_analyst",
        status="RUNNING",
        output={},
        instruction_snapshot={"independent": True},
    )
    recorder = Recorder.for_payload(
        {"request_id": str(value.pk), "attempt_id": str(step.attempt_id)}
    )
    assert recorder.preview_field({"schema": {"properties": {"answer": {}}}}) == ""
    recorder.receive(frame())
    step.refresh_from_db()
    run.refresh_from_db()
    assert step.output == {} and step.instruction_snapshot == {"independent": True}
    assert run.context_snapshot == {"human": "Confirmed context"}
    assert run.orchestration == {"outputs": {"analyst": {"summary": "Initial facts"}}}


def test_runtime_stream_records_only_public_frames_and_preserves_final_contract(
    client, environment, settings, monkeypatch
):
    value, job, payload = prepared(client, environment)
    settings.RUNTIME_TOKEN = "fixture-control-token"
    result = {
        "output": {"message": "The final reply"},
        "session_id": str(uuid4()),
        "quota_status": {"state": "unavailable"},
    }
    wire = []
    original = httpx.Client

    def handler(request):
        wire.append(json.loads(request.content))
        events = [
            frame(1, "First public words"),
            {"type": "heartbeat"},
            frame(2, "The final reply"),
            {"type": "result", "result": result},
        ]
        return httpx.Response(
            200,
            headers={"Content-Type": "application/x-ndjson"},
            content="\n".join(json.dumps(e) for e in events) + "\n",
        )

    monkeypatch.setattr(
        "core.agent.httpx.Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    observations = []
    monkeypatch.setattr(
        "core.quota_refresh.record_invocation_metadata", lambda p, r: observations.append(r)
    )
    assert runtime_call("/run", payload) == result
    assert wire[0]["stream_events"] and wire[0]["preview_field"] == "message"
    job.refresh_from_db()
    phase = job.progress["phases"][0]
    assert phase["sequence"] == 2 and phase["closed"]
    assert len(observations) == 1


@pytest.mark.parametrize("transport_failure", [False, True])
def test_incomplete_stream_clears_draft_and_records_one_metadata_failure(
    client, environment, settings, monkeypatch, transport_failure
):
    _, job, payload = prepared(client, environment)
    settings.RUNTIME_TOKEN = "fixture-control-token"
    original = httpx.Client

    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield (json.dumps(frame(1, "A pending answer")) + "\n").encode()
            if transport_failure:
                raise httpx.ReadError("Disconnected")

    def handler(request):
        return httpx.Response(
            200, headers={"Content-Type": "application/x-ndjson"}, stream=Interrupted()
        )

    monkeypatch.setattr(
        "core.agent.httpx.Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    observations = []
    monkeypatch.setattr(
        "core.quota_refresh.record_invocation_metadata", lambda p, r: observations.append(r)
    )
    with pytest.raises(ValueError):
        runtime_call("/run", payload)
    job.refresh_from_db()
    phase = job.progress["phases"][0]
    assert phase["closed"] and not phase["preview"]
    assert observations == [{"quota_status": {"state": "error"}}]


def test_duplicate_or_malformed_frames_do_not_override_observed_history(client, environment):
    _, job, payload = prepared(client, environment)
    recorder = Recorder.for_payload(payload)
    recorder.receive(frame(3))
    recorder.receive({**frame(4), "private_reasoning": "Never stored"})
    recorder.receive(frame(2, "Out of order"))
    recorder.flush()
    job.refresh_from_db()
    phase = job.progress["phases"][0]
    assert phase["sequence"] == 3
    assert "Never stored" not in json.dumps(job.progress)
    assert "Out of order" not in json.dumps(job.progress)
