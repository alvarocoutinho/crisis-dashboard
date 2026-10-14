"""Leitura do feed Atom/CAP 1.2 da IDAP (Interface de Divulgação de Alertas Públicos).

Fonte: ``https://idapfile.mdr.gov.br/idap/api/rss/cap`` (endereço registrado na
OMM, WMO Register of Alerting Authorities; o guia operacional do Fórum SBTVD
cita também ``idapfile.mi.gov.br``). Cada ``<entry>`` traz um ``<alert>`` CAP 1.2
completo: identificador oficial, emissor, horários, evento, severidade, texto
enviado à população e área (polígonos e, às vezes, geocódigos IBGE).

Só biblioteca padrão: ``xml.etree`` não resolve entidades externas.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

ATOM = "{http://www.w3.org/2005/Atom}"
CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"
FEED_URLS = (
    "https://idapfile.mdr.gov.br/idap/api/rss/cap",
    "https://idapfile.mi.gov.br/idap/api/rss/cap",
)


def _t(node, name: str, ns: str = CAP) -> str:
    if node is None:
        return ""
    e = node.find(ns + name)
    return (e.text or "").strip() if e is not None else ""


def _all(node, name: str) -> list[str]:
    return [] if node is None else [(e.text or "").strip() for e in node.findall(CAP + name)]


def _pairs(node, name: str) -> list[dict]:
    return [] if node is None else [{"name": _t(e, "valueName"), "value": _t(e, "value")} for e in node.findall(CAP + name)]


def to_utc(iso: str) -> str:
    """ISO 8601 com fuso → UTC ``YYYY-MM-DDTHH:MM:SSZ`` ("" se inválido)."""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if dt.tzinfo is None:
        return ""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def id_number(identifier: str) -> int | None:
    """``"193759/2026"`` → 193759 (a numeração é sequencial: serve para achar lacunas)."""
    head = (identifier or "").split("/", 1)[0]
    return int(head) if head.isdigit() else None


def parse_alert(cap, *, atom_updated: str = "") -> dict | None:
    """Um ``<alert>`` CAP → dicionário plano (só a primeira ``<info>`` em pt-BR vira coluna;
    todas as áreas de todas as ``<info>`` são mantidas)."""
    identifier, sender, sent = _t(cap, "identifier"), _t(cap, "sender"), _t(cap, "sent")
    if not (identifier and sender and sent):
        return None
    infos = cap.findall(CAP + "info")
    info = next((i for i in infos if _t(i, "language").lower().startswith("pt")), infos[0] if infos else None)
    areas = []
    for inf in infos:
        for ar in inf.findall(CAP + "area"):
            areas.append({
                "area_desc": _t(ar, "areaDesc"),
                "polygons": [p for p in _all(ar, "polygon") if p],
                "circles": [c for c in _all(ar, "circle") if c],
                "geocodes": _pairs(ar, "geocode"),
            })
    ibge = sorted({g["value"] for a in areas for g in a["geocodes"] if g["name"].upper() == "IBGE" and g["value"]})
    return {
        "identifier": identifier,
        "id_num": id_number(identifier),
        "sender": sender,
        "sent": sent,
        "sent_utc": to_utc(sent),
        "status": _t(cap, "status"),
        "msg_type": _t(cap, "msgType"),
        "source": _t(cap, "source"),
        "scope": _t(cap, "scope"),
        "references": _t(cap, "references"),
        "incidents": _t(cap, "incidents"),
        "atom_updated": atom_updated,
        "language": _t(info, "language"),
        "category": " | ".join(_all(info, "category")),
        "event": _t(info, "event"),
        "response_type": " | ".join(_all(info, "responseType")),
        "urgency": _t(info, "urgency"),
        "severity": _t(info, "severity"),
        "certainty": _t(info, "certainty"),
        "effective": _t(info, "effective"),
        "onset": _t(info, "onset"),
        "onset_utc": to_utc(_t(info, "onset")),
        "expires": _t(info, "expires"),
        "expires_utc": to_utc(_t(info, "expires")),
        "sender_name": _t(info, "senderName"),
        "headline": _t(info, "headline"),
        "description": _t(info, "description"),
        "instruction": _t(info, "instruction"),
        "web": _t(info, "web"),
        "channels": " | ".join(p["value"] for p in _pairs(info, "parameter") if p["name"].upper() == "CHANNEL-LIST"),
        "area_desc": " ; ".join(a["area_desc"] for a in areas if a["area_desc"]),
        "ibge": ibge,
        "n_polygons": sum(len(a["polygons"]) for a in areas),
        "n_vertices": sum(len(p.split()) for a in areas for p in a["polygons"]),
        "n_circles": sum(len(a["circles"]) for a in areas),
        "areas": areas,
        "cap_xml": ET.tostring(cap, encoding="unicode"),
    }


def read_feed(payload: bytes) -> tuple[dict, list[dict]]:
    """Feed Atom → (metadados do feed, alertas). Entradas sem CAP válido são contadas e ignoradas."""
    root = ET.fromstring(payload)
    if root.tag != ATOM + "feed":
        raise ValueError(f"resposta não é um feed Atom: {root.tag}")
    entries = root.findall(ATOM + "entry")
    alerts, invalid = [], 0
    for entry in entries:
        content = entry.find(ATOM + "content")
        cap = content.find(CAP + "alert") if content is not None else None
        if cap is None and content is not None and (content.text or "").strip().startswith("<"):
            try:
                cap = ET.fromstring(content.text)
            except ET.ParseError:
                cap = None
        if cap is None:
            cap = entry.find(CAP + "alert")
        parsed = parse_alert(cap, atom_updated=_t(entry, "updated", ATOM)) if cap is not None else None
        if parsed is None:
            invalid += 1
            continue
        alerts.append(parsed)
    meta = {"feed_updated": _t(root, "updated", ATOM), "n_entries": len(entries), "n_invalid": invalid}
    return meta, alerts
