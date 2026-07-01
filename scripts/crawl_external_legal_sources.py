#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import ssl
import sys
import time
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.validate_external_sources import validate_registry


ALLOWED_CATEGORIES = {
    "raw_legal_text",
    "official_legal_document",
    "public_legal_database",
    "non_annotated_reference",
}


class TextAndLinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self._skip_depth = 0
        self.text_parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(urljoin(self.base_url, href))
        if tag in {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = html.unescape(data)
        if text.strip():
            self.text_parts.append(text)

    def text(self) -> str:
        value = " ".join(part.strip() for part in self.text_parts if part.strip())
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\s*\n\s*", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def slugify(value: str) -> str:
    value = re.sub(r"https?://", "", value.lower())
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "source"


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def append_jsonl(path: str | Path, item: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def normalize_url(url: str) -> str:
    clean, _fragment = urldefrag(url)
    return clean.rstrip("/")


def is_same_domain(seed: str, candidate: str) -> bool:
    seed_host = urlparse(seed).netloc.lower()
    candidate_host = urlparse(candidate).netloc.lower()
    return bool(candidate_host) and candidate_host == seed_host


def should_visit(seed: str, url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not is_same_domain(seed, url):
        return False
    path = parsed.path.lower()
    blocked_ext = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".jpg", ".jpeg", ".png")
    return not path.endswith(blocked_ext)


def build_robot_parser(seed_url: str, user_agent: str) -> RobotFileParser | None:
    parsed = urlparse(seed_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception:
        return None
    return parser


def fetch_html(url: str, user_agent: str, timeout: int, ssl_context: ssl.SSLContext | None = None) -> str:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout, context=ssl_context) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            raise ValueError(f"Unsupported content type: {content_type}")
        raw = response.read()
    for encoding in ("utf-8", "utf-8-sig", "cp1258"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def save_document(
    output_dir: Path,
    source: dict[str, Any],
    url: str,
    text: str,
) -> dict[str, Any]:
    digest = hashlib.sha256((url + "\n" + text).encode("utf-8")).hexdigest()
    source_slug = slugify(str(source["url_or_path"]))
    target_dir = output_dir / source_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    text_path = target_dir / f"{digest[:16]}.txt"
    text_path.write_text(text + "\n", encoding="utf-8")
    return {
        "doc_id": digest,
        "source_name": source["name"],
        "source_category": source["category"],
        "url": url,
        "text_path": str(text_path),
        "sha256": digest,
        "chars": len(text),
        "contains_labels": bool(source.get("contains_labels", False)),
        "intended_use": source.get("intended_use", ""),
        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def crawl_source(
    source: dict[str, Any],
    output_dir: Path,
    manifest_path: Path,
    max_pages: int,
    delay_seconds: float,
    min_chars: int,
    timeout: int,
    user_agent: str,
    respect_robots: bool,
    ssl_context: ssl.SSLContext | None,
) -> tuple[int, int]:
    seed_url = normalize_url(str(source["url_or_path"]))
    robot_parser = build_robot_parser(seed_url, user_agent) if respect_robots else None
    queue: deque[str] = deque([seed_url])
    seen: set[str] = set()
    saved = 0
    attempted = 0

    while queue and saved < max_pages:
        url = normalize_url(queue.popleft())
        if url in seen or not should_visit(seed_url, url):
            continue
        seen.add(url)
        if robot_parser is not None and not robot_parser.can_fetch(user_agent, url):
            print(f"robots.txt disallows: {url}", file=sys.stderr)
            continue
        attempted += 1
        try:
            html_text = fetch_html(url, user_agent, timeout, ssl_context)
            extractor = TextAndLinkExtractor(url)
            extractor.feed(html_text)
            text = extractor.text()
        except Exception as exc:
            print(f"Warning: failed to fetch {url}: {exc}", file=sys.stderr)
            continue

        for link in extractor.links:
            link = normalize_url(link)
            if link not in seen and should_visit(seed_url, link):
                queue.append(link)

        if len(text) >= min_chars:
            item = save_document(output_dir, source, url, text)
            append_jsonl(manifest_path, item)
            saved += 1
            print(f"saved {source['name']}: {url} -> {item['text_path']}")
        else:
            print(f"skipped short page ({len(text)} chars): {url}", file=sys.stderr)
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    return attempted, saved


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl allowed non-labeled external Vietnamese legal sources.")
    parser.add_argument("--registry", default="data/external_sources.json")
    parser.add_argument("--output-dir", default="data/external_raw")
    parser.add_argument("--manifest", default="data/external_raw/manifest.jsonl")
    parser.add_argument("--max-pages-per-source", type=int, default=2)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--min-chars", type=int, default=300)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--user-agent", default="alqac-2026-research-crawler/0.1")
    parser.add_argument("--ignore-robots", action="store_true")
    parser.add_argument("--no-verify-ssl", action="store_true")
    args = parser.parse_args()

    validation = validate_registry(args.registry)
    if not validation["ok"]:
        print(json.dumps(validation, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    registry = load_json(args.registry)
    output_dir = Path(args.output_dir)
    manifest_path = Path(args.manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    ssl_context = ssl._create_unverified_context() if args.no_verify_ssl else None

    total_attempted = 0
    total_saved = 0
    for source in registry.get("sources", []):
        if source.get("contains_labels") is True:
            print(f"Skipping labeled source: {source.get('name')}", file=sys.stderr)
            continue
        if source.get("category") not in ALLOWED_CATEGORIES:
            print(f"Skipping unallowed category source: {source.get('name')}", file=sys.stderr)
            continue
        attempted, saved = crawl_source(
            source,
            output_dir,
            manifest_path,
            max_pages=max(0, args.max_pages_per_source),
            delay_seconds=max(0.0, args.delay_seconds),
            min_chars=max(0, args.min_chars),
            timeout=args.timeout,
            user_agent=args.user_agent,
            respect_robots=not args.ignore_robots,
            ssl_context=ssl_context,
        )
        total_attempted += attempted
        total_saved += saved

    print(json.dumps({"attempted": total_attempted, "saved": total_saved, "manifest": str(manifest_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
