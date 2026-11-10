"""Bounded upload inspection; document parsers run only inside the isolated runtime."""

import stat
import struct
import zipfile
from pathlib import Path, PurePosixPath

from ninja.errors import HttpError

TEXT = {".txt", ".md", ".csv", ".json", ".log", ".sql"}
TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    **{extension: "text/plain" for extension in TEXT},
}
MAX_BYTES = 25 * 1024 * 1024


def inspect_file(path, name):
    """Identify signatures and bound supported Office containers without executing content."""
    suffix = Path(name).suffix.lower()
    if suffix not in TYPES:
        raise HttpError(422, "File format not allowed")
    size = path.stat().st_size
    if not 0 < size <= MAX_BYTES:
        raise HttpError(422, "Files must contain between 1 byte and 25 MB.")
    with path.open("rb") as stream:
        header = stream.read(1024)
    valid = False
    if suffix in TEXT:
        try:
            text = path.read_text(encoding="utf-8-sig")
            valid = "\x00" not in text and not header.startswith((b"MZ", b"\x7fELF", b"PK\x03\x04", b"\x1f\x8b"))
        except UnicodeError:
            pass
    elif suffix == ".pdf":
        valid = header.startswith(b"%PDF-")
    elif suffix == ".png":
        valid = header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24 and header[12:16] == b"IHDR"
        if valid:
            width, height = struct.unpack(">II", header[16:24])
            valid = 0 < width <= 20000 and 0 < height <= 20000 and width * height <= 40000000
    elif suffix in {".jpg", ".jpeg"}:
        valid = header.startswith(b"\xff\xd8\xff")
    elif suffix == ".gif":
        valid = header[:6] in {b"GIF87a", b"GIF89a"} and len(header) >= 10
        if valid:
            width, height = struct.unpack("<HH", header[6:10])
            valid = 0 < width * height <= 40000000
    elif suffix == ".webp":
        valid = header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    elif suffix in {".docx", ".xlsx"}:
        valid = inspect_office(path, suffix)
    if valid:
        from .sensitive_data import configured_secrets

        data = path.read_bytes()
        if any(secret.encode() in data for secret in configured_secrets()):
            raise HttpError(422, "Keep configured credentials in the secure connection settings.")
    if not valid:
        raise HttpError(422, "The file content does not match a supported safe format.")
    return TYPES[suffix]


def inspect_office(path, suffix):
    try:
        with zipfile.ZipFile(path) as archive:
            items = archive.infolist()
            names = {item.filename for item in items}
            required = {"[Content_Types].xml", "xl/workbook.xml" if suffix == ".xlsx" else "word/document.xml"}
            if len(items) > 500 or not required <= names:
                return False
            expanded = 0
            for item in items:
                parts = PurePosixPath(item.filename).parts
                if (item.flag_bits & 1 or not parts or item.filename.startswith("/") or ".." in parts
                    or "\\" in item.filename or len(parts) > 12
                    or stat.S_ISLNK(item.external_attr >> 16)
                    or any(value in item.filename.lower() for value in ("vbaproject", "embeddings/", "activex/"))
                    or suffix == ".xlsx" and any(value in item.filename.lower() for value in ("externallinks/", "macrosheets/", "dialogsheets/", "connections.xml"))):
                    return False
                expanded += item.file_size
                if expanded > 50 * 1024 * 1024 or item.file_size > 10 * 1024 * 1024 or item.file_size > max(1024 * 1024, item.compress_size * 100):
                    return False
            # Inspect the bounded content-type declaration as inert bytes, never
            # parse Office XML or execute macros, formulas or external links here.
            if suffix == ".xlsx":
                if archive.getinfo("[Content_Types].xml").file_size > 1024 * 1024:
                    return False
                types = archive.read("[Content_Types].xml").lower()
                if any(value in types for value in (b"macroenabled", b"vbaproject", b"macrosheet")):
                    return False
            return len(names) == len(items)
    except (zipfile.BadZipFile, OSError, ValueError, RuntimeError, NotImplementedError):
        return False


def attachment_path(attachment):
    from django.conf import settings

    root = Path(settings.MEDIA_ROOT) / str(attachment.request_id) / "attachments"
    path = Path(attachment.path)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise HttpError(404, "Attachment unavailable.")
    return path
