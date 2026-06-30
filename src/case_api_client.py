from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .utils import append_jsonl, normalize_query


class RetrievalAPIError(RuntimeError):
    pass


class CaseAPIClient:
    def __init__(
        self,
        base_url: str,
        endpoint: str,
        api_key: str,
        cache_path: str | Path,
        min_interval_seconds: float = 5.0,
        timeout_seconds: float = 30.0,
        max_retries: int = 5,
        ssl_verify: bool = False,
    ) -> None:
        self.url = base_url.rstrip("/") + "/" + endpoint.lstrip("/")
        self.api_key = api_key
        self.cache_path = Path(cache_path)
        self.min_interval_seconds = float(min_interval_seconds)
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.ssl_context = None if ssl_verify else ssl._create_unverified_context()
        self.last_request_at = 0.0
        self.cache: dict[str, dict[str, Any]] = {}
        self.api_call_count = 0
        self._load_cache()

    def _cache_key(self, case_id: str, query: str) -> str:
        return json.dumps([case_id, normalize_query(query)], ensure_ascii=False)

    def _load_cache(self) -> None:
        if not self.cache_path.exists():
            return
        with self.cache_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    self.cache[item["key"]] = item["response"]
                except (json.JSONDecodeError, KeyError):
                    continue

    def retrieve(self, case_id: str, query: str) -> dict[str, Any]:
        key = self._cache_key(case_id, query)
        if key in self.cache:
            response = dict(self.cache[key])
            response["_cached"] = True
            return response

        response = self._request_with_retries(case_id, query)
        self.cache[key] = response
        append_jsonl(self.cache_path, {"key": key, "case_id": case_id, "query": query, "response": response})
        return dict(response)

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        wait = self.min_interval_seconds - elapsed
        if wait > 0:
            time.sleep(wait)

    def _request_with_retries(self, case_id: str, query: str) -> dict[str, Any]:
        payload = json.dumps({"case_id": case_id, "query": query}, ensure_ascii=False).encode("utf-8")
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        backoff = self.min_interval_seconds
        for attempt in range(self.max_retries + 1):
            self._rate_limit()
            request = urllib.request.Request(self.url, data=payload, headers=headers, method="POST")
            self.last_request_at = time.monotonic()
            self.api_call_count += 1
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=self.timeout_seconds,
                    context=self.ssl_context,
                ) as resp:
                    body = resp.read().decode("utf-8")
                    data = json.loads(body)
                    return self._parse_response(data)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in {403, 422}:
                    raise RetrievalAPIError(f"Retrieval API failed with {exc.code}: {body}") from exc
                if exc.code in {429, 503} and attempt < self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise RetrievalAPIError(f"Retrieval API failed with {exc.code}: {body}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if self._is_certificate_error(exc):
                    self.ssl_context = ssl._create_unverified_context()
                    if attempt < self.max_retries:
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                if attempt < self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise RetrievalAPIError(f"Retrieval API request failed: {exc}") from exc
        raise RetrievalAPIError("Retrieval API request failed after retries")

    @staticmethod
    def _is_certificate_error(exc: BaseException) -> bool:
        reason = getattr(exc, "reason", exc)
        return isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc)

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> dict[str, Any]:
        results = data.get("results")
        if not isinstance(results, list) or not results:
            return {"results": []}
        first = results[0]
        if not isinstance(first, dict):
            return {"results": []}
        return {
            "results": [
                {
                    "chunk_id": str(first.get("chunk_id", "")),
                    "score": float(first.get("score", 0) or 0),
                    "text": str(first.get("text", "")),
                }
            ]
        }
