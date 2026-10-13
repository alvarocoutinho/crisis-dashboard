"""Restaura no live.json o conteúdo apagado por falhas de cota (v0.2.x → v0.3).

Contexto: até a v0.2.2, quando a coleta de um alerta falhava por cota
(quota_exhausted), o build_live reconstruía o entry a partir de CSVs vazios e
gravava n_comments=0 / n_videos=0 / "silent:no_videos_found" por cima do
conteúdo bom do ciclo anterior. Este script percorre o histórico git de
src/data/live.json e, para cada alerta hoje "esvaziado", recupera o conteúdo
da versão histórica com MAIS comentários (amostra mais completa observada; em
empate, a mais recente). Só campos de conteúdo são restaurados; campos
operacionais continuam vindo do state.

A proveniência fica registrada em `content_restored_from` (commit + data de
geração) para auditoria.

Uso (na raiz do repo, com histórico completo — não roda no Actions, que faz
checkout com fetch-depth=1):

    git fetch --unshallow   # se necessário
    python scripts/restore_live_from_history.py [--dry-run] [--recount-state]

--recount-state: até a v0.2.2 o n_comments_valid do state era somado de novo a
cada ciclo (comentários recoletados contados como novos), inflando-o ~36×.
Com esta opção o state recebe a melhor estimativa disponível — comentários com
≥1 rótulo do modelo na maior amostra observada no live.json (limite inferior
dos comentários únicos). O valor antigo é preservado em
`n_comments_valid_legacy`. As flags NÃO são alteradas (regra "sem regressão").
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
LIVE_REL = "src/data/live.json"
STATE_REL = "src/data/state.json"

CONTENT_FIELDS = (
    "n_comments", "n_videos", "unlabeled", "unlabeled_pct", "date_range",
    "distribution", "timeline", "videos", "all_samples",
)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO_ROOT), *args], check=True,
                          capture_output=True, text=True).stdout


def _is_blank(entry: dict) -> bool:
    return not entry.get("n_videos") and not entry.get("n_comments")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recount-state", action="store_true")
    args = ap.parse_args()

    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        print("AVISO: repositório raso — o histórico pode estar incompleto. Rode `git fetch --unshallow`.")

    live_path = REPO_ROOT / LIVE_REL
    live = json.loads(live_path.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
    state = json.loads((REPO_ROOT / STATE_REL).read_text(encoding="utf-8"))
    state_alerts = {**state.get("active_alerts", {}), **state.get("extended_window_alerts", {})}

    # Candidatos: todos os alertas com vídeos aderentes no state. A amostra de
    # cada ciclo v0.2 era limitada (200 tópicos mais recentes por vídeo), então
    # a maior amostra histórica é a mais completa para a janela do evento.
    targets = {
        a["id"] for a in live["alerts"]
        if state_alerts.get(a["id"], {}).get("n_videos_aderentes", 0) > 0
    }
    print(f"{sum(_is_blank(a) for a in live['alerts'] if a['id'] in targets)} alertas esvaziados; "
          f"{len(targets)} com vídeos registrados no state")

    best: dict[str, tuple[int, str, str, dict]] = {}
    commits = _git("log", "--format=%H", "--", LIVE_REL).split()
    for sha in commits:  # mais recente primeiro
        try:
            old = json.loads(_git("show", f"{sha}:{LIVE_REL}"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        for entry in old.get("alerts", []):
            aid = entry.get("id")
            if aid not in targets or _is_blank(entry):
                continue
            n = int(entry.get("n_comments") or 0)
            if aid not in best or n > best[aid][0]:  # empate: mantém o mais recente
                best[aid] = (n, sha, old.get("generated_at", ""), entry)

    restored = 0
    for entry in live["alerts"]:
        hit = best.get(entry["id"])
        if not hit:
            continue
        n, sha, generated_at, old = hit
        if not _is_blank(entry) and n <= int(entry.get("n_comments") or 0):
            continue  # o atual já é a maior amostra
        for field in CONTENT_FIELDS:
            entry[field] = old.get(field)
        entry["collection_health"] = old.get("collection_health", entry.get("collection_health"))
        entry["content_restored_from"] = {"commit": sha[:12], "generated_at": generated_at}
        restored += 1
        print(f"  {entry['id']}: {n} comentários, {old.get('n_videos')} vídeos ← {sha[:7]} ({generated_at})")

    missing = sorted(targets - set(best))
    if missing:
        print(f"sem versão histórica com conteúdo: {missing}")
    print(f"{restored} entries restaurados com a maior amostra histórica")

    if not args.dry_run and restored:
        live_path.write_text(json.dumps(live, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"gravado {live_path}")

    if args.recount_state:
        recount_state(live, state)
        if not args.dry_run:
            (REPO_ROOT / STATE_REL).write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"gravado {STATE_REL}")
    return 0


def recount_state(live: dict, state: dict) -> None:
    """Substitui n_comments_valid inflado pela estimativa observada."""
    by_id = {a["id"]: a for a in live.get("alerts", [])}
    for bucket in ("active_alerts", "extended_window_alerts"):
        for aid, meta in state.get(bucket, {}).items():
            if meta.get("counters_integrity") not in (None, "inflated_pre_v0.3"):
                continue
            if "n_comments_valid_legacy" in meta or not meta.get("n_comments_valid"):
                continue
            entry = by_id.get(aid)
            if not entry:
                continue
            observed = int(entry.get("n_comments") or 0) - int(entry.get("unlabeled") or 0)
            meta["n_comments_valid_legacy"] = meta["n_comments_valid"]
            meta["n_comments_valid"] = max(0, observed)
            meta["counters_integrity"] = "recounted_from_live_history_v0.3"
            print(f"  recontagem {aid}: {meta['n_comments_valid_legacy']} → {meta['n_comments_valid']}")


if __name__ == "__main__":
    raise SystemExit(main())
