from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_CONFIG: dict[str, Any] = {
    "api": {
        "base_url": "https://alqac-api.ngrok.pro",
        "endpoint": "/retrieve",
        "api_key_env": "ALQAC_API_KEY",
        "api_key_env_fallback": "ALQAC_TOKEN",
        "min_interval_seconds": 5,
        "timeout_seconds": 30,
        "max_retries": 5,
        "ssl_verify": False,
    },
    "retrieval": {
        "queries_per_case": 15,
        "min_queries_per_case": 6,
        "adaptive_stop": True,
        "max_case_evidence": 8,
    },
    "law_retrieval": {
        "method": "bm25",
        "top_k": 6,
        "embedding_model_name": "BAAI/bge-m3",
        "bm25_weight": 0.45,
        "dense_weight": 0.55,
        "embedding_batch_size": 16,
        "embedding_max_length": 8192,
        "dense_fallback_to_bm25": True,
    },
    "prediction": {
        "labels": ["A_WIN", "B_WIN"],
        "use_rule_override": True,
        "use_model_reasoner": False,
        "model_name": "Qwen/Qwen2.5-7B-Instruct",
        "adapter_path": None,
        "max_input_chars": 12000,
        "max_new_tokens": 256,
        "model_override_min_confidence": 0.80,
        "rule_override_max_confidence": 0.55,
    },
    "paths": {"cache_dir": "cache", "logs_dir": "logs"},
}


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def append_jsonl(path: str | Path, item: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_query(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    return normalize_space(text)


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", (text or "").lower())
    return re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)


def deep_update(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_update(out[key], value)
        else:
            out[key] = value
    return out


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"null", "None", "~"}:
        return None
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value.replace("'", '"'))
        except json.JSONDecodeError:
            return [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def load_config(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return DEFAULT_CONFIG
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    root: dict[str, Any] = {}
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            key = line[:-1].strip()
            root[key] = {}
            current = root[key]
        elif current is not None and ":" in line:
            key, value = line.strip().split(":", 1)
            current[key.strip()] = parse_scalar(value)
    return deep_update(DEFAULT_CONFIG, root)


def load_dotenv(path: str | Path = ".env") -> None:
    path = Path(path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_api_key(config: dict[str, Any]) -> str:
    load_dotenv()
    api_cfg = config.get("api", {})
    names = [
        api_cfg.get("api_key_env", "ALQAC_API_KEY"),
        api_cfg.get("api_key_env_fallback", "ALQAC_TOKEN"),
        "ALQAC_API_KEY",
        "ALQAC_TOKEN",
    ]
    for name in names:
        if name and os.environ.get(name):
            return os.environ[name]
    raise RuntimeError("Missing API key. Set ALQAC_API_KEY or ALQAC_TOKEN in .env/env.")
