#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.law_retriever import normalize_law_records
from src.utils import read_json


def iter_jsonl(path: str | Path):
    path = Path(path)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def file_size(path: str | Path) -> int:
    path = Path(path)
    return path.stat().st_size if path.exists() else 0


def audit(
    law_corpus: str | Path,
    external_registry: str | Path,
    external_manifest: str | Path,
    finetune_file: str | Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    report: dict[str, Any] = {}

    law_path = Path(law_corpus)
    if law_path.exists():
        law_records = normalize_law_records(read_json(law_path))
        report["law_corpus"] = {
            "path": str(law_path),
            "exists": True,
            "bytes": file_size(law_path),
            "records": len(law_records),
            "laws": len({str(item.get("law_id", "")) for item in law_records}),
        }
    else:
        warnings.append(f"Missing law corpus: {law_path}")
        report["law_corpus"] = {"path": str(law_path), "exists": False}

    registry_path = Path(external_registry)
    registry_sources = []
    if registry_path.exists():
        registry = read_json(registry_path)
        registry_sources = registry.get("sources", []) if isinstance(registry, dict) else []
        categories = Counter(str(item.get("category", "")) for item in registry_sources if isinstance(item, dict))
        report["external_registry"] = {
            "path": str(registry_path),
            "exists": True,
            "bytes": file_size(registry_path),
            "sources": len(registry_sources),
            "categories": dict(categories),
            "contains_labeled_sources": sum(1 for item in registry_sources if item.get("contains_labels") is True),
        }
    else:
        warnings.append(f"Missing external registry: {registry_path}")
        report["external_registry"] = {"path": str(registry_path), "exists": False}

    manifest_path = Path(external_manifest)
    manifest_items = list(iter_jsonl(manifest_path)) if manifest_path.exists() else []
    source_names = Counter(str(item.get("source_name", "")) for item in manifest_items)
    missing_text_paths = [
        str(item.get("text_path", ""))
        for item in manifest_items
        if item.get("text_path") and not Path(str(item["text_path"])).exists()
    ]
    manifest_chars = 0
    for item in manifest_items:
        text_path = Path(str(item.get("text_path", "")))
        if text_path.exists():
            manifest_chars += len(text_path.read_text(encoding="utf-8", errors="replace"))
    report["external_manifest"] = {
        "path": str(manifest_path),
        "exists": manifest_path.exists(),
        "bytes": file_size(manifest_path),
        "documents": len(manifest_items),
        "source_names": dict(source_names),
        "text_chars": manifest_chars,
        "missing_text_paths": missing_text_paths[:20],
        "missing_text_path_count": len(missing_text_paths),
    }
    if registry_sources and len(manifest_items) < len(registry_sources):
        warnings.append(
            "External manifest has fewer documents than registered sources. "
            "Run or expand scripts/crawl_external_legal_sources.py if this is intentional."
        )
    if manifest_items and manifest_chars < 20_000:
        warnings.append("External raw text is very small; external data is likely only a seed crawl.")

    finetune_path = Path(finetune_file)
    finetune_items = list(iter_jsonl(finetune_path)) if finetune_path.exists() else []
    source_type_counts = Counter(str(item.get("source_type", "unknown")) for item in finetune_items)
    finetune_chars = sum(len(str(item.get("text", ""))) for item in finetune_items)
    external_chunks = source_type_counts.get("allowed_external_raw_legal_text", 0)
    report["finetune"] = {
        "path": str(finetune_path),
        "exists": finetune_path.exists(),
        "bytes": file_size(finetune_path),
        "items": len(finetune_items),
        "text_chars": finetune_chars,
        "source_types": dict(source_type_counts),
        "external_chunk_ratio": external_chunks / len(finetune_items) if finetune_items else 0.0,
    }
    if not finetune_items:
        warnings.append(f"Missing or empty fine-tune file: {finetune_path}")
    elif external_chunks == 0 and manifest_items:
        warnings.append("Fine-tune file does not include external chunks even though manifest has external documents.")
    elif external_chunks and external_chunks / len(finetune_items) < 0.05:
        warnings.append("External chunks are under 5% of fine-tune corpus; current training is dominated by law corpus.")

    report["ok"] = not any(message.startswith("Missing") for message in warnings)
    report["warnings"] = warnings
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ALQAC official, external, and fine-tune data coverage.")
    parser.add_argument("--law-corpus", default="data/corpus_law_pub.json")
    parser.add_argument("--external-registry", default="data/external_sources.json")
    parser.add_argument("--external-manifest", default="data/external_raw/manifest.jsonl")
    parser.add_argument("--finetune-file", default="data/finetune/domain_adaptation.jsonl")
    args = parser.parse_args()

    report = audit(args.law_corpus, args.external_registry, args.external_manifest, args.finetune_file)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
