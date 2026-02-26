# Versioning And Release Hygiene

This rule is mandatory for every completed engineering task.

## Required steps before declaring "done"

1) Update documentation
- Update all impacted docs/runbooks/prompts.

2) Update versioning artefacts
- Bump `VERSION` (SemVer).
- Add/update `CHANGELOG.md` with date, summary, and verification notes.

3) Commit and push
- Commit all related changes.
- Push to `origin/main`.

## Minimal command sequence

```bash
git add .
git commit -m "chore: <summary>"
git push origin main
```

## SemVer rule

- Patch (`x.y.Z`): docs, tests, bug fixes, non-breaking internal updates.
- Minor (`x.Y.z`): backward-compatible new features.
- Major (`X.y.z`): breaking changes.
