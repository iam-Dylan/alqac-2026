# Kaggle Setup

This project is intended to run heavyweight local open-weight models on Kaggle, not on a laptop.

## Recommended Workflow

1. Push code to GitHub:

```bash
git add .
git commit -m "Add Kaggle model runner"
git push
```

2. In Kaggle, create a new Notebook.
3. In Notebook settings:
   - Accelerator: `GPU T4 x2` or better.
   - Internet: `On`, unless you attach the model as a Kaggle Dataset.
4. Add Kaggle Secret:
   - Name: `ALQAC_API_KEY`
   - Value: your ALQAC token.
5. Attach data as Kaggle Dataset if needed:
   - `ALQAC2026_public_test.json`
   - `private_test.json`
   - `corpus_law_pub.json`
6. Use `notebooks/alqac_kaggle_model_runner.ipynb`.

## GitHub Link Options

Simplest and most reproducible:

```python
!git clone https://github.com/iam-Dylan/alqac-2026.git /kaggle/working/alqac-2026
```

If the repo is private, create a Kaggle Secret named `GITHUB_TOKEN`, then clone with:

```python
!git clone https://$GITHUB_TOKEN@github.com/iam-Dylan/alqac-2026.git /kaggle/working/alqac-2026
```

Do not commit `.env` or hard-code secrets in notebooks.

## Model Choice

Default notebook model:

```text
Qwen/Qwen2.5-7B-Instruct
```

Fallback for smaller GPU:

```text
Qwen/Qwen2.5-3B-Instruct
```

Both are intended to be loaded locally with `transformers`; do not use closed model APIs.

## Outcome Guardrail

The notebook can enable `USE_MODEL_REASONER=True`, but the model is not allowed to blindly override the rule predictor. The pipeline now uses a conservative arbiter:

- if rule and model agree, keep that label;
- if they conflict, keep the rule when rule confidence is strong;
- allow model override only when the rule is weak and model confidence is high.

Check `logs/prediction_logs.jsonl` after a run. The `prediction_source` field shows whether the final label came from `rule`, `rule_model_agree`, or `model_override_weak_rule`.

For public debugging, run:

```bash
python3 scripts/diagnose_outcome.py \
  --input data/ALQAC2026_public_test.json \
  --submission outputs/public_submission.json \
  --logs logs/prediction_logs.jsonl
```

This reports `model_only`, `rule_only`, and final submission accuracy when the updated logs contain `model_prediction`. It also flags wrong cases where retrieved snippets miss decision markers such as `Tuyên xử` or `Quyết định`.

## Dependency Note

Kaggle images already include PyTorch/CUDA/RAPIDS packages. Do not upgrade CUDA, `numba`, `cudf`, `cuml`, or `dask-cuda` inside the notebook. The provided notebook installs only missing lightweight Hugging Face packages with `--no-deps` to avoid dependency resolver conflicts such as `cuda-core` or `numba-cuda` mismatches.

## Optional BGE-M3 Law Retrieval

The default law retriever remains BM25. To test BGE-M3 hybrid retrieval, set:

```yaml
law_retrieval:
  method: "bm25_bge_m3"
  embedding_model_name: "BAAI/bge-m3"
  dense_fallback_to_bm25: true
```

This optional path requires `FlagEmbedding` and the BGE-M3 model files to be available in the Kaggle environment. If they are unavailable and `dense_fallback_to_bm25` is true, the pipeline falls back to BM25.

## Optional Qwen LoRA Domain Adaptation

The prepared fine-tune corpus is unlabeled legal text for domain-adaptive LoRA training, not supervised outcome labels:

```bash
python scripts/build_finetune_corpus.py \
  --law-corpus data/corpus_law_pub.json \
  --external-manifest data/external_raw/manifest.jsonl \
  --output data/finetune/domain_adaptation.jsonl

python scripts/train_qwen_lora_domain.py \
  --train-file data/finetune/domain_adaptation.jsonl \
  --output-dir outputs/adapters/qwen2_5_legal_dapt_lora \
  --load-in-4bit \
  --max-steps 200
```

After training, set `prediction.adapter_path` to the adapter directory in the run config to load it during inference.

The Kaggle notebook now loads the prepared fine-tune file from `data/finetune/domain_adaptation.jsonl`; it does not crawl external sources during the Kaggle run. When `TRAIN_QWEN_LORA = True` in the first settings cell, it runs this flow:

1. verify `data/finetune/domain_adaptation.jsonl` exists;
2. train a Qwen LoRA adapter;
3. write config with `adapter_path`;
4. run the ALQAC pipeline and validate/evaluate.

For a faster inference-only run, set `TRAIN_QWEN_LORA = False`.
