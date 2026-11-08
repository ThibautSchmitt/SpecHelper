"""Bind Docker's inspected image to the config digest used by an archive scanner.

Containerd stores may expose an OCI index ID where classic Docker exposes a
config ID. Match filesystem layers and execution configuration before accepting
the config digest; never copy the scanner's claimed identity into the evidence.
"""

import hashlib
import json
import sys
import tarfile
from pathlib import Path


def bind(directory):
    inspected = json.loads((directory / "image-inspect.json").read_text())[0]
    evidence = json.loads((directory / "image-evidence.json").read_text())
    if inspected["Id"] != evidence["image_id"]:
        raise ValueError("Probe and Docker inspection identify different images")
    with tarfile.open(directory / "image.tar", "r") as archive:
        def read(name, limit):
            member = archive.getmember(name)
            if not member.isfile() or member.size > limit:
                raise ValueError("Invalid image archive metadata")
            return archive.extractfile(member).read()
        manifest = json.loads(read("manifest.json", 2 * 1024 * 1024))
        if len(manifest) != 1:
            raise ValueError("Expected exactly one exported platform image")
        raw = read(manifest[0]["Config"], 16 * 1024 * 1024)
    config = json.loads(raw)
    if config["rootfs"]["diff_ids"] != inspected["RootFS"]["Layers"]:
        raise ValueError("Exported filesystem differs from the probed image")
    for name in ("architecture", "os", "variant"):
        if (config.get(name) or "") != (inspected.get(name.capitalize()) or ""):
            raise ValueError("Exported platform differs from the probed image")
    for name in ("User", "Env", "Cmd", "Entrypoint", "WorkingDir", "Labels", "ExposedPorts", "Volumes", "StopSignal", "Healthcheck", "Shell", "OnBuild"):
        if (config.get("config", {}).get(name) or None) != (inspected["Config"].get(name) or None):
            raise ValueError("Exported execution configuration differs: " + name)
    evidence["archive_config_id"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    evidence["archive_binding_verified"] = True
    (directory / "image-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    bind(Path(sys.argv[1]))
