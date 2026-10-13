"""Evidência municipal para os vídeos já coletados (v0.3.1).

Para cada vínculo alerta–vídeo do state, verifica se o vídeo NOMEIA o
município do alerta, usando título + descrição completa (API oficial,
``videos.list part=snippet``: 1 unidade por lote de 50 vídeos) e,
opcionalmente, transcrições locais. Grava só o rótulo da evidência no
state (``video_evidence``), nunca a descrição nem a transcrição.

Uso:
    # no GitHub Actions (workflow "ODRD Evidência municipal — backfill"):
    python scripts/backfill_video_evidence.py [--dry-run]

    # localmente, somando transcrições já baixadas (pasta texto/<id>.txt):
    python scripts/backfill_video_evidence.py --transcripts caminho/para/texto --no-api

Idempotente: a evidência só é promovida, nunca rebaixada.
"""
from __future__ import annotations

import argparse
import collections
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from faa_poc.constants import YT_BASE  # noqa: E402
from faa_poc.evidence import municipal_evidence  # noqa: E402
from odrd_bridge import state_manager  # noqa: E402

STATE_PATH = REPO_ROOT / "src" / "data" / "state.json"
BUCKETS = ("active_alerts", "extended_window_alerts", "archived_alerts")


def fetch_metadata(video_ids: list[str], key: str) -> tuple[dict[str, dict], int]:
    """Título e descrição de até 50 vídeos por chamada. Retorna (metadados, unidades)."""
    meta, units = {}, 0
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        r = requests.get(f"{YT_BASE}/videos", timeout=30, params={
            "part": "snippet", "id": ",".join(batch), "key": key, "maxResults": 50})
        units += 1
        if r.status_code != 200:
            raise RuntimeError(f"videos.list falhou: {r.status_code} {r.text[:200]}")
        for item in r.json().get("items", []):
            s = item.get("snippet", {})
            meta[item["id"]] = {"title": s.get("title", ""), "description": s.get("description", "")}
    return meta, units


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--transcripts", type=Path, help="pasta com <video_id>.txt (transcrições locais)")
    ap.add_argument("--no-api", action="store_true", help="não chama a API (só transcrições locais)")
    args = ap.parse_args()

    state = state_manager.load_state(STATE_PATH)
    links = [(b, aid, m, v) for b in BUCKETS for aid, m in state.get(b, {}).items()
             for v in m.get("videos_collected", [])]
    video_ids = sorted({v for *_, v in links})
    print(f"{len(links)} vínculos, {len(video_ids)} vídeos únicos")

    meta, units = {}, 0
    if not args.no_api:
        key = os.environ.get("YOUTUBE_API_KEY")
        if not key:
            print("::error::YOUTUBE_API_KEY ausente")
            return 1
        meta, units = fetch_metadata(video_ids, key)
        print(f"metadados de {len(meta)}/{len(video_ids)} vídeos ({units} unidades de cota)")
        missing = sorted(set(video_ids) - set(meta))
        if missing:
            print(f"::notice title=indisponíveis::{len(missing)} vídeos removidos/privados: {' '.join(missing[:20])}")

    transcripts = {}
    if args.transcripts:
        for p in args.transcripts.glob("*.txt"):
            transcripts[p.stem] = p.read_text(encoding="utf-8", errors="ignore")
        print(f"{len(transcripts)} transcrições locais")

    counts = collections.Counter()
    per_alert = {}
    for bucket, aid, m, vid in links:
        md = meta.get(vid)
        tr = transcripts.get(vid, "")
        if md is None and not tr:
            continue  # sem nada para verificar
        ev = municipal_evidence(m.get("municipio", ""), m.get("uf", ""),
                                title=(md or {}).get("title", ""),
                                description=(md or {}).get("description", ""), transcript=tr)
        if md is None and ev == "nenhuma":
            continue  # só transcrição, e ela não cita: não é prova de ausência
        state_manager.merge_video_evidence(m, {vid: ev})
        counts[ev] += 1
        per_alert[aid] = (m.get("municipio"), m.get("n_videos_municipais", 0), len(m.get("videos_collected", [])))

    total = sum(counts.values())
    for ev, n in counts.most_common():
        print(f"::notice title=evidência {ev}::{n} de {total} vínculos")
    zero = [f"{mun} (0/{nv})" for _, (mun, nm, nv) in sorted(per_alert.items()) if nm == 0 and nv > 0]
    print(f"::notice title=alertas sem vídeo que cite o município::{len(zero)}: {'; '.join(zero)[:900]}")

    if args.dry_run:
        print("--dry-run: state não gravado")
        return 0
    if units:
        q = state_manager.roll_quota_day(state, datetime.now(timezone.utc))
        q["used_today"] = int(q.get("used_today", 0)) + units
    state_manager.save_state(state, STATE_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
