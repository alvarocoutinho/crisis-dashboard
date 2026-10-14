"""v0.3.4: formato do vídeo (short | longo | ao_vivo | indeterminado)."""
from faa_poc.youtube import parse_duration, video_format
from odrd_bridge.state_manager import merge_video_format


def _item(dur="PT45S", w="405", h="720", published="2026-09-10T12:00:00Z", live="none", details=None):
    item = {"snippet": {"publishedAt": published, "liveBroadcastContent": live},
            "contentDetails": {"duration": dur}, "player": {}}
    if w is not None:
        item["player"]["embedWidth"] = w
    if h is not None:
        item["player"]["embedHeight"] = h
    if details is not None:
        item["liveStreamingDetails"] = details
    return item


def test_parse_duration():
    assert parse_duration("PT45S") == 45
    assert parse_duration("PT2M59S") == 179
    assert parse_duration("PT1H2M3S") == 3723
    assert parse_duration("P1DT1S") == 86401
    assert parse_duration("P0D") == 0
    assert parse_duration("") is None and parse_duration(None) is None and parse_duration("xyz") is None


def test_short_vertical_and_square():
    assert video_format(_item())["formato"] == "short"
    assert video_format(_item(dur="PT3M", w="720", h="720"))["formato"] == "short"


def test_horizontal_short_duration_is_longo():
    assert video_format(_item(w="1280", h="720"))["formato"] == "longo"


def test_vertical_over_3min_is_longo():
    assert video_format(_item(dur="PT3M1S"))["formato"] == "longo"


def test_pre_2024_limit_is_60s():
    old = "2024-05-01T00:00:00Z"
    assert video_format(_item(dur="PT59S", published=old))["formato"] == "short"
    assert video_format(_item(dur="PT90S", published=old))["formato"] == "longo"
    assert video_format(_item(dur="PT90S", published="2024-10-15T00:00:00Z"))["formato"] == "short"


def test_live_takes_precedence():
    assert video_format(_item(live="live", dur="P0D"))["formato"] == "ao_vivo"
    done = video_format(_item(dur="PT2H", w="1280", h="720", details={"actualEndTime": "x"}))
    assert done["formato"] == "ao_vivo" and done["live_status"] == "encerrada"


def test_unknown_aspect_is_indeterminado():
    r = video_format(_item(w=None, h=None))
    assert r["formato"] == "indeterminado" and r["duration_s"] == 45 and r["embed_width"] == ""
    # sem proporção, mas longo pela duração: não precisa da proporção
    assert video_format(_item(dur="PT10M", w=None, h=None))["formato"] == "longo"


def test_merge_never_downgrades():
    meta = {}
    merge_video_format(meta, {"a": "indeterminado", "b": "short", "c": "", "d": "lixo"})
    merge_video_format(meta, {"a": "longo", "b": "indeterminado"})
    assert meta["video_format"] == {"a": "longo", "b": "short"}


def test_formato_chega_aos_vinculos_e_candidatos():
    from faa_poc import pipeline, youtube
    from faa_poc.constants import CANDIDATE_FIELDS, VIDEO_LINK_FIELDS
    from tests.test_v033 import ALERT, CONFIG
    vids = [{"video_id": "s", "title": "Deslizamento em Juquitiba SP", "description_snippet": ""},
            {"video_id": "l", "title": "Deslizamento atinge casas em Juquitiba SP", "description_snippet": ""}]
    orig = (youtube.search, youtube._request, youtube.comments)
    youtube.search = lambda q, a, b, k, n: youtube.ApiResult(items=[{**v, "channel_id": "UC1", "channel_title": "x", "published_at": a} for v in vids])
    raw = {"s": _item(), "l": _item(dur="PT4M", w="1280", h="720")}
    seen = {}

    def fake_request(endpoint, params):
        seen.update(params)
        return youtube.ApiResult(items=[{"id": i, "statistics": {}, **raw[i]} for i in params["id"].split(",")])
    youtube._request = fake_request
    youtube.comments = lambda *a, **kw: youtube.ApiResult(items=[])
    try:
        q = youtube.QuotaTracker(ceiling=100, high_reserve=0, search_ceiling=10, search_high_reserve=0)
        r = pipeline._collect_for_alert(ALERT, "K", q, {**CONFIG, "MAX_VIDEOS_PER_ALERT": 10, "MAX_COMMENT_PAGES": 1}, set(), set(), set())
    finally:
        youtube.search, youtube._request, youtube.comments = orig
    assert "contentDetails" in seen["part"] and seen["maxHeight"] == 720
    assert {x["video_id"]: x["formato"] for x in r["links"]} == {"s": "short", "l": "longo"}
    assert {x["video_id"]: x["formato"] for x in r["candidate_rows"]} == {"s": "short", "l": "longo"}
    assert "formato" in VIDEO_LINK_FIELDS and "formato" in CANDIDATE_FIELDS
    assert all(set(CANDIDATE_FIELDS) >= set(x) for x in r["candidate_rows"])
