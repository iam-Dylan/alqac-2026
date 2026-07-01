#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ssl
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_data_sources import audit
from scripts.build_finetune_corpus import main as build_finetune_main
from scripts.crawl_external_legal_sources import (
    ALLOWED_CATEGORIES,
    crawl_source,
    load_existing_manifest,
    load_json,
)
from scripts.validate_external_sources import validate_registry


def run_build_finetune(args: argparse.Namespace) -> None:
    old_argv = sys.argv[:]
    try:
        sys.argv = [
            "build_finetune_corpus.py",
            "--law-corpus",
            args.law_corpus,
            "--external-manifest",
            args.manifest,
            "--output",
            args.finetune_output,
            "--max-chars",
            str(args.chunk_max_chars),
            "--overlap-chars",
            str(args.chunk_overlap_chars),
        ]
        build_finetune_main()
    finally:
        sys.argv = old_argv


def crawl_all(args: argparse.Namespace) -> dict[str, Any]:
    validation = validate_registry(args.registry)
    if not validation["ok"]:
        raise RuntimeError(json.dumps(validation, ensure_ascii=False, indent=2))

    registry = load_json(args.registry)
    output_dir = Path(args.output_dir)
    manifest_path = Path(args.manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    ssl_context = ssl._create_unverified_context() if args.no_verify_ssl else None
    known_urls, known_text_hashes = load_existing_manifest(manifest_path)

    total_attempted = 0
    total_saved = 0
    per_source: dict[str, dict[str, int]] = {}

    for source in registry.get("sources", []):
        name = str(source.get("name", "unknown"))
        if source.get("contains_labels") is True:
            print(f"Skipping labeled source: {name}", file=sys.stderr)
            continue
        if source.get("category") not in ALLOWED_CATEGORIES:
            print(f"Skipping unallowed category source: {name}", file=sys.stderr)
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
            max_depth=max(0, args.max_depth),
            known_urls=known_urls,
            known_text_hashes=known_text_hashes,
        )
        total_attempted += attempted
        total_saved += saved
        per_source[name] = {"attempted": attempted, "saved": saved}

    return {
        "attempted": total_attempted,
        "saved": total_saved,
        "manifest": str(manifest_path),
        "per_source": per_source,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Aggressively crawl allowed non-labeled external legal sources, "
            "then rebuild the domain-adaptation corpus."
        )
    )
    parser.add_argument("--registry", default="data/external_sources.json")
    parser.add_argument("--output-dir", default="data/external_raw")
    parser.add_argument("--manifest", default="data/external_raw/manifest.jsonl")
    parser.add_argument("--law-corpus", default="data/corpus_law_pub.json")
    parser.add_argument("--finetune-output", default="data/finetune/domain_adaptation.jsonl")

    parser.add_argument("--max-pages-per-source", type=int, default=1000)
    parser.add_argument("--max-depth", type=int, default=8)
    parser.add_argument("--delay-seconds", type=float, default=0.7)
    parser.add_argument("--min-chars", type=int, default=300)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--user-agent", default="alqac-2026-research-crawler/0.2")
    parser.add_argument("--ignore-robots", action="store_true")
    parser.add_argument("--no-verify-ssl", action="store_true")

    parser.add_argument("--chunk-max-chars", type=int, default=1800)
    parser.add_argument("--chunk-overlap-chars", type=int, default=150)
    parser.add_argument("--skip-rebuild-finetune", action="store_true")
    args = parser.parse_args()

    crawl_report = crawl_all(args)
    print("Crawl report:")
    print(json.dumps(crawl_report, ensure_ascii=False, indent=2))

    if not args.skip_rebuild_finetune:
        run_build_finetune(args)

    audit_report = audit(args.law_corpus, args.registry, args.manifest, args.finetune_output)
    print("Audit report:")
    print(json.dumps(audit_report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
