"""Strict geographical and event relevance scoring for YouTube candidates."""
from __future__ import annotations
import re
from .constants import BRAZIL_STATES, EVENT_TERMS, IMPACT_TERMS, NEGATIVE_TERMS, REGIONAL_ALIASES
from .text import has_cjk, normalize

def _uf_token_present(raw: str, uf: str) -> bool:
    uf = (uf or "").upper().strip()
    return bool(len(uf) == 2 and re.search(rf"(?<![A-Za-zÀ-ÿ0-9]){re.escape(uf)}(?![A-Za-zÀ-ÿ0-9])", raw))

def _event_family(evento: str) -> str:
    return next((k for k in EVENT_TERMS if k != "default" and k.lower() in (evento or "").lower()), "default")

def score_video(video: dict, alert: dict, config: dict) -> dict:
    title, desc = video.get("title", ""), video.get("description_snippet", "")
    raw, text = f"{title} {desc}", normalize(f"{title} {desc}")
    municipio, uf, evento = normalize(alert.get("municipio", "")), (alert.get("uf") or "").upper(), alert.get("evento", "")
    if has_cjk(title): return _reject("cjk_script", "cjk_reject")
    for term in NEGATIVE_TERMS:
        if normalize(term) in text: return _reject(f"negative_term:{term}", "negative")

    state_name = BRAZIL_STATES.get(uf, "")
    muni_hit = bool(municipio) and len(municipio) >= 4 and municipio in text
    state_hit = bool(state_name and normalize(state_name) in text)
    uf_hit = _uf_token_present(raw, uf)
    aliases = sum(1 for alias in REGIONAL_ALIASES.get(uf, []) if normalize(alias) in text)
    aliases = min(aliases, 3)
    reasons, geo_score, match_type = [], 0.0, "none"

    # Direct municipal evidence requires municipality + explicit UF/state co-evidence.
    if muni_hit and (state_hit or uf_hit):
        geo_score, match_type = 5.0, "municipality_direct"
        reasons.append("municipality+state")
    elif state_hit:
        geo_score, match_type = 3.0, "state_level"
        reasons.append("state_name")
    elif uf_hit:
        geo_score, match_type = 1.5, "state_level"
        reasons.append("uf_token")
    elif muni_hit:
        reasons.append("municipality_without_state_ignored")
    if aliases and match_type != "municipality_direct":
        geo_score += aliases
        match_type = "regional_alias" if match_type == "none" else match_type
        reasons.append(f"alias×{aliases}")

    other_states = [state for code, state in BRAZIL_STATES.items() if code != uf and normalize(state) in text]
    if other_states and match_type != "municipality_direct":
        geo_score = max(0.0, geo_score - 2.0)
        reasons.append(f"cross_state_penalty:{other_states[0]}")
    if not config.get("ALLOW_STATE_LEVEL_MATCHES", True) and match_type != "municipality_direct":
        geo_score = 0.0

    family = _event_family(evento)
    primary = EVENT_TERMS[family]
    cross = [t for key, terms in EVENT_TERMS.items() if key not in (family, "default") for t in terms]
    primary_hits = [term for term in primary if normalize(term) in text]
    impact_hits = [term for term in IMPACT_TERMS if normalize(term) in text]
    event_score = min(5.0, 1.5 * len(primary_hits)) + min(3.0, sum(normalize(t) in text for t in cross)) + min(2.25, .75 * len(impact_hits))
    if primary_hits: reasons.append("event_terms:" + ",".join(primary_hits[:5]))
    if impact_hits: reasons.append("impact:" + ",".join(impact_hits[:3]))
    if primary_hits and not impact_hits and match_type != "municipality_direct":
        event_score *= .4
        reasons.append("penalty:no_impact_and_no_direct_geo")

    total = geo_score + event_score
    relevant = geo_score >= config["MIN_GEO_SCORE"] and event_score >= config["MIN_EVENT_SCORE"] and total >= config["MIN_RELEVANCE_SCORE"]
    reject = []
    if geo_score < config["MIN_GEO_SCORE"]: reject.append(f"geo={geo_score:.1f}<{config['MIN_GEO_SCORE']}")
    if event_score < config["MIN_EVENT_SCORE"]: reject.append(f"event={event_score:.1f}<{config['MIN_EVENT_SCORE']}")
    if total < config["MIN_RELEVANCE_SCORE"]: reject.append(f"total={total:.1f}<{config['MIN_RELEVANCE_SCORE']}")
    return {"is_relevant": relevant, "relevance_score": round(total,2), "geo_score": round(geo_score,2), "event_score": round(event_score,2), "geo_match_type": match_type, "link_scope": "municipality_direct" if match_type == "municipality_direct" else "broader_than_municipality", "is_municipal_evidence": match_type == "municipality_direct", "relevance_reasons": ";".join(reasons), "rejection_reason": ";".join(reject)}

def _reject(reason: str, match_type: str) -> dict:
    return {"is_relevant": False, "relevance_score": 0.0, "geo_score": 0.0, "event_score": 0.0, "geo_match_type": match_type, "link_scope": "none", "is_municipal_evidence": False, "relevance_reasons": "", "rejection_reason": reason}
