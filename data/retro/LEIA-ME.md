# Coleta retrospectiva (regime `retrospective_backfill`)

Arquivos deste diretório (só metadados públicos do CEMADEN, contagens e IDs de vídeo):

- `universo_alertas.csv` — gerado por `scripts/build_retro_universe.py` a partir do histórico do `state.json`:
  - **calibracao** (38): alertas com vídeos conhecidos.
  - **silencio** (449): alertas que saíram do state sem vídeo entre agosto e outubro de 2026, quando a cota estava estourada em 45 de 60 dias.
  - **amostra=1** (120): amostra sistemática ordenada por UF × mês × abertura; semente 20261013.
- `resultados_alertas.csv` — gravado por `scripts/merge_retro_backfill.py` a partir da saída do notebook `notebooks/ODRD_coleta_retrospectiva.ipynb`.

Títulos de vídeos e textos de comentários ficam só no Drive do pesquisador.

**Interpretação.** A busca retrospectiva do YouTube não é exaustiva: tende aos vídeos mais recentes e pode devolver zero em períodos de pouco interesse (Efstratiou, 2025).
- Um vídeo achado que cita o município **refuta** o silêncio do alerta.
- Não achar nada é **inconclusivo**.
- A taxa da amostra é um limite inferior dos falsos silêncios. A calibração estima a sensibilidade da busca.
- Os resultados não alteram flags nem o painel; entram na análise de H1 como sensibilidade do denominador de silêncio.

**Instrumento.** O notebook roda em projeto Google Cloud e chave próprios, separado do pipeline (Políticas do YouTube API Services, III.D.1.c). Ele deve ser registrado como tal no protocolo e no material do CEP.

Efstratiou, A. (2025). *I'm sorry Dave, I'm afraid I can't return that: On YouTube Search API use in research* (arXiv:2506.04422). https://arxiv.org/abs/2506.04422
