"""Observador horário do CEMADEN: catálogo, durações e alertas que o pipeline não viu."""
from odrd_cemaden import observer


def _a(cod, nivel="Moderado", evento="Risco Hidrológico", uf="SP", criado="2026-10-14T10:00:00Z"):
    return {"cod_alerta": cod, "uf": uf, "municipio": "X", "codibge": "1", "evento": evento,
            "nivel": nivel, "status": "1", "datahoracriacao": criado, "ult_atualizacao": criado}


def test_relevante():
    assert observer.relevante(_a(1))
    assert observer.relevante(_a(1, nivel="Muito Alto", evento="Movimentos de Massa"))
    assert not observer.relevante(_a(1, nivel="Baixo"))
    assert not observer.relevante(_a(1, evento="Incêndio"))


def test_ciclo_completo():
    cat = {}
    # 11h: dois alertas; o pipeline (state) só conhece o 1
    c = observer.update_catalog(cat, [_a(1), _a(2, nivel="Alto")], "2026-10-14T11:00:00Z", {"cemaden_sp_1"})
    assert c["n_novos"] == 2 and c["n_fechados"] == 0 and c["n_relevantes"] == 2
    assert cat["1"]["visto_no_state"] == 1 and cat["2"]["visto_no_state"] == 0
    # 12h: o 2 sobe de nível
    observer.update_catalog(cat, [_a(1), _a(2, nivel="Muito Alto")], "2026-10-14T12:00:00Z", {"cemaden_sp_1"})
    assert cat["2"]["niveis_vistos"] == "Alto|Muito Alto" and cat["2"]["n_capturas"] == 2
    assert cat["2"]["duracao_min_h"] == 2.0
    # 13h: o 2 fecha sem nunca ter entrado no state; o 1 saiu do state (arquivo puro) mas foi visto antes
    c = observer.update_catalog(cat, [], "2026-10-14T13:00:00Z", set())
    assert c["n_fechados"] == 2 and c["n_relevantes_fechados_fora_do_state"] == 1
    assert cat["2"]["aberto"] == 0 and cat["2"]["duracao_max_h"] == 3.0
    assert cat["1"]["visto_no_state"] == 1                      # cumulativo
    # 14h: o 2 reaparece
    observer.update_catalog(cat, [_a(2)], "2026-10-14T14:00:00Z", set())
    assert cat["2"]["aberto"] == 1 and cat["2"]["n_reaberturas"] == 1 and cat["2"]["fechado_visto_utc"] == ""


def test_valores_lidos_do_csv_sao_texto():
    # ao reler o CSV tudo vem como texto: a lógica não pode depender de int
    cat = {"9": {"cod_alerta": "9", "alert_id": "cemaden_sp_9", "aberto": "1", "relevante_pipeline": "1",
                 "visto_no_state": "0", "n_capturas": "3", "n_reaberturas": "0",
                 "datahoracriacao": "2026-10-14T10:00:00Z", "niveis_vistos": "Moderado"}}
    c = observer.update_catalog(cat, [], "2026-10-14T12:00:00Z", set())
    assert c["n_fechados"] == 1 and c["n_relevantes_fechados_fora_do_state"] == 1


def test_hash_ignora_ordem():
    assert observer.snapshot_hash([_a(1), _a(2)]) == observer.snapshot_hash([_a(2), _a(1)])
    assert observer.snapshot_hash([_a(1)]) != observer.snapshot_hash([_a(1, nivel="Alto")])
