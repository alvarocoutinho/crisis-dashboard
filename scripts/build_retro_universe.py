"""Universo da coleta retrospectiva (v0.3.2+): alertas a re-buscar no YouTube.

Contexto: com a cota estourada em 45 de 60 dias (25/08–13/10/2026), alertas
sem vídeo eram os últimos da fila e, até a v0.3, falha de cota era registrada
como "nenhum vídeo encontrado". Os 449 alertas que saíram do state como
"alerta puro" estão contados como silêncio sem prova de que a busca rodou.

Gera data/retro/universo_alertas.csv (só metadados públicos do CEMADEN):
  grupo=calibracao : alertas com vídeos conhecidos (state atual). A busca
                     retrospectiva neles mede quanto ela reencontra.
  grupo=silencio   : alertas que saíram do state sem vídeo.
  amostra=1        : amostra sistemática de N alertas de silêncio, ordenados
                     por UF, mês e abertura (estratificação implícita,
                     autoponderada), início aleatório com semente fixa.
  ordem            : ordem de execução (calibração → amostra → restante).

Precisa do histórico completo do git (`git fetch --unshallow`).

Uso: python scripts/build_retro_universe.py [--n-amostra 120] [--semente 20261013]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent.resolve()
STATE_REL = "src/data/state.json"
OUT = REPO / "data" / "retro" / "universo_alertas.csv"
BUCKETS = ("active_alerts", "extended_window_alerts", "archived_alerts")
FIELDS = ["ordem", "alert_id", "cod_alerta", "municipio", "uf", "codibge", "evento", "nivel",
          "opened_at", "closed_at", "mes", "grupo", "amostra", "visto_no_state_de", "visto_no_state_ate",
          "videos_conhecidos", "videos_municipais_conhecidos"]


def _git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *a], check=True, capture_output=True, text=True).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-amostra", type=int, default=120)
    ap.add_argument("--semente", type=int, default=20261013)
    args = ap.parse_args()
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        print("ERRO: repositório raso; rode `git fetch --unshallow`.")
        return 1

    seen: dict[str, dict] = {}
    for line in filter(None, _git("log", "--reverse", "--format=%H %cI", "--", STATE_REL).split("\n")):
        sha, date = line.split()
        try:
            state = json.loads(_git("show", f"{sha}:{STATE_REL}"))
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        for b in BUCKETS:
            for aid, m in (state.get(b) or {}).items():
                rec = seen.setdefault(aid, {"de": date, "meta": {}})
                rec["ate"] = date
                # metadados não-nulos mais recentes (o schema v0.1 não tinha evento)
                rec["meta"].update({k: v for k, v in m.items() if v not in (None, "", [])})

    current = json.loads((REPO / STATE_REL).read_text(encoding="utf-8"))
    present = {aid: m for b in BUCKETS for aid, m in current.get(b, {}).items()}

    rows = []
    for aid, rec in seen.items():
        m = present.get(aid) or rec["meta"]
        vids = m.get("videos_collected", []) if aid in present else []
        ev = m.get("video_evidence", {}) or {}
        if aid in present and not vids:
            continue  # alerta vivo sem vídeo: a coleta ao vivo (v0.3+) já cobre
        rows.append({
            "alert_id": aid, "cod_alerta": aid.rsplit("_", 1)[-1], "municipio": m.get("municipio", ""),
            "uf": m.get("uf", ""), "codibge": m.get("codibge", ""), "evento": m.get("evento") or "",
            "nivel": m.get("nivel_atual", ""), "opened_at": m.get("opened_at", ""),
            "closed_at": m.get("closed_at") or "", "mes": (m.get("opened_at") or "")[:7],
            "grupo": "calibracao" if aid in present else "silencio", "amostra": 0,
            "visto_no_state_de": rec["de"], "visto_no_state_ate": rec["ate"],
            "videos_conhecidos": ";".join(sorted(vids)),
            "videos_municipais_conhecidos": ";".join(sorted(v for v in vids if ev.get(v) not in (None, "", "nenhuma"))),
        })

    silencio = sorted((r for r in rows if r["grupo"] == "silencio"), key=lambda r: (r["uf"], r["mes"], r["opened_at"]))
    n = min(args.n_amostra, len(silencio))
    step = len(silencio) / n
    start = random.Random(args.semente).random() * step
    for i in range(n):
        silencio[int(start + i * step)]["amostra"] = 1

    calib = sorted((r for r in rows if r["grupo"] == "calibracao"), key=lambda r: r["opened_at"])
    amostra = sorted((r for r in silencio if r["amostra"]), key=lambda r: r["opened_at"])
    resto = sorted((r for r in silencio if not r["amostra"]), key=lambda r: r["opened_at"])
    ordered = calib + amostra + resto
    for i, r in enumerate(ordered, 1):
        r["ordem"] = i

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(ordered)
    sem_evento = sum(1 for r in ordered if not r["evento"])
    print(f"{len(calib)} calibração, {len(amostra)} amostra, {len(resto)} restante "
          f"(semente {args.semente}); {sem_evento} sem tipo de evento → {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
