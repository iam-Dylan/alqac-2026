# EEDI-Inspired ALQAC V2 Notes

This is a separate design note. It does not replace the current ALQAC pipeline.

## Goal

Create an optional V2 pipeline inspired by `report-eedi.ipynb`:

1. Keep the current rule-only / hybrid system intact.
2. Add a candidate-first reranking layer.
3. Prevent the LLM from generating free-form evidence IDs or labels.
4. Use the LLM only to choose from closed candidate lists.

The main expected benefit is better `case_evidence` and `law_evidence` selection, especially because current score issues are more evidence-selection related than pure outcome-classification related.

## Key Idea From EEDI

The EEDI notebook uses two stages:

1. First retrieval:
   - create detailed query text;
   - embed query and documents;
   - rank candidates by vector similarity;
   - keep top-K candidates.

2. Second retrieval / rerank:
   - present a small numbered candidate list to a large LLM;
   - force the model to choose only `1..9`;
   - run a tournament over candidate groups;
   - put the final survivor first, then keep the remaining retrieval order.

For ALQAC, the equivalent is:

1. Retrieval API + law retriever create candidate chunks/provisions.
2. LLM/rule reranker chooses the strongest candidate from a closed list.
3. Submission uses only candidate IDs/strings that already exist.

## V2 Layer Design

### Layer 1: Candidate Generation

Use current components without changing their public behavior:

- `query_planner.py` creates 20+ query variants.
- Retrieval API returns case chunks.
- `law_retriever.py` returns law candidates.
- `evidence_store.py` deduplicates and gives utility roles.

Candidate pools:

- `case_candidates`: deduped retrieved chunks, ideally 20-40 per case when available.
- `law_candidates`: top 20-30 law provisions before final trimming.

### Layer 2: Case Evidence Tournament Reranker

Create a new optional module, not replacing the existing selector:

```text
src/llm_evidence_reranker.py
```

Suggested functions:

```python
rerank_case_evidence_tournament(case_query, segments, model, group_size=8, target_role="decision")
rerank_law_evidence_tournament(case_query, law_hits, model, group_size=8)
```

Run separate tournaments for roles:

- `decision`: chunks containing `Quyết định`, `Tuyên xử`, `Chấp nhận`, `Không chấp nhận`, `Bác yêu cầu`.
- `reasoning`: chunks containing `Hội đồng xét xử nhận định`, `Xét thấy`, `Có căn cứ`, `Không có căn cứ`.
- `claim_or_defense`: chunks explaining plaintiff claim / defendant defense.

Final `case_evidence` order:

1. best decision chunks;
2. best reasoning chunks;
3. best claim/defense chunks;
4. remaining high-utility chunks from current selector.

This keeps recall-first behavior while putting high-value evidence first.

### Layer 3: Closed-Choice Outcome

Instead of free-form JSON-only reasoning, add an optional closed-choice mode:

```text
1. A_WIN
2. B_WIN
```

Prompt:

```text
Bạn là trợ lý pháp lý.
Chỉ dựa trên case_query và candidate evidence đã cho.
Nếu yêu cầu chính của nguyên đơn được chấp nhận toàn bộ hoặc một phần đáng kể, chọn 1.
Nếu yêu cầu chính bị bác/không có căn cứ, chọn 2.
Chỉ trả lời đúng một ký tự: 1 hoặc 2.
```

Then map:

- `1 -> A_WIN`
- `2 -> B_WIN`

In vLLM/Kaggle, this can use a logits processor similar to EEDI.
In plain `transformers`, approximate with `max_new_tokens=1` and strict parsing.

### Layer 4: Law Evidence Rerank

Use the same numbered-list pattern:

```text
Case query: ...
Candidate laws:
1. Bộ luật Dân sự 2015 | Điều 584
2. Bộ luật Dân sự 2015 | Điều 585
...
Chọn các điều luật liên quan trực tiếp nhất.
```

For a constrained single-choice tournament:

1. Split candidates into groups of 8 + survivor.
2. Ask LLM to pick one best law each round.
3. Repeat for multiple survivors if wanting top 3-6.

Important: never let the model invent law strings. It may only choose from candidate list.

## V2 Files To Add Later

Keep V2 isolated under new files:

```text
configs/eedi_v2_config.yaml
src/llm_choice.py
src/llm_evidence_reranker.py
scripts/run_eedi_v2_public.py
scripts/run_eedi_v2_private.py
notebooks/alqac_kaggle_eedi_v2_runner.ipynb
```

Do not modify these current files for the first experiment:

```text
src/pipeline.py
src/evidence_selector.py
notebooks/alqac_kaggle_model_runner.ipynb
configs/config.yaml
```

If V2 proves useful, integrate later behind config flags.

## Minimal Experiment

Start with case evidence only.

Input:

- existing `retrieval_logs.jsonl`
- existing `outputs/public_submission.json` or a fresh rule-only run

Experiment script:

```text
scripts/rerank_case_evidence_eedi_v2.py
```

Output:

```text
outputs/eedi_v2_public_submission.json
logs/eedi_v2_rerank_logs.jsonl
```

Evaluation:

```bash
python3 scripts/evaluate_public.py \
  --input data/ALQAC2026_public_test.json \
  --submission outputs/eedi_v2_public_submission.json

python3 scripts/evaluate_case_recall.py \
  --input data/ALQAC2026_public_test.json \
  --submission outputs/eedi_v2_public_submission.json \
  --retrieval-log logs/retrieval_logs.jsonl \
  --cache cache/case_api_cache.jsonl
```

Public file still has no official gold case chunk IDs, so recall is only a proxy locally.
The real test is leaderboard Penalized Case Recall.

## Recommended Implementation Order

1. Add `src/llm_choice.py`:
   - wrapper for numbered-choice prompts;
   - supports plain `transformers` first;
   - optional vLLM backend later.

2. Add `src/llm_evidence_reranker.py`:
   - tournament logic;
   - role-specific prompts;
   - deterministic fallback to current utility score.

3. Add `scripts/rerank_case_evidence_eedi_v2.py`:
   - reads previous logs/submission;
   - writes a new submission file;
   - never overwrites existing outputs.

4. Add Kaggle V2 notebook:
   - separate notebook file;
   - optional vLLM / AWQ model;
   - no dependency conflict with current runner.

## Risks

- LLM rerank can hurt if retrieval candidates do not contain the gold chunk.
- If prompt is too long, candidate text truncation may hide the key sentence.
- vLLM/AWQ dependency setup can be fragile on Kaggle.
- Tournament optimizes top-1 candidate; official metric may want several evidence chunks.

## Guardrails

- Keep recall-first: final evidence should include LLM winners plus remaining high-score chunks.
- Never ask LLM to generate chunk IDs or law strings.
- Keep rule predictor as fallback for outcome.
- Log every candidate list and chosen number for debugging.
- Write all V2 outputs to `outputs/eedi_v2_*.json`, never current `outputs/public_submission.json` or `outputs/kaggle_submission.json`.

