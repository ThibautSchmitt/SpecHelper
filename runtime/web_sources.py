"""Bounded public HTTPS reading with pinned DNS, no cookies, credentials or proxy inheritance."""

import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
import uuid
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, urljoin, urlsplit

from core.official_sources import public_reference_url

MAX_BYTES = 512 * 1024
MAX_TEXT = 20000


class PublicHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the validated address, retaining the original hostname for TLS verification.
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def resolved_address(host):
    addresses = {row[4][0] for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Private or mixed-network destinations are denied.")
    return sorted(addresses)[0]


def read_public(url, deadline):
    for _ in range(4):
        url = public_reference_url(url)
        parsed = urlsplit(url)
        host = parsed.hostname
        address = resolved_address(host)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("The Web read time limit was reached.")
        connection = PublicHTTPS(host, address, min(8, remaining))
        try:
            connection.request(
                "GET",
                parsed.path + ("?" + parsed.query if parsed.query else ""),
                headers={
                    "Accept": "text/html,text/plain",
                    "Accept-Encoding": "identity",
                    "User-Agent": "SpecHelper/2.5 reference-reader",
                },
            )
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                target = response.getheader("Location", "")
                if not target:
                    raise ValueError("The reference redirect is unavailable.")
                url = urljoin(url, target)
                continue
            if response.status != 200:
                raise ValueError("The reference could not be read.")
            content_type = response.getheader("Content-Type", "").split(";")[0].lower()
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise ValueError("Only HTML and plain text reference pages are supported.")
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                raise ValueError("Compressed reference responses are not accepted.")
            data = bytearray()
            while True:
                if time.monotonic() >= deadline:
                    raise ValueError("The Web read time limit was reached.")
                chunk = response.read(min(16384, MAX_BYTES + 1 - len(data)))
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ValueError("The reference exceeds the transfer limit.")
                if not chunk:
                    break
            return url, bytes(data), content_type
        finally:
            connection.close()
    raise ValueError("The reference has too many redirects.")


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.in_title = False
        self.title = []
        self.text = []
        self.published_at = ""
        self.links = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta" and attributes.get("property", attributes.get("name", "")).lower() in {
            "article:published_time",
            "date",
            "datepublished",
            "dcterms.date",
        }:
            self.published_at = attributes.get("content", "")[:100]
        if tag == "a":
            self.anchor = {"url": attributes.get("href", ""), "title": ""}

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.anchor:
            self.links.append(self.anchor)
            self.anchor = None
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.text.append("\n")

    def handle_data(self, data):
        if self.hidden:
            return
        if self.in_title:
            self.title.append(data)
        self.text.append(data)
        if self.anchor:
            self.anchor["title"] += data

    def plain(self):
        return re.sub(r"[ \t\r\f\v]+", " ", " ".join(self.text)).strip()


class WebReader:
    def __init__(self, timeout, redact=lambda value: value):
        self.deadline = time.monotonic() + min(timeout, 90)
        self.receipts = []
        self.calls = 0
        self.transferred = 0
        self.lock = threading.Lock()
        self.redact = redact

    def read(self, url, search=False):
        clean = self.redact(url)
        if clean != url:
            raise ValueError("Credentials cannot be sent to reference destinations.")
        with self.lock:
            if self.calls >= 16 or self.transferred >= 4 * MAX_BYTES:
                raise ValueError("The Web reference budget is exhausted.")
            self.calls += 1
            # Reserve the maximum transfer before concurrent network requests start.
            self.transferred += MAX_BYTES
        url, data, kind = read_public(url, min(self.deadline, time.monotonic() + 15))
        text = data.decode("utf-8", errors="replace")
        page = PageText()
        if kind != "text/plain":
            page.feed(text)
            text = page.plain()
        if search:
            return page
        receipt = self.redact(
            {
                "reference_id": "web-" + uuid.uuid4().hex,
                "url": url,
                "title": " ".join(page.title).strip()[:500] or urlsplit(url).hostname,
                "consulted_at": datetime.now(UTC).isoformat(),
                "published_at": page.published_at,
                "sha256": hashlib.sha256(data).hexdigest(),
                "text_sha256": hashlib.sha256(text[:MAX_TEXT].encode()).hexdigest(),
                "text": text[:MAX_TEXT],
                "truncated": len(text) > MAX_TEXT,
                "status": "checked",
            }
        )
        with self.lock:
            self.receipts.append(receipt)
        return receipt

    def search(self, query):
        if (
            not isinstance(query, str)
            or not 3 <= len(query) <= 300
            or any(ord(c) < 32 for c in query)
        ):
            raise ValueError("Enter a short public reference search query.")
        if self.redact(query) != query:
            raise ValueError("Credentials cannot be sent to reference search.")
        page = self.read("https://html.duckduckgo.com/html/?q=" + quote(query), search=True)
        results = []
        for link in page.links:
            target = link["url"]
            if target.startswith("//"):
                target = "https:" + target
            parsed = urlsplit(target)
            if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
                target = parse_qs(parsed.query).get("uddg", [""])[0]
            try:
                target = public_reference_url(target)
            except ValueError:
                continue
            if "duckduckgo.com" in urlsplit(target).hostname or not link["title"].strip():
                continue
            if target not in {item["url"] for item in results}:
                results.append({"url": target, "title": link["title"].strip()[:300]})
        return {
            "results": results[:8],
            "evidence": False,
            "note": "Search suggestions are not evidence. Read a primary official page and assess applicability before citing it.",
        }
