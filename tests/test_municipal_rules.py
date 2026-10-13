"""Regras municipais da v0.3.2 (pontuação, ordenação, promoção, arquivamento).

    python -m pytest tests/        ou        python tests/test_municipal_rules.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from faa_poc.config import CONFIG  # noqa: E402
from faa_poc.geo import score_video  # noqa: E402
from odrd_bridge import state_manager as sm  # noqa: E402

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


def _score(municipio, uf, evento, title, desc=""):
    return score_video({"title": title, "description_snippet": desc},
                       {"municipio": municipio, "uf": uf, "evento": evento}, CONFIG)


def test_grande_sao_paulo_nao_supera_municipio():
    regional = _score("Osasco", "SP", "Movimentos de Massa", "Deslizamento deixa mortos",
                      "São Paulo, sao paulo, Grande São Paulo")
    municipal = _score("Osasco", "SP", "Movimentos de Massa", "Deslizamento em Osasco SP deixa mortos")
    assert regional["geo_score"] == 4.0  # state_name 3 + 1 alias (antes: 6,0)
    assert municipal["geo_score"] == 5.0
    assert municipal["relevance_score"] > regional["relevance_score"]


def test_preposicao_para_nao_e_o_estado_do_para():
    r = _score("Lajeado", "RS", "Risco Hidrológico",
               "Enchente no Rio Grande do Sul deixa desabrigados, alerta para hoje")
    assert "cross_state_penalty" not in r["relevance_reasons"]
    assert r["geo_score"] == 3.0


def test_parana_e_mato_grosso_do_sul():
    assert "cross_state_penalty" not in _score("Curitiba", "PR", "Risco Hidrológico",
                                               "Enchente no Paraná deixa desabrigados")["relevance_reasons"]
    assert "cross_state_penalty" not in _score("Campo Grande", "MS", "Risco Hidrológico",
                                               "Enchente em Mato Grosso do Sul deixa desabrigados")["relevance_reasons"]
    assert _score("Belém", "PA", "Risco Hidrológico",
                  "Enchente em Belém, Pará, deixa desabrigados")["geo_match_type"] == "municipality_direct"


def test_alias_contido_conta_uma_vez():
    r = _score("Olinda", "PE", "Movimentos de Massa", "Deslizamento na Grande Recife deixa mortos")
    assert "alias×1" in r["relevance_reasons"]


def _meta(flag="alerta"):
    return {"codibge": "1", "municipio": "X", "uf": "SP", "opened_at": "2026-10-10T00:00:00Z",
            "nivel_atual": "Moderado", "flag": flag, "flag_history": [{"flag": flag, "at": "2026-10-10T00:00:00Z"}],
            "videos_collected": [], "n_videos_aderentes": 0, "n_comments_valid": 0,
            "videos_with_valid_comments": [], "last_new_data_at": None, "last_new_comment_at": None}


def _complete(state, aid, vids, evidence, comments):
    df = pd.DataFrame(comments, columns=["comment_id", "video_id", "n_model_labels"])
    sm.mark_collection_complete(state, aid, {}, videos_collected_now=vids,
                                predictions_this_alert=df, now=NOW, video_evidence=evidence)


def test_video_regional_nao_promove():
    state = {"active_alerts": {"a": _meta()}, "extended_window_alerts": {}}
    _complete(state, "a", ["v1"], {"v1": "nenhuma"}, [])
    assert state["active_alerts"]["a"]["flag"] == "alerta"
    _complete(state, "a", ["v2"], {"v2": "titulo"}, [])
    assert state["active_alerts"]["a"]["flag"] == "acompanhamento"


def test_prioritario_conta_so_comentarios_municipais():
    state = {"active_alerts": {"a": _meta()}, "extended_window_alerts": {}}
    regional = [(f"r{i}", "reg", 1) for i in range(200)]
    municipal = [(f"m{i}", "mun1", 1) for i in range(40)]
    _complete(state, "a", ["reg", "mun1"], {"reg": "nenhuma", "mun1": "titulo"}, regional + municipal)
    meta = state["active_alerts"]["a"]
    assert meta["n_comments_valid"] == 240 and meta["n_comments_valid_municipal"] == 40
    assert meta["flag"] == "acompanhamento"
    _complete(state, "a", ["mun2"], {"mun2": "descricao"}, [(f"n{i}", "mun2", 1) for i in range(10)])
    assert meta["n_comments_valid_municipal"] == 50 and meta["flag"] == "prioritario"
    assert meta["flag_history"][-1]["criterio"] == sm.FLAG_CRITERION


def test_transcricao_posterior_reconta_sem_recoleta():
    state = {"active_alerts": {"a": _meta("acompanhamento")}, "extended_window_alerts": {}}
    _complete(state, "a", ["v1", "v2"], {"v1": "titulo", "v2": "nenhuma"},
              [(f"a{i}", "v1", 1) for i in range(30)] + [(f"b{i}", "v2", 1) for i in range(30)])
    meta = state["active_alerts"]["a"]
    assert meta["flag"] == "acompanhamento"
    sm.merge_video_evidence(meta, {"v2": "transcricao"})
    assert meta["n_comments_valid_municipal"] == 60
    sm.promote_flag_if_eligible(meta, {}, NOW)
    assert meta["flag"] == "prioritario"


def test_alerta_com_cobertura_regional_nao_some_ao_fechar():
    meta = _meta()
    meta.update(videos_collected=["reg"], last_new_data_at="2026-10-01T00:00:00Z")
    state = {"active_alerts": {"a": meta}, "extended_window_alerts": {}, "archived_alerts": {}}
    sm.merge_new_alerts_from_cemaden(state, [], {}, now=NOW, close_missing=True)
    assert "a" in state["extended_window_alerts"]
    archived = sm.archive_exhausted(state, {}, now=NOW + timedelta(days=10))
    assert archived == ["a"]
    assert state["archived_alerts"]["a"]["archive_reason"] == "alerta_regional_esgotado_14d"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
