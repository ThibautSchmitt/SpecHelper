import fcntl
import os

from cryptography.fernet import Fernet
from django.conf import settings


def cipher():
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        path = settings.DATA_DIR / "encryption.key"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
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
