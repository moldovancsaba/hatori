# Task Prompt Template (Injected per request)

```text
Connectivity: {OFFLINE|ONLINE-UNVERIFIED|ONLINE-VERIFIED}
Time: <timestamp>
Active Project: <name or NONE>

User request:
<text>

Retrieved PKS (relevant only, with provenance/status):
- ...

Local evidence snippets (with artefact IDs):
- ...

Required behaviour:
- Follow Charter v3.
- State assumptions.
- Cite provenance for PKS and local artefacts.
- If proposing memory changes, output a Memory Patch.
```