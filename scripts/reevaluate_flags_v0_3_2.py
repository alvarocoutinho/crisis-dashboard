"""Reavaliação única das flags pelo critério municipal (pipeline 0.3.2).

Contexto: até a v0.3.1 as flags eram concedidas contando todos os vídeos
aceitos pelo filtro de relevância, inclusive os de escopo estadual/regional
("SP", "Grande São Paulo"). A auditoria de 13/10/2026 mostrou alertas
`prioritario` sem nenhum vídeo que nomeie o município. Desde a v0.3.2 só
contam vídeos com evidência municipal (`video_evidence` ≠ "nenhuma"); este
script aplica a mesma regra às flags já concedidas — inclusive rebaixando,
exceção única e documentada à regra "sem regressão".

O que faz:
  1. Semeia `valid_comments_by_video` (comentários válidos por vídeo) a partir
     do histórico git do live.json: para cada vídeo, a maior amostra observada;
     válidos estimados pela fração rotulada do alerta naquela amostra. Guarda
     também o teto (todos os comentários do vídeo) para testar a robustez.
  2. Recalcula os contadores municipais e a flag pelo critério v0.3.2.
  3. Registra a proveniência: `flag_reassessment`, `flag_legacy_v0_3_1` e uma
     entrada em `flag_history` com `reason`.
  4. Reconstrói src/data/alertas_agregados.csv a partir do histórico do
     state.json (até a v0.3.1 o log não era commitado pelo workflow).
  5. Atualiza os campos de flag no live.json e grava um relatório sem texto
     de comentário em docs/reavaliacao_flags_v0_3_2.csv.

Idempotente: alertas que já têm `flag_reassessment` não são reavaliados de
novo. Precisa do histórico completo (fetch-depth: 0).

Uso:
    python scripts/reevaluate_flags_v0_3_2.py --dry-run
    python scripts/reevaluate_flags_v0_3_2.py
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from odrd_bridge import state_manager as sm  # noqa: E402

LIVE_REL = "src/data/live.json"
STATE_REL = "src/data/state.json"
LOG_REL = "src/data/alertas_agregados.csv"
REPORT_REL = "docs/reavaliacao_flags_v0_3_2.csv"
REASON = "reavaliação v0.3.2: só vídeos que nomeiam o município contam"
BUCKETS = ("active_alerts", "extended_window_alerts", "archived_alerts")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], check=True,
                          capture_output=True, text=True).stdout


def _history(rel: str):
    for sha in _git("log", "--format=%H", "--", rel).split():  # mais recente primeiro
        try:
            yield sha, json.loads(_git("show", f"{sha}:{rel}"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue


def per_video_from_live_history() -> dict[str, dict[str, tuple[int, int]]]:
    """{alert_id: {video_id: (válidos_estimados, todos)}} na maior amostra de cada vídeo."""
    best: dict[str, dict[str, tuple[int, int]]] = defaultdict(dict)
    for _sha, live in _history(LIVE_REL):
        for a in live.get("alerts", []):
            n_all = int(a.get("n_comments") or 0)
            labeled = (n_all - int(a.get("unlabeled") or 0)) / n_all if n_all else 0.0
            for v in a.get("videos") or []:
                n = int(v.get("n_comments") or 0)
                vid = str(v.get("video_id"))
                if n and (vid not in best[a["id"]] or n > best[a["id"]][vid][1]):
                    best[a["id"]][vid] = (round(n * labeled), n)
    return best


def flag_for(n_videos_mun: int, n_valid_mun: int, n_videos_valid_mun: int) -> str:
    if (n_valid_mun >= sm.PROMOTE_PRIORITARIO_N_COMMENTS
            and n_videos_valid_mun >= sm.PROMOTE_PRIORITARIO_N_VIDEOS):
        return "prioritario"
    return "acompanhamento" if n_videos_mun >= 1 else "alerta"


def reevaluate(state: dict, best: dict, now: datetime) -> list[dict]:
    now_iso = sm._iso_utc(now)
    report = []
    for bucket in BUCKETS:
        for aid, meta in state.get(bucket, {}).items():
            if meta.get("flag_reassessment"):
                continue
            seeded = False
            if "valid_comments_by_video" not in meta and best.get(aid):
                meta["valid_comments_by_video"] = {v: est for v, (est, _all) in best[aid].items() if est > 0}
                meta["valid_comments_by_video_source"] = "estimado_historico_live_v0.3.2"
                seeded = True
                total = sum(meta["valid_comments_by_video"].values())
                if total > int(meta.get("n_comments_valid", 0)):
                    meta["n_comments_valid"] = total  # soma por vídeo é a melhor estimativa
            sm.recompute_municipal_counters(meta)

            ev = meta.get("video_evidence", {}) or {}
            mun = meta.get("videos_with_valid_comments_municipal", [])
            new_flag = flag_for(meta["n_videos_municipais"], meta["n_comments_valid_municipal"], len(mun))
            # Robustez: o teto (todos os comentários dos vídeos municipais) muda a decisão?
            upper = sum(best.get(aid, {}).get(v, (0, 0))[1] for v in meta.get("videos_collected", [])
                        if sm._EVIDENCE_RANK.get(ev.get(v), 0) > 0)
            upper_videos = sum(1 for v in meta.get("videos_collected", [])
                               if sm._EVIDENCE_RANK.get(ev.get(v), 0) > 0
                               and best.get(aid, {}).get(v, (0, 0))[1] > 0)
            flag_upper = flag_for(meta["n_videos_municipais"], upper, upper_videos)

            old_flag = meta.get("flag") or (meta.get("flag_history") or [{}])[-1].get("flag", "alerta")
            meta["flag_reassessment"] = {
                "at": now_iso, "from": old_flag, "to": new_flag, "criterio": sm.FLAG_CRITERION,
                "n_videos": len(meta.get("videos_collected", [])),
                "n_videos_municipais": meta["n_videos_municipais"],
                "n_comments_valid_municipal": meta["n_comments_valid_municipal"],
                "n_videos_with_valid_municipal": len(mun),
                "contagem": "estimada_historico_live" if seeded or meta.get("valid_comments_by_video_source") else "observada",
                "robusta_ao_teto": flag_upper == new_flag,
            }
            if new_flag != old_flag:
                meta["flag_legacy_v0_3_1"] = old_flag
                meta["flag"] = new_flag
                meta.setdefault("flag_history", []).append({
                    "flag": new_flag, "at": now_iso, "criterio": sm.FLAG_CRITERION, "reason": REASON,
                })
                if bucket != "archived_alerts" and not meta.get("window_finalized_at"):
                    meta["next_collection_at"] = sm._next_collection_from_flag(new_flag, now)
            report.append({
                "alert_id": aid, "municipio": meta.get("municipio"), "uf": meta.get("uf"),
                "aberto_em": meta.get("opened_at"), "situacao": bucket.replace("_alerts", ""),
                "flag_antes": old_flag, "flag_depois": new_flag,
                "n_videos": len(meta.get("videos_collected", [])),
                "n_videos_municipais": meta["n_videos_municipais"],
                "n_comentarios_validos_total": meta.get("n_comments_valid", 0),
                "n_comentarios_validos_municipais_est": meta["n_comments_valid_municipal"],
                "n_comentarios_municipais_teto": upper,
                "n_videos_municipais_com_comentario": len(mun),
                "decisao_robusta_ao_teto": flag_upper == new_flag,
            })
    return report


def rebuild_aggregate_log(state: dict) -> dict:
    """Reconstrói o log agregado: um alerta = uma linha de n_emitidos."""
    last_seen: dict[str, dict] = {}
    for _sha, old in _history(STATE_REL):  # mais recente primeiro: guarda a 1ª ocorrência
        for bucket in BUCKETS:
            for aid, meta in (old.get(bucket) or {}).items():
                last_seen.setdefault(aid, meta)
    current = {aid: (bucket, meta) for bucket in BUCKETS for aid, meta in state.get(bucket, {}).items()}
    log: dict = {}
    for aid, meta in last_seen.items():
        bucket, meta = current.get(aid, (None, meta))
        if not meta.get("codibge"):
            continue
        sm.bump_aggregate_log(log, meta, "n_emitidos")
        flag = meta.get("flag", "alerta")
        if bucket is None:
            sm.bump_aggregate_log(log, meta, "n_arquivados_alerta_puro")
        if flag in ("acompanhamento", "prioritario"):
            sm.bump_aggregate_log(log, meta, "n_migrados_acompanhamento")
        if flag == "prioritario":
            sm.bump_aggregate_log(log, meta, "n_migrados_prioritario")
        if bucket == "archived_alerts":
            sm.bump_aggregate_log(log, meta, "n_arquivados_completos")
    return log


def patch_live(live: dict, state: dict) -> None:
    metas = {aid: m for b in BUCKETS for aid, m in state.get(b, {}).items()}
    for entry in live.get("alerts", []):
        m = metas.get(entry.get("id"))
        if not m:
            continue
        for k in ("flag", "flag_history", "n_comments_valid", "n_comments_valid_municipal",
                  "videos_with_valid_comments_municipal", "flag_reassessment", "next_collection_at"):
            entry[k] = m.get(k)
        # mesmos campos que o build_live grava (v0.3.1/v0.3.2), sem esperar o próximo ciclo
        ev = m.get("video_evidence", {}) or {}
        for v in entry.get("videos") or []:
            v["municipal_evidence"] = ev.get(str(v.get("video_id")), "")
        videos = entry.get("videos") or []
        entry["n_videos_municipais"] = sum(1 for v in videos if v["municipal_evidence"] not in ("", "nenhuma"))
        entry["n_videos_verificados"] = sum(1 for v in videos if v["municipal_evidence"] != "")
        entry["n_comments_municipais"] = sum(
            int(v.get("n_comments") or 0) for v in videos if v["municipal_evidence"] not in ("", "nenhuma"))
    for entry in live.get("archived_alerts", []):
        m = state.get("archived_alerts", {}).get(entry.get("id"))
        if not m:
            continue
        entry["flag_final"] = m.get("flag") or entry.get("flag_final")
        entry["flag_history"] = m.get("flag_history", [])
        for k in ("n_comments_valid", "n_videos_municipais", "n_comments_valid_municipal", "flag_reassessment"):
            entry[k] = m.get(k)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        print("ERRO: repositório raso. Rode `git fetch --unshallow` (no Actions: fetch-depth: 0).")
        return 1

    now = datetime.now(timezone.utc)
    state = json.loads((REPO_ROOT / STATE_REL).read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    live = json.loads((REPO_ROOT / LIVE_REL).read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)

    report = reevaluate(state, per_video_from_live_history(), now)
    changed = [r for r in report if r["flag_antes"] != r["flag_depois"]]
    print(f"{len(report)} alertas reavaliados; {len(changed)} mudam de flag")
    for r in sorted(report, key=lambda r: (r["flag_antes"], r["alert_id"])):
        mark = "→" if r["flag_antes"] != r["flag_depois"] else "="
        warn = "" if r["decisao_robusta_ao_teto"] else "  [sensível à estimativa]"
        print(f"  {r['alert_id']:18s} {str(r['municipio'])[:22]:22s} {r['flag_antes']:>14s} {mark} {r['flag_depois']:14s} "
              f"vídeos {r['n_videos_municipais']}/{r['n_videos']} mun.; válidos mun. "
              f"{r['n_comentarios_validos_municipais_est']} (teto {r['n_comentarios_municipais_teto']}) "
              f"em {r['n_videos_municipais_com_comentario']} vídeo(s){warn}")
    if not report:
        print("nada a reavaliar (já aplicado)")

    log = rebuild_aggregate_log(state)
    totals = defaultdict(int)
    for row in log.values():
        for k in sm.AGGREGATE_LOG_HEADER[6:]:
            totals[k] += row[k]
    print(f"log agregado reconstruído: {len(log)} linhas; {dict(totals)}")

    if args.dry_run:
        print("--dry-run: nada gravado")
        return 0
    patch_live(live, state)
    (REPO_ROOT / STATE_REL).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (REPO_ROOT / LIVE_REL).write_text(json.dumps(live, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sm.save_aggregate_log(log, REPO_ROOT / LOG_REL)
    if report:
        path = REPO_ROOT / REPORT_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(report[0]))
            w.writeheader()
            w.writerows(report)
    print("gravados state.json, live.json, alertas_agregados.csv" + (f" e {REPORT_REL}" if report else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
