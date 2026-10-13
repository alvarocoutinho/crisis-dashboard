"""Strict geographical and event relevance scoring for YouTube candidates."""
from __future__ import annotations
import re
from .constants import BRAZIL_STATES, EVENT_TERMS, IMPACT_TERMS, NEGATIVE_TERMS, REGIONAL_ALIASES
from .text import has_cjk, normalize

def _uf_token_present(raw: str, uf: str) -> bool:
    uf = (uf or "").upper().strip()
    return bool(len(uf) == 2 and re.search(rf"(?<![A-Za-zÀ-ÿ0-9]){re.escape(uf)}(?![A-Za-zÀ-ÿ0-9])", raw))

def _has_phrase(text: str, phrase: str) -> bool:
    """Frase normalizada como palavra inteira ("para" não casa com "parada")."""
    return bool(phrase) and re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None

def _state_present(uf: str, raw: str, text: str) -> bool:
    """O texto nomeia o estado `uf`? (v0.3.2)

    Até a v0.3.1 a busca era por substring do nome normalizado. Para o Pará
    isso é "para", a preposição: quase todo título em português "citava o
    Pará", o que disparava cross_state_penalty em vídeos de RS, SP, SC... e
    "Paraná"/"Paraíba" também continham "para". Agora: palavra inteira, e o
    Pará só com acento ("Pará") ou "estado do Pará". "Mato Grosso" não casa
    dentro de "Mato Grosso do Sul".
    """
    name = normalize(BRAZIL_STATES.get(uf, ""))
    if not name:
        return False
    if uf == "PA":
        return bool(re.search(r"(?<![a-zà-ÿ0-9])pará(?![a-zà-ÿ0-9])", raw.lower())) or _has_phrase(text, "estado do para")
    if uf == "MT":
        return re.search(r"(?<![a-z0-9])mato grosso(?! do sul)(?![a-z0-9])", text) is not None
    return _has_phrase(text, name)

def _regional_alias_hits(uf: str, text: str, municipio: str) -> list[str]:
    """Aliases regionais presentes, cada lugar contado uma vez (v0.3.2).

    Antes, "sao paulo" e "são paulo" (a mesma string depois de normalizar)
    contavam duas vezes, e ainda somavam com o nome do estado: "Grande São
    Paulo" dava geo 6,0, acima de um vídeo que nomeia o município (5,0).
    Agora: aliases deduplicados após normalizar; o nome do estado (e, em SP
    e RJ, da capital homônima) não é alias, porque já conta como state_name;
    o município do alerta não é alias; um alias contido em outro que também
    casou ("recife" em "grande recife") não conta de novo.
    """
    state_name = normalize(BRAZIL_STATES.get(uf, ""))
    aliases = {normalize(a) for a in REGIONAL_ALIASES.get(uf, [])} - {state_name, municipio, ""}
    hits = sorted(a for a in aliases if _has_phrase(text, a))
    return [a for a in hits if not any(a != b and a in b for b in hits)]

def _event_family(evento: str) -> str:
    return next((k for k in EVENT_TERMS if k != "default" and k.lower() in (evento or "").lower()), "default")

def score_video(video: dict, alert: dict, config: dict) -> dict:
    title, desc = video.get("title", ""), video.get("description_snippet", "")
    raw, text = f"{title} {desc}", normalize(f"{title} {desc}")
    municipio, uf, evento = normalize(alert.get("municipio", "")), (alert.get("uf") or "").upper(), alert.get("evento", "")
    if has_cjk(title): return _reject("cjk_script", "cjk_reject")
    for term in NEGATIVE_TERMS:
        if normalize(term) in text: return _reject(f"negative_term:{term}", "negative")

    muni_hit = bool(municipio) and len(municipio) >= 4 and _has_phrase(text, municipio)
    state_hit = _state_present(uf, raw, text)
    uf_hit = _uf_token_present(raw, uf)
    aliases = min(len(_regional_alias_hits(uf, text, municipio)), 3)
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

    other_states = [state for code, state in BRAZIL_STATES.items() if code != uf and _state_present(code, raw, text)]
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
