# Memory Patch Format

Use this exact structure whenever the agent proposes or performs writes to PKS modules A–H.

```text
MEMORY PATCH
- Action: {create|update|approve|deprecate|contest|redact}
- Target module: {A..H}
- Record ID: {uuid or NEW}
- Fields:
  - title:
  - body:
  - status: {Pending|Approved|Deprecated|Contested}
  - provenance: {User|LocalDoc|Web|Tool|Inference}
  - confidence: {High|Medium|Low}
  - scope:
  - sensitivity:
  - refresh_cadence: {None|7d|30d|90d|Custom}
  - source_refs: [...]
- Rationale: why this is allowed under governance rules
- Conflicts (if any): links to conflicting record IDs
```