"""Entrypoint do pipeline ODRD para GitHub Actions.

Orquestra: consulta CEMADEN → decide alertas devidos → roda faa_poc filtrado
→ BERTimbau → gera live.json/state.json → sobe crus para Drive → sinaliza
status para o workflow.

Chamado pelo .github/workflows/pipeline.yml a cada 6h ou via workflow_dispatch.
Exit codes:
    0 = sucesso completo
    1 = falha catastrófica (workflow falha, dispara issue)
    2 = manutenção (atualização parcial — commit acontece com status='partial')

Uso local para debug:
    python scripts/pipeline.py [--dry-run] [--limit-alerts N] [--skip-gdrive]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Ajuste de path — assume execução da raiz do repo
REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from odrd_bridge import state_manager
from odrd_bridge.bertimbau import predict_comments
from odrd_bridge.build_live import build_live_json, save_json


# Caminhos padrão (podem ser sobrescritos por variáveis de ambiente)
STATE_PATH = REPO_ROOT / "src" / "data" / "state.json"
LIVE_PATH = REPO_ROOT / "src" / "data" / "live.json"
FAA_OUTPUT_DIR = Path(os.environ.get("FAA_OUTPUT_DIR", "/tmp/faa_pipeline_run"))
PIPELINE_VERSION = "0.1.0"


def log(msg: str, level: str = "INFO") -> None:
    """Log estruturado com timestamp — GitHub Actions colore por nível."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    prefix = {"INFO": "ℹ", "WARN": "⚠", "ERROR": "✗", "OK": "✓"}.get(level, "•")
    print(f"[{ts}] {prefix} {msg}", flush=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pipeline ODRD — orquestrador")
    p.add_argument("--dry-run", action="store_true",
                   help="Executa sem persistir state/live/drive (útil para debug local)")
    p.add_argument("--limit-alerts", type=int, default=None,
                   help="Processa no máximo N alertas devidos (útil para debug)")
    p.add_argument("--skip-gdrive", action="store_true",
                   help="Pula upload de crus para Google Drive")
    p.add_argument("--force-all", action="store_true",
                   help="Ignora next_collection_at e processa todos os alertas")
    return p.parse_args()


def check_required_env() -> list[str]:
    """Valida secrets obrigatórios. Retorna lista de faltantes."""
    required = ["YOUTUBE_API_KEY", "HF_TOKEN", "PED_EMAIL", "PED_PASSWORD"]
    optional = ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    missing = [k for k in required if not os.environ.get(k)]
    for k in optional:
        if not os.environ.get(k):
            log(f"secret opcional ausente: {k} (upload para Drive será pulado)", "WARN")
    return missing


def fetch_cemaden_active_alerts() -> list[dict]:
    """Consulta o painel CEMADEN e retorna alertas Moderado/Alto/Muito Alto
    de Risco Hidrológico e Movimentos de Massa ativos nacionalmente.

    Delegado ao faa_poc.cemaden.fetch_alerts — reusa a lógica já testada do
    PoC frozen. Sem filtro de UF (queremos ver TODOS para reconciliar com state).

    Raises:
        RuntimeError: em qualquer falha de comunicação/parse. É importante
            que o chamador saiba distinguir "CEMADEN falhou" de "CEMADEN
            retornou lista vazia genuinamente" — nunca mascarar exceção.
    """
    from faa_poc.cemaden import fetch_alerts
    log("consultando painel CEMADEN...")
    try:
        alerts = fetch_alerts({
            "FILTER_LEVELS": ["moderado", "alto", "muito alto"],
            "FILTER_EVENTS": ["Risco Hidrológico", "Movimentos de Massa"],
        })
    except Exception as e:
        raise RuntimeError(f"consulta ao CEMADEN falhou: {e}") from e
    log(f"CEMADEN devolveu {len(alerts)} alertas ativos", "OK")
    return alerts


def run_faa_pipeline_for_alerts(alert_ids: list[str], state: dict) -> Path:
    """Executa faa_poc.run() filtrado apenas para os alertas devidos.

    O faa_poc não tem filtro por alert_id específico — filtramos por UF+município
    dos alertas do state para minimizar o escopo. Melhor que rodar tudo de novo.
    """
    from faa_poc import run

    # Deriva UFs e municípios dos alertas devidos
    ufs = set()
    for aid in alert_ids:
        meta = state.get("active_alerts", {}).get(aid) or state.get("extended_window_alerts", {}).get(aid)
        if meta:
            ufs.add(meta.get("uf"))

    log(f"executando faa_poc para UFs: {sorted(ufs)}")

    FAA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run({
        "MODE": "FULL_PIPELINE",
        "FILTER_UF": sorted(ufs),
        "FILTER_LEVELS": ["moderado", "alto", "muito alto"],
        "FILTER_EVENTS": ["Risco Hidrológico", "Movimentos de Massa"],
        "OUTPUT_DIR": str(FAA_OUTPUT_DIR),
        "INTERACTIVE_CREDENTIALS": False,
        "MAX_ALERTS": len(alert_ids) + 2,   # margem de segurança
        "MAX_VIDEOS_PER_ALERT": 10,
        "MAX_COMMENT_PAGES": 10,
        "YT_QUOTA_CEILING": 5000,
    })
    log(f"faa_poc concluído — outputs em {FAA_OUTPUT_DIR}", "OK")
    return FAA_OUTPUT_DIR


def main() -> int:
    args = parse_args()
    t_start = time.time()
    now = datetime.now(timezone.utc)

    log(f"=== Pipeline ODRD v{PIPELINE_VERSION} — {now.strftime('%Y-%m-%d %H:%M:%S UTC')} ===")

    # 1. Validação de secrets
    missing = check_required_env()
    if missing:
        log(f"secrets obrigatórios ausentes: {missing}", "ERROR")
        return 1

    # 2. Carrega state
    state = state_manager.load_state(STATE_PATH)
    log(f"state carregado: {len(state.get('active_alerts', {}))} active, "
        f"{len(state.get('extended_window_alerts', {}))} extended")

    # 3. Consulta CEMADEN e reconcilia
    cemaden_ok = True
    try:
        cemaden_alerts = fetch_cemaden_active_alerts()
    except Exception as e:
        log(f"consulta ao CEMADEN falhou (pipeline continua com state anterior): {e}", "WARN")
        traceback.print_exc()
        cemaden_alerts = []
        cemaden_ok = False
        partial_failures_flag = True
    else:
        partial_failures_flag = False

    # CRÍTICO: só permite fechar alertas se a consulta foi bem-sucedida.
    # Se cemaden_ok=False, cemaden_alerts=[] seria interpretado como
    # "todos os alertas fecharam" — nunca queremos isso por engano.
    state, new_ids, closed_ids = state_manager.merge_new_alerts_from_cemaden(
        state, cemaden_alerts, now=now, close_missing=cemaden_ok,
    )
    if new_ids:
        log(f"alertas novos: {new_ids}", "OK")
    if closed_ids:
        log(f"alertas fechados no CEMADEN → extended_window: {closed_ids}", "OK")
    if not cemaden_ok:
        log("transições active→extended puladas (consulta CEMADEN falhou)", "WARN")

    # 4. Decide quais alertas processar neste ciclo
    decisions = state_manager.decide_alerts_to_process(state, now=now)
    to_collect = [d for d in decisions if d.action == "collect"]
    to_close = [d for d in decisions if d.action == "transition_to_closed"]
    skipped = [d for d in decisions if d.action == "skip_not_due"]

    log(f"decisões: {len(to_collect)} coletar, {len(to_close)} fechar 365d, "
        f"{len(skipped)} pular (não devidos)")

    if args.limit_alerts and len(to_collect) > args.limit_alerts:
        log(f"--limit-alerts={args.limit_alerts} aplicado, cortando de {len(to_collect)}", "WARN")
        to_collect = to_collect[:args.limit_alerts]

    # 5. Fecha alertas que completaram 365d
    for decision in to_close:
        state_manager.close_extended_alert(state, decision.alert_id)

    # 6. Se há alertas a coletar, roda o pipeline
    partial_failures: list[str] = []
    quota_used_this_run = 0
    live_data = None

    if to_collect:
        collect_ids = [d.alert_id for d in to_collect]
        try:
            faa_output = run_faa_pipeline_for_alerts(collect_ids, state)
        except Exception as e:
            log(f"falha catastrófica no faa_poc: {e}", "ERROR")
            traceback.print_exc()
            # Ainda commit do state para preservar transições, mas status = failed
            state_manager.update_run_metadata(state, "failed", int(time.time() - t_start),
                                              quota_used_this_run, now=now,
                                              pipeline_version=PIPELINE_VERSION)
            if not args.dry_run:
                state_manager.save_state(state, STATE_PATH)
            return 1

        # 7. BERTimbau
        try:
            comments_csv = faa_output / "youtube_comments_canonical.csv"
            if comments_csv.exists() and comments_csv.stat().st_size > 0:
                df_pred = predict_comments(
                    comments_csv=comments_csv,
                    model_repo="alvarocoutinho/bertimbau-weaklabels-odrd",
                    hf_token=os.environ["HF_TOKEN"],
                    subfolder="best_model",
                    batch_size=32,
                )
                df_pred.to_csv(faa_output / "predictions.csv", index=False)
                log(f"BERTimbau ok: {len(df_pred)} comentários classificados", "OK")
            else:
                import pandas as pd
                df_pred = pd.DataFrame()
                log("sem comentários para classificar (silêncio observável)", "WARN")
        except Exception as e:
            log(f"falha no BERTimbau: {e}", "ERROR")
            traceback.print_exc()
            partial_failures.append("bertimbau")
            import pandas as pd
            df_pred = pd.DataFrame()

        # 8. Build live.json
        try:
            live_data = build_live_json(
                output_dir=faa_output,
                predictions_df=df_pred,
                pilot_mode=True,   # até CEP aprovado
                dry_run=False,
                pipeline_version=PIPELINE_VERSION,
            )
        except Exception as e:
            log(f"falha ao construir live.json: {e}", "ERROR")
            traceback.print_exc()
            partial_failures.append("build_live")

        # 9. Marca coletas completas no state
        for decision in to_collect:
            # Descobrir vídeos coletados neste ciclo (do CSV)
            videos_this_alert = []
            try:
                import pandas as pd
                links_csv = faa_output / "youtube_alert_video_links.csv"
                if links_csv.exists():
                    links_df = pd.read_csv(links_csv)
                    cod = decision.alert_id.split("_")[-1]
                    videos_this_alert = links_df[
                        links_df["cod_alerta"].astype(str) == cod
                    ]["video_id"].tolist()
            except Exception as e:
                log(f"não foi possível ler videos coletados de {decision.alert_id}: {e}", "WARN")

            state_manager.mark_collection_complete(
                state, decision.alert_id, videos_collected=videos_this_alert, now=now,
            )

        # Estimativa de cota consumida (aproximação — refinar depois)
        quota_used_this_run = len(to_collect) * 100  # search.list ~= 100 unidades
    else:
        log("nenhum alerta devido neste ciclo — apenas atualiza metadados", "OK")

    # 10. Upload de crus para Drive
    if args.skip_gdrive:
        log("upload para Drive pulado (--skip-gdrive)", "INFO")
    elif not os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        log("upload para Drive pulado (GOOGLE_SERVICE_ACCOUNT_JSON ausente)", "INFO")
    elif to_collect:
        try:
            from odrd_bridge.gdrive import upload_run_to_drive
            run_id = now.strftime("%Y%m%d-%H%M%S")
            results = upload_run_to_drive(
                alert_ids=[d.alert_id for d in to_collect],
                faa_output_dir=FAA_OUTPUT_DIR,
                predictions_df=df_pred if 'df_pred' in locals() else None,
                pipeline_version=PIPELINE_VERSION,
                run_id=run_id,
                root_folder_name=os.environ.get("GDRIVE_FOLDER_NAME", "ODRD-piloto-tecnico"),
            )
            n_ok = sum(1 for r in results.values() if r)
            log(f"Drive: {n_ok}/{len(to_collect)} alertas com upload bem-sucedido", "OK")
            if n_ok < len(to_collect):
                partial_failures.append("gdrive")
        except Exception as e:
            log(f"falha geral no upload para Drive: {e}", "WARN")
            traceback.print_exc()
            partial_failures.append("gdrive")
    else:
        log("upload para Drive pulado (nenhum alerta processado neste ciclo)", "INFO")

    # 11. Persistência final
    duration = int(time.time() - t_start)
    if partial_failures or partial_failures_flag:
        status = "partial"
    else:
        status = "success"

    state_manager.update_run_metadata(
        state, status, duration, quota_used_this_run,
        now=now, pipeline_version=PIPELINE_VERSION,
    )

    if args.dry_run:
        log(f"--dry-run: NÃO persistindo state/live (duration={duration}s)", "WARN")
        return 0

    state_manager.save_state(state, STATE_PATH)

    if live_data is not None:
        save_json(live_data, LIVE_PATH)

    log(f"=== FIM — status={status}, duration={duration}s, quota={quota_used_this_run} ===",
        "OK" if status == "success" else "WARN")

    # Exit code
    if status == "failed":
        return 1
    elif status == "partial":
        return 2  # workflow trata como manutenção, não como falha
    return 0


if __name__ == "__main__":
    sys.exit(main())
