"""Gerenciamento de state.json — decide o que processar em cada ciclo.

O pipeline dispara a cada 6h (cron mínimo), mas cada alerta tem sua própria
cadência por tier (6h/12h/24h/48h). Este módulo é o cérebro que, dado o state
atual e o timestamp de agora, decide QUAIS alertas processar no ciclo corrente.

Também administra transições entre estados:
- active → extended_window (quando alerta fecha no CEMADEN)
- extended_window → closed (quando completa 365 dias desde abertura)
- descoberta de novos alertas (adiciona a active_alerts)

Filosofia: nunca perder informação de coleta anterior. Sempre commit do state,
mesmo em execuções parciais (com last_run_status refletindo o resultado real).
"""
from __future__ import annotations

import json
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal


# Cadências (horas entre coletas) por tier — pactuadas com Alvaro
CADENCE_HOURS = {
    "muito_alto": 6,
    "alto": 12,
    "moderado": 24,
    "acompanhamento": 48,
}

# Duração máxima da janela de acompanhamento antes de fechar
EXTENDED_WINDOW_DAYS = 365


def _nivel_to_tier(nivel: str) -> str:
    """Mapeia nivel CEMADEN → priority_tier operacional."""
    n = (nivel or "").lower().strip()
    return {"muito alto": "muito_alto", "alto": "alto", "moderado": "moderado"}.get(
        n, "moderado"
    )


def _parse_iso(dt_str: str | None) -> datetime | None:
    """Parse ISO 8601 tolerante — devolve None em qualquer erro."""
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _iso_utc(dt: datetime) -> str:
    """Serializa datetime como ISO 8601 UTC com sufixo Z."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AlertDecision:
    """Uma decisão sobre um alerta para o ciclo corrente."""
    alert_id: str
    action: Literal["collect", "skip_not_due", "transition_to_extended", "transition_to_closed"]
    tier: str
    reason: str  # legível em log


def load_state(path: str | Path) -> dict:
    """Carrega state.json. Se não existir, devolve state vazio."""
    path = Path(path)
    if not path.exists():
        return _empty_state()
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[state_manager] AVISO: state.json corrompido ({e}) — usando state vazio")
        return _empty_state()


def _empty_state() -> dict:
    """Estrutura mínima válida de state — usada em bootstrap ou recuperação."""
    return {
        "pipeline_version": "0.1.0",
        "last_run_at": None,
        "last_run_status": None,
        "last_run_duration_seconds": 0,
        "youtube_quota": {"used_today": 0, "reset_at": None},
        "active_alerts": {},
        "extended_window_alerts": {},
    }


def save_state(state: dict, path: str | Path) -> None:
    """Salva state.json atomicamente (write-then-rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)
    print(f"[state_manager] state salvo: {path} ({path.stat().st_size} bytes)")


def decide_alerts_to_process(
    state: dict,
    now: datetime | None = None,
) -> list[AlertDecision]:
    """Dado o state atual e o timestamp de agora, decide QUAIS alertas processar.

    Regra: um alerta é elegível se `next_collection_at <= now`. Alertas em
    extended_window com >365 dias desde opened_at transitam para closed
    (sem coleta). Alertas ainda não vistos aparecem como decisões novas
    a partir do CEMADEN — este método NÃO consulta o CEMADEN; quem faz
    isso é o pipeline.py, que passa alertas novos via merge_new_alerts().

    Returns:
        Lista de AlertDecision. Ordem importa: primeiro Muito Alto,
        depois Alto, Moderado, Acompanhamento (para o pipeline gastar
        cota nos mais críticos primeiro se cota apertar).
    """
    now = now or datetime.now(timezone.utc)
    decisions: list[AlertDecision] = []

    # 1. Active alerts: coletar se next_collection_at passou
    for alert_id, meta in state.get("active_alerts", {}).items():
        next_at = _parse_iso(meta.get("next_collection_at"))
        tier = meta.get("priority_tier", "moderado")
        if next_at is None or next_at <= now:
            decisions.append(AlertDecision(
                alert_id=alert_id,
                action="collect",
                tier=tier,
                reason=f"active, next_collection_at={next_at}, tier={tier}",
            ))
        else:
            decisions.append(AlertDecision(
                alert_id=alert_id,
                action="skip_not_due",
                tier=tier,
                reason=f"active, próxima coleta em {next_at}",
            ))

    # 2. Extended window: verifica se completou 365 dias; senão, avalia cadência
    for alert_id, meta in state.get("extended_window_alerts", {}).items():
        opened_at = _parse_iso(meta.get("opened_at"))
        if opened_at and (now - opened_at).days >= EXTENDED_WINDOW_DAYS:
            decisions.append(AlertDecision(
                alert_id=alert_id,
                action="transition_to_closed",
                tier="acompanhamento",
                reason=f"365 dias completos desde opened_at={opened_at}",
            ))
            continue
        next_at = _parse_iso(meta.get("next_collection_at"))
        if next_at is None or next_at <= now:
            decisions.append(AlertDecision(
                alert_id=alert_id,
                action="collect",
                tier="acompanhamento",
                reason=f"extended, next_collection_at={next_at}",
            ))
        else:
            decisions.append(AlertDecision(
                alert_id=alert_id,
                action="skip_not_due",
                tier="acompanhamento",
                reason=f"extended, próxima coleta em {next_at}",
            ))

    # Ordenar: collect primeiro, por severidade decrescente
    tier_priority = {"muito_alto": 0, "alto": 1, "moderado": 2, "acompanhamento": 3}
    decisions.sort(key=lambda d: (
        0 if d.action == "collect" else (1 if d.action.startswith("transition") else 2),
        tier_priority.get(d.tier, 99),
    ))

    return decisions


def merge_new_alerts_from_cemaden(
    state: dict,
    cemaden_active_alerts: list[dict],
    now: datetime | None = None,
    close_missing: bool = True,
) -> tuple[dict, list[str], list[str]]:
    """Reconcilia alertas do CEMADEN com o state.

    Args:
        state: state atual (será mutado)
        cemaden_active_alerts: lista de dicts do painel CEMADEN, cada um com pelo
            menos: cod_alerta, codibge, municipio, uf, nivel, datahoracriacao
        now: timestamp de referência
        close_missing: se True (default), alertas em active_alerts que NÃO
            aparecem na lista do CEMADEN são transitados para extended_window
            (fechamento). Passar False quando a consulta ao CEMADEN falhou
            ou é suspeita — evita fechar alertas por engano.

    Returns:
        (state_atualizado, ids_novos, ids_que_fecharam)

    Efeitos:
        - Alertas novos (não em state): adicionados a active_alerts
        - Alertas em active_alerts mas NÃO no CEMADEN: transitam para extended_window
          APENAS se close_missing=True (fecharam no CEMADEN, começa janela 365d)
        - Alertas em active_alerts com nivel mudado: registra transition
    """
    now = now or datetime.now(timezone.utc)
    now_iso = _iso_utc(now)
    new_ids: list[str] = []
    closed_ids: list[str] = []

    active = state.setdefault("active_alerts", {})
    extended = state.setdefault("extended_window_alerts", {})

    cemaden_ids = set()
    for alert in cemaden_active_alerts:
        cod = str(alert.get("cod_alerta", ""))
        uf = str(alert.get("uf", "")).upper()
        if not cod or not uf:
            continue
        alert_id = f"cemaden_{uf.lower()}_{cod}"
        cemaden_ids.add(alert_id)

        nivel = alert.get("nivel", "Moderado")
        tier = _nivel_to_tier(nivel)
        opened_at = alert.get("datahoracriacao", "")
        opened_iso = _iso_utc(_parse_iso(opened_at) or now)

        if alert_id in active:
            # Alerta já conhecido — verificar mudança de nível
            prev = active[alert_id]
            prev_nivel = prev.get("nivel_atual")
            if prev_nivel and prev_nivel != nivel:
                prev.setdefault("transitions", []).append({
                    "from": prev_nivel,
                    "to": nivel,
                    "at": now_iso,
                })
                prev["nivel_atual"] = nivel
                prev["priority_tier"] = tier
            prev["last_seen_open_at"] = now_iso
        else:
            # Alerta novo
            municipio_raw = str(alert.get("municipio", "")).lower()
            _lower = {"de", "da", "do", "das", "dos", "e"}
            municipio = " ".join(
                p.capitalize() if (i == 0 or p not in _lower) else p
                for i, p in enumerate(municipio_raw.split())
            )
            next_iso = _iso_utc(now + timedelta(hours=CADENCE_HOURS[tier]))
            active[alert_id] = OrderedDict([
                ("codibge", str(alert.get("codibge", ""))),
                ("municipio", municipio),
                ("uf", uf),
                ("nivel_atual", nivel),
                ("priority_tier", tier),
                ("opened_at", opened_iso),
                ("last_seen_open_at", now_iso),
                ("transitions", []),
                ("videos_collected", []),
                ("last_collection_at", None),
                ("next_collection_at", now_iso),  # coleta imediata no próximo ciclo
            ])
            new_ids.append(alert_id)

    # Alertas que sumiram do CEMADEN → transitam para extended_window
    # SÓ FAZ ISSO se close_missing=True (proteção contra falha silenciosa
    # da consulta ao CEMADEN, que devolve [] em vez de exceção em alguns casos)
    if close_missing:
        active_ids_snapshot = list(active.keys())
        for alert_id in active_ids_snapshot:
            if alert_id not in cemaden_ids:
                meta = active.pop(alert_id)
                meta["closed_at"] = now_iso
                meta["priority_tier"] = "acompanhamento"
                meta["next_collection_at"] = _iso_utc(
                    now + timedelta(hours=CADENCE_HOURS["acompanhamento"])
                )
                extended[alert_id] = meta
                closed_ids.append(alert_id)

    return state, new_ids, closed_ids


def mark_collection_complete(
    state: dict,
    alert_id: str,
    videos_collected: list[str] | None = None,
    now: datetime | None = None,
) -> None:
    """Atualiza state depois de uma coleta bem-sucedida de um alerta.

    Registra last_collection_at, calcula next_collection_at baseado no tier,
    e faz merge (não overwrite) de videos_collected para preservar
    idempotência.
    """
    now = now or datetime.now(timezone.utc)
    now_iso = _iso_utc(now)

    # Procurar em active ou extended
    for bucket_name in ("active_alerts", "extended_window_alerts"):
        bucket = state.get(bucket_name, {})
        if alert_id in bucket:
            meta = bucket[alert_id]
            tier = meta.get("priority_tier", "moderado")
            meta["last_collection_at"] = now_iso
            meta["next_collection_at"] = _iso_utc(
                now + timedelta(hours=CADENCE_HOURS.get(tier, 24))
            )
            if videos_collected:
                existing = set(meta.get("videos_collected", []))
                existing.update(videos_collected)
                meta["videos_collected"] = sorted(existing)
            return
    print(f"[state_manager] AVISO: alert_id {alert_id} não encontrado em state")


def close_extended_alert(state: dict, alert_id: str) -> None:
    """Remove alerta de extended_window (completou 365 dias)."""
    extended = state.get("extended_window_alerts", {})
    if alert_id in extended:
        del extended[alert_id]
        print(f"[state_manager] alerta {alert_id} fechou janela 365d — removido do state")


def update_run_metadata(
    state: dict,
    status: Literal["success", "partial", "failed"],
    duration_seconds: int,
    quota_used: int,
    now: datetime | None = None,
    pipeline_version: str = "0.1.0",
) -> None:
    """Atualiza metadados de execução do state — sempre chamado no fim do run."""
    now = now or datetime.now(timezone.utc)
    state["pipeline_version"] = pipeline_version
    state["last_run_at"] = _iso_utc(now)
    state["last_run_status"] = status
    state["last_run_duration_seconds"] = duration_seconds

    # Reset de cota YouTube: se passou da meia-noite Pacific desde last_run
    quota = state.setdefault("youtube_quota", {"used_today": 0, "reset_at": None})
    reset_at = _parse_iso(quota.get("reset_at"))
    if reset_at is None or now >= reset_at:
        quota["used_today"] = quota_used
    else:
        quota["used_today"] = quota.get("used_today", 0) + quota_used

    # Próximo reset: 07h UTC (meia-noite Pacific)
    next_reset = (now + timedelta(days=1)).replace(hour=7, minute=0, second=0, microsecond=0)
    quota["reset_at"] = _iso_utc(next_reset)
