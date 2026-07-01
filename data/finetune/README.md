# Fine-Tune Data Staging

This directory is for derived training/evaluation files only.

Allowed by default:

- `domain_adaptation.jsonl`: unlabeled Vietnamese legal text chunks from the official law corpus and compliant external raw legal sources.

Not allowed by default:

- Externally labeled legal QA datasets.
- Externally labeled legal entailment datasets.
- Externally outcome-labeled case datasets.

Use unlabeled data for domain-adaptive pretraining or retrieval/reranking experiments. Do not treat it as supervised `A_WIN`/`B_WIN` outcome data.
