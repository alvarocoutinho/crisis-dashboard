"""Observação horária do painel de alertas do CEMADEN (ver odrd_cemaden/observer.py).

Grava, em ``data/cemaden/``:
- ``alertas_observados.csv``: catálogo, uma linha por alerta, com primeira e
  última observação, níveis vistos, duração e se o pipeline chegou a vê-lo;
- ``capturas.csv``: uma linha por consulta (status, contagens, hash);
- ``snapshots/AAAA-MM.jsonl``: o JSON bruto de cada consulta cujo conteúdo
  mudou em relação à anterior.

Uso:
    python scripts/observe_cemaden.py [--arquivo resposta.json] [--capturado-em ISO] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from faa_poc.constants import CEMADEN_ALERTS_URL  # noqa: E402
from odrd_cemaden import observer  # noqa: E402

DIR = REPO / "data" / "cemaden"
CATALOG = DIR / "alertas_observados.csv"
CAPTURES = DIR / "capturas.csv"
STATE = REPO / "src" / "data" / "state.json"


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _append(path: Path, fields: list[str], row: dict) -> None:
    novo = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if novo:
            w.writeheader()
        w.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivo", type=Path, help="resposta JSON já baixada (teste)")
    ap.add_argument("--capturado-em", help="horário UTC da captura de --arquivo")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    agora = args.capturado_em or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cap = {"captured_at_utc": agora}
    try:
        if args.arquivo:
            payload = json.loads(args.arquivo.read_text(encoding="utf-8"))
        else:
            r = requests.get(CEMADEN_ALERTS_URL, timeout=(20, 60))
            r.raise_for_status()
            payload = r.json()
        alertas = payload.get("alertas")
        if not isinstance(alertas, list):
            raise ValueError("resposta sem lista 'alertas'")
    except Exception as e:  # noqa: BLE001 — registrar e sair limpo; a próxima hora tenta de novo
        cap.update(status="falha", erro=f"{type(e).__name__}: {e}"[:300])
        print(f"::warning title=CEMADEN indisponível::{cap['erro']}")
        if not args.dry_run:
            _append(CAPTURES, observer.CAPTURE_FIELDS, cap)
        return 0

    state_ids = observer.state_alert_ids(json.loads(STATE.read_text(encoding="utf-8"))) if STATE.exists() else set()
    catalog = {r["cod_alerta"]: r for r in _read(CATALOG)}
    contagens = observer.update_catalog(catalog, alertas, agora, state_ids)
    sha = observer.snapshot_hash(alertas)
    anteriores = [c for c in _read(CAPTURES) if c.get("status") == "ok"]
    mudou = not anteriores or anteriores[-1].get("sha256") != sha
    cap.update(status="ok", erro="", sha256=sha, **contagens)

    print(f"CEMADEN: {contagens['n_total']} alertas ativos ({contagens['n_relevantes']} no escopo do pipeline) | "
          f"novos {contagens['n_novos']} | fechados {contagens['n_fechados']} | "
          f"relevantes fechados sem passar pelo pipeline: {contagens['n_relevantes_fechados_fora_do_state']} | "
          f"níveis {contagens['niveis']}")
    if args.dry_run:
        print("--dry-run: nada gravado")
        return 0

    rows = sorted(catalog.values(), key=lambda r: (r.get("first_seen_utc", ""), r.get("cod_alerta", "")))
    _write(CATALOG, observer.CATALOG_FIELDS, rows)
    _append(CAPTURES, observer.CAPTURE_FIELDS, cap)
    if mudou:
        snap = DIR / "snapshots" / f"{agora[:7]}.jsonl"
        snap.parent.mkdir(parents=True, exist_ok=True)
        with snap.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"captured_at_utc": agora, "alertas": alertas}, ensure_ascii=False) + "\n")
    fora = [r for r in rows if str(r.get("aberto")) == "0" and str(r.get("relevante_pipeline")) == "1"
            and str(r.get("visto_no_state")) != "1"]
    print(f"::notice title=CEMADEN horário::{contagens['n_total']} ativos; {len(rows)} no catálogo; "
          f"{len(fora)} relevantes já fechados sem nunca entrar no pipeline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
