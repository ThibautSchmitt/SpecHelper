"""Real Linux sandbox smoke test. Run inside the runtime image with its Compose capabilities."""

import subprocess
import tempfile
from pathlib import Path

from runtime import server


def git(*args):
    return subprocess.check_output(["git", *map(str, args)], text=True).strip()


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    server.DATA = root / "data"
    workspace = server.DATA / "analysis-workspaces" / "fixture"
    source = root / "source"
    source.mkdir()
    git("init", "-b", "main", source)
    git("-C", source, "config", "user.name", "Fixture")
    git("-C", source, "config", "user.email", "fixture@example.invalid")
    (source / "domain.txt").write_text("immutable source")
    git("-C", source, "add", ".")
    git("-C", source, "commit", "-m", "fixture")
    mirror = server.DATA / "git-cache" / "fixture.git"
    mirror.parent.mkdir(parents=True)
    git("clone", "--mirror", source, mirror)
    workspace.mkdir(parents=True)
    git("--git-dir", mirror, "worktree", "add", "--detach", workspace / "project", "HEAD")
    attachments = root / "attachments"
    attachments.mkdir()
    (attachments / "need.txt").write_text("attachment")
    session = root / "session"
    session.mkdir()
    (root / "private-secret.txt").write_text("PRIVATE")
    checks = r"""
import json, os, pathlib, subprocess
assert pathlib.Path('/workspace/project/domain.txt').read_text() == 'immutable source'
assert pathlib.Path('/attachments/need.txt').read_text() == 'attachment'
denied=[]
for path in ['/workspace/project/domain.txt','/attachments/need.txt',MIRROR_CONFIG]:
    try:
        with open(path,'a') as stream: stream.write('FORBIDDEN')
    except OSError:
        denied.append(path)
assert len(denied)==3, denied
assert not pathlib.Path(PRIVATE_SECRET).exists()
assert not pathlib.Path('/app').exists()
assert not pathlib.Path('/credentials').exists()
assert not pathlib.Path('/control').exists()
assert not pathlib.Path('/sessions').exists()
assert 'RUNTIME_TOKEN' not in os.environ
for proc in pathlib.Path('/proc').iterdir():
    if proc.name.isdigit():
        try: assert b'RUNTIME_TOKEN=' not in (proc/'environ').read_bytes()
        except (PermissionError, ProcessLookupError, FileNotFoundError): pass
result=subprocess.run(['git','-C','/workspace/project','show','HEAD:domain.txt'],capture_output=True,text=True)
assert result.returncode==0, result.stderr
assert result.stdout=='immutable source'
pathlib.Path('/session/probe').write_text('own session writable')
print(json.dumps({'source_read':True,'git_history':True,'writes_denied':len(denied),'secrets_hidden':True,'session_isolated':True}))
""".replace("MIRROR_CONFIG", repr(str(mirror / "config"))).replace(
        "PRIVATE_SECRET", repr(str(root / "private-secret.txt"))
    )
    command = server.sandbox(workspace, session, attachments) + ["python3", "-c", checks]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    if result.returncode:
        raise RuntimeError(result.stderr + result.stdout)
    assert (workspace / "project" / "domain.txt").read_text() == "immutable source"
    print(result.stdout.strip())
