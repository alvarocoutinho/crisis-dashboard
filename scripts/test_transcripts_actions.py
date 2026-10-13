"""Teste de viabilidade: o YouTube entrega legendas para um runner do GitHub Actions?

Experimento descartável (13/10/2026). Tenta listar e baixar a legenda de
poucos vídeos que, no Colab, TINHAM legenda disponível. Não grava nenhum
texto: registra só status, idioma e tamanho, como anotações do job
(legíveis pela API de check-runs) e no resumo da execução.

Uso: python scripts/test_transcripts_actions.py ID1 ID2 ...
"""
from __future__ import annotations

import os
import sys
import time

from youtube_transcript_api import (
    AgeRestricted, IpBlocked, NoTranscriptFound, PoTokenRequired, RequestBlocked,
    TranscriptsDisabled, VideoUnavailable, VideoUnplayable, YouTubeTranscriptApi,
)

PREF = ["pt-BR", "pt", "pt-PT", "es", "en"]


def tentar(ytt: YouTubeTranscriptApi, vid: str) -> tuple[str, str]:
    try:
        lista = ytt.list(vid)
        try:
            tr = lista.find_transcript(PREF)
        except NoTranscriptFound:
            tr = next(iter(lista))
        f = tr.fetch()
        n = sum(len(s.text) for s in f)
        return "ok", f"{f.language_code} auto={f.is_generated} segmentos={len(f)} caracteres={n}"
    except (RequestBlocked, IpBlocked) as e:
        return "bloqueado", type(e).__name__
    except TranscriptsDisabled as e:
        return "desativada", type(e).__name__
    except NoTranscriptFound as e:
        return "sem_transcricao", type(e).__name__
    except (VideoUnavailable, VideoUnplayable, AgeRestricted, PoTokenRequired) as e:
        return "indisponivel", type(e).__name__
    except Exception as e:  # noqa: BLE001 — experimento: registrar qualquer falha
        return "erro", f"{type(e).__name__}: {str(e)[:200]}"


def main(ids: list[str]) -> int:
    ytt = YouTubeTranscriptApi()
    linhas = []
    for vid in ids:
        status, detalhe = tentar(ytt, vid)
        nivel = "notice" if status == "ok" else "warning"
        print(f"::{nivel} title=transcricao {vid}::{status} | {detalhe}", flush=True)
        linhas.append(f"| `{vid}` | {status} | {detalhe} |")
        if status == "bloqueado":
            break
        time.sleep(2)
    ok = sum("| ok |" in l for l in linhas)
    resumo = f"{ok}/{len(ids)} vídeos com legenda obtida no runner do Actions"
    print(f"::notice title=resultado::{resumo}", flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"## Teste de transcrições no Actions\n\n{resumo}\n\n| vídeo | status | detalhe |\n|---|---|---|\n")
            fh.write("\n".join(linhas) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
