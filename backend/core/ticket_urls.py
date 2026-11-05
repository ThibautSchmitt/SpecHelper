"""Keep user-facing connector addresses separate from Docker transport addresses."""

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def in_container():
    return Path("/.dockerenv").exists()


def transport_host(value):
    return "host.docker.internal" if in_container() and value in {"localhost", "127.0.0.1", "::1"} else value


def transport_url(value):
    parsed = urlsplit(value)
    if transport_host(parsed.hostname) != parsed.hostname:
        parsed = parsed._replace(
            netloc="host.docker.internal" + (f":{parsed.port}" if parsed.port else "")
        )
    return urlunsplit(parsed)


def same_instance(left, right, platform):
    """Presentation-only aliases must not retarget or duplicate an old destination."""

    def endpoint(value):
        parsed = urlsplit(transport_url(value))
        path = parsed.path.rstrip("/")
        if platform == "glpi":
            path = path.removesuffix("/apirest.php")
        return parsed.scheme, parsed.hostname, parsed.port, path

    return endpoint(left) == endpoint(right)
