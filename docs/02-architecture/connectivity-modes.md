# Connectivity Modes

Hatori must always operate in one of:
- OFFLINE
- ONLINE-UNVERIFIED
- ONLINE-VERIFIED

## OFFLINE
- Only local PKS + local artefacts + local indexes.
- No third-party factual assertions requiring verification.
- Output must mark external items: "Not verified (offline)" and provide verification plan.

## ONLINE-UNVERIFIED
- Internet available, but sources not yet retrieved/validated.
- External claims labelled "Unverified" until sources exist.

## ONLINE-VERIFIED
- Sources retrieved and cited.
- Material claims cross-checked when feasible.

## Automatic degradation
If any network/tool dependency fails -> immediately switch to OFFLINE and continue.
