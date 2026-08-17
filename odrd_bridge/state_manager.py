"""Gerenciamento de state.json — decide o que processar em cada ciclo (v0.2).

Reforma das três flags (17/08/2026). O drive único de cadência passa a ser
`flag ∈ {"alerta", "acompanhamento", "prioritario"}`, não `priority_tier`
(que vira metadado visual). Cadências: 24h / 12h / 6h.

Transições:
- alerta → acompanhamento: primeiro vídeo aderente (entrou em videos_collected)
- acompanhamento → prioritario: n_comments_valid ≥ 50 E
  len(videos_with_valid_comments) ≥ 2
- Sem regressão: nunca retrocede de flag.

Arquivamento:
- Alerta fechado no CEMADEN com flag=alerta: some do state, incrementa
  n_arquivados_alerta_puro no log agregado (não vai para extended_window).
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
import json
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal


SCHEMA_VERSION = "0.2"
PIPELINE_VERSION = "0.2.0"

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
    action: Literal["collect", "skip_not_due", "archive_exhausted"]
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

    # Ordenação: collect primeiro; dentro de collect, prioritario > acompanhamento > alerta
    flag_priority = {"prioritario": 0, "acompanhamento": 1, "alerta": 2}
    action_priority = {"collect": 0, "archive_exhausted": 1, "skip_not_due": 2}
    decisions.sort(key=lambda d: (
        action_priority.get(d.action, 99),
        flag_priority.get(d.flag, 99),
    ))
    return decisions


def _should_archive_by_time(meta: dict, now: datetime) -> bool:
    """Verifica se alerta em extended cruzou janela temporal de arquivamento.

    Regras:
    - flag=acompanhamento: now - last_new_data_at ≥ 14 dias
    - flag=prioritario: now - last_new_comment_at ≥ 28 dias
    - flag=alerta em extended: anomalia (não deveria acontecer com nova regra),
      não arquiva por tempo — deixa fluxo natural resolver
    """
    flag = meta.get("flag", "alerta")
    if flag == "acompanhamento":
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

            if flag == "alerta":
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
) -> None:
    """Atualiza state depois de uma coleta bem-sucedida de um alerta (v0.2).

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

    # 3. Timestamps de "dado novo"
    if new_videos or n_new_valid_comments > 0:
        meta["last_new_data_at"] = now_iso
    if has_any_new_comment:
        meta["last_new_comment_at"] = now_iso

    # 4. Timestamps de coleta e próxima coleta pela flag atual
    meta["last_collection_at"] = now_iso
    meta["next_collection_at"] = _next_collection_from_flag(meta.get("flag", "alerta"), now)

    # 5. Promoção de flag (pode mutar meta["flag"], meta["flag_history"] e log)
    promote_flag_if_eligible(meta, log, now)


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

    Returns:
        Nova flag se houve promoção, senão None.
    """
    now = now or datetime.now(timezone.utc)
    now_iso = _iso_utc(now)
    original_flag = meta.get("flag", "alerta")
    current_flag = original_flag

    # alerta → acompanhamento
    if current_flag == "alerta" and meta.get("n_videos_aderentes", 0) >= 1:
        current_flag = "acompanhamento"
        meta["flag"] = current_flag
        meta.setdefault("flag_history", []).append({
            "flag": current_flag, "at": now_iso,
        })
        bump_aggregate_log(log, meta, "n_migrados_acompanhamento")
        print(f"[state_manager] promoção alerta → acompanhamento (n_videos={meta['n_videos_aderentes']})")

    # acompanhamento → prioritario
    if current_flag == "acompanhamento":
        n_valid = meta.get("n_comments_valid", 0)
        n_videos_valid = len(meta.get("videos_with_valid_comments", []))
        if (n_valid >= PROMOTE_PRIORITARIO_N_COMMENTS
                and n_videos_valid >= PROMOTE_PRIORITARIO_N_VIDEOS):
            current_flag = "prioritario"
            meta["flag"] = current_flag
            meta.setdefault("flag_history", []).append({
                "flag": current_flag, "at": now_iso,
            })
            bump_aggregate_log(log, meta, "n_migrados_prioritario")
            print(f"[state_manager] promoção acompanhamento → prioritario "
                  f"(n_comments_valid={n_valid}, n_videos_valid={n_videos_valid})")

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
