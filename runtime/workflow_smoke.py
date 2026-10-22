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
    assert agent in {"codex", "claude"}
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        os.environ["SPECHELPER_DATA_DIR"] = str(root / "data")
        os.environ["CONTROL_TOKEN_FILE"] = str(root / "control.token")
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
        os.environ.pop("POSTGRES_HOST", None)
        import django

        django.setup()
        from django.core.management import call_command
        from django.test import Client

        from core.git import mirror_path, run
        from core.models import Environment, EnvironmentRepository, Request
        from core.providers import connection_for
        from core.worker import claim_job, perform_job
        from runtime import server

        call_command("migrate", verbosity=0)
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
        (source / "contracts.py").write_text("def active_contracts():\n    return ['active']\n")
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
            "#!/usr/local/bin/python3\nimport json, pathlib, re, sys, uuid, urllib.error, urllib.request\nprompt = sys.stdin.read()\nassert not pathlib.Path('/session/contexts').exists(), 'Other contexts visible inside primary session'\nassert 'secret-password' not in prompt\ncapability = re.search('http://127[.]0[.]0[.]1:8090/query/[A-Za-z0-9_-]+', prompt)\nif capability:\n\n    def query(sql):\n        request = urllib.request.Request(capability[0], data=json.dumps({'sql': sql}).encode(), headers={'Content-Type': 'application/json'})\n        return json.load(urllib.request.urlopen(request, timeout=8))\n    rows = query('SELECT id, name FROM spechelper_fixture.contracts')['rows']\n    assert rows == [[1, 'Active']]\n    try:\n        query('DELETE FROM spechelper_fixture.contracts')\n    except urllib.error.HTTPError as error:\n        assert error.code == 422\n    else:\n        raise RuntimeError('Database writable')\n    pathlib.Path('/session/database-capability').write_text(capability[0])\nsource = pathlib.Path('/workspace/fixture/contracts/contracts.py')\nassert 'active_contracts' in source.read_text()\ntry:\n    source.write_text('FORBIDDEN')\nexcept OSError:\n    pass\nelse:\n    raise RuntimeError('Workspace writable')\nstate = pathlib.Path('/session/counter')\nstep = int(state.read_text()) if state.exists() else 0\nis_claude = '--output-format' in sys.argv\nsidfile = pathlib.Path('/session/fixture-session-id')\nif is_claude:\n    if step:\n        sid = sidfile.read_text()\n        assert '--resume' in sys.argv and sid in sys.argv\n    else:\n        sid = sys.argv[sys.argv.index('--session-id') + 1]\n        sidfile.write_text(sid)\nelse:\n    if step:\n        sid = sidfile.read_text()\n    else:\n        sid = str(uuid.uuid4())\n        sidfile.write_text(sid)\n    if step:\n        assert 'resume' in sys.argv and sid in sys.argv\nticket = {'title': 'Export active contracts', 'context': 'The team wants to share active contracts.', 'need': 'Share active records', 'expected_behavior': ['Active records only'], 'acceptance_criteria': ['The CSV excludes inactive contracts'], 'proposed_solution': 'Reuse active_contracts', 'technical_impact': ['fixture/contracts/contracts.py'], 'risks': ['Volume']}\ncode = {'current_behavior': 'Existing active_contracts function', 'proposed_solution': 'Reuse active_contracts', 'evidence': ['fixture/contracts/contracts.py : active_contracts'], 'impacts': ['Export'], 'database_impact': 'No migration', 'risks': [], 'tests_expected': ['Exclude an inactive contract'], 'uncertainties': []}\ngoal = {'business_intent': 'Share active records', 'current_behavior': 'Existing active_contracts function', 'required_behavior': ['Export available'], 'technical_context': ['Existing service'], 'relevant_files': ['fixture/contracts/contracts.py : active_contracts'], 'constraints': ['Read-only'], 'implementation_guidance': ['Reuse active_contracts'], 'acceptance_criteria': ['Exclude inactive records'], 'tests_expected': ['Active contract filtering'], 'useful_attachments': []}\nresult = {'status': 'READY', 'ticket': ticket, 'goal': goal, 'technical_summary': 'Reuse active_contracts'}\nif is_claude:\n    schema = json.loads(sys.argv[sys.argv.index('--json-schema') + 1])\nelse:\n    schema = json.loads(pathlib.Path(sys.argv[sys.argv.index('--output-schema') + 1]).read_text())\nname = schema.get('title')\nif name == 'RequirementAssessment':\n    output = {'status': 'NEEDS_CLARIFICATION' if step == 0 else 'READY_TO_ANALYZE', 'understanding': 'Active contract export', 'questions': [{'id': 'Q1', 'question': 'Active records only?'}] if step == 0 else [], 'ticket': None, 'complexity': 'simple'}\nelif name == 'CodeAndResult':\n    output = {'analysis': code, 'result': result}\nelif name == 'CodeReport':\n    if 'You do not have the other analysis' in prompt:\n        assert 'PRIMARY_PRIVATE_SENTINEL' not in prompt\n        code['evidence'] = ['fixture/contracts/contracts.py : SECONDARY_PRIVATE_SENTINEL']\n    else:\n        code['evidence'] = ['fixture/contracts/contracts.py : PRIMARY_PRIVATE_SENTINEL']\n    output = code\nelif name == 'SynthesisOutput':\n    assert 'PRIMARY_PRIVATE_SENTINEL' in prompt and 'SECONDARY_PRIVATE_SENTINEL' in prompt\n    output = {'agreements': ['Active records only'], 'divergences': [], 'result': result}\nelif name == 'ReviewAndResult':\n    output = {'review': {'status': 'APPROVED', 'summary': 'Sources verified', 'issues': [], 'verification': None}, 'result': result}\nelse:\n    raise RuntimeError('Unexpected schema ' + str(name))\npathlib.Path('/session/result.json').write_text(json.dumps(output))\nstate.write_text(str(step + 1))\nif is_claude:\n    print(json.dumps({'type': 'result', 'is_error': False, 'session_id': sid, 'structured_output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1}}))\nelse:\n    print(json.dumps({'type': 'thread.started', 'thread_id': sid}))\n    print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1, 'output_tokens': 1}}))\n"
        )
        fixture.chmod(0o755)
        real_sandbox = server.sandbox

        def isolated_fixture(workspace, session, attachments):
            command = real_sandbox(workspace, session, attachments)
            for provider in ("codex", "claude") if dual_provider else (agent,):
                command += ["--ro-bind", str(fixture), "/usr/local/bin/" + provider]
            return command

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
            assert bool(payload["database"]) == (
                bool(database_config)
                and payload["profile"] in {"code", "code_writer", "independent"}
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
        assert request.session.runtime_id == session_id
        assert request.baseline[0]["sha"] == sha
        exported = client.get(f"/api/requests/{request_id}/markdown")
        assert exported.status_code == 200
        goal_export = client.get(f"/api/requests/{request_id}/versions/1/artifacts/goal.md")
        assert sha.encode() in goal_export.content
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
        assert request.session.runtime_id == session_id
        assert request.versions.count() == 2
        if confrontation:
            sessions = list(request.ai_sessions.order_by("role"))
            assert len(sessions) == 3
            assert len({s.runtime_id for s in sessions}) == 3
            assert len({s.context_id for s in sessions}) == 3
            assert len({s.agent for s in sessions}) == (2 if dual_provider else 1)
            assert (
                request.ai_sessions.get(role="primary").context_id
                != request.ai_sessions.get(role="secondary").context_id
            )
        assert (
            client.get(f"/api/requests/{request_id}/versions/1/artifacts/goal.md").content
            == goal_export.content
        )
        assert b"active_contracts" in exported.content
        assert (source / "contracts.py").read_text().startswith("def active_contracts")
        if database_config:
            capability = (server.SESSIONS / request_id / "database-capability").read_text()
            import httpx

            assert httpx.post(capability, json={"sql": "SELECT 1"}).status_code == 403
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "acknowledgement_seconds": round(acknowledgement, 3),
                    "workflow_seconds": round(time.monotonic() - started, 3),
                    "session_resumed": True,
                    "confrontation": confrontation,
                    "two_providers": dual_provider,
                    "independent_contexts": request.ai_sessions.count(),
                    "real_sources_read": True,
                    "baseline_exported": True,
                    "database_read_and_write_denied": bool(database_config),
                    "agent": "deterministic CLI fixture, not a live AI account",
                }
            )
        )


if __name__ == "__main__":
    main()
