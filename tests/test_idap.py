"""Coletor IDAP (CAP 1.2): leitura, geometria e armazenamento incremental.

A amostra ``fixtures/idap_feed_amostra.xml`` tem 4 alertas reais do feed de
14/10/2026: Rosana sem polígono, Blumenau com geocódigo IBGE, Paraná, e o de
Piracicaba/Rio Claro.
"""
import gzip
import json
from pathlib import Path

from odrd_idap import store
from odrd_idap.cap import id_number, read_feed, to_utc
from odrd_idap.geometry import area_geometry, parse_polygon

FIX = Path(__file__).parent / "fixtures" / "idap_feed_amostra.xml"


def _alerts():
    return {a["identifier"]: a for a in read_feed(FIX.read_bytes())[1]}


def test_le_feed_real():
    meta, alerts = read_feed(FIX.read_bytes())
    assert meta == {"feed_updated": "2026-10-14T19:25:28Z", "n_entries": 4, "n_invalid": 0}
    a = {x["identifier"]: x for x in alerts}["193759/2026"]
    assert a["sender"] == "CENAD-SEDEC" and a["msg_type"] == "Alert" and a["severity"] == "Extreme"
    assert a["sent_utc"] == "2026-10-14T16:43:43Z" and a["expires_utc"] == "2026-10-15T02:35:00Z"
    assert "Piracicaba" in a["description"] and a["n_polygons"] == 1 and a["channels"] == "Google"
    assert "<" in a["cap_xml"] and "193759/2026" in a["cap_xml"]


def test_utc_e_numero():
    assert to_utc("2026-10-14T13:43:43-03:00") == "2026-10-14T16:43:43Z"
    assert to_utc("2026-10-14T13:43:43") == "" and to_utc("") == ""
    assert id_number("193759/2026") == 193759 and id_number("abc") is None


def test_geometria_lat_lon_vira_lon_lat_e_fecha_anel():
    poly, fechado = parse_polygon("-22.7,-47.6 -22.4,-47.6 -22.4,-47.3")
    assert fechado and poly.exterior.coords[0] == poly.exterior.coords[-1] == (-47.6, -22.7)
    assert parse_polygon("1,2 3,4") == (None, False)


def test_geometria_dos_alertas_reais():
    a = _alerts()
    g, qa = area_geometry(a["193759/2026"]["areas"])
    assert g["type"] in ("Polygon", "MultiPolygon") and not qa["sem_geometria"]
    lon, lat = qa["ponto"]
    assert -48.5 < lon < -46.5 and -23.5 < lat < -21.5        # região de Piracicaba / Rio Claro
    g, qa = area_geometry(a["193713/2026"]["areas"])        # Rosana: CAP sem polígono
    assert g is None and qa["sem_geometria"]
    g, qa = area_geometry(a["193718/2026"]["areas"])        # 4.282 vértices → simplificado
    n = sum(len(r) for r in (g["coordinates"] if g["type"] == "Polygon" else [r for p in g["coordinates"] for r in p]))
    assert n < 4282


def test_ufs_inferidas():
    a = _alerts()
    assert store.infer_ufs(a["193718/2026"]) == ["SC"]          # IBGE 42… e "Blumenau/SC"
    assert store.infer_ufs(a["193713/2026"]) == ["SP"]          # área "mapa": vem do emissor
    assert store.infer_ufs(a["193720/2026"]) == ["PR"]
    assert store.infer_ufs({"ibge": [], "area_desc": "", "sender_name": "Defesa Civil de Barra Mansa (RJ)"}) == ["RJ"]
    assert store.infer_ufs({"ibge": [], "area_desc": "", "sender_name": "Defesa Civil Estadual do Mato Grosso do Sul"}) == ["MS"]


def test_lacunas_na_numeracao():
    assert store.missing_ids([{"id_num": "10"}, {"id_num": "13"}, {"id_num": "11"}]) == [12]
    assert store.missing_ids([{"id_num": "10"}]) == []


def test_armazenamento_incremental(tmp_path):
    alerts = list(_alerts().values())
    raw = tmp_path / "idap_cap_2026-10-14.jsonl.gz"
    lines = [store.raw_line(a, "2026-10-14T19:29:44Z") for a in alerts]
    assert store.merge_raw_day(raw, lines[:2]) == 2
    assert store.merge_raw_day(raw, lines) == 2                 # só os 2 que faltavam
    assert store.merge_raw_day(raw, lines) == 0
    with gzip.open(raw, "rt", encoding="utf-8") as fh:
        ids = [json.loads(ln)["identifier"] for ln in fh]
    assert sorted(ids) == sorted(a["identifier"] for a in alerts)

    feats = [store.build_record(a, "2026-10-14T19:29:44Z")[1] for a in alerts]
    day = tmp_path / "dias" / "2026-10-14.geojson"
    assert store.write_day_geojson(day, feats[:1]) == 1
    assert store.write_day_geojson(day, feats) == 4
    fc = json.loads(day.read_text(encoding="utf-8"))
    assert [f["properties"]["id_num"] for f in fc["features"]] == sorted(f["properties"]["id_num"] for f in feats)
    rosana = next(f for f in fc["features"] if f["id"] == "193713/2026")
    assert rosana["geometry"] is None and rosana["properties"]["ufs"] == ["SP"]


def test_linha_do_catalogo():
    row, feat = store.build_record(_alerts()["193759/2026"], "2026-10-14T19:29:44Z")
    assert set(row) == set(store.CATALOG_FIELDS)
    assert row["dia_emissao"] == "2026-10-14" and row["ufs"] == "SP" and row["sem_geometria"] == 0
    assert "cap_xml" not in row and "areas" not in row          # catálogo sem geometria nem XML
    assert feat["properties"]["identifier"] == "193759/2026"
