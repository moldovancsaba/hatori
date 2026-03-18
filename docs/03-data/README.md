# Data and PKS schema

PKS (Personal Knowledge System) schema and migrations live in the repo root:

- **Schema and migrations:** `pks/migrations/`
  - `0001_init.sql` — core tables (pks_records, artefacts, interaction_events, learning_events, audit_events, embeddings)
  - `0002_delivery_events.sql` — delivery_events for outcome feedback

Overview of runtime data and PKS modules (A–J) is in `docs/00-overview/README.md` and `docs/01-charters/hatori-charter-v3.md`.

Target implementation contracts (PKS as a formal module) are in `docs/10-api-contracts/interfaces.md`; current implementation uses direct DB access and CLI/UI/API.
