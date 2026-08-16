"""CEMADEN alert retrieval and scope filtering."""
from __future__ import annotations
import requests
from .constants import CEMADEN_ALERTS_URL
_RANK = {"muito alto": 0, "alto": 1, "moderado": 2, "baixo": 3}

def fetch_raw_alerts(timeout: int=30) -> list[dict]:
    response = requests.get(CEMADEN_ALERTS_URL, timeout=timeout); response.raise_for_status()
    return response.json().get("alertas", []) or []

def fetch_alerts(config: dict) -> list[dict]:
    alerts = fetch_raw_alerts()
    ufs = set(config.get("FILTER_UF") or [])
    levels = {str(x).lower().strip() for x in config.get("FILTER_LEVELS") or []}
    events = [str(x).lower() for x in config.get("FILTER_EVENTS") or []]
    kept=[]
    for alert in alerts:
        if ufs and alert.get("uf") not in ufs: continue
        if levels and (alert.get("nivel") or "").lower().strip() not in levels: continue
        if events and not any(term in (alert.get("evento") or "").lower() for term in events): continue
        kept.append(alert)
    return sorted(kept, key=lambda a: _RANK.get((a.get("nivel") or "").lower().strip(), 9))

def is_high_priority(level: str|None) -> bool:
    return (level or "").lower().strip() in {"alto", "muito alto"}
