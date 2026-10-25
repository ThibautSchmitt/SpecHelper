"""Install one pinned official native CLI; never execute a rolling installer."""

import hashlib
import json
import os
import platform
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 512 * 1024 * 1024


def install(manifest_path, destination):
    manifest = json.loads(Path(manifest_path).read_text())
    architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine())
    if platform.system() != "Linux" or not architecture:
        raise ValueError("Antigravity runtime requires supported 64-bit Linux.")
    release = manifest["platforms"][architecture]
    url = urlsplit(release["url"])
    if (
        url.scheme != "https"
        or url.hostname != "storage.googleapis.com"
        or not url.path.startswith("/antigravity-public/antigravity-cli/")
        or url.username
        or url.password
        or url.query
        or url.fragment
        or release["version"] != manifest["version"]
    ):
        raise ValueError("Invalid pinned Antigravity release.")
    target = Path(destination)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("Invalid CLI installation destination.")
    digest, size = hashlib.sha512(), 0
    with tempfile.TemporaryDirectory(prefix="antigravity-install-") as temporary:
        archive = Path(temporary) / "release.tar.gz"
        # Build-time public artifacts only; no ambient proxy or credentials.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(release["url"], timeout=120) as response, archive.open("wb") as output:
            if response.url != release["url"]:
                raise ValueError("Pinned binary redirects are not supported.")
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("CLI download exceeds the installation bound.")
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != release["sha512"]:
            raise ValueError("Antigravity binary checksum mismatch.")
        with tarfile.open(archive, "r:gz") as package:
            member = package.getmember("antigravity")
            if not member.isfile() or member.size > MAX_BYTES:
                raise ValueError("Invalid CLI archive member.")
            stream = package.extractfile(member)
            if stream is None:
                raise ValueError("CLI binary is missing.")
            with stream, target.open("wb") as output:
                while chunk := stream.read(1024 * 1024):
                    output.write(chunk)
        os.chmod(target, 0o755)
    return manifest["version"]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("destination")
    arguments = parser.parse_args()
    print("Installed Antigravity CLI " + install(arguments.manifest, arguments.destination))
