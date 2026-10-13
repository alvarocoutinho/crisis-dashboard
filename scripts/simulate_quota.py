"""Replay the ODRD pipeline against a fake YouTube API to measure quota use.

Usage (dev only; needs `pip install freezegun`):
    python scripts/simulate_quota.py <repo_path> <days> [--label NAME]
    FAKE_DAILY_QUOTA=1500 python scripts/simulate_quota.py . 2   # chave compartilhada

Runs scripts/pipeline.py main() 4x/day (00/06/12/18 UTC) under freezegun,
starting from the repo's current src/data/state.json. CEMADEN returns the
alerts currently in active_alerts (nothing closes, nothing new), PED is
stubbed, BERTimbau is stubbed. The fake YouTube API enforces a 10,000-unit
daily quota that resets at midnight America/Los_Angeles, and charges only
requests it actually served.
"""
from __future__ import annotations
import hashlib, importlib.util, json, os, shutil, sys, tempfile, types
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from freezegun import freeze_time

REPO = Path(sys.argv[1]).resolve()
DAYS = int(sys.argv[2])
LABEL = sys.argv[4] if len(sys.argv) > 4 else REPO.name
START = datetime(2026, 10, 13, 12, 3, tzinfo=timezone.utc)
DAILY_QUOTA = int(os.environ.get("FAKE_DAILY_QUOTA", "10000"))
# FAKE_MODEL=2026 (padrão): tabela oficial atualizada em 08/10/2026 — toda
# chamada custa 1 unidade e search.list tem limite próprio de 100/dia.
# FAKE_MODEL=legacy: modelo antigo, search.list = 100 unidades, sem limite próprio.
FAKE_MODEL = os.environ.get("FAKE_MODEL", "2026")
COST = {"search": 1 if FAKE_MODEL == "2026" else 100, "videos": 1, "commentThreads": 1, "comments": 1}
SEARCH_DAILY_LIMIT = int(os.environ.get("FAKE_SEARCH_LIMIT", "100")) if FAKE_MODEL == "2026" else 10**9

work = Path(tempfile.mkdtemp(prefix="odrd_sim_"))
shutil.copy(REPO / "src/data/state.json", work / "state.json")
shutil.copy(REPO / "src/data/live.json", work / "live.json")
shutil.copy(REPO / "src/data/alertas_agregados.csv", work / "agg.csv")
initial_state = json.loads((work / "state.json").read_text())

os.environ.update(YOUTUBE_API_KEY="fake", HF_TOKEN="fake", PED_EMAIL="x", PED_PASSWORD="x")
os.environ.pop("GOOGLE_SERVICE_ACCOUNT_JSON", None)


def h(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------------------------------------------------------- fake world
class World:
    def __init__(self):
        self.used = defaultdict(int)          # pacific day -> units served
        self.searches = defaultdict(int)      # pacific day -> search calls served
        self.calls = Counter()
        self.denied = Counter()
        self.videos: dict[str, dict] = {}
        self.run_units = 0

    def now(self):
        return datetime.now(timezone.utc)

    def day(self):
        return self.now().astimezone(ZoneInfo("America/Los_Angeles")).date()

    def charge(self, endpoint):
        cost = COST[endpoint]
        if self.used[self.day()] + cost > DAILY_QUOTA or (
                endpoint == "search" and self.searches[self.day()] + 1 > SEARCH_DAILY_LIMIT):
            self.denied[endpoint] += 1
            return False
        if endpoint == "search":
            self.searches[self.day()] += 1
        self.used[self.day()] += cost
        self.calls[endpoint] += 1
        self.run_units += cost
        return True

    # Videos for a query: deterministic per municipality, published in window
    def search(self, params):
        q = params["q"]; after = parse(params["publishedAfter"]); before = parse(params["publishedBefore"])
        parts = q.split()
        uf = parts[-1]; muni = " ".join(parts[1:-1])
        n_total = h(muni, uf) % 9          # 0..8 videos exist for this place
        items = []
        span = max(1, int((before - after).total_seconds()))
        for i in range(n_total):
            vid = f"v{h(muni, uf, i):08x}"
            pub = after + timedelta(seconds=h(vid) % span)
            self.videos.setdefault(vid, {"pub": pub, "n_threads": h(vid, "n") % 400, "muni": muni, "uf": uf})
            items.append({"id": {"videoId": vid}, "snippet": {
                "title": f"Enchente em {muni} {uf}: chuva forte deixa desabrigados",
                "channelTitle": "TV Local", "channelId": "c1", "publishedAt": iso(pub),
                "description": f"Alagamento atinge {muni}, {uf}; desabrigados e estragos."}})
        return items[: int(params.get("maxResults", 5))]

    def threads(self, vid):
        v = self.videos.get(vid)
        if not v: return []
        out = []
        for i in range(v["n_threads"]):
            # 65% of comments inside the first 72h, rest spread over 40 days
            if h(vid, i, "w") % 100 < 65:
                pub = v["pub"] + timedelta(minutes=h(vid, i) % (72 * 60))
            else:
                pub = v["pub"] + timedelta(minutes=72 * 60 + h(vid, i) % (40 * 24 * 60))
            if pub > self.now(): continue
            n_rep = 2 if i % 4 == 0 else (7 if i % 29 == 0 else 0)
            out.append((f"{vid}c{i}", pub, n_rep))
        out.sort(key=lambda t: t[1], reverse=True)   # order=time: newest first
        return out

    def comment_threads(self, params):
        vid = params["videoId"]; per = int(params.get("maxResults", 20))
        start = int(params.get("pageToken") or 0)
        allt = self.threads(vid); page = allt[start:start + per]
        include_replies = "replies" in params.get("part", "")
        items = []
        for cid, pub, n_rep in page:
            snip = {"textDisplay": f"que tristeza {cid}", "authorDisplayName": "a", "publishedAt": iso(pub), "likeCount": 0}
            item = {"snippet": {"topLevelComment": {"id": cid, "snippet": snip}, "totalReplyCount": n_rep}}
            if include_replies and n_rep:
                item["replies"] = {"comments": [self._reply(cid, pub, j) for j in range(min(n_rep, 5))]}
            items.append(item)
        body = {"items": items}
        if start + per < len(allt): body["nextPageToken"] = str(start + per)
        return body

    def _reply(self, cid, pub, j):
        rp = min(pub + timedelta(hours=1 + j), self.now())
        return {"id": f"{cid}.r{j}", "snippet": {"textDisplay": f"força {cid} {j}", "authorDisplayName": "b", "publishedAt": iso(rp), "likeCount": 0}}

    def replies(self, params):
        cid = params["parentId"]; vid = cid.split("c")[0]
        for tcid, pub, n_rep in self.threads(vid):
            if tcid == cid:
                return {"items": [self._reply(cid, pub, j) for j in range(n_rep)]}
        return {"items": []}


W = World()


class Resp:
    def __init__(self, code, body):
        self.status_code = code; self._b = body; self.text = json.dumps(body)
    def json(self): return self._b


def fake_get(url, params=None, timeout=None, **kw):
    endpoint = url.rstrip("/").rsplit("/", 1)[-1]
    if endpoint not in COST:
        raise RuntimeError(f"unexpected URL {url}")
    if not W.charge(endpoint):
        return Resp(403, {"error": {"errors": [{"reason": "quotaExceeded"}], "message": "The request cannot be completed because you have exceeded your quota."}})
    if endpoint == "search": return Resp(200, {"items": W.search(params)})
    if endpoint == "videos":
        return Resp(200, {"items": [{"id": v, "statistics": {"viewCount": 100, "likeCount": 1, "commentCount": W.videos.get(v, {}).get("n_threads", 0)}} for v in params["id"].split(",")]})
    if endpoint == "commentThreads": return Resp(200, W.comment_threads(params))
    return Resp(200, W.replies(params))


# ---------------------------------------------------------------- stubs
sys.path.insert(0, str(REPO))
import requests  # noqa: E402
requests.get = fake_get

bert = types.ModuleType("odrd_bridge.bertimbau")
def predict_comments(comments_csv, **kw):
    import pandas as pd
    df = pd.read_csv(comments_csv)
    if df.empty: return df
    for i, cat in enumerate(bert.CATEGORY_ORDER):
        df[f"score_{cat}"] = [((h(c, cat) % 100) / 100) for c in df["comment_id"]]
        df[f"pred_{cat}"] = (df[f"score_{cat}"] >= 0.85).astype(int)
    df["n_model_labels"] = df[[f"pred_{c}" for c in bert.CATEGORY_ORDER]].sum(axis=1)
    df["model_labels"] = ""
    return df
bert.predict_comments = predict_comments
bert.CATEGORY_ORDER = ["solidariedade_oracao_luto","ajuda_resgate_doacoes","responsabilizacao_governanca","infraestrutura_ocupacao_risco","clima_chuva_meio_ambiente","experiencia_pessoal_local","alerta_prevencao_cobranca","critica_midia_informacao"]
sys.modules["odrd_bridge.bertimbau"] = bert

import faa_poc.ped as ped  # noqa: E402
class FakePed:
    last_error = ""
    def __init__(self, cfg): pass
    def login(self): pass
ped.PedClient = FakePed
ped.fetch_accumulations = lambda alert, client: ([], {})

import faa_poc.cemaden as cemaden  # noqa: E402
def fake_alerts(config=None):
    st = json.loads((work / "state.json").read_text())
    out = []
    for aid, m in initial_state["active_alerts"].items():
        out.append({"cod_alerta": aid.rsplit("_", 1)[-1], "uf": m["uf"], "nivel": m["nivel_atual"],
                    "datahoracriacao": m["opened_at"], "municipio": m["municipio"].upper(),
                    "codibge": m["codibge"], "evento": m["evento"]})
    return out
cemaden.fetch_alerts = fake_alerts

spec = importlib.util.spec_from_file_location("odrd_pipeline_main", REPO / "scripts/pipeline.py")
P = importlib.util.module_from_spec(spec); sys.modules["odrd_pipeline_main"] = P; spec.loader.exec_module(P)
P.STATE_PATH = work / "state.json"; P.LIVE_PATH = work / "live.json"; P.AGGREGATE_LOG_PATH = work / "agg.csv"
sys.argv = ["pipeline.py"]

# ---------------------------------------------------------------- replay
rows = []
t = START
end = START + timedelta(days=DAYS)
import contextlib, io
while t < end:
    W.run_units = 0
    out_dir = Path(tempfile.mkdtemp(prefix="faa_"))
    P.FAA_OUTPUT_DIR = out_dir
    buf = io.StringIO()
    with freeze_time(t), contextlib.redirect_stdout(buf):
        code = P.main()
    log = buf.getvalue()
    vis = out_dir / "visibility_observations.csv"
    quota_hits = 0; searched_alerta_ok = 0
    if vis.exists():
        import csv
        vrows = list(csv.DictReader(vis.open()))
        quota_hits = sum(r["status"] == "quota_exhausted" for r in vrows)
    st = json.loads((work / "state.json").read_text())
    flags = Counter(m.get("flag") for b in ("active_alerts", "extended_window_alerts") for m in st[b].values())
    ncmt = sum(m.get("n_comments_valid", 0) for b in ("active_alerts", "extended_window_alerts") for m in st[b].values())
    collect_line = next((l for l in log.splitlines() if "decisões:" in l), "")
    rows.append({"t": t.strftime("%m-%d %H:%M"), "exit": code, "units": W.run_units,
                 "pacific_day_total": W.used[W.day() if False else t.astimezone(ZoneInfo('America/Los_Angeles')).date()],
                 "quota_exhausted_alerts": quota_hits, "decisions": collect_line.split("decisões:")[-1].strip(),
                 "flags": dict(flags), "archived": len(st["archived_alerts"]), "sum_n_comments_valid": ncmt})
    t += timedelta(hours=6)

print(f"\n=== {LABEL}: {DAYS} days ===")
for r in rows:
    print(f"{r['t']} exit={r['exit']} units={r['units']:>6} day_total={r['pacific_day_total']:>6} "
          f"quota_exh={r['quota_exhausted_alerts']:>2} archived={r['archived']} ncmt={r['sum_n_comments_valid']:>7} "
          f"flags={r['flags']} | {r['decisions']}")
print("calls served:", dict(W.calls), "| denied:", dict(W.denied))
print(f"model={FAKE_MODEL} units per pacific day:", {str(k): v for k, v in sorted(W.used.items())})
print("search calls per pacific day:", {str(k): v for k, v in sorted(W.searches.items())})
final = json.loads((work / "state.json").read_text())
print("state.youtube_quota:", final.get("youtube_quota"))
alerta_status = {aid: (m.get("flag"), m.get("n_videos_aderentes"), m.get("last_collection_at"), m.get("collection_error"))
                 for aid, m in final["active_alerts"].items()}
print("active alerts after replay:")
for k, v in alerta_status.items(): print("  ", k, v)
live = json.loads((work / "live.json").read_text())
print("live collection_health:", Counter(a["collection_health"].get("status") for a in live["alerts"]),
      Counter(a["collection_health"].get("silence_type") for a in live["alerts"]))
json.dump(rows, open(work / "rows.json", "w"))
print("workdir:", work)
