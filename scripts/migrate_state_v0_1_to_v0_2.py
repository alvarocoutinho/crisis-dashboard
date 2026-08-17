"""
migrate_state_v0_1_to_v0_2.py — Migração de schema state.json v0.1 → v0.2.

Aplica a Reforma das três flags conforme docs/state-schema-v0.2.md.

Política pactuada:
- D1=B (retroativa): alertas antigos em extended_window sem migrar são removidos
  do state e contabilizados no log agregado como n_arquivados_alerta_puro.
- D2=2: priority_tier é preservado como metadado visual (espelho de nivel_atual).

Uso:
    python scripts/migrate_state_v0_1_to_v0_2.py \
        --state src/data/state.json \
        --log src/data/alertas_agregados.csv \
        [--dry-run] [--backup-dir src/data/backups]

Se --dry-run: imprime plano e novo state.json em stdout, não escreve.
Caso contrário: backup do state antigo, escreve novo state, atualiza log agregado.

Retrocompatibilidade: state v0.1 não tem schema_version; se já for v0.2 (tem
schema_version="0.2"), o script aborta com mensagem — migração é idempotente
apenas no sentido de que não faz nada em v0.2 (não re-migra).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_VERSION_NEW = "0.2"
PIPELINE_VERSION_NEW = "0.2.0"

# Cadências novas por flag (horas)
CADENCE_HOURS_BY_FLAG = {
    "alerta": 24,
    "acompanhamento": 12,
    "prioritario": 6,
}

# Header do log agregado
LOG_HEADER = [
    "municipio", "uf", "codibge", "ano_mes", "evento", "nivel_cemaden",
    "n_emitidos", "n_arquivados_alerta_puro",
    "n_migrados_acompanhamento", "n_migrados_prioritario",
    "n_arquivados_completos",
]


def load_state(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_existing_log(path: Path) -> dict:
    """Carrega log agregado existente como dict indexado por chave composta.

    Chave: (codibge, ano_mes, evento, nivel_cemaden). Se arquivo não existe,
    retorna dict vazio.
    """
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


def save_log(rows: dict, path: Path) -> None:
    """Escreve log agregado ordenado por (codibge, ano_mes, evento, nivel)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_rows = sorted(rows.values(),
                         key=lambda r: (r["codibge"], r["ano_mes"], r["evento"], r["nivel_cemaden"]))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_HEADER)
        writer.writeheader()
        writer.writerows(sorted_rows)


def bump_log(log: dict, alert: dict, counter_field: str, delta: int = 1) -> None:
    """Incrementa um contador em log agregado, criando a linha se necessário."""
    opened = alert.get("opened_at", "")
    ano_mes = opened[:7] if opened else "unknown"
    # nivel_atual é do CEMADEN (fonte da verdade); evento não está no state v0.1
    # e será populado com "unknown" na migração (não temos como recuperar sem CSVs).
    # Coletas futuras poderão preencher o evento correto — enquanto isso, "unknown"
    # é honesto sobre a limitação da migração retroativa.
    evento = alert.get("evento_cemaden", "unknown")
    key = (alert["codibge"], ano_mes, evento, alert["nivel_atual"])
    if key not in log:
        log[key] = {
            "municipio": alert["municipio"],
            "uf": alert["uf"],
            "codibge": alert["codibge"],
            "ano_mes": ano_mes,
            "evento": evento,
            "nivel_cemaden": alert["nivel_atual"],
            "n_emitidos": 0,
            "n_arquivados_alerta_puro": 0,
            "n_migrados_acompanhamento": 0,
            "n_migrados_prioritario": 0,
            "n_arquivados_completos": 0,
        }
    log[key][counter_field] += delta


def next_collection_from_flag(flag: str, from_iso: str | None = None) -> str:
    """Calcula next_collection_at baseado na flag."""
    if from_iso:
        base = datetime.fromisoformat(from_iso.replace("Z", "+00:00"))
    else:
        base = datetime.now(timezone.utc)
    from datetime import timedelta
    hours = CADENCE_HOURS_BY_FLAG[flag]
    nxt = base + timedelta(hours=hours)
    return nxt.strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_and_upgrade(alert_id: str, alert: dict, log: dict) -> tuple[dict | None, str]:
    """Classifica um alerta v0.1 na nova taxonomia e retorna versão v0.2.

    Returns:
        (novo_alerta_v0.2_ou_None_se_deve_ser_removido, categoria_migração)
        categoria_migração ∈ {
            "alerta_ativo",           # ficou em active_alerts com flag=alerta
            "acompanhamento_ativo",   # ficou em active_alerts com flag=acompanhamento
            "acompanhamento_extended",# ficou em extended_window com flag=acompanhamento
            "removido_alerta_puro",   # removido do state, contabilizado no log
        }
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Todos os alertas atuais contam para n_emitidos (base de H2)
    bump_log(log, alert, "n_emitidos")

    has_video = bool(alert.get("videos_collected"))
    is_closed = bool(alert.get("closed_at"))

    if not has_video and is_closed:
        # Regra retroativa: fechou sem migrar → n_arquivados_alerta_puro,
        # removido do state
        bump_log(log, alert, "n_arquivados_alerta_puro")
        return None, "removido_alerta_puro"

    # Precisa gerar entry v0.2. Campos comuns:
    opened_at = alert.get("opened_at")
    if has_video:
        flag = "acompanhamento"
        # flag_history: entrada inicial em opened_at, transição em last_collection_at
        # (aproximação; primeiro vídeo real não é rastreável do state v0.1)
        transition_at = alert.get("last_collection_at", opened_at)
        flag_history = [
            {"flag": "alerta", "at": opened_at},
            {"flag": "acompanhamento", "at": transition_at},
        ]
        bump_log(log, alert, "n_migrados_acompanhamento")
        last_new_data_at = alert.get("last_collection_at", opened_at)
    else:
        flag = "alerta"
        flag_history = [{"flag": "alerta", "at": opened_at}]
        last_new_data_at = None

    new_alert = OrderedDict([
        # v0.1 preservados
        ("codibge", alert["codibge"]),
        ("municipio", alert["municipio"]),
        ("uf", alert["uf"]),
        ("nivel_atual", alert["nivel_atual"]),
        ("priority_tier", alert.get("priority_tier", "moderado")),
        # v0.2 novos
        ("flag", flag),
        ("flag_history", flag_history),
        # v0.1 preservados (cont.)
        ("opened_at", opened_at),
        ("last_seen_open_at", alert.get("last_seen_open_at", opened_at)),
        ("closed_at", alert.get("closed_at")),
        ("transitions", alert.get("transitions", [])),
        ("videos_collected", alert.get("videos_collected", [])),
        # v0.2 novos (cont.)
        ("n_videos_aderentes", len(alert.get("videos_collected", []))),
        ("n_comments_valid", 0),
        ("videos_with_valid_comments", []),
        ("last_new_data_at", last_new_data_at),
        ("last_new_comment_at", None),
        # v0.1 preservados
        ("last_collection_at", alert.get("last_collection_at")),
        # next_collection_at recalculado pela nova cadência da flag
        ("next_collection_at", next_collection_from_flag(
            flag, alert.get("last_collection_at"))),
    ])

    if is_closed:
        category = "acompanhamento_extended"
    elif has_video:
        category = "acompanhamento_ativo"
    else:
        category = "alerta_ativo"
    return new_alert, category


def migrate(state: dict, log: dict) -> tuple[dict, dict]:
    """Aplica migração v0.1 → v0.2. Muta log in-place, retorna novo state."""
    if state.get("schema_version") == SCHEMA_VERSION_NEW:
        raise RuntimeError(
            f"state.json já está em v{SCHEMA_VERSION_NEW}; migração seria no-op. "
            "Se quer re-executar, remova o campo schema_version manualmente."
        )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    new_active = OrderedDict()
    new_extended = OrderedDict()

    stats = defaultdict(int)

    # Processa active_alerts
    for aid, alert in state.get("active_alerts", {}).items():
        new_alert, category = classify_and_upgrade(aid, alert, log)
        stats[category] += 1
        if new_alert is not None:
            # active sempre vai para active (não pode estar closed_at != null)
            # Se por algum motivo estava e agora tem closed_at, vai para extended
            if new_alert["closed_at"]:
                new_extended[aid] = new_alert
            else:
                new_active[aid] = new_alert

    # Processa extended_window_alerts
    for aid, alert in state.get("extended_window_alerts", {}).items():
        new_alert, category = classify_and_upgrade(aid, alert, log)
        stats[category] += 1
        if new_alert is not None:
            new_extended[aid] = new_alert

    new_state = OrderedDict([
        ("schema_version", SCHEMA_VERSION_NEW),
        ("pipeline_version", PIPELINE_VERSION_NEW),
        ("last_run_at", state.get("last_run_at", now_iso)),
        ("last_run_status", state.get("last_run_status", "success")),
        ("last_run_duration_seconds", state.get("last_run_duration_seconds", 0)),
        ("last_cemaden_check_at", state.get("last_run_at", now_iso)),
        ("youtube_quota", state.get("youtube_quota", {
            "used_today": 0, "reset_at": now_iso,
        })),
        ("active_alerts", new_active),
        ("extended_window_alerts", new_extended),
        ("archived_alerts", OrderedDict()),
    ])
    return new_state, dict(stats)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", type=Path, required=True, help="Caminho para state.json")
    p.add_argument("--log", type=Path, required=True, help="Caminho para src/data/alertas_agregados.csv")
    p.add_argument("--dry-run", action="store_true", help="Não escreve; imprime plano e novo state")
    p.add_argument("--backup-dir", type=Path, default=Path("src/data/backups"),
                   help="Onde salvar backup do state antigo (default: src/data/backups/)")
    args = p.parse_args()

    print(f"=== Migração state.json v0.1 → v{SCHEMA_VERSION_NEW} ===")
    print(f"Modo: {'DRY-RUN' if args.dry_run else 'ESCRITA'}")
    print(f"State: {args.state}")
    print(f"Log agregado: {args.log}")
    print()

    state = load_state(args.state)
    log = load_existing_log(args.log)
    print(f"State v0.1: {len(state.get('active_alerts', {}))} active, "
          f"{len(state.get('extended_window_alerts', {}))} extended")
    print(f"Log agregado existente: {len(log)} linhas")
    print()

    new_state, stats = migrate(state, log)

    print("=== Plano de migração ===")
    for cat, n in sorted(stats.items()):
        print(f"  {cat:32s}: {n}")
    print()
    print(f"State v0.2 resultante: {len(new_state['active_alerts'])} active, "
          f"{len(new_state['extended_window_alerts'])} extended, "
          f"{len(new_state['archived_alerts'])} archived")
    print(f"Log agregado atualizado: {len(log)} linhas")
    print()

    # Sumário por alerta
    print("=== Detalhe por alerta ===")
    for section in ("active_alerts", "extended_window_alerts"):
        for aid, a in new_state[section].items():
            print(f"  [{section:24s}] {aid:22s} flag={a['flag']:15s} n_videos={a['n_videos_aderentes']} "
                  f"n_comments={a['n_comments_valid']} closed_at={a['closed_at'] or '-'}")
    print()

    if args.dry_run:
        print("=== DRY-RUN: nada escrito ===")
        return 0

    # Backup
    args.backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = args.backup_dir / f"state.v0_1.{ts}.json"
    shutil.copy2(args.state, backup_path)
    print(f"Backup do state v0.1: {backup_path}")

    # Escreve novo state
    with args.state.open("w", encoding="utf-8") as f:
        json.dump(new_state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"State v0.2 gravado: {args.state}")

    # Escreve log agregado
    save_log(log, args.log)
    print(f"Log agregado atualizado: {args.log} ({len(log)} linhas)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
