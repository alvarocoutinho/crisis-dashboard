"""Observação horária do painel de alertas do CEMADEN (wsAlertas2).

O pipeline principal consulta o painel a cada 6 h e só "vê" os alertas abertos
naquele instante. Um alerta que abre e fecha entre duas consultas nunca entra no
state. Este observador consulta o painel de hora em hora, sem filtro, e mantém um
catálogo com primeira e última observação de cada alerta. Assim dá para medir:

- a duração observada dos alertas (limite inferior: da abertura à última vez visto;
  limite superior: da abertura à primeira consulta em que já não estava);
- quantos alertas relevantes para o pipeline (moderado ou acima; risco hidrológico
  ou movimentos de massa) fecharam sem nunca entrar no state.

Não altera o state nem o pipeline: só observa.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

NIVEIS_PIPELINE = {"moderado", "alto", "muito alto"}
EVENTOS_PIPELINE = ("risco hidrológico", "movimentos de massa")

CATALOG_FIELDS = [
    "cod_alerta", "alert_id", "uf", "municipio", "codibge", "evento", "nivel_primeiro", "nivel_ultimo",
    "niveis_vistos", "status_ultimo", "datahoracriacao", "ult_atualizacao", "latitude", "longitude",
    "relevante_pipeline", "first_seen_utc", "last_seen_utc", "n_capturas", "aberto", "fechado_visto_utc",
    "n_reaberturas", "duracao_min_h", "duracao_max_h", "visto_no_state",
]
CAPTURE_FIELDS = [
    "captured_at_utc", "status", "erro", "n_total", "n_relevantes", "n_novos", "n_fechados",
    "n_relevantes_fechados_fora_do_state", "niveis", "sha256",
]


def _dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def _horas(a: str, b: str) -> str:
    da, db = _dt(a), _dt(b)
    if not (da and db):
        return ""
    return round((db - da).total_seconds() / 3600, 2)


def relevante(alerta: dict) -> bool:
    nivel = str(alerta.get("nivel") or "").lower().strip()
    evento = str(alerta.get("evento") or "").lower()
    return nivel in NIVEIS_PIPELINE and any(e in evento for e in EVENTOS_PIPELINE)


def alert_id(alerta: dict) -> str:
    """Mesmo identificador do state: ``cemaden_<uf>_<cod>``."""
    return f"cemaden_{str(alerta.get('uf', '')).lower()}_{alerta.get('cod_alerta', '')}"


def snapshot_hash(alertas: list[dict]) -> str:
    """Hash estável do conteúdo da consulta (ordem e espaços não importam)."""
    canon = sorted(json.dumps(a, sort_keys=True, ensure_ascii=False) for a in alertas)
    return hashlib.sha256("\n".join(canon).encode()).hexdigest()


def update_catalog(catalog: dict[str, dict], alertas: list[dict], captured_at: str,
                   state_ids: set[str]) -> dict:
    """Atualiza o catálogo (por ``cod_alerta``) com uma consulta bem-sucedida.

    Retorna as contagens da captura. Só chamar com consulta bem-sucedida: uma lista
    vazia por falha seria lida como "todos fecharam".
    """
    vistos, novos = set(), 0
    for a in alertas:
        cod = str(a.get("cod_alerta", "")).strip()
        if not cod:
            continue
        vistos.add(cod)
        nivel = str(a.get("nivel") or "")
        row = catalog.get(cod)
        if row is None:
            novos += 1
            row = catalog[cod] = {
                "cod_alerta": cod, "alert_id": alert_id(a), "uf": a.get("uf", ""), "municipio": a.get("municipio", ""),
                "codibge": a.get("codibge", ""), "evento": a.get("evento", ""), "nivel_primeiro": nivel,
                "niveis_vistos": nivel, "datahoracriacao": a.get("datahoracriacao", ""),
                "latitude": a.get("latitude", ""), "longitude": a.get("longitude", ""),
                "first_seen_utc": captured_at, "n_capturas": 0, "n_reaberturas": 0, "fechado_visto_utc": "",
            }
        elif str(row.get("aberto")) == "0":
            row["n_reaberturas"] = int(row.get("n_reaberturas") or 0) + 1
            row["fechado_visto_utc"] = ""
        niveis = [n for n in str(row.get("niveis_vistos", "")).split("|") if n]
        if nivel and nivel not in niveis:
            niveis.append(nivel)
        row.update({
            "nivel_ultimo": nivel, "niveis_vistos": "|".join(niveis), "status_ultimo": a.get("status", ""),
            "ult_atualizacao": a.get("ult_atualizacao", ""), "last_seen_utc": captured_at,
            "n_capturas": int(row.get("n_capturas") or 0) + 1, "aberto": 1,
            "relevante_pipeline": int(relevante(a) or str(row.get("relevante_pipeline")) == "1"),
        })
        row["duracao_min_h"] = _horas(row["datahoracriacao"], row["last_seen_utc"])
        row["duracao_max_h"] = ""

    # "visto no state" é cumulativo: alertas fechados sem sinal digital saem do state
    # (vão só para o log agregado), então a presença atual não basta.
    for row in catalog.values():
        if row.get("alert_id") in state_ids:
            row["visto_no_state"] = 1
        else:
            row.setdefault("visto_no_state", 0)

    fechados = fora = 0
    for cod, row in catalog.items():
        if cod in vistos or str(row.get("aberto")) == "0":
            continue
        row["aberto"] = 0
        row["fechado_visto_utc"] = captured_at
        row["duracao_max_h"] = _horas(row.get("datahoracriacao", ""), captured_at)
        fechados += 1
        if str(row.get("relevante_pipeline")) == "1" and str(row.get("visto_no_state")) != "1":
            fora += 1

    niveis = {}
    for a in alertas:
        k = str(a.get("nivel") or "?")
        niveis[k] = niveis.get(k, 0) + 1
    return {
        "n_total": len(alertas), "n_relevantes": sum(1 for a in alertas if relevante(a)),
        "n_novos": novos, "n_fechados": fechados, "n_relevantes_fechados_fora_do_state": fora,
        "niveis": json.dumps(niveis, ensure_ascii=False, sort_keys=True),
    }


def state_alert_ids(state: dict) -> set[str]:
    return {aid for b in ("active_alerts", "extended_window_alerts", "archived_alerts")
            for aid in (state.get(b) or {})}
