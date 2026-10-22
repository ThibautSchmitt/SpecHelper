"""Validate frozen resources and observe actual Linux file reads without model claims."""

import ctypes
import hashlib
import os
import re
import struct
import uuid
from pathlib import Path, PurePosixPath


def validated_resources(data: Path, request_id: str, directory: str | None, resources: list):
    """Return only exact, regular snapshot files; never mount their parent wholesale."""
    if not directory:
        if resources:
            raise ValueError("Invalid context resources")
        return []
    base = data / "analysis-context" / request_id
    root = Path(directory)
    try:
        suffix = root.relative_to(base)
        if len(suffix.parts) != 1 or str(uuid.UUID(suffix.name)) != suffix.name:
            raise ValueError
        if root.resolve(strict=True) != root or not root.is_dir():
            raise ValueError
        result = []
        seen = set()
        if len(resources) > 64:
            raise ValueError
        for resource in resources:
            version = str(resource.version_id)
            relative = PurePosixPath(resource.path)
            if (
                not resource.path
                or str(relative) != resource.path
                or relative.is_absolute()
                or any(part in {".", ".."} for part in resource.path.split("/"))
                or "\\" in resource.path
                or any(ord(char) < 32 for char in resource.path)
                or resource.path in seen
                or not re.fullmatch(r"[0-9a-f]{64}", resource.sha256)
            ):
                raise ValueError
            source = root / resource.path
            if source.resolve(strict=True) != source or not source.is_file():
                raise ValueError
            if source.stat().st_size > 25 * 1024 * 1024:
                raise ValueError
            digest = hashlib.sha256()
            with source.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != resource.sha256:
                raise ValueError
            result.append((version, source, resource.path))
            seen.add(resource.path)
        return result
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError("Invalid context resources") from exc


def mount_resources(resources):
    """Expose only allowlisted immutable files, including an empty /context when absent."""
    command = ["--dir", "/context"]
    directories = set()
    for _, source, relative in resources:
        parent = PurePosixPath(relative).parent
        for directory in reversed(parent.parents):
            if str(directory) != "." and str(directory) not in directories:
                command += ["--dir", "/context/" + str(directory)]
                directories.add(str(directory))
        if str(parent) != "." and str(parent) not in directories:
            command += ["--dir", "/context/" + str(parent)]
            directories.add(str(parent))
        command += ["--ro-bind", str(source), "/context/" + relative]
    return command


class ResourceReads:
    """IN_ACCESS proves file reads, not comprehension; mmap access may be unobservable.

    Only snapshot inodes are watched. Paths, contents and provider output are never
    returned. Overflow or unsupported kernels explicitly invalidate the observation.
    """

    def __init__(self, resources):
        self.fd = None
        self.watches = {}
        self.used = set()
        self.status = "unavailable"
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            initialize = libc.inotify_init1
            initialize.argtypes = [ctypes.c_int]
            initialize.restype = ctypes.c_int
            watch = libc.inotify_add_watch
            watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
            watch.restype = ctypes.c_int
            self.fd = initialize(os.O_NONBLOCK | os.O_CLOEXEC)
            if self.fd < 0:
                self.fd = None
                return
            for version, source, _ in resources:
                descriptor = watch(self.fd, os.fsencode(source), 0x00000001)
                if descriptor < 0:
                    self.close()
                    return
                self.watches.setdefault(descriptor, set()).add(version)
            self.status = "observed"
        except (AttributeError, OSError):
            self.close()

    def finish(self):
        """Drain at most one MiB of kernel events, then close every descriptor."""
        try:
            total = 0
            while self.fd is not None:
                try:
                    events = os.read(self.fd, 65536)
                except BlockingIOError:
                    break
                if not events:
                    break
                total += len(events)
                if total > 1024 * 1024:
                    self.status = "unavailable"
                    break
                position = 0
                while position + 16 <= len(events):
                    descriptor, mask, _, length = struct.unpack_from("iIII", events, position)
                    position += 16 + length
                    if mask & (0x00004000 | 0x00008000 | 0x00002000):
                        self.status = "unavailable"
                    if mask & 0x00000001:
                        self.used.update(self.watches.get(descriptor, ()))
        except OSError:
            self.status = "unavailable"
        finally:
            self.close()
        return {"context_usage": sorted(self.used), "context_audit": self.status}

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
