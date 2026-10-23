import fcntl
import os

from cryptography.fernet import Fernet
from django.conf import settings


def cipher():
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        import stat
        from pathlib import Path

        path = Path(os.environ.get("ENCRYPTION_KEY_FILE", str(settings.DATA_DIR / "encryption.key")))
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            os.close(fd)
            raise ValueError("Encryption key must be a private regular file")
        with os.fdopen(fd, "r+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            key = stream.read()
            if not key:
                key = Fernet.generate_key()
                stream.write(key)
                stream.flush()
                os.fsync(stream.fileno())
    return Fernet(key)


def encrypt(value):
    return cipher().encrypt(value.encode()).decode()


def decrypt(value):
    return cipher().decrypt(value.encode()).decode()
