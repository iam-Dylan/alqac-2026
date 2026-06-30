from __future__ import annotations

import json
import re
from typing import Any

from .query_parser import ParsedQuery


class ModelReasonerUnavailable(RuntimeError):
    pass


class LocalLLMReasoner:
    def __init__(
        self,
        model_name: str,
        max_input_chars: int = 12000,
        max_new_tokens: int = 256,
        load_in_4bit: bool = True,
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ModelReasonerUnavailable(
                "Install transformers, accelerate, torch, and bitsandbytes to use LocalLLMReasoner."
            ) from exc

        self.model_name = model_name
        self.max_input_chars = int(max_input_chars)
        self.max_new_tokens = int(max_new_tokens)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        kwargs: dict[str, Any] = {
            "device_map": "auto",
            "trust_remote_code": True,
        }
        if load_in_4bit:
            kwargs["load_in_4bit"] = True
        else:
            kwargs["torch_dtype"] = torch.float16
        self.model = AutoModelForCausalLM.from_pretrained(model_name, **kwargs)

    def predict(
        self,
        case_query: str,
        parsed: ParsedQuery,
        case_segments: list[dict[str, Any]],
        law_evidence: list[str],
    ) -> dict[str, Any]:
        prompt = self._build_prompt(case_query, parsed, case_segments, law_evidence)
        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là hệ thống dự đoán kết quả vụ án dân sự Việt Nam. "
                    "Chỉ trả JSON hợp lệ, không thêm giải thích ngoài JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(text, return_tensors="pt").to(self.model.device)
        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=self.max_new_tokens,
            do_sample=False,
            temperature=0.0,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        generated = self.tokenizer.decode(output_ids[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True)
        return self._parse_output(generated)

    def _build_prompt(
        self,
        case_query: str,
        parsed: ParsedQuery,
        case_segments: list[dict[str, Any]],
        law_evidence: list[str],
    ) -> str:
        evidence_lines = []
        for idx, segment in enumerate(case_segments[:8], start=1):
            text = str(segment.get("text", "")).strip()
            chunk_id = str(segment.get("chunk_id", f"chunk_{idx}"))
            evidence_lines.append(f"[{idx}] {chunk_id}: {text[:1800]}")
        prompt = f"""
Nhiệm vụ: dự đoán nhãn nhị phân cho yêu cầu chính của nguyên đơn.

Nhãn:
- A_WIN: Tòa chấp nhận toàn bộ hoặc chấp nhận đáng kể/một phần yêu cầu chính của nguyên đơn.
- B_WIN: Tòa bác hoặc không chấp nhận yêu cầu chính của nguyên đơn.

Quy tắc:
- Nếu quyết định ghi "chấp nhận một phần yêu cầu" thì thường là A_WIN, trừ khi phần chính trong case_query bị bác.
- Tập trung vào yêu cầu chính trong case_query, không nhầm với phản tố/yêu cầu phụ.
- Chỉ trả JSON: {{"prediction":"A_WIN|B_WIN","confidence":0.0,"rationale":"..."}}

case_query:
{case_query}

parsed:
{json.dumps(parsed.to_dict(), ensure_ascii=False)}

case_evidence:
{chr(10).join(evidence_lines)}

law_evidence:
{json.dumps(law_evidence[:10], ensure_ascii=False)}
""".strip()
        return prompt[: self.max_input_chars]

    @staticmethod
    def _parse_output(text: str) -> dict[str, Any]:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError(f"Model did not return JSON: {text[:300]}")
        data = json.loads(match.group(0))
        prediction = data.get("prediction")
        if prediction not in {"A_WIN", "B_WIN"}:
            raise ValueError(f"Invalid model prediction: {prediction!r}")
        confidence = float(data.get("confidence", 0.5))
        return {
            "prediction": prediction,
            "confidence": max(0.0, min(1.0, confidence)),
            "rationale": str(data.get("rationale", ""))[:1000],
        }
