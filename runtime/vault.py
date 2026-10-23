"""Authenticated encryption for CLI files; only the trusted runtime materializes plaintext."""

import base64
import json
import os
import stat
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core.control import control_token

PREFIX = b"SPECHELPER_AI_V1\n"
FILENAMES = {"auth.json", ".credentials.json", ".claude.json"}


def cipher(token=None):
    material = token or control_token()
    if not material:
        raise ValueError("AI vault key unavailable")
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"spechelper-ai-vault-v1", info=b"trusted-runtime-cli-credentials").derive(material.encode())
    return Fernet(base64.urlsafe_b64encode(key))


def read(path, token=None):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1024 * 1024:
            raise ValueError("Invalid credential file")
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("Invalid credential file")
    if not data.startswith(PREFIX):
        return data
    try:
        return cipher(token).decrypt(data[len(PREFIX):])
    except InvalidToken as exc:
        raise ValueError("AI vault key does not match") from exc


def write(path, data, token=None):
    path = Path(path)
    if len(data) > 512 * 1024:
        raise ValueError("Credential file exceeds limits")
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Invalid credential file")
    key = cipher(token)
    encrypted = key.encrypt(data)
    assert key.decrypt(encrypted) == data
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    fd, name = tempfile.mkstemp(prefix=".vault-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(PREFIX + encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def seal(root, validate_json=True):
    root = Path(root)
    if not root.exists():
        return 0
    root.chmod(0o700)
    sealed = 0
    examined = 0
    for path in root.rglob("*"):
        if path.name not in FILENAMES:
            continue
        if path.is_symlink():
            if not validate_json:
                path.unlink()
            continue
        if not path.is_file():
            continue
        examined += 1
        if examined > 10000:
            raise ValueError("Credential storage limit exceeded")
        try:
            data = read(path)
            if len(data) > 512 * 1024:
                raise ValueError("Credential file exceeds limits")
        except (OSError, ValueError):
            if validate_json:
                raise
            # Session credential copies are disposable; never let an untrusted
            # oversized/malformed copy prevent recovery of the trusted identity.
            path.unlink()
            continue
        if validate_json:
            json.loads(data)
        if not path.read_bytes().startswith(PREFIX):
            write(path, data)
            sealed += 1
        else:
            path.chmod(0o600)
    return sealed
