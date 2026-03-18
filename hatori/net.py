"""
Connectivity status — implementation of docs/10-api-contracts/interfaces.md.
NET.status() -> {OFFLINE, ONLINE-UNVERIFIED, ONLINE-VERIFIED}.
"""
import os


def status() -> str:
    """Return current connectivity state. Orchestrator branches behaviour accordingly."""
    explicit = os.environ.get("HATORI_CONNECTIVITY_STATE", "").strip().upper()
    if explicit in {"OFFLINE", "ONLINE-UNVERIFIED", "ONLINE-VERIFIED"}:
        return explicit
    if os.environ.get("HATORI_ENABLE_ONLINE_VERIFIED", "").strip() == "1":
        return "ONLINE-VERIFIED"
    if os.environ.get("HATORI_ENABLE_ONLINE", "").strip() == "1":
        return "ONLINE-UNVERIFIED"
    return "OFFLINE"
