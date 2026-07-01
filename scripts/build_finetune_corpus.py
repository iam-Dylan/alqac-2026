#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.law_retriever import normalize_law_records
from src.utils import read_json


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text


def chunk_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("; ", start, end), text.rfind("\n", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return [chunk for chunk in chunks if chunk]


def iter_law_corpus_items(path: str | Path, max_chars: int, overlap_chars: int):
    records = normalize_law_records(read_json(path))
    for record in records:
        text = normalize_text(record.get("text", ""))
        for idx, chunk in enumerate(chunk_text(text, max_chars, overlap_chars)):
            yield {
                "text": chunk,
                "source_type": "official_competition_law_corpus",
                "source_id": f"{record['law_id']}|{record['aid']}#{idx}",
                "contains_labels": False,
                "task": "domain_adaptation",
            }


def iter_external_items(manifest_path: str | Path, max_chars: int, overlap_chars: int):
    path = Path(manifest_path)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("contains_labels") is True:
                continue
            text_path = Path(item["text_path"])
            if not text_path.exists():
                continue
            text = text_path.read_text(encoding="utf-8")
            for idx, chunk in enumerate(chunk_text(text, max_chars, overlap_chars)):
                yield {
                    "text": chunk,
                    "source_type": "allowed_external_raw_legal_text",
                    "source_id": f"{item['doc_id']}#{idx}",
                    "source_name": item.get("source_name", ""),
                    "url": item.get("url", ""),
                    "contains_labels": False,
                    "task": "domain_adaptation",
                }


def write_jsonl(path: str | Path, items) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build non-labeled legal-domain adaptation corpus for fine-tuning/pretraining experiments."
    )
    parser.add_argument("--law-corpus", default="data/corpus_law_pub.json")
    parser.add_argument("--external-manifest", default="data/external_raw/manifest.jsonl")
    parser.add_argument("--output", default="data/finetune/domain_adaptation.jsonl")
    parser.add_argument("--max-chars", type=int, default=1800)
    parser.add_argument("--overlap-chars", type=int, default=150)
    parser.add_argument("--include-official-law-corpus", action="store_true")
    parser.add_argument("--include-external", action="store_true")
    args = parser.parse_args()

    if not args.include_official_law_corpus and not args.include_external:
        args.include_official_law_corpus = True
        args.include_external = True

    def items():
        if args.include_official_law_corpus:
            yield from iter_law_corpus_items(args.law_corpus, args.max_chars, args.overlap_chars)
        if args.include_external:
            yield from iter_external_items(args.external_manifest, args.max_chars, args.overlap_chars)

    count = write_jsonl(args.output, items())
    print(json.dumps({"output": args.output, "items": count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
