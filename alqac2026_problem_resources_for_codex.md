# ALQAC 2026 — Problem Definition, Available Resources, and Implementation Brief

## 0. Purpose of this document

This document describes the ALQAC 2026 task and the resources available to build a competition system. It is written as an implementation brief for Codex or any coding agent that will build the pipeline.

The system to build is an **Agentic Retrieval-Augmented Generation / Retrieval-Augmented Reasoning system** for Vietnamese legal case outcome prediction. The system must start from a short `case_query`, retrieve supporting case-content evidence through the official API, retrieve relevant legal provisions from the provided law corpus, predict the outcome, and create a valid `submission.json`.

When the original specification has contradictions, this document resolves them using the following priority:

1. **Submission Format / Submission Validation** has priority for output schema and labels.
2. **Latest Retrieval API documentation** has priority for case-evidence retrieval implementation.
3. Earlier overview text is used only as conceptual context if it conflicts with the two sources above.

---

## 1. Competition task

### 1.1 Task name

`Legal Case Outcome Prediction with Evidence Retrieval`

### 1.2 Task objective

For each Vietnamese legal case, the system receives a short natural-language query describing the dispute. The system must:

1. Read the provided `case_query`.
2. Retrieve relevant case-content segments through the official Retrieval API.
3. Retrieve relevant legal provisions from the provided law corpus.
4. Predict whether the plaintiff or defendant wins the main claim described in the query.
5. Produce a valid `submission.json` containing prediction, case evidence, and law evidence.

### 1.3 Why this is not a simple classifier

The input query does **not** contain the full judgment, final decision, full court reasoning, or gold evidence. The system must actively retrieve additional case segments before making a grounded prediction. This means the system should be implemented as an Agentic RAG / legal reasoning pipeline, not as a pure text classifier over `case_query` only.

---

## 2. Input data

### 2.1 Private Test input format

The decisive Private Test input is strictly limited to two fields:

```json
{
  "case_id": "case_1087_0037",
  "case_query": "Ông Nguyễn Khắc Vũ H1 (nguyên đơn) và Chu Quang Nguyễn H2 (bị đơn) tranh chấp hợp đồng chuyển nhượng quyền sử dụng đất đối với một phần thửa 366. Nguyên đơn yêu cầu được công nhận hợp đồng chuyển nhượng cho diện tích nêu trên. Agent cần dự đoán nguyên đơn thắng kiện hay bị đơn thắng kiện?"
}
```

The actual input file is a JSON list:

```json
[
  {
    "case_id": "case_1087_0037",
    "case_query": "..."
  },
  {
    "case_id": "case_1087_0041",
    "case_query": "..."
  }
]
```

### 2.2 Field definitions

| Field | Type | Description |
|---|---:|---|
| `case_id` | string | Public identifier of the test case. Must be passed to the Retrieval API. |
| `case_query` | string | Short Vietnamese natural-language description of the dispute and prediction question. |

### 2.3 Information not included in input

The input does **not** include:

- gold verdict;
- court reasoning;
- court decision;
- gold case evidence;
- gold law evidence;
- full judgment text.

### 2.4 Public Test role

The Public Test currently has 50 cases and is primarily a testing ground. It may be used to test retrieval strategies, reasoning strategies, and leaderboard submissions. Do not build inference code that depends on extra public-test fields beyond `case_id` and `case_query`. The Private Test should be treated as the authoritative input format.

---

## 3. Output / submission

### 3.1 File name

The final output file must be named:

```text
submission.json
```

### 3.2 Final submission schema

Use the following schema:

```json
[
  {
    "case_id": "case_1087_0037",
    "prediction": "A_WIN",
    "case_evidence": [
      "case_1087_0037_chunk_2",
      "case_1087_0037_chunk_5"
    ],
    "law_evidence": [
      {
        "law_id": "47/2010/QH12",
        "aid": 270
      },
      {
        "law_id": "91/2015/QH13",
        "aid": 357
      }
    ]
  }
]
```

### 3.3 Required fields

| Field | Type | Required | Description |
|---|---:|---:|---|
| `case_id` | string | yes | Official case identifier. |
| `prediction` | string | yes | Must be `A_WIN` or `B_WIN`. |
| `case_evidence` | list[string] | yes | List of `chunk_id` values returned by the Retrieval API. |
| `law_evidence` | list[object] | yes | List of relevant legal provisions. Each item must have `law_id` and `aid`. |

### 3.4 Prediction labels

Although the task overview mentioned partial labels, the Submission Format / Validation should be followed. Therefore the final submitted prediction must be binary:

| Label | Meaning |
|---|---|
| `A_WIN` | Plaintiff wins. The court substantially accepts the plaintiff's main claim described in `case_query`. |
| `B_WIN` | Defendant wins. The court substantially rejects the plaintiff's main claim or rules in favor of the defendant. |

Do **not** submit:

- `PARTIAL_A_WIN`
- `PARTIAL_B_WIN`

Partial labels may be used internally for reasoning, but they must be mapped to `A_WIN` or `B_WIN` before writing `submission.json`.

### 3.5 Law evidence format

Use the Submission Format form:

```json
"law_evidence": [
  {
    "law_id": "91/2015/QH13",
    "aid": 117
  }
]
```

Where:

| Field | Type | Required | Description |
|---|---:|---:|---|
| `law_id` | string | yes | Identifier of the legal document in the law corpus. |
| `aid` | integer | yes | Article/provision ID inside the corresponding legal document. |

Do not use the older ambiguous list-string example for law evidence.

### 3.6 Case evidence format

Use the latest Retrieval API documentation. Each API response returns a `chunk_id`. Record these IDs in `case_evidence`:

```json
"case_evidence": [
  "case_1087_0037_chunk_2",
  "case_1087_0037_chunk_5"
]
```

Do not include segment `text` or `score` in the final submission unless the official validator later explicitly allows it.

---

## 4. Available resources

### 4.1 Case Query Input

The initial input for every test case consists of `case_id` and `case_query`. The query may contain:

- plaintiff name;
- defendant name;
- disputed legal relationship;
- disputed asset or contract;
- brief summary of plaintiff's claim;
- defendant's position if included;
- prediction question.

The query is only the starting point. It is insufficient to solve the task reliably without retrieval.

### 4.2 Segmented Case Content Corpus

The full raw judgments are not directly provided for the test set. Instead, case content is segmented into chunks and exposed through the official Retrieval API.

A case segment may contain:

- plaintiff's claims;
- defendant's arguments;
- related parties' statements;
- facts;
- procedural information;
- court reasoning;
- final verdict / final decision.

The system must retrieve relevant segments using the API and use the returned `chunk_id` values as `case_evidence`.

### 4.3 Law Corpus

The law corpus is provided to teams separately. The system must build its own retrieval component over this corpus.

A legal provision can be represented internally as:

```json
{
  "law_id": "91/2015/QH13",
  "aid": 117,
  "content_Article": "..."
}
```

Implementation should preprocess the law corpus into article/provision-level records and build lexical and/or dense indices for retrieval.

### 4.4 Retrieval API

The official API is used to retrieve case-content segments.

#### Endpoint

```http
POST https://alqac-api.ngrok.pro/retrieve
```

#### Authentication

Every request must include the team's secret token in the `X-API-Key` header:

```http
X-API-Key: alqac_xxxxxxxxxxxxxxxxxxxxxxxx
```

Do not use Bearer authentication for the current API.

#### Request body

```json
{
  "query": "tranh chấp quyền sử dụng đất",
  "case_id": "case_1087_0037"
}
```

| Field | Type | Description |
|---|---:|---|
| `query` | string | Vietnamese search query describing the evidence being sought. |
| `case_id` | string | Target case ID, e.g. `case_1087_0037`. Must be in the official test set. |

#### Response

Each request returns exactly one top-ranked segment inside `results`:

```json
{
  "results": [
    {
      "score": 0.886,
      "text": "Người có quyền lợi nghĩa vụ liên quan: ...",
      "chunk_id": "case_1087_0037_chunk_2"
    }
  ]
}
```

| Field | Description |
|---|---|
| `score` | BM25 relevance score. Higher is more relevant. |
| `text` | Retrieved segment text. Use it for reasoning. |
| `chunk_id` | Segment identifier. Record it in `case_evidence`. |

#### Rate limit

The API is limited to:

```text
1 request every 5 seconds per team
```

The implementation must include a rate limiter and a cache.

#### Error codes

| Code | Meaning | Required handling |
|---:|---|---|
| 200 | Success | Parse `results[0]`. |
| 403 | Missing or invalid `X-API-Key` | Stop; token/config is wrong. |
| 422 | Malformed request, missing `query` or `case_id` | Stop and fix request validation. |
| 429 | Rate limit exceeded | Sleep at least 5 seconds and retry. |
| 503 | Team database temporarily unavailable | Retry with exponential backoff. |

---

## 5. Evaluation

### 5.1 Final score

The final score is:

```text
FinalScore = 0.70 * OutcomeAccuracy
           + 0.20 * PenalizedCaseRecall
           + 0.10 * F1_law_micro
```

Priority for implementation:

1. maximize outcome prediction accuracy;
2. retrieve correct case evidence while keeping API calls economical;
3. retrieve relevant legal provisions with good micro-F1.

### 5.2 Outcome Accuracy

For each case `i`:

```text
Outcome_i = 1 if y_hat_i == y_i
Outcome_i = 0 otherwise
```

Overall:

```text
OutcomeAccuracy = (1 / N) * sum_i Outcome_i
```

This component is worth 70% of the final score.

### 5.3 Case Evidence Recall

For each case `i`:

```text
Recall_case_i = |P_case_i ∩ G_case_i| / |G_case_i|
```

Where:

| Symbol | Meaning |
|---|---|
| `G_case_i` | Gold set of case evidence segments. |
| `P_case_i` | Submitted set of case evidence segments. |

This measures how many gold case evidence segments were successfully retrieved/submitted.

### 5.4 API efficiency penalty

Let:

| Symbol | Meaning |
|---|---|
| `n_i` | Number of available case-content segments for case `i`. |
| `c_i` | Number of Retrieval API calls made by the system for case `i`. |

No-penalty budget:

```text
B_i = 2 * n_i
```

Efficiency factor:

```text
E_i = 1                                  if c_i <= 2*n_i
E_i = 1 - (c_i - 2*n_i) / (3*n_i)        if 2*n_i < c_i < 5*n_i
E_i = 0                                  if c_i >= 5*n_i
```

Compact form:

```text
E_i = max(0, 1 - max(0, c_i - 2*n_i) / (3*n_i))
```

### 5.5 Penalized Case Recall

For each case:

```text
PenalizedRecall_case_i = Recall_case_i * E_i
```

Overall:

```text
PenalizedCaseRecall = (1 / N) * sum_i (Recall_case_i * E_i)
```

This component is worth 20% of the final score.

### 5.6 Micro Law Evidence F1

Law evidence is evaluated with micro-F1 over the full test set:

```text
Precision_law_micro = |P_law ∩ G_law| / |P_law|
Recall_law_micro    = |P_law ∩ G_law| / |G_law|
F1_law_micro        = 2 * Precision_law_micro * Recall_law_micro
                      / (Precision_law_micro + Recall_law_micro)
```

This component is worth 10% of the final score.

Do not submit too many irrelevant law provisions, because precision will decrease.

---

## 6. System requirements and restrictions

### 6.1 Model restrictions

The submitted system must not use closed/proprietary models or non-open API-based models, including but not limited to:

- ChatGPT;
- GPT-4;
- Claude;
- Gemini;
- other closed API-based models.

Only open-weight models with fewer than 10 billion parameters are allowed.

### 6.2 External dataset restrictions

Querying online legal databases is allowed, but externally annotated datasets specifically created for legal QA or legal entailment are not allowed. Examples of prohibited data include pre-labeled legal QA pairs or legal entailment examples.

### 6.3 Submission limit

The official leaderboard permits at most:

```text
3 submissions per day
```

### 6.4 Reproducibility

The organizers may request:

- source code;
- configuration files;
- logs;
- a short technical report.

The technical report should describe:

- Case Content API retrieval strategy;
- law corpus retrieval strategy;
- reasoning and prediction method;
- models and tools used;
- prompting or agent design, if applicable;
- post-processing and validation steps.

---

## 7. Recommended implementation workflow

### 7.1 High-level pipeline

```text
private_test.json
    ↓
[1] Input Loader
    ↓
[2] Case Query Parser
    ↓
[3] Case Retrieval Query Planner
    ↓
[4] Retrieval API Client
    ↓
[5] Evidence Deduplication and Ranking
    ↓
[6] Law Corpus Retriever
    ↓
[7] Outcome Reasoner / Classifier
    ↓
[8] Evidence Selector
    ↓
[9] Submission Builder
    ↓
[10] Submission Validator
    ↓
submission.json
```

### 7.2 Module responsibilities

#### Module 1 — Input Loader

Read a JSON list of cases. Only rely on:

```python
case_id: str
case_query: str
```

Reject or ignore all other fields during inference.

#### Module 2 — Case Query Parser

Extract structured fields from `case_query`:

```json
{
  "plaintiff": "...",
  "defendant": "...",
  "legal_relation": "...",
  "disputed_object": "...",
  "plaintiff_claim": "...",
  "defendant_position": "...",
  "keywords": ["..."]
}
```

This can be rule-based, model-based with an allowed open-weight model, or hybrid.

#### Module 3 — Case Retrieval Query Planner

Generate multiple Vietnamese search queries per case. The goal is to retrieve diverse evidence types:

1. plaintiff claim;
2. defendant argument;
3. relevant facts;
4. court reasoning;
5. final decision;
6. legal basis.

Recommended base templates:

```text
[legal_relation] + [disputed_object]
[plaintiff] + "yêu cầu" + [plaintiff_claim]
[defendant] + "không đồng ý" + [legal_relation]
"Hội đồng xét xử nhận định" + [legal_relation]
"Xét thấy" + [plaintiff_claim]
"Căn cứ" + [legal_relation]
"Quyết định" + [plaintiff] + [defendant]
"Chấp nhận yêu cầu khởi kiện" + [plaintiff]
"Không chấp nhận yêu cầu khởi kiện" + [plaintiff]
"Tuyên xử" + [plaintiff] + [defendant]
```

Suggested retrieval budget:

```text
MVP:        8 queries per case
Standard:   12–15 queries per case
Aggressive: 20–25 queries per case
```

Do not brute-force blindly because API calls affect the 20% Penalized Case Recall component.

#### Module 4 — Retrieval API Client

Implement:

```python
POST https://alqac-api.ngrok.pro/retrieve
headers = {
    "X-API-Key": ALQAC_TOKEN,
    "Content-Type": "application/json",
}
json = {
    "query": query,
    "case_id": case_id,
}
```

Required features:

- rate limit: 1 request / 5 seconds / team;
- cache by `(case_id, normalized_query)`;
- retry 429 and 503;
- no blind retry on 403 or 422;
- save full retrieval logs.

#### Module 5 — Evidence Deduplication and Ranking

Deduplicate by `chunk_id`.

Rank segment utility using markers:

Decision markers:

```text
"QUYẾT ĐỊNH"
"Tuyên xử"
"Chấp nhận yêu cầu"
"Không chấp nhận yêu cầu"
"Bác yêu cầu"
```

Reasoning markers:

```text
"Hội đồng xét xử nhận định"
"Xét thấy"
"Có căn cứ"
"Không có căn cứ"
"Căn cứ vào"
```

Claim/defense markers:

```text
"Nguyên đơn yêu cầu"
"Bị đơn trình bày"
"Không đồng ý"
"Phản tố"
```

Keep the most useful chunks for reasoning and final `case_evidence`.

#### Module 6 — Law Corpus Retriever

Preprocess law corpus into records:

```json
{
  "law_id": "91/2015/QH13",
  "aid": 117,
  "text": "..."
}
```

Build at least a BM25 index. Optionally add dense embedding and reranking using allowed open-weight/local models.

Queries for law retrieval should be built from:

- `case_query`;
- parsed legal issue;
- retrieved court reasoning segments;
- dispute category.

Recommended top-k:

```text
MVP:      3–5 law provisions per case
Standard: 5–8 law provisions per case
Avoid:    >10 unless highly confident
```

#### Module 7 — Outcome Reasoner / Classifier

Input:

```text
case_query
parsed case structure
selected case segments
selected law provisions
```

Output:

```json
{
  "prediction": "A_WIN",
  "confidence": 0.74,
  "rationale": "..."
}
```

Reasoning procedure:

1. Identify the main claim described in `case_query`.
2. Determine whether retrieved reasoning/final-decision segments accept or reject that main claim.
3. If decision text is explicit, use it as a rule override.
4. Otherwise use evidence-grounded legal reasoning.
5. Map result to `A_WIN` or `B_WIN`.

Rule examples:

```text
"Chấp nhận yêu cầu khởi kiện của nguyên đơn"      -> A_WIN
"Không chấp nhận yêu cầu khởi kiện của nguyên đơn" -> B_WIN
"Bác yêu cầu khởi kiện của nguyên đơn"             -> B_WIN
```

For partial decisions, focus on the main claim in `case_query` and map to the binary label that best reflects whether the main claim was substantially accepted or rejected.

#### Module 8 — Evidence Selector

Select final `case_evidence` IDs from retrieved chunks.

Prioritize:

1. final decision chunk;
2. court reasoning chunk;
3. plaintiff's main claim chunk;
4. defendant's core argument chunk;
5. legal basis chunk.

Suggested final count:

```text
MVP:      3–5 chunks per case
Standard: 5–8 chunks per case
```

#### Module 9 — Submission Builder

For each case, create:

```json
{
  "case_id": "...",
  "prediction": "A_WIN",
  "case_evidence": ["..."],
  "law_evidence": [
    {"law_id": "...", "aid": 123}
  ]
}
```

Do not add extra fields to the final submission unless the official validator explicitly permits them.

#### Module 10 — Submission Validator

Validate before submission:

- JSON is parseable;
- number of objects equals number of input cases;
- no missing `case_id`;
- no extra `case_id`;
- no duplicate `case_id`;
- `prediction` is either `A_WIN` or `B_WIN`;
- `case_evidence` is a list of strings;
- no duplicate `chunk_id` within a case;
- `law_evidence` is a list of objects;
- each law evidence item has `law_id` and `aid`;
- `law_id` exists in the law corpus;
- `aid` exists under the corresponding `law_id`;
- no duplicate law evidence items.

---

## 8. Recommended repository structure

```text
alqac2026/
  configs/
    config.yaml
    prompts.yaml
    law_retrieval.yaml

  data/
    public_test.json
    private_test.json
    law_corpus.json
    processed_law_corpus.jsonl

  cache/
    case_api_cache.jsonl
    law_index/
    embeddings/

  logs/
    retrieval_logs.jsonl
    prediction_logs.jsonl
    validation_report.json

  src/
    input_loader.py
    query_parser.py
    query_planner.py
    case_api_client.py
    evidence_store.py
    law_retriever.py
    outcome_predictor.py
    evidence_selector.py
    submission_builder.py
    validator.py

  scripts/
    build_law_index.py
    run_public.py
    run_private.py
    validate_submission.py
    analyze_errors.py

  outputs/
    public_submission.json
    private_submission.json
```

---

## 9. Suggested CLI commands

Codex should implement scripts that support at least these commands:

```bash
# Build law corpus index
python scripts/build_law_index.py \
  --law-corpus data/law_corpus.json \
  --output-dir cache/law_index

# Run on public/private-like input
python scripts/run_public.py \
  --input data/public_test.json \
  --law-corpus data/law_corpus.json \
  --output outputs/public_submission.json \
  --config configs/config.yaml

# Run on private input
python scripts/run_private.py \
  --input data/private_test.json \
  --law-corpus data/law_corpus.json \
  --output outputs/private_submission.json \
  --config configs/config.yaml

# Validate submission
python scripts/validate_submission.py \
  --input data/private_test.json \
  --submission outputs/private_submission.json \
  --law-corpus data/law_corpus.json
```

---

## 10. Configuration requirements

`configs/config.yaml` should include:

```yaml
api:
  base_url: "https://alqac-api.ngrok.pro"
  endpoint: "/retrieve"
  api_key_env: "ALQAC_TOKEN"
  min_interval_seconds: 5
  timeout_seconds: 30
  max_retries: 5

retrieval:
  queries_per_case: 12
  adaptive_queries: true
  max_case_evidence: 8

law_retrieval:
  method: "bm25"
  top_k: 6

prediction:
  labels: ["A_WIN", "B_WIN"]
  use_rule_override: true
  use_llm_reasoner: false
  model_name: null

paths:
  cache_dir: "cache"
  logs_dir: "logs"
```

Do not hard-code API keys. Read them from environment variables.

---

## 11. Logging requirements

For each case, save a structured log like:

```json
{
  "case_id": "case_1087_0037",
  "case_query": "...",
  "parsed": {
    "plaintiff": "...",
    "defendant": "...",
    "legal_relation": "...",
    "plaintiff_claim": "..."
  },
  "queries": ["..."],
  "retrieved_segments": [
    {
      "query": "...",
      "chunk_id": "case_1087_0037_chunk_2",
      "score": 0.886,
      "text": "..."
    }
  ],
  "selected_case_evidence": ["case_1087_0037_chunk_2"],
  "law_evidence": [
    {"law_id": "91/2015/QH13", "aid": 117}
  ],
  "prediction": "A_WIN",
  "confidence": 0.74,
  "reasoning_summary": "...",
  "api_call_count": 12
}
```

These logs are needed for debugging, leaderboard error analysis, and technical report preparation.

---

## 12. Implementation phases

### Phase A — End-to-end MVP

Goal: produce a valid `submission.json`.

Tasks:

1. Implement input loader.
2. Implement Retrieval API client with cache and rate limit.
3. Implement fixed query planner.
4. Implement evidence deduplication.
5. Implement BM25 law retriever.
6. Implement simple rule-based outcome predictor.
7. Implement submission builder.
8. Implement validator.

### Phase B — Improve case retrieval

Goal: retrieve decision/reasoning chunks more often.

Tasks:

1. Add dispute-type detection.
2. Add adaptive query generation.
3. Add query templates targeting final decision and court reasoning.
4. Add evidence utility ranking.
5. Tune query budget per case.

### Phase C — Improve outcome prediction

Goal: maximize the 70% outcome score.

Tasks:

1. Add final-decision phrase detector.
2. Add court-reasoning phrase detector.
3. Add main-claim extraction.
4. Add binary mapping for partial decisions.
5. Optionally add an allowed open-weight local reasoner.
6. Add confidence and conflict resolution.

### Phase D — Improve law evidence retrieval

Goal: improve 10% law micro-F1.

Tasks:

1. Improve law corpus preprocessing.
2. Add dense retrieval if feasible.
3. Add reranking.
4. Remove generic/irrelevant law provisions.
5. Tune `top_k` for law evidence.

### Phase E — Final private run

Goal: stable private-test submission.

Tasks:

1. Freeze config.
2. Freeze query budget.
3. Run private input once with logs.
4. Validate output.
5. Submit `submission.json`.
6. Archive code, config, logs, and report material.

---

## 13. Key risks and mitigations

### Risk 1 — Retrieval returns only fact segments, not decision/reasoning

Mitigation: Always include decision/reasoning queries:

```text
"Hội đồng xét xử nhận định"
"Xét thấy"
"Quyết định"
"Tuyên xử"
"Chấp nhận yêu cầu"
"Không chấp nhận yêu cầu"
```

### Risk 2 — Predictor guesses from `case_query` only

Mitigation: Predictor must use retrieved evidence. If no decision/reasoning segment is found, use fallback retrieval queries before final prediction.

### Risk 3 — Too many irrelevant law provisions

Mitigation: Keep law evidence compact, usually 3–8 provisions per case. Prioritize provisions directly linked to the legal issue and retrieved reasoning.

### Risk 4 — Excessive API calls

Mitigation: Use fixed budget, adaptive stopping, cache, and deduplication. Stop early if decision and reasoning chunks are already retrieved.

### Risk 5 — Invalid submission schema

Mitigation: Run validator before every submission. Never submit partial labels or ambiguous law-evidence formats.

---

## 14. Acceptance criteria for Codex implementation

The implementation is acceptable when:

1. It can read a private-test-like JSON file containing only `case_id` and `case_query`.
2. It can query the Retrieval API using `X-API-Key` from an environment variable.
3. It respects the 1 request / 5 seconds rate limit.
4. It caches API responses.
5. It records `chunk_id` values into `case_evidence`.
6. It builds law evidence as `{law_id, aid}` objects.
7. It predicts only `A_WIN` or `B_WIN`.
8. It creates a valid `submission.json` list with one object per case.
9. It validates the submission before writing final output.
10. It logs retrieval, prediction, evidence selection, and API call counts per case.

---

## 15. Minimal final output example

```json
[
  {
    "case_id": "case_1087_0037",
    "prediction": "A_WIN",
    "case_evidence": [
      "case_1087_0037_chunk_2",
      "case_1087_0037_chunk_5"
    ],
    "law_evidence": [
      {
        "law_id": "91/2015/QH13",
        "aid": 117
      }
    ]
  },
  {
    "case_id": "case_1087_0041",
    "prediction": "B_WIN",
    "case_evidence": [
      "case_1087_0041_chunk_3"
    ],
    "law_evidence": [
      {
        "law_id": "91/2015/QH13",
        "aid": 357
      }
    ]
  }
]
```

