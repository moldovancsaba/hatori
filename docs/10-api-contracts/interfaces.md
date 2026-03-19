# Interfaces (Implementation Contracts)

**Status:** Implemented as discrete modules in `hatori/`: `hatori.pks`, `hatori.rag`, `hatori.net`, `hatori.eval`. CLI/UI/API may still call DB/helpers directly; new code should prefer the module APIs where applicable.

Canonical external API spec:
- See `docs/10-api-contracts/hatori-api-v1.md`

## PKS
- PKS.append_interaction(event) -> writes to module I (append-only)
- PKS.log_learning(signal) -> writes to module J
- PKS.write_pending(module, record) -> Pending entry in A–H
- PKS.approve(record_id) / PKS.deprecate(record_id) / PKS.redact(record_id)
- PKS.query(filters) -> returns records with provenance+confidence+status

## RAG
- RAG.index_document(path, metadata) -> chunk+embed+store
- RAG.search_local(query, k, filters) -> passages + provenance
- RAG.get_sources(source_ids) -> artefacts for citations

## Connectivity
- NET.status() -> {OFFLINE, ONLINE}
- Orchestrator branches behaviour accordingly.

## Evaluation
- EVAL.run_golden_tests(subset=None) -> pass/fail + reasons
- EVAL.run_rag_eval_suite() -> pass/fail + reasons (retrieval recall@k / MRR; `tests/rag_eval/`)

Assertions:
- no fabricated citations
- offline mode limits claims
- Memory Patch format compliance
- inference not promoted to fact
- feedback learning logged correctly
