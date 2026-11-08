"""Inventory and clean one explicitly identified Compose installation, fail closed."""

import argparse
import json
import re
import subprocess
from pathlib import Path

LABEL = "com.docker.compose."


def docker(*arguments, json_output=False):
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=90)
    if result.returncode:
        # Docker/config errors may contain environment values; never echo them.
        raise ValueError("Docker command failed: " + " ".join(arguments[:2]))
    return json.loads(result.stdout) if json_output else result.stdout.strip()


def owned(row, project):
    labels = row.get("Labels") or (row.get("Config") or {}).get("Labels") or {}
    return labels.get(LABEL + "project") == project


def inspect_many(kind, ids):
    return docker(kind, "inspect", *ids, json_output=True) if ids else []


def inventory(root, project):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project):
        raise ValueError("Invalid Compose project name")
    root = root.resolve(strict=True)
    if root == Path(root.anchor) or root == Path.home():
        raise ValueError("Refusing an ambiguous installation directory")
    configuration = docker(
        "compose",
        "--project-directory",
        str(root),
        "-p",
        project,
        "config",
        "--format",
        "json",
        json_output=True,
    )
    external_volumes = {
        item.get("name", key)
        for key, item in configuration.get("volumes", {}).items()
        if item.get("external")
    }
    external_networks = {
        item.get("name", key)
        for key, item in configuration.get("networks", {}).items()
        if item.get("external")
    }
    containers = inspect_many("container", docker("ps", "-aq").split())
    selected = [row for row in containers if owned(row, project)]
    for row in selected:
        labels = row["Config"]["Labels"]
        directory = labels.get(LABEL + "project.working_dir", "")
        if not directory or Path(directory).resolve() != root:
            raise ValueError("Project name belongs to another or unidentified installation")
    others = [row for row in containers if row not in selected]
    mounted_elsewhere = {
        mount.get("Name")
        for row in others
        for mount in row.get("Mounts", [])
        if mount.get("Type") == "volume"
    }
    other_networks = {
        name for row in others for name in row.get("NetworkSettings", {}).get("Networks", {})
    }
    other_images = {row["Image"] for row in others}
    volumes = inspect_many(
        "volume",
        docker("volume", "ls", "-q", "--filter", "label=" + LABEL + "project=" + project).split(),
    )
    networks = inspect_many(
        "network",
        docker("network", "ls", "-q", "--filter", "label=" + LABEL + "project=" + project).split(),
    )
    images = inspect_many(
        "image",
        docker("image", "ls", "-q", "--filter", "label=" + LABEL + "project=" + project).split(),
    )
    # Without a live container's directory labels, volume ownership cannot be
    # inferred from a reused project name. A persisted receipt binds the name.
    receipt = root / ".spechelper-installation.json"
    if receipt.is_symlink():
        raise ValueError("Invalid installation receipt")
    known = False
    if receipt.is_file():
        data = json.loads(receipt.read_text())
        known = data == {"project": project, "directory": str(root)}
        if not known:
            raise ValueError("Installation receipt does not match this project")
    if not selected and not known:
        raise ValueError("No verified installation; run inventory while its containers exist")
    skipped = []

    def exclusive(rows, kind):
        result = []
        for row in rows:
            identifier = row.get("Name") if kind != "image" else row["Id"]
            shared = (
                identifier
                in {"volume": mounted_elsewhere, "network": other_networks, "image": other_images}[
                    kind
                ]
            )
            if kind == "volume":
                shared = shared or identifier in external_volumes
            if kind == "image":
                shared = shared or any(
                    not tag.startswith((project + "-", project + "_"))
                    for tag in row.get("RepoTags", []) or []
                )
            # A network may have containers invisible to this installation.
            if kind == "network":
                shared = (
                    shared
                    or identifier in external_networks
                    or any(
                        item not in {c["Id"] for c in selected}
                        for item in row.get("Containers", {})
                    )
                )
            if not owned(row, project) or shared:
                skipped.append({"kind": kind, "id": identifier, "reason": "shared or unverified"})
            else:
                result.append(identifier)
        return sorted(set(result))

    binds = sorted(
        {
            mount["Source"]
            for row in selected
            for mount in row.get("Mounts", [])
            if mount.get("Type") == "bind"
        }
    )
    return {
        "project": project,
        "directory": str(root),
        "containers": sorted(row["Id"] for row in selected),
        "volumes": exclusive(volumes, "volume"),
        "networks": exclusive(networks, "network"),
        "images": exclusive(images, "image"),
        "preserved_bind_paths": binds,
        "preserved": skipped,
    }


def execute(plan, action):
    # Re-inventory immediately before each phase. No global prune or Compose
    # down can accidentally include external volumes or shared resources.
    root, project = Path(plan["directory"]), plan["project"]
    current = inventory(root, project)
    if current != plan:
        raise ValueError("Resources changed after confirmation; inspect again")
    receipt = root / ".spechelper-installation.json"
    if not receipt.exists():
        # Exclusive creation; refuse a concurrent receipt or symlink swap.
        with receipt.open("x") as stream:
            json.dump({"project": project, "directory": str(root)}, stream)
    for identifier in plan["containers"]:
        docker("container", "stop", "--time", "30", identifier)
    if action == "stop":
        return
    for identifier in plan["containers"]:
        docker("container", "rm", identifier)
    refreshed = inventory(root, project)
    for identifier in refreshed["networks"]:
        docker("network", "rm", identifier)
    for identifier in refreshed["images"]:
        docker("image", "rm", identifier)  # no --force; a concurrent user wins
    if action == "purge":
        for identifier in inventory(root, project)["volumes"]:
            docker("volume", "rm", identifier)  # Docker refuses volumes in use
        receipt.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stop", "clean", "purge"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        plan = inventory(args.directory, args.project)
        operations = {
            "stop_containers": plan["containers"],
            "remove_containers": plan["containers"] if args.action != "stop" else [],
            "remove_networks": plan["networks"] if args.action != "stop" else [],
            "remove_images": plan["images"] if args.action != "stop" else [],
            "remove_volumes": plan["volumes"] if args.action == "purge" else [],
        }
        print(
            json.dumps(
                {"action": args.action, "dry_run": args.dry_run, "operations": operations, **plan},
                indent=2,
            )
        )
        print(
            "Bind mounts, source checkout, .env, host backups, external services and unlabelled/shared images are preserved."
        )
        if args.dry_run:
            return
        if args.action != "stop":
            phrase = "PURGE SPECHELPER" if args.action == "purge" else "CLEAN SPECHELPER"
            if (
                input("Irreversible removal of the listed resources. Type " + phrase + ": ")
                != phrase
            ):
                raise ValueError("Confirmation does not match; nothing removed")
        execute(plan, args.action)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, "Cleanup stopped: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
