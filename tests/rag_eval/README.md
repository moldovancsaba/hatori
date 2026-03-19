# RAG retrieval eval (#350 Phase 1)

Small **retrieval** regression suite: ingest fixtures, run `hatori search` (same path as `search_runtime`), assert the expected artefact or PKS row appears in the top‑k merged results.

## Metrics

- **recall@k** (per case): `1` if the expected `artefact_id` or `pks:{uuid}` appears in the first `k` results, else `0`.
- **MRR** (per case): `1/rank` of the first relevant hit, else `0`.
- Summary lines print **mean** recall and MRR across cases.

## Cases

Defined in [`cases.json`](cases.json). Fields:

| Field | Meaning |
|--------|--------|
| `id` | Stable case id for logs |
| `ingest` | Repo-relative paths passed to `hatori ingest` (in order) |
| `query` | Search query string |
| `expect_uri_contains` | Fragment matched against `artefacts.uri` (absolute path) to resolve expected artefact |
| `k` | `--limit` for search and recall cutoff |
| `pks` | Optional: insert one Approved PKS row before search (`module`, `title`, `body`, `status`) |

## When it runs

- **`make test`:** After `db_reset` + lock/self_test/`dod_gate`, **before** `tests/golden/run_golden.py`, so the DB only contains seed PKS + eval ingests (no golden pollution).

## Run manually

```bash
make reset   # recommended
. .venv/bin/activate
python tests/rag_eval/run_rag_eval.py
```

Or:

```bash
make rag-eval   # does not reset; use on a DB you prepared
```

## Optional rerank (Phase 3)

Compare metrics with default merge vs lexical rerank:

```bash
make reset && . .venv/bin/activate && python tests/rag_eval/run_rag_eval.py
HATORI_RERANK_MODE=lexical make reset && . .venv/bin/activate && python tests/rag_eval/run_rag_eval.py
```

See [RAG-rerank-phase3.md](../../docs/06-evaluation/RAG-rerank-phase3.md).

## Adding cases

1. Add or reuse a fixture under `tests/rag_eval/fixtures/` or `tests/golden/fixtures/`.
2. Append an object to `cases.json` with a unique query or marker.
3. Run `python tests/rag_eval/run_rag_eval.py` after `make reset`.

## References

- Roadmap: [RAG-phased-roadmap-D5.md](../../docs/06-evaluation/RAG-phased-roadmap-D5.md) Phase 1
- Retrieval implementation: `hatori/cli.py` — `search_runtime`, `merge_rank_results`
