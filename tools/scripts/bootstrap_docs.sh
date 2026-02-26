#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

mkdir -p docs/{00-overview,01-charters,02-architecture,03-data,04-ops,05-security,06-evaluation,07-runbooks,08-decisions,09-prompts,10-api-contracts}
mkdir -p pks/{schemas,migrations,seed,examples}
mkdir -p logs/{audit,events}
mkdir -p tests/{golden,fixtures}
mkdir -p artefacts/{samples,imports,exports}

cat > docs/00-overview/README.md <<'MD'
# Hatori (Local, Offline-First Agent)

## Goal
Build a long-lived personal agent ("Hatori") that:
- runs fully locally and continues operating offline,
- uses only open-source components,
- maintains an auditable, modular PKS (Personal Knowledge System),
- is LLM-swappable without losing behaviour or memory,
- learns from explicit feedback and *softly* from implicit positive outcomes.

## Non-negotiables
- Truth > fluency (no fabricated facts/sources)
- Offline-first degradation (no crash; reduced claims)
- PKS governance (append-only logs + controlled promotion to facts/preferences)
- Audit trail + backups + portability
- Regression tests for behavioural stability

## Where things live
- Charter and prompts: `docs/01-charters/`, `docs/09-prompts/`
- Architecture decisions: `docs/02-architecture/`, ADRs in `docs/08-decisions/`
- PKS spec and schema: `docs/03-data/`, `pks/`
- Ops/runbooks: `docs/04-ops/`, `docs/07-runbooks/`
- Evaluation: `docs/06-evaluation/`, golden tests in `tests/golden/`
- Audit/event logs: `logs/audit/`, `logs/events/`
MD

