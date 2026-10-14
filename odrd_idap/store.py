"""Armazenamento incremental dos alertas IDAP.

Três camadas, com papéis diferentes:

1. **Arquivo bruto** (``idap_cap_AAAA-MM-DD.jsonl.gz``, um por dia de emissão): o XML
   CAP original de cada alerta, com a geometria em precisão total. É publicado
   como asset de um GitHub Release (``idap-arquivo``), fora do histórico do git.
2. **Catálogo** (``data/idap/alertas.csv``): uma linha por alerta, só atributos e
   texto, sem geometria. É a base de pesquisa.
3. **Camada do painel** (``public/data/idap/dias/AAAA-MM-DD.geojson`` e
   ``public/data/idap/indice.json``): geometria simplificada para exibição.

A chave de um alerta é o ``identifier`` CAP (ex.: ``193759/2026``). Atualizações e
cancelamentos CAP chegam com identificador próprio e apontam o original em
``references``.
"""
from __future__ import annotations

import csv
import gzip
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .geometry import area_geometry

BRT = ZoneInfo("America/Sao_Paulo")
CATALOG_FIELDS = [
    "identifier", "id_num", "sender", "sent", "sent_utc", "dia_emissao", "status", "msg_type", "references",
    "sender_name", "event", "category", "urgency", "severity", "certainty", "response_type",
    "onset", "onset_utc", "expires", "expires_utc", "headline", "description", "instruction",
    "area_desc", "ufs", "ibge", "n_ibge", "n_polygons", "n_vertices", "n_circles", "area_km2",
    "bbox", "ponto", "sem_geometria", "poligonos_fechados_pelo_coletor", "channels",
    "first_seen_utc", "collector_version",
]
CAPTURE_FIELDS = [
    "captured_at_utc", "url", "status", "http_status", "bytes", "sha256", "feed_updated",
    "n_entries", "n_invalid", "n_alerts", "min_id", "max_id", "min_sent_utc", "max_sent_utc",
    "horas_cobertas", "n_novos", "ids_faltantes_total", "erro",
]
COLLECTOR_VERSION = "0.1.0"

UF_IBGE = {"11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO", "21": "MA",
           "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE", "29": "BA",
           "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR", "42": "SC", "43": "RS", "50": "MS",
           "51": "MT", "52": "GO", "53": "DF"}
UF_NOMES = {"ACRE": "AC", "ALAGOAS": "AL", "AMAPA": "AP", "AMAZONAS": "AM", "BAHIA": "BA", "CEARA": "CE",
            "DISTRITO FEDERAL": "DF", "ESPIRITO SANTO": "ES", "GOIAS": "GO", "MARANHAO": "MA",
            "MATO GROSSO": "MT", "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG", "PARA": "PA",
            "PARAIBA": "PB", "PARANA": "PR", "PERNAMBUCO": "PE", "PIAUI": "PI", "RIO DE JANEIRO": "RJ",
            "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS", "RONDONIA": "RO", "RORAIMA": "RR",
            "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SERGIPE": "SE", "TOCANTINS": "TO"}
_UF_SIGLAS = set(UF_IBGE.values())
_SUFIXO_UF = re.compile(r"/\s*([A-Z]{2})\b")
_SIGLA_PAREN = re.compile(r"\(([A-Z]{2})\)")


def _sem_acento(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def infer_ufs(alert: dict) -> list[str]:
    """UFs do alerta, pela ordem de confiança: códigos IBGE, sufixos "/UF" da área, emissor."""
    ufs = {UF_IBGE[c[:2]] for c in alert.get("ibge", []) if c[:2] in UF_IBGE}
    ufs |= {m for m in _SUFIXO_UF.findall(alert.get("area_desc", "")) if m in _UF_SIGLAS}
    if not ufs:
        nome = _sem_acento(alert.get("sender_name", "")).upper()
        ufs |= {m for m in _SIGLA_PAREN.findall(alert.get("sender_name", "")) if m in _UF_SIGLAS}
        if not ufs:
            m = re.search(r"ESTADUAL\s+D[EOA]S?\s+(.+)$", nome)
            if m and m.group(1).strip() in UF_NOMES:
                ufs.add(UF_NOMES[m.group(1).strip()])
    return sorted(ufs)


def local_day(sent: str) -> str:
    """Dia da emissão no horário de Brasília (AAAA-MM-DD)."""
    try:
        return datetime.fromisoformat(sent.replace("Z", "+00:00")).astimezone(BRT).strftime("%Y-%m-%d")
    except ValueError:
        return "sem-data"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def append_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    novo = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if novo:
            w.writeheader()
        w.writerows(rows)


def build_record(alert: dict, first_seen_utc: str) -> tuple[dict, dict | None]:
    """Alerta parseado → (linha do catálogo, Feature GeoJSON para o painel)."""
    geom, qa = area_geometry(alert["areas"])
    ufs = infer_ufs(alert)
    row = {k: alert.get(k, "") for k in CATALOG_FIELDS}
    row.update({
        "dia_emissao": local_day(alert["sent"]),
        "ufs": "|".join(ufs),
        "ibge": "|".join(alert["ibge"]),
        "n_ibge": len(alert["ibge"]),
        "area_km2": qa.get("area_km2", ""),
        "bbox": json.dumps(qa["bbox"]) if qa.get("bbox") else "",
        "ponto": json.dumps(qa["ponto"]) if qa.get("ponto") else "",
        "sem_geometria": int(qa["sem_geometria"]),
        "poligonos_fechados_pelo_coletor": qa.get("poligonos_fechados_pelo_coletor", 0),
        "first_seen_utc": first_seen_utc,
        "collector_version": COLLECTOR_VERSION,
    })
    props = {k: row[k] for k in (
        "identifier", "id_num", "sent_utc", "onset_utc", "expires_utc", "status", "msg_type", "references",
        "sender_name", "event", "urgency", "severity", "certainty", "headline", "description", "instruction",
        "area_desc", "n_ibge", "area_km2", "first_seen_utc")}
    props["ufs"] = ufs
    props["ponto"] = qa.get("ponto")
    props["bbox"] = qa.get("bbox")
    feature = {"type": "Feature", "id": alert["identifier"], "properties": props, "geometry": geom}
    return row, feature


def raw_line(alert: dict, first_seen_utc: str) -> str:
    return json.dumps({"identifier": alert["identifier"], "sender": alert["sender"], "sent": alert["sent"],
                       "first_seen_utc": first_seen_utc, "atom_updated": alert.get("atom_updated", ""),
                       "cap_xml": alert["cap_xml"]}, ensure_ascii=False)


def merge_raw_day(path: Path, lines: list[str]) -> int:
    """Acrescenta ao .jsonl.gz do dia os alertas ainda ausentes. Retorna quantos entraram."""
    existentes, atuais = set(), []
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for ln in fh:
                if ln.strip():
                    atuais.append(ln.rstrip("\n"))
                    existentes.add(json.loads(ln)["identifier"])
    novos = [ln for ln in lines if json.loads(ln)["identifier"] not in existentes]
    if not novos and path.exists():
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for ln in atuais + novos:
            fh.write(ln + "\n")
    return len(novos)


def write_day_geojson(path: Path, features: list[dict]) -> int:
    """Mescla Features no GeoJSON do dia (por identificador). Retorna o total do dia."""
    atuais = {}
    if path.exists():
        atuais = {f["id"]: f for f in json.loads(path.read_text(encoding="utf-8")).get("features", [])}
    for f in features:
        atuais.setdefault(f["id"], f)
    ordenadas = sorted(atuais.values(), key=lambda f: (f["properties"].get("id_num") or 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": ordenadas},
                               ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(ordenadas)


def missing_ids(catalog: list[dict]) -> list[int]:
    """Números de identificador ausentes entre o menor e o maior já arquivados."""
    nums = sorted({int(r["id_num"]) for r in catalog if str(r.get("id_num", "")).isdigit()})
    if len(nums) < 2:
        return []
    have = set(nums)
    return [n for n in range(nums[0], nums[-1] + 1) if n not in have]


def write_index(path: Path, catalog: list[dict], captures: list[dict], dias_dir: Path) -> dict:
    """Índice do painel: dias disponíveis, contagens e saúde da coleta."""
    por_dia = {}
    for r in catalog:
        d = r.get("dia_emissao") or "sem-data"
        por_dia[d] = por_dia.get(d, 0) + 1
    ok = [c for c in captures if c.get("status") == "ok"]
    ultima = captures[-1] if captures else {}
    faltantes = missing_ids(catalog)
    agora = datetime.now(timezone.utc)
    ultimas_24h = [c for c in captures if c.get("captured_at_utc", "") >= (agora - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")]
    idx = {
        "gerado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fonte": "IDAP — feed Atom/CAP 1.2 (idapfile.mdr.gov.br/idap/api/rss/cap)",
        "versao_coletor": COLLECTOR_VERSION,
        "total_alertas": len(catalog),
        "primeira_captura": captures[0]["captured_at_utc"] if captures else None,
        "ultima_captura": ultima.get("captured_at_utc"),
        "ultima_captura_status": ultima.get("status"),
        "ultima_captura_ok": ok[-1]["captured_at_utc"] if ok else None,
        "capturas_24h": len(ultimas_24h),
        "capturas_24h_ok": sum(1 for c in ultimas_24h if c.get("status") == "ok"),
        "horas_cobertas_ultima": ultima.get("horas_cobertas"),
        "ids_faltantes_total": len(faltantes),
        "dias": [{"dia": d, "n": n, "arquivo": f"dias/{d}.geojson"}
                 for d, n in sorted(por_dia.items(), reverse=True) if (dias_dir / f"{d}.geojson").exists()],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    return idx
