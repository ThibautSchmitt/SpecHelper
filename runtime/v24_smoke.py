"""Real Linux probes for parallel isolation, lazy skill reads and exact-attempt cancellation."""

import concurrent.futures
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from runtime import server
from runtime.global_skills import SkillResources


def parallel_isolation(root):
    data = root / "data"
    (data / "git-cache").mkdir(parents=True)
    jobs = []
    for name in ("first", "second"):
        workspace = data / "analysis-workspaces" / name
        session, attachments = root / name, data / "requests" / name / "attachments"
        for path in (workspace, session, attachments):
            path.mkdir(parents=True)
        seed = root / ("seed-" + name)
        seed.mkdir()
        (seed / "private.txt").write_text(name)
        common = data / "git-cache" / (name + ".git")
        repository = workspace / "repository"
        for arguments in (
            ["init", "-q", str(seed)],
            ["-C", str(seed), "add", "private.txt"],
            [
                "-C",
                str(seed),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            ["clone", "-q", "--mirror", str(seed), str(common)],
            ["--git-dir", str(common), "worktree", "add", "--detach", str(repository), "HEAD"],
            [
                "--git-dir",
                str(common),
                "worktree",
                "add",
                "--detach",
                str(root / ("other-" + name)),
                "HEAD",
            ],
        ):
            subprocess.run(["git", *arguments], check=True, capture_output=True)
        (attachments / "private.txt").write_text(name)
        os.chown(session, 10001, 10001)
        jobs.append((name, workspace, session, attachments))

    def execute(job):
        name, workspace, session, attachments = job
        definitions = [
            {
                "slug": slug,
                "name": slug,
                "version": 3,
                "instructions": "Read the frozen source and state its limits.",
            }
            for slug in ("used", "unused")
        ]
        with SkillResources(definitions, root, "codex") as skills:
            code = """import json,os,time,subprocess
from pathlib import Path
started=time.monotonic()
assert os.getuid()==10001
name=Path('/workspace/repository/private.txt').read_text()
assert Path('/attachments/private.txt').read_text()==name
assert 'state its limits' in Path('/skills/used/v3.md').read_text()
assert not Path('/credentials').exists() and not Path('/sessions').exists()
assert not Path('OTHER_SOURCE').exists()
assert not Path('OTHER_CACHE').exists()
assert not Path('OTHER_METADATA').exists()
assert len(subprocess.check_output(['git','-C','/workspace/repository','rev-parse','HEAD']).strip())==40
try: Path('/workspace/repository/private.txt').write_text('forbidden')
except OSError: pass
else: raise AssertionError('Sources must remain read-only')
Path('/session/own.txt').write_text(name)
time.sleep(1)
print(json.dumps({'name':name,'start':started,'end':time.monotonic()}))
""".replace(
                "OTHER_SOURCE",
                str(
                    data
                    / "analysis-workspaces"
                    / ("second" if name == "first" else "first")
                    / "repository"
                    / "private.txt"
                ),
            )
            code = code.replace(
                "OTHER_CACHE",
                str(data / "git-cache" / (("second" if name == "first" else "first") + ".git")),
            )
            code = code.replace(
                "OTHER_METADATA",
                str(data / "git-cache" / (name + ".git") / "worktrees" / ("other-" + name)),
            )
            result = subprocess.run(
                server.sandbox(
                    workspace,
                    session,
                    attachments,
                    skill_mounts=skills.mounts,
                    git_repositories=["repository"],
                )
                + ["python3", "-c", code],
                capture_output=True,
                text=True,
                timeout=15,
            )
            assert result.returncode == 0, result.stderr
            observation = skills.finish()
            assert observation["skills_audit"] == "observed", observation
            assert [(item["slug"], item["version"]) for item in observation["loaded_skills"]] == [
                ("used", 3)
            ]
            return json.loads(result.stdout)

    with (
        patch.object(server, "DATA", data),
        concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool,
    ):
        results = list(pool.map(execute, jobs))
    assert max(item["start"] for item in results) < min(item["end"] for item in results)
    assert {item["name"] for item in results} == {"first", "second"}
    for name, workspace, session, _ in jobs:
        assert (workspace / "repository/private.txt").read_text() == name
        assert (session / "own.txt").read_text() == name
    return {
        "parallel_sandboxes": 2,
        "separate_sources_attachments_sessions": True,
        "sources_read_only": True,
        "only_actually_read_skill_recorded": True,
        "authorized_git_history_readable": True,
        "other_repository_cache_hidden": True,
        "other_job_git_metadata_hidden": True,
    }


def cancellation():
    process = subprocess.Popen(
        [
            "python3",
            "-c",
            "import subprocess,time; child=subprocess.Popen(['python3','-c','import time; time.sleep(60)']); print(child.pid,flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    request_id, attempt_id = uuid.uuid4(), uuid.uuid4()
    key = (str(request_id), str(attempt_id))
    try:
        child = int(process.stdout.readline())
        server.run_controls[key] = {
            "process": process,
            "cancelled": threading.Event(),
            "created": time.monotonic(),
        }
        server.cancel_run(server.CancelRunIn(request_id=request_id, attempt_id=uuid.uuid4()))
        assert process.poll() is None, "Another attempt must not be cancelled"
        assert server.cancel_run(server.CancelRunIn(request_id=request_id, attempt_id=attempt_id))[
            "stopped"
        ]
        assert process.poll() is not None
        child_status = Path(f"/proc/{child}/stat")
        assert (
            not child_status.exists()
            or child_status.read_text().rsplit(")", 1)[1].split()[0] == "Z"
        )
        assert server.cancel_run(server.CancelRunIn(request_id=request_id, attempt_id=attempt_id))[
            "stopped"
        ]
        return {
            "exact_attempt_only": True,
            "process_and_children_stopped": True,
            "cancellation_idempotent": True,
        }
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        server.run_controls.pop(key, None)


def main():
    with tempfile.TemporaryDirectory() as temporary:
        print(json.dumps({**parallel_isolation(Path(temporary)), **cancellation()}))


if __name__ == "__main__":
    main()
