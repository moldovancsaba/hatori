# RAG — Phase 3 optional rerank (#350)

**Issue:** [mvp-factory-control#350](https://github.com/moldovancsaba/mvp-factory-control/issues/350).  
**Placement:** After `merge_rank_results()` in `hatori/cli.py` (`search_runtime`, `ask_runtime`).  
**Default:** **Off** — no behaviour change unless env is set.

## Modes

| `HATORI_RERANK_MODE` | Behaviour |
|----------------------|-----------|
| unset / `off` / `none` / `0` / `false` | Pass-through (same order as merged retrieval scores). |
| `lexical` | Re-rank merged candidates by `W * token_overlap(query, title+excerpt) + original_score` (`W` = `HATORI_RERANK_LEXICAL_WEIGHT`, default `3.0`). |

No extra ML models or network calls — suitable for local-first and CI.

## Env vars

- **`HATORI_RERANK_MODE`** — `off` (default) or `lexical`.
- **`HATORI_RERANK_LEXICAL_WEIGHT`** — multiplier for overlap term (default `3.0`). Increase to favour lexical match over raw retrieval score.

## Eval / regression

- **`make test`:** Golden `test_113`–`test_115` cover default path, lexical reordering on synthetic rows, and CLI search with `lexical` enabled.
- **RAG eval:** Run `make reset && python tests/rag_eval/run_rag_eval.py` with and without `HATORI_RERANK_MODE=lexical` to compare mean recall@k (optional manual A/B).

## Future

Cross-encoder or small local reranker can plug in as an additional mode when PO approves new dependencies; keep default `off`.

## References

- Roadmap: [RAG-phased-roadmap-D5.md](RAG-phased-roadmap-D5.md) §4  
- Retrieval merge: `hatori/cli.py` — `merge_rank_results`, `rerank_merged_results`
