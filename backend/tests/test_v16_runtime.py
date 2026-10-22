"""Runtime snapshot validation and filesystem observations independent of AI output."""

import hashlib
import os
import sys
import uuid

import pytest

from runtime.context_resources import ResourceReads, mount_resources, validated_resources
from runtime.server import ContextResource, RunIn


@pytest.fixture
def snapshot(tmp_path):
    request = str(uuid.uuid4())
    folder = tmp_path / "analysis-context" / request / str(uuid.uuid4())
    folder.mkdir(parents=True)
    resources = []
    for name in ("long.md", "other.txt"):
        content = (name + "\n") * 40000
        (folder / name).write_text(content)
        resources.append(ContextResource(
            version_id=uuid.uuid4(), path=name, sha256=hashlib.sha256(content.encode()).hexdigest()
        ))
    return tmp_path, request, folder, resources


def test_context_only_mounts_verified_allowlisted_files(snapshot):
    data, request, folder, resources = snapshot
    (folder / "not-in-manifest").write_text("Do not expose")
    result = validated_resources(data, request, str(folder), resources)
    command = mount_resources(result)
    assert str(folder) not in command
    assert str(folder / "not-in-manifest") not in command
    assert "/context/long.md" in command
    payload = RunIn(
        request_id=request, workspace="/workspace", prompt="Only references", schema={}, timeout=1,
        context_dir=str(folder), context_resources=resources,
    )
    assert "long.md\nlong.md" not in payload.prompt
    assert payload.context_resources[0].sha256 == resources[0].sha256


@pytest.mark.parametrize("bad_path", ["../long.md", "/long.md", "a/../long.md", "a//long.md", "a\\long.md"])
def test_context_rejects_traversal_and_noncanonical_paths(snapshot, bad_path):
    data, request, folder, resources = snapshot
    resources[0].path = bad_path
    with pytest.raises(ValueError, match="Invalid context resources"):
        validated_resources(data, request, str(folder), resources)


def test_context_rejects_different_request_hash_change_and_symlink(snapshot):
    data, request, folder, resources = snapshot
    with pytest.raises(ValueError):
        validated_resources(data, str(uuid.uuid4()), str(folder), resources)
    (folder / "long.md").write_text("Changed after snapshot")
    with pytest.raises(ValueError):
        validated_resources(data, request, str(folder), resources)
    (folder / "long.md").unlink()
    (folder / "long.md").symlink_to(folder / "other.txt")
    with pytest.raises(ValueError):
        validated_resources(data, request, str(folder), resources)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux kernel read observation")
def test_actual_reads_only_no_claim_for_stat_open_or_untouched(snapshot):
    data, request, folder, resources = snapshot
    files = validated_resources(data, request, str(folder), resources)
    watcher = ResourceReads(files)
    assert watcher.status == "observed"
    os.stat(folder / "other.txt")
    descriptor = os.open(folder / "other.txt", os.O_RDONLY)
    os.close(descriptor)
    (folder / "long.md").read_bytes()
    assert watcher.finish() == {
        "context_usage": [str(resources[0].version_id)], "context_audit": "observed"
    }


def test_observation_explicitly_unavailable_when_kernel_not_supported(monkeypatch):
    monkeypatch.setattr("runtime.context_resources.ctypes.CDLL", lambda *args, **kwargs: object())
    assert ResourceReads([]).finish() == {"context_usage": [], "context_audit": "unavailable"}
