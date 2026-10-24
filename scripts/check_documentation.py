"""Check repository Markdown links, GitHub-style anchors and shell examples offline."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
LINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)(?:\s+['\"][^)\n]*['\"])?\s*\)")
REFERENCE = re.compile(r"^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", re.M)
HEADING = re.compile(r"^ {0,3}#{1,6}\s+(.+?)(?:\s+#+)?$")
ANCHOR = re.compile(r"<[a-z][a-z0-9]*\b[^>]*\b(?:id|name)=['\"]([^'\"]+)['\"]", re.I)


def documents(root):
    """Exclude local instructions, dependencies, private data and generated reports."""
    paths = list(root.glob("*.md"))
    paths += list((root / "docs").rglob("*.md"))
    paths += list((root / ".github").rglob("*.md"))
    return sorted(path for path in paths if path.name != "AGENTS.md")


def parse_markdown(text):
    """Separate fenced examples so sample links/headings are not treated as prose."""
    prose, blocks = [], []
    fence, language, lines = None, "", []
    for line in text.splitlines():
        match = FENCE.match(line)
        if fence:
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                blocks.append((language, "\n".join(lines) + "\n"))
                fence, lines = None, []
            else:
                lines.append(line)
        elif match:
            fence, language = match[1], match[2].strip().lower()
        else:
            prose.append(line)
    return "\n".join(prose), blocks, fence is not None


def anchors(text):
    prose, _, _ = parse_markdown(text)
    values = set(ANCHOR.findall(prose))
    used = {}
    for line in prose.splitlines():
        match = HEADING.match(line)
        if not match:
            continue
        title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", match[1]).lower()
        title = re.sub(r"<[^>]*>", "", title)
        title = re.sub(r"[^\w\- ]", "", title)
        slug = title.replace(" ", "-")
        count = used.get(slug, 0)
        used[slug] = count + 1
        values.add(f"{slug}-{count}" if count else slug)
    return values


def check(root):
    root = root.resolve()
    errors, link_count, shell_count = [], 0, 0
    files = documents(root)
    contents = {path: path.read_text(encoding="utf-8") for path in files}
    for path, text in contents.items():
        name = path.relative_to(root)
        prose, blocks, unclosed = parse_markdown(text)
        if unclosed:
            errors.append(f"{name}: unclosed fenced code block")
        urls = [match[1].strip("<>") for match in LINK.finditer(prose)]
        urls += [match[1].strip("<>") for match in REFERENCE.finditer(prose)]
        for url in urls:
            parts = urlsplit(url)
            if parts.scheme or parts.netloc:
                continue
            link_count += 1
            target = (path.parent / unquote(parts.path)).resolve() if parts.path else path
            if not target.is_relative_to(root):
                errors.append(f"{name}: link escapes repository: {url}")
            elif not target.exists():
                errors.append(f"{name}: missing target: {url}")
            elif parts.fragment and target.suffix == ".md":
                target_text = contents.get(target)
                if target_text is None:
                    target_text = target.read_text(encoding="utf-8")
                if unquote(parts.fragment) not in anchors(target_text):
                    errors.append(f"{name}: missing anchor: {url}")
        if "archive" in name.parts:
            continue
        for language, body in blocks:
            if language not in {"sh", "shell", "bash"}:
                continue
            shell_count += 1
            result = subprocess.run(
                ["bash", "-n"], input=body, text=True, capture_output=True, check=False
            )
            if result.returncode:
                errors.append(f"{name}: shell syntax: {result.stderr.strip()}")
        for module in re.findall(r"python(?:3)?\s+-m\s+(runtime\.[a-zA-Z0-9_.]+)", text):
            if not (root / (module.replace(".", "/") + ".py")).is_file():
                errors.append(f"{name}: missing Python module: {module}")
        package = root / "frontend/package.json"
        if package.is_file():
            scripts = json.loads(package.read_text())["scripts"]
            for script in re.findall(r"npm run ([a-zA-Z0-9:_-]+)", text):
                if script not in scripts:
                    errors.append(f"{name}: unknown npm script: {script}")
    return {
        "markdown_files": len(files),
        "relative_links": link_count,
        "current_shell_blocks": shell_count,
        "errors": errors,
        "scope": "offline relative targets/Markdown anchors, shell syntax, runtime modules and npm script names; no command execution or external URL validation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = check(args.root.resolve())
    print(json.dumps(result, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
