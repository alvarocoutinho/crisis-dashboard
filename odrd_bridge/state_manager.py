"""Gerenciamento de state.json — decide o que processar em cada ciclo (v0.2).

Reforma das três flags (17/08/2026). O drive único de cadência passa a ser
`flag ∈ {"alerta", "acompanhamento", "prioritario"}`, não `priority_tier`
(que vira metadado visual). Cadências: 24h / 12h / 6h.

Transições (v0.3.2 — só contam vídeos que NOMEIAM o município do alerta,
`video_evidence` ≠ "nenhuma"; vídeos de escopo estadual/regional continuam em
videos_collected e servem ao episódio regional, H1):
- alerta → acompanhamento: n_videos_municipais ≥ 1
- acompanhamento → prioritario: n_comments_valid_municipal ≥ 50 E
  len(videos_with_valid_comments_municipal) ≥ 2
- Sem regressão no ciclo normal. A reavaliação única de 13/10/2026
  (scripts/reevaluate_flags_v0_3_2.py) rebaixou flags concedidas pelo critério
  antigo e registrou a proveniência em flag_history.
- Até a v0.3.1 o critério usava todos os vídeos aderentes (n_videos_aderentes,
  n_comments_valid), o que promovia alertas por cobertura estadual.

Arquivamento:
- Alerta fechado no CEMADEN com flag=alerta e SEM vídeo algum: some do state,
  incrementa n_arquivados_alerta_puro no log agregado. Com vídeos regionais
  (v0.3.2), vai para extended_window e é arquivado após 14d sem dado novo.
- acompanhamento sem novo dado por 14d: vai para archived_alerts, incrementa
  n_arquivados_completos.
- prioritario sem novo comentário por 28d: vai para archived_alerts, incrementa
  n_arquivados_completos.

Log agregado (src/data/alertas_agregados.csv):
- Chave: (codibge, ano_mes(opened_at), evento, nivel_cemaden)
- Colunas contadoras: n_emitidos, n_arquivados_alerta_puro,
  n_migrados_acompanhamento, n_migrados_prioritario, n_arquivados_completos
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from faa_poc.config import CONFIG as _FAA_CONFIG


SCHEMA_VERSION = "0.2"
PIPELINE_VERSION = "0.3.0"

# ------------------------------------------------------------------------------
# v0.3 — Janela de coleta (correção do consumo de cota, 13/10/2026)
# ------------------------------------------------------------------------------
# O faa_poc só aceita vídeos publicados em [abertura-6h, abertura+72h] e só
# conta comentários com |publicação - abertura| ≤ 72h. Passado esse prazo,
# nenhum dado novo *dentro da janela* pode surgir: refazer search.list (100
# unidades cada) e paginar comentários devolve sempre o mesmo conjunto.
# Regra: depois que uma coleta BEM-SUCEDIDA ocorre após o fim da janela
# (+ margem para atraso de indexação), a janela é dada como finalizada e o
# alerta não gera mais chamadas à API. Ele continua no state/dashboard e segue
# as regras de arquivamento homologadas (14d/28d sem dado novo).
COLLECTION_WINDOW_HOURS = max(
    int(_FAA_CONFIG["SEARCH_POST_ALERT_HOURS"]), int(_FAA_CONFIG["EVENT_WINDOW_HOURS"])
)
FINAL_SWEEP_MARGIN_HOURS = 6

# Cota YouTube Data API: o dia de cota vira à meia-noite de America/Los_Angeles
QUOTA_TZ = ZoneInfo("America/Los_Angeles")

# Cadências (horas) por flag — pactuadas no wrap-up de 17/08/2026, homologadas Leila
CADENCE_HOURS_BY_FLAG = {
    "alerta": 24,
    "acompanhamento": 12,
    "prioritario": 6,
}

# Regras temporais de arquivamento (dias) — homologadas Leila
ARCHIVE_ACOMPANHAMENTO_DAYS = 14
ARCHIVE_PRIORITARIO_DAYS = 28

# Massa crítica para promoção acompanhamento → prioritario — homologada Leila
PROMOTE_PRIORITARIO_N_COMMENTS = 50
PROMOTE_PRIORITARIO_N_VIDEOS = 2
# Rótulo gravado em flag_history: qual regra concedeu a flag
FLAG_CRITERION = "municipal_v0.3.2"

# Ordem canônica das colunas do log agregado
AGGREGATE_LOG_HEADER = [
    "municipio", "uf", "codibge", "ano_mes", "evento", "nivel_cemaden",
    "n_emitidos", "n_arquivados_alerta_puro",
    "n_migrados_acompanhamento", "n_migrados_prioritario",
    "n_arquivados_completos",
]

_MUNICIPIO_LOWER = {"de", "da", "do", "das", "dos", "e"}


# ==============================================================================
# Utilitários de parse/format
# ==============================================================================

def _nivel_to_tier(nivel: str) -> str:
    """Mapeia nivel CEMADEN → priority_tier (metadado VISUAL, não operacional).

    Preservado por retrocompatibilidade com Live.jsx enquanto o frontend não
    é refatorado para consumir `flag` diretamente.
    """
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


def _title_case_municipio(raw: str) -> str:
    """CEMADEN devolve CAPS; converte para Title Case brasileiro."""
    parts = str(raw or "").lower().split()
    return " ".join(
        p.capitalize() if (i == 0 or p not in _MUNICIPIO_LOWER) else p
        for i, p in enumerate(parts)
    )


def _next_collection_from_flag(flag: str, base: datetime | None = None) -> str:
    """Calcula next_collection_at somando a cadência da flag ao base (ou now)."""
    base = base or datetime.now(timezone.utc)
    hours = CADENCE_HOURS_BY_FLAG[flag]
    return _iso_utc(base + timedelta(hours=hours))


# ==============================================================================
# Log agregado — I/O
# ==============================================================================

def load_aggregate_log(path: str | Path) -> dict:
    """Carrega log agregado como dict indexado por chave composta.

    Chave: (codibge, ano_mes, evento, nivel_cemaden). Se arquivo não existe,
    retorna dict vazio (será criado no primeiro save).
    """
    path = Path(path)
    if not path.exists():
        return {}
    rows = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["codibge"], row["ano_mes"], row["evento"], row["nivel_cemaden"])
            for col in ("n_emitidos", "n_arquivados_alerta_puro",
                        "n_migrados_acompanhamento", "n_migrados_prioritario",
                        "n_arquivados_completos"):
                row[col] = int(row[col])
            rows[key] = row
    return rows


def save_aggregate_log(log: dict, path: str | Path) -> None:
    """Escreve log agregado ordenado por (codibge, ano_mes, evento, nivel)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(
        log.values(),
        key=lambda r: (r["codibge"], r["ano_mes"], r["evento"], r["nivel_cemaden"]),
    )
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=AGGREGATE_LOG_HEADER)
        writer.writeheader()
        writer.writerows(sorted_rows)
    tmp.replace(path)
    print(f"[state_manager] log agregado salvo: {path} ({len(log)} linhas)")


def bump_aggregate_log(log: dict, alert: dict, counter: str, delta: int = 1) -> None:
    """Incrementa um contador no log agregado, criando a linha se necessário.

    Chave composta: (codibge, ano_mes(opened_at), evento, nivel_atual).
    `evento` vem do próprio alerta se disponível (populado em coleta nova
    a partir do faa_poc). Alertas migrados retroativamente podem ter
    evento="unknown".
    """
    opened = alert.get("opened_at") or ""
    ano_mes = opened[:7] if opened else "unknown"
    evento = alert.get("evento") or alert.get("evento_cemaden") or "unknown"
    nivel = alert.get("nivel_atual", "Moderado")
    key = (alert["codibge"], ano_mes, evento, nivel)
    if key not in log:
        log[key] = {
            "municipio": alert["municipio"],
            "uf": alert["uf"],
            "codibge": alert["codibge"],
            "ano_mes": ano_mes,
            "evento": evento,
            "nivel_cemaden": nivel,
            "n_emitidos": 0,
            "n_arquivados_alerta_puro": 0,
            "n_migrados_acompanhamento": 0,
            "n_migrados_prioritario": 0,
            "n_arquivados_completos": 0,
        }
    log[key][counter] += delta


# ==============================================================================
# State — I/O
# ==============================================================================

@dataclass
class AlertDecision:
    """Uma decisão sobre um alerta para o ciclo corrente."""
    alert_id: str
    action: Literal["collect", "skip_not_due", "archive_exhausted", "skip_window_closed"]
    flag: str
    reason: str


def _empty_state() -> dict:
    """Estrutura mínima válida de state v0.2 — usada em bootstrap ou recuperação."""
    return OrderedDict([
        ("schema_version", SCHEMA_VERSION),
        ("pipeline_version", PIPELINE_VERSION),
        ("last_run_at", None),
        ("last_run_status", None),
        ("last_run_duration_seconds", 0),
        ("last_cemaden_check_at", None),
        ("youtube_quota", {"used_today": 0, "reset_at": None}),
        ("active_alerts", OrderedDict()),
        ("extended_window_alerts", OrderedDict()),
        ("archived_alerts", OrderedDict()),
    ])


def load_state(path: str | Path) -> dict:
    """Carrega state.json. Se não existir, devolve state vazio v0.2.

    Aborta com erro se ler state v0.1 (sem schema_version) — força executar
    o script de migração scripts/migrate_state_v0_1_to_v0_2.py primeiro.
    """
    path = Path(path)
    if not path.exists():
        return _empty_state()
    try:
        with path.open("r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[state_manager] AVISO: state.json corrompido ({e}) — usando state vazio")
        return _empty_state()

    v = state.get("schema_version")
    if v != SCHEMA_VERSION:
        raise RuntimeError(
            f"state.json em schema_version={v!r}, esperado {SCHEMA_VERSION!r}. "
            "Rode scripts/migrate_state_v0_1_to_v0_2.py primeiro."
        )
    # Garante existência dos três buckets (retrocompatibilidade defensiva)
    state.setdefault("active_alerts", OrderedDict())
    state.setdefault("extended_window_alerts", OrderedDict())
    state.setdefault("archived_alerts", OrderedDict())
    return state


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


# ==============================================================================
# Decisão de coleta por ciclo
# ==============================================================================

def decide_alerts_to_process(
    state: dict,
    now: datetime | None = None,
) -> list[AlertDecision]:
    """Decide QUAIS alertas processar neste ciclo com base em flag + next_collection_at.

    Cadência é derivada de `flag`, não mais de `priority_tier`.
    Arquivos esgotados (regra temporal) são identificados aqui e devem ser
    tratados pelo pipeline via archive_exhausted().

    Ordem retornada: collect primeiro, depois skip_not_due, depois archive_exhausted.
    Dentro de collect, ordena por flag (prioritario > acompanhamento > alerta)
    para gastar cota nos alertas mais engajados primeiro.
    """
    now = now or datetime.now(timezone.utc)
    decisions: list[AlertDecision] = []

    for bucket_name in ("active_alerts", "extended_window_alerts"):
        for alert_id, meta in state.get(bucket_name, {}).items():
            flag = meta.get("flag", "alerta")

            # Checagem de arquivamento por tempo (só para extended, em qualquer flag)
            if bucket_name == "extended_window_alerts":
                if _should_archive_by_time(meta, now):
                    decisions.append(AlertDecision(
                        alert_id=alert_id, action="archive_exhausted",
                        flag=flag,
                        reason=_archive_reason(meta, now),
                    ))
                    continue

            # v0.3: janela finalizada → nenhuma chamada à API
            if meta.get("window_finalized_at"):
                decisions.append(AlertDecision(
                    alert_id=alert_id, action="skip_window_closed", flag=flag,
                    reason=f"{bucket_name}, janela finalizada em {meta['window_finalized_at']}",
                ))
                continue

            next_at = _parse_iso(meta.get("next_collection_at"))
            if next_at is None or next_at <= now:
                decisions.append(AlertDecision(
                    alert_id=alert_id, action="collect", flag=flag,
                    reason=f"{bucket_name}, next_collection_at={next_at}, flag={flag}",
                ))
            else:
                decisions.append(AlertDecision(
                    alert_id=alert_id, action="skip_not_due", flag=flag,
                    reason=f"{bucket_name}, próxima coleta em {next_at}",
                ))

    # Ordenação: collect primeiro. v0.3: dentro de collect, alertas com janela
    # ainda aberta vêm antes das varreduras finais (a cota vai para o evento em
    # curso); depois prioritario > acompanhamento > alerta.
    flag_priority = {"prioritario": 0, "acompanhamento": 1, "alerta": 2}
    action_priority = {"collect": 0, "archive_exhausted": 1, "skip_not_due": 2,
                       "skip_window_closed": 3}

    def _window_rank(d: AlertDecision) -> int:
        end = collection_window_end(_find_alert(state, d.alert_id) or {})
        return 0 if (end is None or now < end) else 1

    decisions.sort(key=lambda d: (
        action_priority.get(d.action, 99),
        _window_rank(d) if d.action == "collect" else 0,
        flag_priority.get(d.flag, 99),
    ))
    return decisions


def collection_window_end(meta: dict) -> datetime | None:
    """Fim da janela de coleta do alerta (abertura + 72h + margem)."""
    opened = _parse_iso(meta.get("opened_at"))
    if opened is None:
        return None
    return opened + timedelta(hours=COLLECTION_WINDOW_HOURS + FINAL_SWEEP_MARGIN_HOURS)


def normalize_legacy_v03(state: dict, now: datetime | None = None) -> list[str]:
    """Migração idempotente para a regra de janela v0.3.

    Alertas anteriores à v0.3 não têm `window_finalized_at`. Só é seguro
    finalizá-los quando há evidência de uma coleta bem-sucedida DEPOIS do fim
    da janela: `last_new_data_at`/`last_new_comment_at` só eram gravados quando
    a coleta devolvia dados. Sem essa evidência (ex.: alertas `alerta` cujas
    coletas falharam por cota), o alerta recebe uma varredura final.

    Também marca `counters_integrity`, porque até a v0.2.2 os comentários
    recoletados a cada ciclo eram somados de novo a `n_comments_valid`.

    Returns:
        ids finalizados nesta chamada.
    """
    now = now or datetime.now(timezone.utc)
    finalized = []
    for bucket_name in ("active_alerts", "extended_window_alerts", "archived_alerts"):
        for alert_id, meta in state.get(bucket_name, {}).items():
            if "counters_integrity" not in meta:
                meta["counters_integrity"] = (
                    "inflated_pre_v0.3" if meta.get("n_comments_valid", 0) > 0 else "ok"
                )
            if bucket_name == "archived_alerts" or meta.get("window_finalized_at"):
                continue
            end = collection_window_end(meta)
            stamps = [_parse_iso(meta.get(k)) for k in ("last_new_data_at", "last_new_comment_at")]
            stamps = [p for p in stamps if p is not None]
            proofs = [p for p in stamps if end is not None and p >= end]
            if end is not None and now >= end and proofs:
                meta["window_finalized_at"] = _iso_utc(max(proofs))
                meta["window_finalized_reason"] = "legacy_inferred_v0.3"
                meta.pop("seen_comment_hashes", None)
                finalized.append(alert_id)
            elif not stamps and "legacy_unverified" not in meta:
                # Sem prova de coleta bem-sucedida: as coletas v0.2 deste alerta
                # podem ter sido falhas de cota marcadas como concluídas. Não
                # afirmar silêncio e coletar já no próximo ciclo.
                meta["legacy_unverified"] = True
                meta["next_collection_at"] = _iso_utc(now)
    return finalized


def _should_archive_by_time(meta: dict, now: datetime) -> bool:
    """Verifica se alerta em extended cruzou janela temporal de arquivamento.

    Regras:
    - flag=acompanhamento: now - last_new_data_at ≥ 14 dias
    - flag=prioritario: now - last_new_comment_at ≥ 28 dias
    - flag=alerta em extended: anomalia (não deveria acontecer com nova regra),
      não arquiva por tempo — deixa fluxo natural resolver
    """
    flag = meta.get("flag", "alerta")
    if flag == "acompanhamento" or (flag == "alerta" and meta.get("videos_collected")):
        # v0.3.2: alerta só com cobertura regional segue a regra de 14 dias
        anchor = _parse_iso(meta.get("last_new_data_at"))
        threshold = timedelta(days=ARCHIVE_ACOMPANHAMENTO_DAYS)
    elif flag == "prioritario":
        anchor = _parse_iso(meta.get("last_new_comment_at"))
        threshold = timedelta(days=ARCHIVE_PRIORITARIO_DAYS)
    else:
        return False
    if anchor is None:
        return False
    return (now - anchor) >= threshold


def _archive_reason(meta: dict, now: datetime) -> str:
    flag = meta.get("flag", "alerta")
    if flag == "acompanhamento":
        anchor = meta.get("last_new_data_at")
        return f"acompanhamento sem dado novo desde {anchor} (≥{ARCHIVE_ACOMPANHAMENTO_DAYS}d)"
    if flag == "prioritario":
        anchor = meta.get("last_new_comment_at")
        return f"prioritario sem novo comentário desde {anchor} (≥{ARCHIVE_PRIORITARIO_DAYS}d)"
    if flag == "alerta" and meta.get("videos_collected"):
        anchor = meta.get("last_new_data_at")
        return f"alerta com cobertura só regional sem dado novo desde {anchor} (≥{ARCHIVE_ACOMPANHAMENTO_DAYS}d)"
    return "razão desconhecida"


# ==============================================================================
# Merge com CEMADEN — descoberta e fechamento
# ==============================================================================

def merge_new_alerts_from_cemaden(
    state: dict,
    cemaden_active_alerts: list[dict],
    log: dict,
    now: datetime | None = None,
    close_missing: bool = True,
) -> tuple[dict, list[str], list[str], list[str]]:
    """Reconcilia alertas do CEMADEN com o state (v0.2).

    Diferenças vs v0.1:
    - Aceita `log` (dict do log agregado); incrementa contadores diretamente
    - Novos alertas entram com flag="alerta", flag_history, contadores zerados
    - Alertas que saem do CEMADEN têm tratamento condicional por flag:
        * flag=alerta → some do state, incrementa n_arquivados_alerta_puro
        * flag ∈ {acompanhamento, prioritario} → vai para extended_window
        (comportamento antigo)

    Returns:
        (state, new_ids, closed_to_extended_ids, closed_to_puro_ids)
    """
    now = now or datetime.now(timezone.utc)
    now_iso = _iso_utc(now)
    new_ids: list[str] = []
    closed_to_extended: list[str] = []
    closed_to_puro: list[str] = []

    active = state.setdefault("active_alerts", OrderedDict())
    extended = state.setdefault("extended_window_alerts", OrderedDict())

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
        evento_raw = alert.get("evento", "")
        # tipo: remove sufixo "- Moderado/Alto" se vier concatenado
        evento_clean = evento_raw.split(" - ")[0].strip() if " - " in evento_raw else evento_raw

        if alert_id in active:
            # Alerta já conhecido — atualiza nível e last_seen; NÃO recomputa flag
            prev = active[alert_id]
            prev_nivel = prev.get("nivel_atual")
            if prev_nivel and prev_nivel != nivel:
                prev.setdefault("transitions", []).append({
                    "from": prev_nivel, "to": nivel, "at": now_iso,
                })
                prev["nivel_atual"] = nivel
                prev["priority_tier"] = tier
            prev["last_seen_open_at"] = now_iso
        elif alert_id in extended:
            # Alerta reaberto (raro; CEMADEN normalmente não reabre) — trata como
            # atualização do extended, sem promoção ou rebaixamento de flag
            extended[alert_id]["last_seen_open_at"] = now_iso
        else:
            # Alerta novo — entra em active com flag=alerta
            municipio = _title_case_municipio(alert.get("municipio", ""))
            new_alert = OrderedDict([
                ("codibge", str(alert.get("codibge", ""))),
                ("municipio", municipio),
                ("uf", uf),
                ("nivel_atual", nivel),
                ("priority_tier", tier),
                ("flag", "alerta"),
                ("flag_history", [{"flag": "alerta", "at": opened_iso}]),
                ("evento", evento_clean),
                ("opened_at", opened_iso),
                ("last_seen_open_at", now_iso),
                ("closed_at", None),
                ("transitions", []),
                ("videos_collected", []),
                ("n_videos_aderentes", 0),
                ("n_comments_valid", 0),
                ("videos_with_valid_comments", []),
                ("last_new_data_at", None),
                ("last_new_comment_at", None),
                ("last_collection_at", None),
                ("next_collection_at", now_iso),  # coleta imediata no próximo ciclo
            ])
            active[alert_id] = new_alert
            bump_aggregate_log(log, new_alert, "n_emitidos")
            new_ids.append(alert_id)

    # Alertas que sumiram do CEMADEN — tratamento condicional por flag
    if close_missing:
        active_ids_snapshot = list(active.keys())
        for alert_id in active_ids_snapshot:
            if alert_id in cemaden_ids:
                continue
            meta = active[alert_id]
            flag = meta.get("flag", "alerta")

            if flag == "alerta" and not meta.get("videos_collected"):
                # Regra nova: some do state, incrementa n_arquivados_alerta_puro
                bump_aggregate_log(log, meta, "n_arquivados_alerta_puro")
                del active[alert_id]
                closed_to_puro.append(alert_id)
            else:
                # Migrou em algum ponto — preserva em extended_window
                meta = active.pop(alert_id)
                meta["closed_at"] = now_iso
                # Cadência mantida pela flag atual (não força "acompanhamento" como antes)
                meta["next_collection_at"] = _next_collection_from_flag(flag, now)
                extended[alert_id] = meta
                closed_to_extended.append(alert_id)

    return state, new_ids, closed_to_extended, closed_to_puro


# ==============================================================================
# Registro pós-coleta e promoção de flag
# ==============================================================================

def mark_collection_complete(
    state: dict,
    alert_id: str,
    log: dict,
    videos_collected_now: list[str] | None = None,
    predictions_this_alert: object = None,  # pd.DataFrame; usa duck typing p/ evitar import
    now: datetime | None = None,
    success: bool = True,
    error: str | None = None,
    video_evidence: dict[str, str] | None = None,
    video_format: dict[str, str] | None = None,
) -> None:
    """Atualiza state depois de uma coleta de um alerta (v0.2; v0.3 abaixo).

    v0.3:
        - `success=False` (quota_exhausted/api_error/deferred): dados parciais
          ainda são incorporados (com deduplicação), mas `last_collection_at` e
          `next_collection_at` NÃO avançam — o alerta continua devido e é
          retentado; `consecutive_failures`/`last_error` registram a falha.
        - Deduplicação: só comentários nunca vistos para este alerta contam em
          `n_comments_valid` e renovam `last_new_comment_at` (antes, cada ciclo
          recontava todos os comentários recoletados).
        - Sucesso após o fim da janela de coleta → `window_finalized_at`.

    Args:
        state: state mutável
        alert_id: identificador canônico
        log: log agregado (será mutado se houver promoção de flag)
        videos_collected_now: lista de video_ids que apareceram nos CSVs deste ciclo
            para este alerta (podem incluir vídeos já conhecidos — filtragem
            de duplicatas é feita aqui)
        predictions_this_alert: DataFrame com colunas video_id, n_model_labels
            das predições de BERTimbau para os comentários deste alerta neste
            ciclo. Se None ou vazio, nenhum comentário novo é contabilizado.
        now: timestamp de referência

    Efeitos colaterais:
        1. Atualiza contadores cumulativos (n_videos_aderentes, n_comments_valid,
           videos_with_valid_comments)
        2. Atualiza timestamps de dado novo (last_new_data_at, last_new_comment_at)
        3. Atualiza last_collection_at
        4. Recalcula next_collection_at pela flag ATUAL
        5. Chama promote_flag_if_eligible (pode alterar flag, flag_history e log)
    """
    now = now or datetime.now(timezone.utc)
    now_iso = _iso_utc(now)

    meta = _find_alert(state, alert_id)
    if meta is None:
        print(f"[state_manager] AVISO: alert_id {alert_id} não encontrado em state")
        return

    # 0. v0.3.1: evidência municipal por vídeo (onde o vídeo nomeia o município)
    if video_evidence:
        merge_video_evidence(meta, video_evidence)
    # v0.3.4: formato por vídeo (short | longo | ao_vivo | indeterminado)
    if video_format:
        merge_video_format(meta, video_format)

    # 1. Merge de vídeos coletados (union set, preserva idempotência)
    existing_videos = set(meta.get("videos_collected", []))
    incoming_videos = set(videos_collected_now or [])
    new_videos = incoming_videos - existing_videos
    if new_videos:
        merged = sorted(existing_videos | incoming_videos)
        meta["videos_collected"] = merged
        meta["n_videos_aderentes"] = len(merged)

    # 2. Processa predições — comentários não-FP (n_model_labels ≥ 1)
    n_new_valid_comments = 0
    new_videos_with_valid_comments = set()
    has_any_new_comment = False

    if predictions_this_alert is not None:
        try:
            df = predictions_this_alert
            n_rows = len(df)
        except Exception:
            n_rows = 0

        # v0.3: descarta comentários já contados para este alerta
        if n_rows > 0 and "comment_id" in df.columns:
            seen = set(meta.get("seen_comment_hashes", []))
            hashes = df["comment_id"].astype(str).map(_comment_hash)
            fresh_mask = ~hashes.isin(seen)
            df = df[fresh_mask.values]
            meta["seen_comment_hashes"] = sorted(seen | set(hashes))
            n_rows = len(df)

        if n_rows > 0 and "n_model_labels" in df.columns:
            has_any_new_comment = True
            valid_df = df[df["n_model_labels"] >= 1]
            n_new_valid_comments = len(valid_df)
            if "video_id" in valid_df.columns:
                new_videos_with_valid_comments = set(
                    valid_df["video_id"].astype(str).unique()
                )

    if n_new_valid_comments > 0:
        meta["n_comments_valid"] = meta.get("n_comments_valid", 0) + n_new_valid_comments
        existing_valid_videos = set(meta.get("videos_with_valid_comments", []))
        meta["videos_with_valid_comments"] = sorted(
            existing_valid_videos | new_videos_with_valid_comments
        )
        # v0.3.2: contagem por vídeo, para separar o que vem de vídeos municipais
        if "video_id" in valid_df.columns:
            by_video = meta.setdefault("valid_comments_by_video", {})
            for vid, n in valid_df["video_id"].astype(str).value_counts().items():
                by_video[vid] = int(by_video.get(vid, 0)) + int(n)
    recompute_municipal_counters(meta)

    # 3. Timestamps de "dado novo"
    if new_videos or n_new_valid_comments > 0:
        meta["last_new_data_at"] = now_iso
    if has_any_new_comment:
        meta["last_new_comment_at"] = now_iso

    meta["last_attempt_at"] = now_iso
    if not success:
        # v0.3: falha não é coleta — mantém o alerta devido para retentativa
        meta["consecutive_failures"] = int(meta.get("consecutive_failures", 0)) + 1
        meta["last_error"] = error or "unknown"
        promote_flag_if_eligible(meta, log, now)
        return

    meta["consecutive_failures"] = 0
    meta["last_error"] = None
    meta["legacy_unverified"] = False

    # 4. Timestamps de coleta e próxima coleta pela flag atual
    meta["last_collection_at"] = now_iso
    meta["next_collection_at"] = _next_collection_from_flag(meta.get("flag", "alerta"), now)

    # 5. Promoção de flag (pode mutar meta["flag"], meta["flag_history"] e log)
    promote_flag_if_eligible(meta, log, now)

    # 6. v0.3: coleta bem-sucedida após o fim da janela é a varredura final
    end = collection_window_end(meta)
    if end is not None and now >= end and not meta.get("window_finalized_at"):
        meta["window_finalized_at"] = now_iso
        meta["window_finalized_reason"] = "final_sweep"
        meta.pop("seen_comment_hashes", None)  # minimização: não é mais necessário


_EVIDENCE_RANK = {"titulo+descricao": 4, "titulo": 3, "descricao": 2, "transcricao": 1, "nenhuma": 0}


def merge_video_evidence(meta: dict, incoming: dict[str, str]) -> None:
    """Grava a evidência municipal por vídeo, mantendo a mais forte já vista.

    Uma descrição editada depois ou uma transcrição posterior podem só
    acrescentar evidência; nunca a rebaixam.
    """
    current = meta.setdefault("video_evidence", {})
    for vid, ev in incoming.items():
        if not ev:
            continue
        if _EVIDENCE_RANK.get(ev, 0) >= _EVIDENCE_RANK.get(current.get(vid), -1):
            current[vid] = ev
    recompute_municipal_counters(meta)


VIDEO_FORMATS = ("short", "longo", "ao_vivo", "indeterminado")


def merge_video_format(meta: dict, incoming: dict[str, str]) -> None:
    """Grava o formato por vídeo (v0.3.4).

    O formato é do arquivo enviado e não muda; a única transição esperada é
    ``indeterminado`` → definido (proporção que passou a ser conhecida).
    Valores vazios ou fora do vocabulário são ignorados, e um formato
    definido nunca volta a ``indeterminado``.
    """
    current = meta.setdefault("video_format", {})
    for vid, fmt in incoming.items():
        if fmt not in VIDEO_FORMATS:
            continue
        if fmt == "indeterminado" and current.get(vid) not in (None, "indeterminado"):
            continue
        current[str(vid)] = fmt


def recompute_municipal_counters(meta: dict) -> None:
    """Deriva os contadores municipais (v0.3.2) de video_evidence e valid_comments_by_video.

    São derivados, não acumulados: quando uma transcrição promove um vídeo a
    evidência municipal, os comentários dele passam a contar sem recoleta.
    """
    ev = meta.get("video_evidence", {}) or {}
    by_video = meta.get("valid_comments_by_video", {}) or {}
    vids = set(meta.get("videos_collected", [])) | set(ev)
    municipais = sorted(v for v in vids if _EVIDENCE_RANK.get(ev.get(v), 0) > 0)
    meta["n_videos_municipais"] = len(municipais)
    meta["n_comments_valid_municipal"] = sum(int(by_video.get(v, 0)) for v in municipais)
    meta["videos_with_valid_comments_municipal"] = [v for v in municipais if int(by_video.get(v, 0)) > 0]


def _comment_hash(comment_id: str) -> str:
    """Hash curto e não reversível do comment_id, só para deduplicação.

    O state.json é público; guardar ids crus do YouTube permitiria listar o
    corpus. 12 hex (48 bits) bastam para milhares de ids por alerta.
    """
    return hashlib.sha256(f"odrd-dedup-v1:{comment_id}".encode()).hexdigest()[:12]


def _find_alert(state: dict, alert_id: str) -> dict | None:
    """Localiza alerta em active ou extended. Retorna None se não achar."""
    for bucket_name in ("active_alerts", "extended_window_alerts"):
        bucket = state.get(bucket_name, {})
        if alert_id in bucket:
            return bucket[alert_id]
    return None


def promote_flag_if_eligible(meta: dict, log: dict, now: datetime | None = None) -> str | None:
    """Verifica critérios de promoção e atualiza flag/flag_history/log se elegível.

    Sem regressão: uma vez em prioritario, não muda.
    Cascata em um único ciclo é possível (alerta → acompanhamento → prioritario
    se um único ciclo trouxer vídeo + 50 comentários em 2 vídeos).

    v0.3.2: só vídeos que nomeiam o município contam (ver docstring do módulo).

    Returns:
        Nova flag se houve promoção, senão None.
    """
    now = now or datetime.now(timezone.utc)
    now_iso = _iso_utc(now)
    original_flag = meta.get("flag", "alerta")
    current_flag = original_flag
    recompute_municipal_counters(meta)

    # alerta → acompanhamento
    if current_flag == "alerta" and meta.get("n_videos_municipais", 0) >= 1:
        current_flag = "acompanhamento"
        meta["flag"] = current_flag
        meta.setdefault("flag_history", []).append({
            "flag": current_flag, "at": now_iso, "criterio": FLAG_CRITERION,
        })
        bump_aggregate_log(log, meta, "n_migrados_acompanhamento")
        print(f"[state_manager] promoção alerta → acompanhamento (n_videos_municipais={meta['n_videos_municipais']})")

    # acompanhamento → prioritario
    if current_flag == "acompanhamento":
        n_valid = meta.get("n_comments_valid_municipal", 0)
        n_videos_valid = len(meta.get("videos_with_valid_comments_municipal", []))
        if (n_valid >= PROMOTE_PRIORITARIO_N_COMMENTS
                and n_videos_valid >= PROMOTE_PRIORITARIO_N_VIDEOS):
            current_flag = "prioritario"
            meta["flag"] = current_flag
            meta.setdefault("flag_history", []).append({
                "flag": current_flag, "at": now_iso, "criterio": FLAG_CRITERION,
            })
            bump_aggregate_log(log, meta, "n_migrados_prioritario")
            print(f"[state_manager] promoção acompanhamento → prioritario "
                  f"(n_comments_valid_municipal={n_valid}, n_videos={n_videos_valid})")

    # Se houve mudança, recalcula next_collection_at
    if current_flag != original_flag:
        meta["next_collection_at"] = _next_collection_from_flag(current_flag, now)
        return current_flag
    return None


# ==============================================================================
# Arquivamento por regra temporal
# ==============================================================================

def archive_exhausted(state: dict, log: dict, now: datetime | None = None) -> list[str]:
    """Move alertas esgotados (regra temporal) de extended_window → archived.

    Regras (rechecadas independente de decide_alerts_to_process para robustez):
    - flag=acompanhamento: now - last_new_data_at ≥ 14 dias
    - flag=prioritario: now - last_new_comment_at ≥ 28 dias

    Incrementa n_arquivados_completos no log agregado.

    Returns:
        Lista de alert_ids arquivados.
    """
    now = now or datetime.now(timezone.utc)
    now_iso = _iso_utc(now)
    archived_ids: list[str] = []

    extended = state.setdefault("extended_window_alerts", OrderedDict())
    archived = state.setdefault("archived_alerts", OrderedDict())

    for alert_id in list(extended.keys()):
        meta = extended[alert_id]
        if not _should_archive_by_time(meta, now):
            continue
        flag = meta.get("flag", "alerta")
        reason = ("acompanhamento_esgotado_14d" if flag == "acompanhamento"
                  else "prioritario_esgotado_28d" if flag == "prioritario"
                  else "alerta_regional_esgotado_14d" if flag == "alerta"
                  else "desconhecido")
        meta["archived_at"] = now_iso
        meta["archive_reason"] = reason
        archived[alert_id] = meta
        del extended[alert_id]
        bump_aggregate_log(log, meta, "n_arquivados_completos")
        archived_ids.append(alert_id)
        print(f"[state_manager] arquivado {alert_id}: {reason}")

    return archived_ids


# ==============================================================================
# Metadados de execução
# ==============================================================================

def update_run_metadata(
    state: dict,
    status: Literal["success", "partial", "failed"],
    duration_seconds: int,
    quota_used: int,
    now: datetime | None = None,
    pipeline_version: str = PIPELINE_VERSION,
    cemaden_checked: bool = False,
    searches_used: int = 0,
) -> None:
    """Atualiza metadados de execução do state — sempre chamado no fim do run.

    Args:
        cemaden_checked: se True, atualiza last_cemaden_check_at (Prioridade 3
            do wrap-up: separar "verificação" de "coleta" para observabilidade)
    """
    now = now or datetime.now(timezone.utc)
    now_iso = _iso_utc(now)
    state["schema_version"] = SCHEMA_VERSION
    state["pipeline_version"] = pipeline_version
    state["last_run_at"] = now_iso
    state["last_run_status"] = status
    state["last_run_duration_seconds"] = duration_seconds
    if cemaden_checked:
        state["last_cemaden_check_at"] = now_iso

    # v0.3: contabilidade real por dia de cota (meia-noite America/Los_Angeles).
    # A versão anterior empurrava reset_at sempre para "amanhã 07h UTC" e,
    # como o cron roda a cada 6h, o contador nunca zerava (chegou a 297.300).
    quota = roll_quota_day(state, now)
    quota["used_today"] = int(quota.get("used_today", 0)) + int(quota_used)
    quota["searches_today"] = int(quota.get("searches_today", 0)) + int(searches_used)


def roll_quota_day(state: dict, now: datetime | None = None) -> dict:
    """Zera `youtube_quota.used_today` quando o dia de cota (Pacific) mudou.

    Returns:
        o dict `state["youtube_quota"]` já normalizado.
    """
    now = now or datetime.now(timezone.utc)
    quota = state.setdefault("youtube_quota", {"used_today": 0, "reset_at": None})
    local = now.astimezone(QUOTA_TZ)
    day = local.date().isoformat()
    if quota.get("day") != day:
        quota["day"] = day
        quota["used_today"] = 0
        quota["searches_today"] = 0
        quota.pop("exhausted_by_api", None)
        quota.pop("search_exhausted_by_api", None)
    next_midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    quota["reset_at"] = _iso_utc(next_midnight)
    return quota


# ==============================================================================
# Compatibilidade — funções v0.1 desativadas
# ==============================================================================

def close_extended_alert(state: dict, alert_id: str) -> None:
    """[DEPRECATED v0.2] Regra de 365 dias substituída por arquivamento temporal.

    Mantida como no-op para não quebrar chamadas antigas em pipeline.py enquanto
    a transição para archive_exhausted() está sendo feita. Após Sprint 2, o
    pipeline não deve mais chamar esta função.
    """
    print(f"[state_manager] WARN: close_extended_alert({alert_id}) chamado — "
          "no-op em v0.2 (use archive_exhausted)")
