"""Ownership checks, shared resources, confirmations and dry-run without Docker."""

import json

import pytest
from scripts import cleanup


def fixture_docker(root, monkeypatch):
    project = "test-spechelper"
    labels = {cleanup.LABEL + "project": project, cleanup.LABEL + "project.working_dir": str(root)}
    own = {
        "Id": "own",
        "Image": "app-image",
        "Config": {"Labels": labels},
        "Mounts": [{"Type": "bind", "Source": "/valuable/shared"}],
        "NetworkSettings": {"Networks": {"private": {}}},
    }
    other = {
        "Id": "other",
        "Image": "shared-image",
        "Config": {"Labels": {}},
        "Mounts": [{"Type": "volume", "Name": "shared-volume"}],
        "NetworkSettings": {"Networks": {"shared-network": {}}},
    }
    data = {
        (
            "compose",
            "--project-directory",
            str(root),
            "-p",
            project,
            "config",
            "--format",
            "json",
        ): {},
        ("ps", "-aq"): "own other",
        ("container", "inspect", "own", "other"): [own, other],
        (
            "volume",
            "ls",
            "-q",
            "--filter",
            "label=" + cleanup.LABEL + "project=" + project,
        ): "private-volume shared-volume",
        ("volume", "inspect", "private-volume", "shared-volume"): [
            {"Name": name, "Labels": labels} for name in ["private-volume", "shared-volume"]
        ],
        (
            "network",
            "ls",
            "-q",
            "--filter",
            "label=" + cleanup.LABEL + "project=" + project,
        ): "private shared-network",
        ("network", "inspect", "private", "shared-network"): [
            {"Name": name, "Labels": labels, "Containers": {}}
            for name in ["private", "shared-network"]
        ],
        (
            "image",
            "ls",
            "-q",
            "--filter",
            "label=" + cleanup.LABEL + "project=" + project,
        ): "app-image shared-image",
        ("image", "inspect", "app-image", "shared-image"): [
            {"Id": name, "Config": {"Labels": labels}} for name in ["app-image", "shared-image"]
        ],
    }
    monkeypatch.setattr(cleanup, "docker", lambda *args, **kwargs: data[args])
    return project, own


def test_inventory_never_selects_shared_resources_or_host_paths(tmp_path, monkeypatch):
    project, _ = fixture_docker(tmp_path, monkeypatch)
    result = cleanup.inventory(tmp_path, project)
    assert result["containers"] == ["own"]
    assert result["volumes"] == ["private-volume"]
    assert result["networks"] == ["private"]
    assert result["images"] == ["app-image"]
    assert result["preserved_bind_paths"] == ["/valuable/shared"]
    assert len(result["preserved"]) == 3


def test_reused_project_name_and_symlink_receipt_fail_closed(tmp_path, monkeypatch):
    project, own = fixture_docker(tmp_path, monkeypatch)
    own["Config"]["Labels"][cleanup.LABEL + "project.working_dir"] = "/different/installation"
    with pytest.raises(ValueError, match="another"):
        cleanup.inventory(tmp_path, project)
    own["Config"]["Labels"][cleanup.LABEL + "project.working_dir"] = str(tmp_path)
    (tmp_path / ".spechelper-installation.json").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="receipt"):
        cleanup.inventory(tmp_path, project)


def test_dry_run_has_no_mutations_or_confirmation(tmp_path, monkeypatch, capsys):
    project, _ = fixture_docker(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "sys.argv",
        ["cleanup.py", "purge", "--directory", str(tmp_path), "--project", project, "--dry-run"],
    )
    monkeypatch.setattr("builtins.input", lambda *args: pytest.fail("dry run must not prompt"))
    monkeypatch.setattr(cleanup, "execute", lambda *args: pytest.fail("dry run must not mutate"))
    cleanup.main()
    assert "preserved_bind_paths" in capsys.readouterr().out
    assert not (tmp_path / ".spechelper-installation.json").exists()


def test_confirmation_is_exact_and_resources_are_rechecked(tmp_path, monkeypatch):
    project, _ = fixture_docker(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "sys.argv", ["cleanup.py", "purge", "--directory", str(tmp_path), "--project", project]
    )
    monkeypatch.setattr("builtins.input", lambda *args: "yes")
    monkeypatch.setattr(
        cleanup, "execute", lambda *args: pytest.fail("wrong phrase must not mutate")
    )
    with pytest.raises(SystemExit):
        cleanup.main()


def test_receipt_cannot_authorize_another_project(tmp_path, monkeypatch):
    project, _ = fixture_docker(tmp_path, monkeypatch)
    (tmp_path / ".spechelper-installation.json").write_text(
        json.dumps({"project": "another", "directory": str(tmp_path)})
    )
    with pytest.raises(ValueError, match="match"):
        cleanup.inventory(tmp_path, project)
