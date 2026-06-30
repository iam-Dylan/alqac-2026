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

## Dependency Note

Kaggle images already include PyTorch/CUDA/RAPIDS packages. Do not upgrade CUDA, `numba`, `cudf`, `cuml`, or `dask-cuda` inside the notebook. The provided notebook installs only missing lightweight Hugging Face packages with `--no-deps` to avoid dependency resolver conflicts such as `cuda-core` or `numba-cuda` mismatches.
