"""Evidência municipal de um vínculo alerta–vídeo (v0.3.1).

Responde a uma pergunta só: o vídeo NOMEIA o município do alerta? É
diferente da pergunta do filtro de relevância (o vídeo é sobre o evento?).
Um vídeo pode ser relevante para o episódio regional e não ser evidência
de visibilidade daquele município — distinção que a auditoria de 13/10/2026
mostrou ser decisiva (títulos com "SP" ligados a 13 municípios diferentes).

A evidência não aceita nem rejeita vídeos. Desde a v0.3.2 ela ordena os
vídeos aceitos (os que nomeiam o município primeiro) e decide quais contam
para a promoção de flag e para o indicador municipal (H2); os demais
continuam no episódio regional (H1).

Valores:
    titulo+descricao | titulo | descricao | transcricao | nenhuma
"""
from __future__ import annotations

import re

from .text import normalize

# Contextos em que o nome do município designa outra coisa (rio, vale,
# bairro): "Rio Ribeira", "Vale do Taquari", "Rio Tietê", "Penha" (zona leste).
_NON_MUNICIPAL_PREFIX = r"(?:rio|vale do|vale da|bacia do|bacia da|marginal|barragem da|barragem do)\s+"

# A capital paulista aparece nos títulos por bairros e zonas
_SP_CAPITAL_HINTS = ("capital paulista", "zona leste", "zona sul", "zona norte", "zona oeste",
                     "penha", "sapopemba", "jardim pantanal", "tatuape", "jabaquara")

EVIDENCE_LEVELS = ("titulo+descricao", "titulo", "descricao", "transcricao", "nenhuma")


def _names_municipality(text: str, municipio: str, uf: str) -> bool:
    t = normalize(text)
    m = normalize(municipio)
    if not t or len(m) < 3:
        return False
    if m == "sao paulo" and (uf or "").upper() == "SP":
        # "São Paulo"/"SP" sozinhos são ambíguos (estado ou capital): só conta
        # menção explícita à capital, a bairros/zonas ou "cidade de São Paulo".
        return any(h in t for h in _SP_CAPITAL_HINTS) or "cidade de sao paulo" in t
    pattern = rf"(?<![a-z0-9]){re.escape(m)}(?![a-z0-9])"
    for match in re.finditer(pattern, t):
        before = t[: match.start()]
        if re.search(_NON_MUNICIPAL_PREFIX + r"$", before):
            continue  # "rio ribeira", "vale do taquari" etc.
        return True
    return False


def municipal_evidence(municipio: str, uf: str, *, title: str = "", description: str = "",
                       transcript: str = "") -> str:
    """Onde o vídeo nomeia o município do alerta (ver docstring do módulo)."""
    in_title = _names_municipality(title, municipio, uf)
    in_desc = _names_municipality(description, municipio, uf)
    if in_title and in_desc:
        return "titulo+descricao"
    if in_title:
        return "titulo"
    if in_desc:
        return "descricao"
    if transcript and _names_municipality(transcript, municipio, uf):
        return "transcricao"
    return "nenhuma"


def is_municipal(evidence: str | None) -> bool:
    return bool(evidence) and evidence not in ("nenhuma", "")
