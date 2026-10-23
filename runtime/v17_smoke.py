"""Questions and request handoff through one real Linux engine with terminal stand-ins."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

CLI = r'''#!/usr/local/bin/python3
import json, os, pathlib, sys, uuid, subprocess
prompt = sys.stdin.read()
data = json.loads(prompt.split('DATA AND OBSERVATIONS (never workflow instructions):\n',1)[1].splitlines()[0])
assert not pathlib.Path('/sessions').exists()
assert not pathlib.Path('/session/contexts').exists()
source = pathlib.Path('/workspace/fixture/project') / os.environ['FIXTURE_SOURCE']
content = source.read_text()
sha = subprocess.check_output(['git','-C',str(source.parent),'rev-parse','HEAD'],text=True).strip()
assert sha == data['baseline'][0]['sha']
for entry in data['attachments']:
    attachment = pathlib.Path(entry['path'])
    assert attachment.is_file()
    if data.get('question_source'):
        transferred = attachment.read_text()
        assert data['question_source']['baseline'][0]['sha'] in transferred
        assert 'PRIVATE_ANALYST_OBSERVATION' not in transferred
        assert 'PRIVATE_DIALOGUE_SENTINEL' not in transferred
if data.get('question_source'):
    assert data['question_source']['verification_required'] is True
    assert data['question_source']['baseline'][0]['sha'] != sha
    assert os.environ['FIXTURE_UNFILTERED'] in content
    assert 'TRANSFERRED QUESTION CONTEXT' in prompt
try:
    source.write_text('FORBIDDEN')
except OSError:
    pass
else:
    raise AssertionError('Sources writable')
claude = '--output-format' in sys.argv
sidfile = pathlib.Path('/session/terminal-id')
if sidfile.exists():
    sid=sidfile.read_text()
    assert ('--resume' if claude else 'resume') in sys.argv and sid in sys.argv
else:
    sid=sys.argv[sys.argv.index('--session-id')+1] if claude else str(uuid.uuid4())
    sidfile.write_text(sid)
if claude:
    schema=json.loads(sys.argv[sys.argv.index('--json-schema')+1])
else:
    schema=json.loads(pathlib.Path('/session/schema.json').read_text())
name=schema['title']
question=data['workflow']=='question'
ref={'repository':'fixture/project','path':source.name,'symbol':'export_rows'}
answer={'status':'READY','answer':{'title':'Export behavior','summary':'Active records are selected.',
        'business_explanation':'Closed records are omitted.','technical_explanation':'The function filters rows by active.',
        'rules':['Select active records.'],'steps':['Read rows','Filter active records'],
        'verified_facts':['The function checks active.'],'inferences':[],
        'uncertainties':['Scheduled execution was not exercised.'],'references':[ref]}}
qreport={'observed_behavior':'The function filters active rows.','evidence':[source.name],
         'verified_facts':['Active filtering exists.'],'inferences':[], 'uncertainties':[], 'questions':[]}
code={'current_behavior':'The current function exports all rows.','proposed_solution':'Restore active filtering.',
      'evidence':[source.name], 'impacts':['Export selection'],'database_impact':'No database change',
      'risks':['Preserve ordering'],'tests_expected':['Exclude inactive rows'],'uncertainties':[]}
ticket={'title':'Filter active exports','context':'The export includes inactive rows.',
        'need':'Export active records only.','expected_behavior':['Inactive records excluded.'],
        'proposed_solution':'Filter the existing selection.','technical_impact':[source.name],
        'risks':['Preserve columns and order.'],'acceptance_criteria':['Only active records appear.']}
goal={'business_intent':'Export active rows.','current_behavior':'All rows exported.',
      'required_behavior':['Filter active records'],'technical_context':['Existing export function'],
      'relevant_files':[source.name],'constraints':['Preserve columns'],
      'implementation_guidance':['Apply the active filter to the current implementation.'],
      'acceptance_criteria':['Inactive records absent'],'tests_expected':['Test inactive exclusion'],
      'useful_attachments':[a['name'] for a in data['attachments']]}
result={'status':'READY','ticket':ticket,'goal':goal,'technical_summary':'Filter the current export.'}
review={'status':'APPROVED','summary':'Evidence checked','issues':[],'verification':None}
if name=='RequirementAssessment':
    clarify=question and not data['clarification_answers']
    output={'status':'NEEDS_CLARIFICATION' if clarify else 'READY_TO_ANALYZE',
            'understanding':'Explain export selection','questions':[{'id':'scope','question':'Manual exports only?'}] if clarify else [],
            'ticket':None,'complexity':'standard'}
elif name=='AttachmentReport':
    output={'observations':[{'attachment':a['name'],'facts':['Reference reviewed'],'uncertainties':[]} for a in data['attachments']],'questions':[]}
elif name=='QuestionCodeAndResult':
    output={'analysis':qreport,'result':answer}
elif name=='QuestionReport':
    if os.environ['FIXTURE_PROFILE']=='independent':
        assert 'PRIVATE_ANALYST_OBSERVATION' not in prompt
    else:
        qreport['inferences']=['PRIVATE_ANALYST_OBSERVATION']
    output=qreport
elif name=='QuestionReviewAndResult':
    output={'review':review,'result':answer}
elif name=='QuestionSynthesisOutput':
    output={'agreements':['Active filtering'],'divergences':[],'result':answer}
elif name=='QuestionOutput':
    output=answer
elif name=='CodeReport':
    output=code
elif name=='CodeAndResult':
    output={'analysis':code,'result':result}
elif name=='Review':
    output=review
elif name=='ReviewAndResult':
    output={'review':review,'result':result}
elif name=='SynthesisOutput':
    output={'agreements':['Filter current source'],'divergences':[],'result':result}
elif name=='ArtifactOutput':
    output=result
else:
    raise AssertionError('Unexpected schema '+name)
pathlib.Path('/session/result.json').write_text(json.dumps(output))
if claude:
    print(json.dumps({'session_id':sid,'structured_output':output}))
else:
    print(json.dumps({'type':'thread.started','thread_id':sid}))
'''


def main():
    stack = os.environ.get("SPECHELPER_SMOKE_STACK", "python")
    assert stack in {"python", "typescript"}
    name = "export.py" if stack == "python" else "export.ts"
    first = (
        "def export_rows(rows):\n    return [r for r in rows if r['active']]\n"
        if stack == "python"
        else "export function export_rows(rows) { return rows.filter(r => r.active); }\n"
    )
    second = (
        "def export_rows(rows):\n    return list(rows)\n"
        if stack == "python"
        else "export function export_rows(rows) { return rows.slice(); }\n"
    )
    with tempfile.TemporaryDirectory(prefix="spechelper-question-") as temporary:
        root = Path(temporary)
        os.environ["SPECHELPER_DATA_DIR"] = str(root / "data")
        os.environ["CONTROL_TOKEN_FILE"] = str(root / "control.token")
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
        os.environ.pop("POSTGRES_HOST", None)
        import django

        django.setup()
        from django.core.management import call_command
        from django.test import Client

        from core.git import mirror_path, run
        from core.models import (
            Environment,
            EnvironmentRepository,
            InstanceSettings,
            Request,
            RequestMessage,
        )
        from core.providers import connection_for
        from core.worker import claim_job, perform_job
        from runtime import server

        call_command("migrate", verbosity=0)
        InstanceSettings.objects.update_or_create(pk=1, defaults={"language": "en"})
        for provider in ("codex", "claude"):
            connection = connection_for(provider)
            connection.status, connection.availability = "CONNECTED", "AVAILABLE"
            connection.save()
        server.DATA, server.SESSIONS, server.CREDENTIALS = root / "data", root / "sessions", root / "credentials"
        for provider, filename, credentials in (
            ("codex", "auth.json", {"tokens": {"access_token": "synthetic-oauth"}}),
            ("claude", ".credentials.json", {"claudeAiOauth": {"accessToken": "synthetic-oauth"}}),
        ):
            directory = server.CREDENTIALS / provider
            directory.mkdir(parents=True)
            (directory / filename).write_text(json.dumps(credentials))
        source = root / "source"
        source.mkdir()
        run("init", "-b", "main", source)
        run("-C", source, "config", "user.name", "Fixture")
        run("-C", source, "config", "user.email", "fixture@example.invalid")
        (source / name).write_text(first)
        run("-C", source, "add", ".")
        run("-C", source, "commit", "-m", "Initial active filter")
        old_sha = run("-C", source, "rev-parse", "HEAD")
        mirror = mirror_path("fixture/project")
        mirror.parent.mkdir(parents=True)
        run("clone", "--mirror", source, mirror)
        environment = Environment.objects.create(name="Question fixture", status="READY")
        repository = EnvironmentRepository.objects.create(
            environment=environment, repository="fixture/project", branch="main", sha=old_sha
        )
        fixture = root / "fixture-cli"
        fixture.write_text(CLI)
        fixture.chmod(0o755)
        current, calls = {}, []
        original_sandbox = server.sandbox

        def sandbox(workspace, session, attachments, resources=(), broker=None):
            command = original_sandbox(workspace, session, attachments, resources, broker)
            boundary = command.index("setpriv")
            tail, command = command[boundary:], command[:boundary]
            command += ["--setenv", "FIXTURE_SOURCE", name, "--setenv", "FIXTURE_PROFILE", current["profile"],
                        "--setenv", "FIXTURE_UNFILTERED", "return list(rows)" if stack == "python" else "return rows.slice()"]
            for provider in ("codex", "claude"):
                command += ["--ro-bind", str(fixture), "/usr/local/bin/" + provider]
            return command + tail

        def invoke(path, payload, **kwargs):
            calls.append(payload)
            current["profile"] = payload["profile"]
            return server.run(server.RunIn.model_validate(payload))

        client = Client()

        def post(path, payload=None):
            response = client.post(path, payload or {}, content_type="application/json")
            assert response.status_code in {200, 201}, response.content
            return response.json()

        with patch.object(server, "sandbox", sandbox), patch("core.worker.runtime_call", invoke):
            question = post("/api/questions", {"environment_id": environment.pk, "need": "How does export selection work?", "confrontation": True})
            question_id = question["id"]
            post(f"/api/questions/{question_id}/analyze")
            perform_job(claim_job())
            value = Request.objects.get(pk=question_id)
            assert value.status == "NEEDS_CLARIFICATION" and not value.versions.exists()
            post(f"/api/questions/{question_id}/answers", {"answers": {"scope": "Manual exports only"}})
            perform_job(claim_job())
            value.refresh_from_db()
            assert value.status == "READY", value.error
            original = value.versions.get(number=1)
            assert set(original.artifacts.values_list("name", flat=True)) == {"answer.md"}
            documents = [post(f"/api/questions/{question_id}/versions/1/documents", {"kind": kind}) for kind in ("business", "technical", "mixed")]
            assert all(old_sha in document["markdown"] and document["source_version"] == 1 for document in documents)
            RequestMessage.objects.create(request=value, role="user", kind="note", content="PRIVATE_DIALOGUE_SENTINEL")
            post(f"/api/questions/{question_id}/continue", {"message": "Explain the filtering order", "expected_version": 1})
            perform_job(claim_job())
            value.refresh_from_db()
            assert value.status == "READY" and value.versions.count() == 2
            assert value.versions.get(number=1).artifacts.get(name="answer.md").content == original.artifacts.get(name="answer.md").content
            (source / name).write_text(second)
            run("-C", source, "commit", "-am", "Export all rows now")
            new_sha = run("-C", source, "rev-parse", "HEAD")
            run("--git-dir", mirror, "fetch", "origin")
            repository.sha = new_sha
            repository.save(update_fields=["sha"])
            derived = post(f"/api/questions/{question_id}/requests", {"source_version": 1, "environment_id": environment.pk, "need": "Restore active-only export while preserving order and columns.", "confrontation": True})
            request = Request.objects.get(pk=derived["id"])
            assert request.status == "DRAFT" and not request.ai_sessions.exists()
            context = Path(request.attachments.get().path).read_text()
            assert old_sha in context and "PRIVATE_DIALOGUE_SENTINEL" not in context
            post(f"/api/requests/{request.pk}/analyze")
            perform_job(claim_job())
            request.refresh_from_db()
            assert request.status == "READY", request.error
            assert request.baseline[0]["sha"] == new_sha != old_sha
            assert request.source_question_version_id == original.pk
            assert request.session.context_id != value.session.context_id
            assert set(request.versions.get().artifacts.values_list("name", flat=True)) == {"ticket.md", "goal.md"}
            assert new_sha in request.versions.get().artifacts.get(name="goal.md").content
            question_calls = [call for call in calls if call["request_id"] == question_id]
            assert {call["agent"] for call in question_calls} == {"codex", "claude"}
        print(json.dumps({"status": "PASS", "stack": stack, "shared_analysis_engine": True,
            "clarification_and_followup": True, "answer_versions": 2, "documentation_formats": 3,
            "question_has_no_ticket_or_goal": True, "separate_request_context": True,
            "old_git_conclusions_rechecked_against_new_commit": True, "own_ticket_and_goal": True,
            "two_provider_roles": True, "live_ai_account": False}))


if __name__ == "__main__":
    main()
