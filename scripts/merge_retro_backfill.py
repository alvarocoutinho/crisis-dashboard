"""Incorpora ao repositório o resultado da coleta retrospectiva (notebook Colab).

Lê o resultados_alertas.csv gerado por notebooks/ODRD_coleta_retrospectiva.ipynb
(só contagens e IDs de vídeo, sem títulos nem comentários) e grava/atualiza
data/retro/resultados_alertas.csv, um registro por alerta (o mais recente vence).
Não altera state.json, live.json, flags nem o painel: o regime retrospectivo
fica separado do prospectivo e entra na análise de H1 como sensibilidade.

Uso: python scripts/merge_retro_backfill.py --resultados caminho/resultados_alertas.csv
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

REPO = Path(__file__).parent.parent.resolve()
DEST = REPO / "data" / "retro" / "resultados_alertas.csv"
PERMITIDOS = ["alert_id", "grupo", "amostra", "ordem", "municipio", "uf", "evento", "opened_at", "coletado_em",
              "codigo_pipeline", "busca_de", "busca_ate", "consultas", "status", "erro", "n_candidatos", "n_aceitos",
              "n_aceitos_municipais", "n_candidatos_municipais", "ids_aceitos", "ids_aceitos_municipais",
              "n_conhecidos", "n_conhecidos_nos_candidatos", "n_conhecidos_aceitos", "n_conhecidos_indisponiveis",
              "n_municipais_conhecidos", "n_municipais_conhecidos_reencontrados", "n_comentarios_janela",
              "status_comentarios"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


def _int(x: str) -> int:
    try:
        return int(float(x or 0))
    except ValueError:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resultados", required=True, type=Path)
    args = ap.parse_args()
    with args.resultados.open(encoding="utf-8-sig") as fh:
        novos = list(csv.DictReader(fh))
    extras = set(novos[0]) - set(PERMITIDOS) if novos else set()
    if extras:
        print(f"colunas ignoradas (não vão para o repositório): {sorted(extras)}")
    universo = {r["alert_id"] for r in csv.DictReader((REPO / "data/retro/universo_alertas.csv").open(encoding="utf-8"))}
    fora = [r["alert_id"] for r in novos if r["alert_id"] not in universo]
    if fora:
        print(f"ERRO: {len(fora)} alertas fora do universo (ex.: {fora[:3]}); arquivo errado?")
        return 1

    atuais = {}
    if DEST.exists():
        atuais = {r["alert_id"]: r for r in csv.DictReader(DEST.open(encoding="utf-8"))}
    for r in novos:
        if r.get("status") == "ok" and r["coletado_em"] >= atuais.get(r["alert_id"], {}).get("coletado_em", ""):
            atuais[r["alert_id"]] = {k: r.get(k, "") for k in PERMITIDOS}
    linhas = sorted(atuais.values(), key=lambda r: _int(r["ordem"]))
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with DEST.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=PERMITIDOS)
        w.writeheader()
        w.writerows(linhas)
    print(f"{len(linhas)} alertas em {DEST.relative_to(REPO)}")

    cal = [r for r in linhas if r["grupo"] == "calibracao" and _int(r["n_municipais_conhecidos"]) > 0]
    if cal:
        k = sum(1 for r in cal if _int(r["n_aceitos_municipais"]) > 0)
        p, lo, hi = wilson(k, len(cal))
        print(f"calibração: sensibilidade por alerta {k}/{len(cal)} = {p:.0%} [IC95% {lo:.0%}–{hi:.0%}]")
    am = [r for r in linhas if r["grupo"] == "silencio" and r["amostra"] == "1"]
    if am:
        k = sum(1 for r in am if _int(r["n_aceitos_municipais"]) > 0)
        p, lo, hi = wilson(k, len(am))
        print(f"amostra: silêncio refutado {k}/{len(am)} = {p:.0%} [IC95% {lo:.0%}–{hi:.0%}] "
              f"→ ~{p * 449:.0f} [{lo * 449:.0f}–{hi * 449:.0f}] de 449 (limite inferior)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
