# ADR-0001: Initial Local OSS Stack

## Status
Accepted

## Context
Requirements:
- fully local and offline-capable
- open-source only
- durable storage, portable exports
- LLM swappable
- vector search + structured PKS
- minimal moving parts

## Decision
Use:
- Model runtime: llama.cpp (GGUF)
- Orchestration: LangGraph
- Storage: PostgreSQL + pgvector
- Local indexing: chunk+embed documents into Postgres; store embeddings in pgvector
- Optional UI: separate layer; not the truth store

## Consequences
- Slightly more setup than an all-in-one app, but more durable and testable.
- Single DB reduces operational complexity and improves auditability.
- Model swaps should not affect PKS.
