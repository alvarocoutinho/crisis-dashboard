"""v0.3.3: candidatos guardados, termos negativos por palavra, pseudonimização.

    python -m pytest tests/        ou        python tests/test_v033.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from faa_poc import pipeline, youtube  # noqa: E402
from faa_poc.config import CONFIG  # noqa: E402
from faa_poc.constants import CANDIDATE_FIELDS, COMMENT_CANONICAL_FIELDS  # noqa: E402
from faa_poc.geo import score_video  # noqa: E402
from faa_poc.text import pseudonymize_mentions  # noqa: E402

ALERT = {"cod_alerta": "9999", "municipio": "Juquitiba", "uf": "SP", "codibge": "1", "evento": "Movimentos de Massa",
         "nivel": "Moderado", "datahoracriacao": "2026-09-12T08:03:56Z"}


def test_termo_negativo_por_palavra_inteira():
    for titulo in ("Decisão unânime: Juquitiba SP decreta emergência após deslizamento com mortos",
                   "O melodrama de Juquitiba SP: deslizamento deixa desabrigados"):
        assert "negative" not in score_video({"title": titulo, "description_snippet": ""}, ALERT, CONFIG)["geo_match_type"]
    assert score_video({"title": "Melhor anime da temporada", "description_snippet": ""}, ALERT, CONFIG)["rejection_reason"] == "negative_term:anime"


def test_pseudonimizacao():
    assert pseudonymize_mentions("​@Edileuza-TS concordo") == "@usuario concordo"
    assert pseudonymize_mentions('<a href="https://www.youtube.com/channel/UCx">@Fulano</a> verdade') == "@usuario verdade"
    assert pseudonymize_mentions("email a@b.com e Juquitiba @ 10h") == "email a@b.com e Juquitiba @ 10h"
    assert "author" not in COMMENT_CANONICAL_FIELDS
    row = youtube._comment_row({"textDisplay": "@Fulano mentiu", "authorDisplayName": "Beltrano"},
                               video_id="v", comment_id="c", parent_id=None, is_reply=False)
    assert "author" not in row and "Fulano" not in row["text"] and "Fulano" not in row["text_clean"]


def test_todos_os_candidatos_sao_guardados(monkeypatch=None):
    vids = [
        {"video_id": "a", "title": "Deslizamento em Juquitiba SP deixa desabrigados", "description_snippet": ""},
        {"video_id": "b", "title": "DESLIZAMENTO NA FAVELA DOS BRANCOS EM JUQUITIBA", "description_snippet": ""},
        {"video_id": "c", "title": "Receita de bolo", "description_snippet": ""},
    ]
    orig = (youtube.search, youtube.stats, youtube.comments)
    youtube.search = lambda q, a, b, k, n: youtube.ApiResult(items=[{**v, "channel_id": "UC1", "channel_title": "x", "published_at": a} for v in vids])
    youtube.stats = lambda ids, k: youtube.ApiResult(items=[{"video_id": i, "view_count": 1, "comment_count": 0, "description": "", "tags": ""} for i in ids])
    youtube.comments = lambda *a, **kw: youtube.ApiResult(items=[])
    try:
        q = youtube.QuotaTracker(ceiling=100, high_reserve=0, search_ceiling=10, search_high_reserve=0)
        cfg = {**CONFIG, "MAX_VIDEOS_PER_ALERT": 10, "MAX_COMMENT_PAGES": 1}
        r = pipeline._collect_for_alert(ALERT, "K", q, cfg, set(), set(), set())
    finally:
        youtube.search, youtube.stats, youtube.comments = orig
    rows = {x["video_id"]: x for x in r["candidate_rows"]}
    assert set(rows) == {"a", "b", "c"}
    assert rows["a"]["decision"] == "selecionado" and rows["a"]["rank"] == 1
    assert rows["b"]["decision"] == "rejeitado" and rows["b"]["municipal_evidence"] == "titulo"
    assert rows["c"]["decision"] == "rejeitado" and rows["c"]["rejection_reason"].startswith("negative_term")
    assert all(set(CANDIDATE_FIELDS) >= set(x) for x in r["candidate_rows"])
    assert all(x["filter_version"] == "0.3.3" for x in r["candidate_rows"])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
