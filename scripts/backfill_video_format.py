"""Formato dos vídeos já coletados (v0.3.4): short | longo | ao_vivo | indeterminado.

Usa a mesma regra do pipeline (``faa_poc.youtube.video_format``): duração
(``contentDetails``), proporção do player (``player`` com ``maxHeight``) e
transmissão (``liveStreamingDetails``). Custo: 1 unidade a cada 50 vídeos,
nenhuma busca. Grava só o rótulo do formato no state (``video_format``).

Uso (GitHub Actions, workflow "ODRD Formato dos vídeos — backfill"):
    python scripts/backfill_video_format.py [--dry-run]

Idempotente: um formato definido nunca volta a ``indeterminado``.
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
from faa_poc.youtube import EMBED_MAX_HEIGHT, video_format  # noqa: E402
from odrd_bridge import state_manager  # noqa: E402

STATE_PATH = REPO_ROOT / "src" / "data" / "state.json"
BUCKETS = ("active_alerts", "extended_window_alerts", "archived_alerts")
PARTS = "snippet,contentDetails,player,liveStreamingDetails"


def fetch_formats(video_ids: list[str], key: str) -> tuple[dict[str, dict], int]:
    """Formato de até 50 vídeos por chamada. Retorna (formatos, unidades)."""
    out, units = {}, 0
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        r = requests.get(f"{YT_BASE}/videos", timeout=30, params={
            "part": PARTS, "id": ",".join(batch), "maxHeight": EMBED_MAX_HEIGHT, "key": key})
        units += 1
        if r.status_code != 200:
            raise RuntimeError(f"videos.list falhou: {r.status_code} {r.text[:200]}")
        for item in r.json().get("items", []):
            out[item["id"]] = video_format(item)
    return out, units


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("::error::YOUTUBE_API_KEY ausente")
        return 1

    state = state_manager.load_state(STATE_PATH)
    alerts = [(aid, m) for b in BUCKETS for aid, m in state.get(b, {}).items()]
    video_ids = sorted({v for _, m in alerts for v in m.get("videos_collected", [])})
    print(f"{len(alerts)} alertas, {len(video_ids)} vídeos únicos")

    formats, units = fetch_formats(video_ids, key)
    print(f"formato de {len(formats)}/{len(video_ids)} vídeos ({units} unidades de cota)")
    missing = sorted(set(video_ids) - set(formats))
    if missing:
        print(f"::notice title=indisponíveis::{len(missing)} vídeos removidos/privados: {' '.join(missing[:20])}")

    counts = collections.Counter(f["formato"] for f in formats.values())
    for fmt, n in counts.most_common():
        print(f"::notice title=formato {fmt}::{n} de {len(formats)} vídeos")
    for vid, f in sorted(formats.items()):
        if f["formato"] in ("short", "indeterminado"):
            print(f"  {vid} {f['formato']:<13} {f['duration_s']}s {f['embed_width']}x{f['embed_height']} live={f['live_status']}")

    for _, m in alerts:
        vids = m.get("videos_collected", [])
        state_manager.merge_video_format(m, {v: formats[v]["formato"] for v in vids if v in formats})

    if args.dry_run:
        print("--dry-run: state não gravado")
        return 0
    q = state_manager.roll_quota_day(state, datetime.now(timezone.utc))
    q["used_today"] = int(q.get("used_today", 0)) + units
    state_manager.save_state(state, STATE_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
