# Builder Task Prompt Template

```text
TASK:
Implement: <feature>.

Context:
- Repo: reply-hatori
- Current stack: Docker Postgres (pgvector), CLI (hatori/cli.py), UI (ui/app.py), scripts in tools/scripts, Makefile targets.

Acceptance criteria:
1) ...
2) ...
3) ...

Constraints:
- Offline-first, OSS only.
- Must not break: make reset, make test, make run-ui.

Deliverables:
- Files changed: ...
- Commands to verify: ...
- Any new Make targets: ...

Output format:
- Plan (brief)
- Commands (small copy/paste chunks)
- Patch summary (files + key diffs)
- Verification steps
```