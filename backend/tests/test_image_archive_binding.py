import hashlib
import io
import json
import tarfile

import pytest
from scripts.security.bind_image_archive import bind


@pytest.mark.parametrize("mismatch", [None, "layers", "command", "platform", "probe"])
def test_export_binding_checks_runtime_identity_before_recording_config_digest(tmp_path, mismatch):
    config = {"architecture": "amd64", "os": "linux", "rootfs": {"diff_ids": ["sha256:layer"]}, "config": {"User": "10000", "Cmd": ["server"], "Env": ["FIXTURE=1"]}}
    inspected = {"Id": "sha256:index", "Architecture": "amd64", "Os": "linux", "RootFS": {"Layers": ["sha256:layer"]}, "Config": {**config["config"]}}
    evidence = {"component": "backend", "image_id": "sha256:index"}
    if mismatch == "layers":
        inspected["RootFS"]["Layers"] = ["sha256:other"]
    elif mismatch == "command":
        inspected["Config"]["Cmd"] = ["other"]
    elif mismatch == "platform":
        inspected["Architecture"] = "arm64"
    elif mismatch == "probe":
        evidence["image_id"] = "sha256:other"
    (tmp_path / "image-inspect.json").write_text(json.dumps([inspected]))
    (tmp_path / "image-evidence.json").write_text(json.dumps(evidence))
    raw = json.dumps(config).encode()
    with tarfile.open(tmp_path / "image.tar", "w") as archive:
        for name, content in [("manifest.json", b'[{"Config":"config.json"}]'), ("config.json", raw)]:
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    if mismatch:
        with pytest.raises(ValueError):
            bind(tmp_path)
        assert "archive_config_id" not in json.loads((tmp_path / "image-evidence.json").read_text())
    else:
        bind(tmp_path)
        result = json.loads((tmp_path / "image-evidence.json").read_text())
        assert result["archive_config_id"] == "sha256:" + hashlib.sha256(raw).hexdigest()
        assert result["image_id"] == "sha256:index"
