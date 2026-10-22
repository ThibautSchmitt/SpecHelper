"""Exercise real Linux read observation and Bubblewrap context isolation, without AI."""

import hashlib
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

from runtime import server
from runtime.context_resources import ResourceReads, validated_resources


def main():
    with tempfile.TemporaryDirectory(prefix="spechelper-context-") as temporary:
        data = Path(temporary)
        server.DATA = data
        request = str(uuid.uuid4())
        directory = data / "analysis-context" / request / str(uuid.uuid4())
        directory.mkdir(parents=True)
        ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        documents = ["architecture.md", "untouched.txt"]
        contents = ["Long reference material.\n" * 12000, "Unused reference.\n"]
        resources = []
        for version, name, content in zip(ids, documents, contents, strict=True):
            (directory / name).write_text(content)
            resources.append(server.ContextResource(
                version_id=version, path=name, sha256=hashlib.sha256(content.encode()).hexdigest()
            ))
        files = validated_resources(data, request, str(directory), resources)
        workspace = data / "workspace"
        attachments = data / "attachments"
        primary = data / "primary"
        secondary = data / "secondary"
        other = data / "analysis-context" / str(uuid.uuid4())
        for folder in (workspace, attachments, primary, secondary, data / "git-cache", other):
            folder.mkdir(parents=True)
        (primary / "private-note").write_text("Private analyst session")
        (other / "secret.txt").write_text("Other request resource")
        watcher = ResourceReads(files)
        assert watcher.status == "observed", "Linux access observation unavailable"
        command = server.sandbox(workspace, primary, attachments, files)
        result = subprocess.run(command + ["/bin/sh", "-ec", """
            test $(wc -c </context/architecture.md) -gt 200000
            cat /context/architecture.md >/dev/null
            test -f /context/untouched.txt
            ! touch /context/architecture.md 2>/dev/null
            ! touch /context/new-file 2>/dev/null
            ! sh -c 'echo changed >> /context/architecture.md' 2>/dev/null
            echo my-private-note > /session/notes
        """], capture_output=True, timeout=20)
        assert result.returncode == 0, "Context read-only boundary failed"
        observed = watcher.finish()
        assert observed == {"context_usage": [ids[0]], "context_audit": "observed"}, observed
        second = server.sandbox(workspace, secondary, attachments, files)
        result = subprocess.run(second + ["/bin/sh", "-ec", f"""
            test ! -e /session/private-note
            test ! -e /session/notes
            test ! -e '{other}/secret.txt'
            test ! -e '{directory}/architecture.md'
            test -r /context/architecture.md
            echo separate > /session/notes
        """], capture_output=True, timeout=20)
        assert result.returncode == 0, "Cross-session or host context isolation failed"
        assert (primary / "notes").read_text().strip() == "my-private-note"
        assert (secondary / "notes").read_text().strip() == "separate"
        assert (directory / documents[0]).read_text() == contents[0]
        print(json.dumps({
            "read_only_context": True,
            "long_document_bytes": len(contents[0]),
            "observed_reads": 1,
            "untouched_resource_not_claimed": True,
            "sessions_isolated": True,
            "other_request_unavailable": True,
        }))


if __name__ == "__main__":
    main()
