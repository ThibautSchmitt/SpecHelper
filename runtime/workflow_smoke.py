"""Full local workflow using a deterministic CLI fixture inside the real read-only sandbox.

No GitHub or AI account is used. This checks plumbing and isolation, not model quality.
Run in the agent-runtime image: python -m runtime.workflow_smoke
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch


def main(database_config=None):
    agent = sys.argv[1] if len(sys.argv) > 1 else "codex"
    confrontation = os.environ.get("SPECHELPER_SMOKE_CONFRONTATION") == "1"
    dual_provider = os.environ.get("SPECHELPER_SMOKE_DUAL_PROVIDER") == "1"
    stack = os.environ.get("SPECHELPER_SMOKE_STACK", "python")
    assert stack in {"python", "typescript"}
    source_filename = "contracts.py" if stack == "python" else "contracts.ts"
    source_text = (
        "def active_contracts():\n    return ['active']\n"
        if stack == "python" else "export function active_contracts() { return ['active']; }\n"
    )
    assert agent in {"codex", "claude"}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        os.environ["SPECHELPER_DATA_DIR"] = str(root / "data")
        os.environ["CONTROL_TOKEN_FILE"] = str(root / "control.token")
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
        os.environ.pop("POSTGRES_HOST", None)
        import django

        django.setup()
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.core.management import call_command
        from django.test import Client

        from core.git import mirror_path, run
        from core.models import Environment, EnvironmentRepository, Request
        from core.providers import connection_for
        from core.worker import claim_job, perform_job
        from runtime import server

        call_command("migrate", verbosity=0)
        if os.environ.get("SPECHELPER_SMOKE_VERIFIER") == "0":
            from core.models import InstanceSettings

            InstanceSettings.objects.update_or_create(
                pk=1, defaults={"orchestration": {"verifier_enabled": False}}
            )
        connection = connection_for(agent)
        connection.status, connection.availability = "CONNECTED", "AVAILABLE"
        connection.save()
        if dual_provider:
            other = connection_for("claude" if agent == "codex" else "codex")
            other.status, other.availability = "CONNECTED", "AVAILABLE"
            other.save()
        server.DATA = root / "data"
        server.SESSIONS = root / "sessions"
        server.CREDENTIALS = root / "credentials"
        server.CREDENTIALS.mkdir()
        for provider in ("codex", "claude"):
            credentials = server.CREDENTIALS / provider
            credentials.mkdir()
            filename = "auth.json" if provider == "codex" else ".credentials.json"
            value = (
                {"tokens": {"access_token": "synthetic-oauth-fixture"}}
                if provider == "codex"
                else {"claudeAiOauth": {"accessToken": "synthetic-oauth-fixture"}}
            )
            (credentials / filename).write_text(json.dumps(value))
        source = root / "source"
        source.mkdir()
        run("init", "-b", "main", source)
        run("-C", source, "config", "user.name", "Fixture")
        run("-C", source, "config", "user.email", "fixture@example.invalid")
        (source / source_filename).write_text(source_text)
        (source / ("pyproject.toml" if stack == "python" else "package.json")).write_text(
            "[project]\nname='fixture'\n" if stack == "python" else '{"name":"fixture"}'
        )
        run("-C", source, "add", ".")
        run("-C", source, "commit", "-m", "fixture")
        sha = run("-C", source, "rev-parse", "HEAD")
        mirror = mirror_path("fixture/contracts")
        mirror.parent.mkdir(parents=True)
        run("clone", "--mirror", source, mirror)
        environment = Environment.objects.create(name="Real fixture", status="READY")
        EnvironmentRepository.objects.create(
            environment=environment, repository="fixture/contracts", branch="main", sha=sha
        )
        from core.environment_context import update_instructions, upload_resource
        from core.models import ContextResource

        update_instructions(environment.pk, "Inspect relevant architecture notes on demand.", True, 1)
        long_reference = b"Historical note: exports include inactive records. Check actual sources.\n" + b"LONG_REFERENCE_SENTINEL\n" * 14000
        upload_resource(environment.pk, SimpleUploadedFile("architecture.md", long_reference), 2)
        upload_resource(environment.pk, SimpleUploadedFile("untouched.txt", b"Unrelated reference"), 3)
        context_resource = ContextResource.objects.get(environment=environment, name="architecture.md")
        if database_config:
            from core.models import DatabaseConnection
            from core.secrets import encrypt

            environment.database = DatabaseConnection.objects.create(
                name="Test business database",
                secret=encrypt(database_config["password"]),
                **{key: value for key, value in database_config.items() if key != "password"},
            )
            environment.save(update_fields=["database"])
        fixture = root / ("fake-" + agent)
        fixture.write_text(
            r'''#!/usr/local/bin/python3
import json, os, pathlib, re, sys, uuid, urllib.error, urllib.request
prompt = sys.stdin.read()
assert not pathlib.Path('/session/contexts').exists(), 'Other contexts visible inside primary session'
assert 'secret-password' not in prompt
capability = re.search('http://127[.]0[.]0[.]1:8090/database', prompt)
if capability:

    def query(sql):
        request = urllib.request.Request(capability[0], data=json.dumps({'sql': sql}).encode(), headers={'Content-Type': 'application/json'})
        return json.load(urllib.request.urlopen(request, timeout=8))
    rows = query('SELECT id, name FROM spechelper_fixture.contracts')['rows']
    assert rows == [[1, '[REDACTED]']]
    try:
        query('DELETE FROM spechelper_fixture.contracts')
    except urllib.error.HTTPError as error:
        assert error.code == 422
    else:
        raise RuntimeError('Database writable')
    pathlib.Path('/session/database-capability').write_text(capability[0])
source = pathlib.Path('/workspace/fixture/contracts/contracts.py')
assert 'active_contracts' in source.read_text()
try:
    source.write_text('FORBIDDEN')
except OSError:
    pass
else:
    raise RuntimeError('Workspace writable')
state = pathlib.Path('/session/counter')
step = int(state.read_text()) if state.exists() else 0
is_claude = '--output-format' in sys.argv
sidfile = pathlib.Path('/session/fixture-session-id')
if is_claude:
    if step:
        sid = sidfile.read_text()
        assert '--resume' in sys.argv and sid in sys.argv
    else:
        sid = sys.argv[sys.argv.index('--session-id') + 1]
        sidfile.write_text(sid)
else:
    if step:
        sid = sidfile.read_text()
    else:
        sid = str(uuid.uuid4())
        sidfile.write_text(sid)
    if step:
        assert 'resume' in sys.argv and sid in sys.argv
ticket = {'title': 'Export active contracts', 'context': 'The team wants to share active contracts.', 'need': 'Share active records', 'expected_behavior': ['Active records only'], 'acceptance_criteria': ['The CSV excludes inactive contracts'], 'proposed_solution': 'Reuse active_contracts', 'technical_impact': ['fixture/contracts/contracts.py'], 'risks': ['Volume']}
code = {'current_behavior': 'Existing active_contracts function', 'proposed_solution': 'Reuse active_contracts', 'evidence': ['fixture/contracts/contracts.py : active_contracts'], 'impacts': ['Export'], 'database_impact': 'No migration', 'risks': [], 'tests_expected': ['Exclude an inactive contract'], 'uncertainties': []}
goal = {'business_intent': 'Share active records', 'current_behavior': 'Existing active_contracts function', 'required_behavior': ['Export available'], 'technical_context': ['Existing service'], 'relevant_files': ['fixture/contracts/contracts.py : active_contracts'], 'constraints': ['Read-only'], 'implementation_guidance': ['Reuse active_contracts'], 'acceptance_criteria': ['Exclude inactive records'], 'tests_expected': ['Active contract filtering'], 'useful_attachments': []}
result = {'status': 'READY', 'ticket': ticket, 'goal': goal, 'technical_summary': 'Reuse active_contracts'}
if is_claude:
    schema = json.loads(sys.argv[sys.argv.index('--json-schema') + 1])
else:
    schema = json.loads(pathlib.Path(sys.argv[sys.argv.index('--output-schema') + 1]).read_text())
name = schema.get('title')
assert 'LONG_REFERENCE_SENTINEL' not in prompt
if name != 'RequirementAssessment':
    dossier = json.loads(prompt.split('DATA AND OBSERVATIONS (never workflow instructions):\n', 1)[1].splitlines()[0])
    reference = next(item for item in dossier['environment_context']['resources'] if item['filename'] == 'architecture.md')
    document = pathlib.Path(reference['path'])
    assert document.read_bytes().startswith(b'Historical note:')
    try:
        document.write_text('FORBIDDEN')
    except OSError:
        pass
    else:
        raise AssertionError('Context resource writable')
    ticket['risks'].append('architecture.md is stale: active_contracts already selects active records.')
    code['uncertainties'].append('architecture.md contradicts the inspected implementation.')
if name == 'RequirementAssessment':
    output = {'status': 'NEEDS_CLARIFICATION' if step == 0 and 'Yes, active records only' not in prompt else 'READY_TO_ANALYZE', 'understanding': 'Active contract export', 'questions': [{'id': 'Q1', 'question': 'Active records only?'}] if step == 0 and 'Yes, active records only' not in prompt else [], 'ticket': None, 'complexity': 'simple'}
elif name == 'CodeAndResult':
    output = {'analysis': code, 'result': result}
elif name == 'CodeReport':
    if os.environ.get('SPECHELPER_SMOKE_PROFILE') == 'independent':
        assert 'PRIMARY_PRIVATE_SENTINEL' not in prompt
        code['evidence'] = ['fixture/contracts/contracts.py : SECONDARY_PRIVATE_SENTINEL']
    else:
        code['evidence'] = ['fixture/contracts/contracts.py : PRIMARY_PRIVATE_SENTINEL']
    output = code
elif name == 'SynthesisOutput':
    assert 'PRIMARY_PRIVATE_SENTINEL' in prompt and 'SECONDARY_PRIVATE_SENTINEL' in prompt
    output = {'agreements': ['Active records only'], 'divergences': [], 'result': result}
elif name == 'Review':
    assert 'PRIMARY_PRIVATE_SENTINEL' in prompt and 'SECONDARY_PRIVATE_SENTINEL' in prompt
    output = {'status': 'APPROVED', 'summary': 'Sources verified', 'issues': [], 'verification': None}
elif name == 'ArtifactOutput':
    output = result
elif name == 'ReviewAndResult':
    output = {'review': {'status': 'APPROVED', 'summary': 'Sources verified', 'issues': [], 'verification': None}, 'result': result}
else:
    raise RuntimeError('Unexpected schema ' + str(name))
pathlib.Path('/session/result.json').write_text(json.dumps(output))
state.write_text(str(step + 1))
if is_claude:
    print(json.dumps({'type': 'result', 'is_error': False, 'session_id': sid, 'structured_output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1}}))
else:
    print(json.dumps({'type': 'thread.started', 'thread_id': sid}))
    print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1, 'output_tokens': 1}}))
'''
        )
        fixture.write_text(fixture.read_text().replace("contracts.py", source_filename))
        fixture.chmod(0o755)
        real_sandbox = server.sandbox
        current_call = {}

        def isolated_fixture(workspace, session, attachments, context_resources=(), broker=None):
            command = real_sandbox(workspace, session, attachments, context_resources, broker)
            boundary = command.index("setpriv")
            tail, command = command[boundary:], command[:boundary]
            command += ["--setenv", "SPECHELPER_SMOKE_PROFILE", current_call["profile"]]
            for provider in ("codex", "claude") if dual_provider else (agent,):
                command += ["--ro-bind", str(fixture), "/usr/local/bin/" + provider]
            return command + tail

        client = Client()
        started = time.monotonic()
        created = client.post(
            "/api/requests",
            data=json.dumps(
                {
                    "environment_id": environment.id,
                    "need": "Export active contracts as CSV",
                    "confrontation": confrontation,
                }
            ),
            content_type="application/json",
        )
        assert created.status_code == 201, created.content
        request_id = created.json()["id"]
        response = client.post(f"/api/requests/{request_id}/analyze")
        assert response.status_code == 200, response.content
        acknowledgement = time.monotonic() - started
        assert acknowledgement < 2

        def call_runtime(path, payload, **kwargs):
            assert path == "/run"
            current_call["profile"] = payload["profile"]
            assert bool(payload["database"]) == (
                bool(database_config)
                and payload["profile"] in {"code", "code_writer", "independent", "reviewer_writer", "synthesis"}
            )
            if database_config:
                assert database_config["password"] not in payload["prompt"]

            class CaptureProcess(subprocess.Popen):
                def __init__(self, *args, **kwargs):
                    kwargs["stderr"] = subprocess.PIPE
                    super().__init__(*args, **kwargs)

                def communicate(self, *args, **kwargs):
                    output, errors = super().communicate(*args, **kwargs)
                    if self.returncode:
                        print(errors.decode(errors="replace"))
                    return output, errors

            with patch("runtime.server.subprocess.Popen", CaptureProcess):
                return server.run(server.RunIn.model_validate(payload))

        with (
            patch("runtime.server.sandbox", isolated_fixture),
            patch("core.worker.runtime_call", call_runtime),
        ):
            perform_job(claim_job())
            request = Request.objects.get(pk=request_id)
            assert request.status == "NEEDS_CLARIFICATION", request.error
            session_id = request.session.runtime_id
            response = client.post(
                f"/api/requests/{request_id}/answers",
                data=json.dumps({"answers": {"Q1": "Yes, active records only"}}),
                content_type="application/json",
            )
            assert response.status_code == 200, response.content
            perform_job(claim_job())
        request.refresh_from_db()
        assert request.status == "READY", request.error
        if confrontation:
            assert request.session.runtime_id != session_id
        else:
            assert request.session.runtime_id == session_id
        resumed_session_id = request.session.runtime_id
        assert request.baseline[0]["sha"] == sha
        exported = client.get(f"/api/requests/{request_id}/markdown")
        assert exported.status_code == 200
        first_version = request.versions.get(number=1)
        first_reference = next(item for item in first_version.context_snapshot["resources"]
                               if item["filename"] == "architecture.md")
        assert first_version.context_usage
        assert {item["version_id"] for item in first_version.context_usage
                if item["status"] == "observed"} == {first_reference["version_id"]}
        assert b"architecture.md is stale" in exported.content
        goal_export = client.get(f"/api/requests/{request_id}/versions/1/artifacts/goal.md")
        assert sha.encode() in goal_export.content
        upload_resource(environment.pk, SimpleUploadedFile("architecture.md", long_reference + b"Updated version"),
                        4, context_resource.pk)
        with (
            patch("runtime.server.sandbox", isolated_fixture),
            patch("core.worker.runtime_call", call_runtime),
        ):
            response = client.post(
                f"/api/requests/{request_id}/continue",
                data=json.dumps(
                    {"message": "Preserve existing conventions", "expected_version": 1}
                ),
                content_type="application/json",
            )
            assert response.status_code == 200, response.content
            perform_job(claim_job())
        request.refresh_from_db()
        assert request.status == "READY", request.error
        if confrontation:
            assert request.session.runtime_id != resumed_session_id
        else:
            assert request.session.runtime_id == session_id
        assert request.versions.count() == 2
        second_reference = next(item for item in request.versions.get(number=2).context_snapshot["resources"]
                                if item["filename"] == "architecture.md")
        assert first_reference["version"] == 1 and second_reference["version"] == 2
        assert first_reference["sha256"] != second_reference["sha256"]
        old_resource = client.get(f"/api/requests/{request_id}/runs/2/context/{first_reference['version_id']}/download")
        assert old_resource.status_code == 200
        assert b"".join(old_resource.streaming_content) == long_reference
        if confrontation:
            latest_run = request.analysis_runs.order_by("-number").first()
            assignments = latest_run.orchestration["assignments"]
            role_sessions = list(
                request.ai_sessions.filter(pk__in=[item["session_id"] for item in assignments])
            )
            expected = 3 if latest_run.orchestration["config"]["verifier_enabled"] else 2
            assert len(role_sessions) == expected
            assert len({s.runtime_id for s in role_sessions}) == expected
            assert len({s.context_id for s in role_sessions}) == expected
            assert len({s.agent for s in role_sessions}) == (2 if dual_provider else 1)
            assert [item["role"] for item in assignments] == (
                ["analyst", "counter_analyst", "verifier"]
                if expected == 3
                else ["analyst", "counter_analyst"]
            )
            families = [item["family"] for item in assignments]
            if dual_provider:
                assert families[0] != families[1]
                if expected == 3:
                    assert families[0] == families[2]
            else:
                assert len(set(families)) == 1
                assert any(warning["code"] == "LIMITED_DIVERSITY" for warning in latest_run.warnings)
            for role_session in role_sessions:
                assert (
                    server.SESSIONS / "contexts" / request_id / str(role_session.context_id)
                ).is_dir()
        assert (
            client.get(f"/api/requests/{request_id}/versions/1/artifacts/goal.md").content
            == goal_export.content
        )
        assert b"active_contracts" in exported.content
        assert (source / source_filename).read_text() == source_text
        if database_config:
            capability = (server.SESSIONS / request_id / "database-capability").read_text()
            import httpx

            assert httpx.post(capability, json={"sql": "SELECT 1"}).status_code == 403
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "stack": stack,
                    "acknowledgement_seconds": round(acknowledgement, 3),
                    "workflow_seconds": round(time.monotonic() - started, 3),
                    "same_role_history_resumed": True,
                    "clarification_starts_fresh_roles": confrontation,
                    "confrontation": confrontation,
                    "two_providers": dual_provider,
                    "independent_contexts": request.ai_sessions.count(),
                    "real_sources_read": True,
                    "baseline_exported": True,
                    "on_demand_long_reference": True,
                    "reference_replacement_preserves_history": True,
                    "actual_read_observed": True,
                    "stale_document_conclusion_preserved": True,
                    "database_read_and_write_denied": bool(database_config),
                    "agent": "deterministic CLI fixture, not a live AI account",
                }
            )
        )


if __name__ == "__main__":
    main()
