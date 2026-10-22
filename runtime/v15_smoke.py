"""Exercise independent role sessions inside Linux with deterministic CLI fixtures.

Run in the runtime image with its Compose sandbox capabilities. No provider account,
application database, network request or external source is used.
"""

import json
import subprocess
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from runtime import server
from runtime.auth import identity_root

CLI_FIXTURE = r'''#!/usr/local/bin/python3
import hashlib, json, pathlib, subprocess, sys, uuid
prompt = json.loads(sys.stdin.read())
root = pathlib.Path('/session')
canary = root / (prompt['role'] + '.private')
assert not pathlib.Path(prompt['legacy']).exists()
assert not pathlib.Path(prompt['sessions']).exists()
assert not pathlib.Path('/sessions').exists()
assert not pathlib.Path('/credentials').exists()
assert not (root / 'contexts').exists()
assert sorted(path.name for path in root.glob('*.private')) == (
    [canary.name] if prompt['resume'] else []
)
for forbidden in prompt['others']:
    assert not pathlib.Path(forbidden).exists(), forbidden
assert not pathlib.Path('/tmp/other-role.tmp').exists()
pathlib.Path('/tmp/other-role.tmp').write_text(prompt['role'])
source = pathlib.Path('/workspace/project/domain.txt')
assert hashlib.sha256(source.read_bytes()).hexdigest() == prompt['source_hash']
assert subprocess.check_output(
    ['git', '-C', '/workspace/project', 'rev-parse', 'HEAD'], text=True
).strip() == prompt['sha']
for path in (source, pathlib.Path('/attachments/need.txt')):
    try:
        path.write_text('FORBIDDEN')
    except OSError:
        pass
    else:
        raise AssertionError('Read-only boundary missing: ' + str(path))
history = root / 'conversation-id'
claude = '--output-format' in sys.argv
if prompt['resume']:
    sid = history.read_text()
    assert ('--resume' if claude else 'resume') in sys.argv
    assert sid in sys.argv
else:
    assert not history.exists()
    assert '--resume' not in sys.argv and 'resume' not in sys.argv
    assert '--fork-session' not in sys.argv
    sid = sys.argv[sys.argv.index('--session-id') + 1] if claude else str(uuid.uuid4())
    history.write_text(sid)
    canary.write_text(prompt['role'])
assert canary.read_text() == prompt['role']
output = {'role': prompt['role'], 'source_sha': prompt['sha'], 'isolated': True}
(root / 'result.json').write_text(json.dumps(output))
if claude:
    print(json.dumps({'session_id': sid, 'structured_output': output}))
else:
    print(json.dumps({'type': 'thread.started', 'thread_id': sid}))
'''


def main():
    import hashlib

    with tempfile.TemporaryDirectory(prefix="spechelper-v15-runtime-") as temporary:
        root = Path(temporary)
        request_id, identity = uuid.uuid4(), uuid.uuid4()
        data, sessions, credentials = root / "data", root / "sessions", root / "credentials"
        workspace = data / "analysis-workspaces" / str(request_id)
        workspace.mkdir(parents=True)
        source = root / "source"
        source.mkdir()
        source_file = source / "domain.txt"
        source_file.write_text("Immutable business source\n")

        def git(*args):
            return subprocess.check_output(["git", *map(str, args)], text=True).strip()

        git("init", "-b", "main", source)
        git("-C", source, "config", "user.name", "Fixture")
        git("-C", source, "config", "user.email", "fixture@example.invalid")
        git("-C", source, "add", ".")
        git("-C", source, "commit", "-m", "fixture")
        sha = git("-C", source, "rev-parse", "HEAD")
        source_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
        mirror = data / "git-cache" / "fixture.git"
        mirror.parent.mkdir(parents=True)
        git("clone", "--mirror", source, mirror)
        git("--git-dir", mirror, "worktree", "add", "--detach", workspace / "project", sha)
        attachments = data / "requests" / str(request_id) / "attachments"
        attachments.mkdir(parents=True)
        (attachments / "need.txt").write_text("Business dossier shared read-only")
        legacy = sessions / str(request_id)
        legacy.mkdir(parents=True)
        (legacy / "legacy.private").write_text("Must never leak into any role")
        fixture = root / "fixture-cli"
        fixture.write_text(CLI_FIXTURE)
        fixture.chmod(0o755)
        for provider, filename, content in (
            ("codex", "auth.json", {"tokens": {"access_token": "synthetic-oauth"}}),
            ("claude", ".credentials.json", {"claudeAiOauth": {"accessToken": "synthetic-oauth"}}),
        ):
            directory = identity_root(credentials, identity) / provider
            directory.mkdir(parents=True)
            (directory / filename).write_text(json.dumps(content))
        real_sandbox = server.sandbox

        def fixture_sandbox(workspace, session, attachments):
            command = real_sandbox(workspace, session, attachments)
            for provider in ("codex", "claude"):
                command += ["--ro-bind", str(fixture), "/usr/local/bin/" + provider]
            return command

        observed_sessions = []
        with (
            patch.object(server, "DATA", data),
            patch.object(server, "SESSIONS", sessions),
            patch.object(server, "CREDENTIALS", credentials),
            patch.object(server, "sandbox", fixture_sandbox),
        ):
            for provider in ("codex", "claude"):
                contexts = [request_id, uuid.uuid4(), uuid.uuid4()]
                # The first role deliberately shares the request UUID. It still must
                # mount a context directory rather than the legacy primary directory.
                if provider == "claude":
                    contexts = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
                for role, context in zip(("analyst", "counter_analyst", "verifier"), contexts):
                    context_path = sessions / "contexts" / str(request_id) / str(context)
                    payload = {
                        "request_id": str(request_id),
                        "context_id": str(context),
                        "independent_context": True,
                        "identity_id": str(identity),
                        "agent": provider,
                        "workspace": str(workspace),
                        "schema": {},
                        "timeout": 15,
                    }
                    for resume in (False, True):
                        payload["prompt"] = json.dumps(
                            {
                                "role": role,
                                "resume": resume,
                                "sha": sha,
                                "source_hash": source_hash,
                                "legacy": str(legacy),
                                "sessions": str(sessions),
                                "others": [str(path) for path in observed_sessions],
                            }
                        )
                        result = server.run(server.RunIn.model_validate(payload))
                        assert result.get("output") == {
                            "role": role, "source_sha": sha, "isolated": True
                        }, result
                        if resume:
                            assert result["session_id"] == payload["session_id"]
                        payload["session_id"] = result["session_id"]
                    observed_sessions.append(context_path)
        assert len({(path / "conversation-id").read_text() for path in observed_sessions}) == 6
        assert hashlib.sha256(source_file.read_bytes()).hexdigest() == source_hash
        print(json.dumps({
            "status": "PASS", "independent_role_contexts": 6, "cli_calls": 12,
            "legacy_primary_hidden": True, "other_role_notes_hidden": True,
            "temporary_directories_isolated": True, "same_source_sha": True,
            "source_and_attachment_writes_denied": True, "own_history_resumed": True,
            "providers": ["codex", "claude"], "live_ai_account": False,
        }))


if __name__ == "__main__":
    main()
