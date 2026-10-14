"""Coleta incremental do feed nacional IDAP (Atom/CAP 1.2).

O feed só mantém uma janela curta. Em 14/10/2026, duas capturas indicaram cerca
de 12 h por horário de emissão; o guia do Fórum SBTVD fala em 24 h. Por isso o
workflow ``idap.yml`` roda de hora em hora, e cada execução:

1. baixa o feed e registra a captura em ``data/idap/capturas.csv``, com a
   janela coberta e as lacunas na numeração;
2. acrescenta os alertas novos ao catálogo (``data/idap/alertas.csv``) e ao
   GeoJSON do dia (``public/data/idap/dias/``);
3. grava o XML CAP original dos alertas novos em ``<staging>/idap_cap_<dia>.jsonl.gz``.
   O workflow publica esse arquivo no Release ``idap-arquivo`` ANTES de commitar
   o catálogo. Se a publicação falhar, nada é commitado, e os alertas voltam
   como novos na hora seguinte, enquanto ainda estiverem no feed.

Uso:
    python scripts/collect_idap.py --staging /tmp/idap_raw [--arquivo feed.xml] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from odrd_idap import store  # noqa: E402
from odrd_idap.cap import FEED_URLS, read_feed  # noqa: E402

CATALOG = REPO / "data" / "idap" / "alertas.csv"
CAPTURES = REPO / "data" / "idap" / "capturas.csv"
LACUNAS = REPO / "data" / "idap" / "lacunas.csv"
PUB = REPO / "public" / "data" / "idap"
UA = "ODRD-observatorio/0.1 (pesquisa academica; Unicamp/NEPAM; github.com/alvarocoutinho/crisis-dashboard)"


def baixar() -> tuple[bytes | None, dict]:
    erros = []
    for url in FEED_URLS:
        for tentativa in range(2):
            try:
                r = requests.get(url, timeout=(20, 180), headers={"User-Agent": UA})
                if r.status_code == 200 and r.content.lstrip().startswith(b"<"):
                    return r.content, {"url": url, "http_status": 200}
                erros.append(f"{url} HTTP {r.status_code}")
            except requests.RequestException as e:
                erros.append(f"{url} {type(e).__name__}")
            time.sleep(10 * (tentativa + 1))
    return None, {"url": FEED_URLS[0], "http_status": "", "erro": "; ".join(erros)[:400]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", type=Path, required=True, help="pasta para os .jsonl.gz brutos do dia")
    ap.add_argument("--arquivo", type=Path, help="feed já baixado (teste); dispensa a rede")
    ap.add_argument("--capturado-em", help="horário UTC da captura de --arquivo (ex.: 2026-10-14T19:29:00Z)")
    ap.add_argument("--dry-run", action="store_true", help="não grava nada no repositório")
    args = ap.parse_args()

    agora = args.capturado_em or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if args.arquivo:
        payload, info = args.arquivo.read_bytes(), {"url": f"arquivo:{args.arquivo.name}", "http_status": ""}
    else:
        payload, info = baixar()
    cap_row = {"captured_at_utc": agora, **info}

    if payload is None:
        cap_row["status"] = "falha_download"
        print(f"::warning title=IDAP indisponível::{cap_row.get('erro', '')}")
        if not args.dry_run:
            store.append_csv(CAPTURES, store.CAPTURE_FIELDS, [cap_row])
        return 0   # falha registrada; a próxima hora tenta de novo

    try:
        meta, alerts = read_feed(payload)
    except Exception as e:  # XML quebrado ou HTML de erro com status 200
        cap_row.update(status="falha_parse", bytes=len(payload), erro=f"{type(e).__name__}: {e}"[:400],
                       sha256=hashlib.sha256(payload).hexdigest())
        print(f"::warning title=IDAP feed ilegível::{cap_row['erro']}")
        if not args.dry_run:
            store.append_csv(CAPTURES, store.CAPTURE_FIELDS, [cap_row])
        return 0

    catalog = store.read_csv(CATALOG)
    vistos = {r["identifier"] for r in catalog}
    novos = [a for a in alerts if a["identifier"] not in vistos]
    nums = [a["id_num"] for a in alerts if a["id_num"] is not None]
    sents = sorted(a["sent_utc"] for a in alerts if a["sent_utc"])
    horas = ""
    if len(sents) >= 2:
        f = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
        horas = round((f(sents[-1]) - f(sents[0])).total_seconds() / 3600, 2)
    cap_row.update(status="ok", bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                   n_alerts=len(alerts), min_id=min(nums) if nums else "", max_id=max(nums) if nums else "",
                   min_sent_utc=sents[0] if sents else "", max_sent_utc=sents[-1] if sents else "",
                   horas_cobertas=horas, n_novos=len(novos))
    for k in ("feed_updated", "n_entries", "n_invalid"):
        cap_row[k] = meta[k]

    rows, feats, raws = [], {}, {}
    for a in novos:
        row, feat = store.build_record(a, agora)
        rows.append(row)
        feats.setdefault(row["dia_emissao"], []).append(feat)
        raws.setdefault(row["dia_emissao"], []).append(store.raw_line(a, agora))

    faltantes = store.missing_ids(catalog + rows)
    cap_row["ids_faltantes_total"] = len(faltantes)
    print(f"feed {meta['feed_updated']} | {len(alerts)} alertas (ids {cap_row['min_id']}–{cap_row['max_id']}, "
          f"{horas} h de emissões) | novos {len(novos)} | lacunas na numeração: {len(faltantes)}")
    for r in rows:
        print(f"  novo {r['identifier']:<13} {r['sent'][:16]} {r['severity']:<8} {r['ufs']:<6} "
              f"{r['event'][:30]:<30} {r['area_desc'][:40]}")
    if args.dry_run:
        print("--dry-run: nada gravado")
        return 0

    args.staging.mkdir(parents=True, exist_ok=True)
    for dia, lines in raws.items():
        n = store.merge_raw_day(args.staging / f"idap_cap_{dia}.jsonl.gz", lines)
        print(f"  bruto {dia}: +{n}")
    for dia, fs in feats.items():
        total = store.write_day_geojson(PUB / "dias" / f"{dia}.geojson", fs)
        print(f"  painel {dia}: {total} alertas no dia")
    store.append_csv(CATALOG, store.CATALOG_FIELDS, rows)
    store.append_csv(CAPTURES, store.CAPTURE_FIELDS, [cap_row])
    LACUNAS.parent.mkdir(parents=True, exist_ok=True)
    LACUNAS.write_text("id_num\n" + "".join(f"{n}\n" for n in faltantes), encoding="utf-8")
    idx = store.write_index(PUB / "indice.json", store.read_csv(CATALOG), store.read_csv(CAPTURES), PUB / "dias")
    print(f"::notice title=IDAP::{len(novos)} novos; {idx['total_alertas']} no catálogo; "
          f"janela do feed {horas} h; lacunas {len(faltantes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
