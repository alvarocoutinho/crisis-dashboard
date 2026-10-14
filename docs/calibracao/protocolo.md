# Protocolo de calibração dos filtros do ODRD (v0.3.3 → v0.4)

**Status:** aprovado em 13/10/2026 (divisão v0.3.3 / estudo / v0.4).

**Problema.** Nenhum filtro do pipeline foi medido contra julgamento humano. O primeiro lote da coleta retrospectiva (47 alertas, 520 candidatos) mostrou:
- **Falsos negativos sistemáticos.** Dos 46 vídeos rejeitados que tinham o município no título junto com um termo de perigo, 45 caíram porque o estado não aparece no texto. A regra penaliza a mídia local.
- **Falsos positivos.** Um alerta sem tipo de evento foi buscado com termos genéricos e a busca trouxe um acidente de ônibus.
- **Defeitos de lista.** Termos negativos comparados por trecho de palavra ("unânime" contém "anime").
- **Classificador de comentários sem validação humana.** O BERTimbau foi validado contra rótulos fracos, que são gerados por palavras-chave, e roda com limiar 0,5 igual para todas as categorias.

## Princípios

1. **Separar recuperação de decisão.** Desde a v0.3.3, todos os candidatos são guardados com seus atributos (`youtube_candidates.csv` e `candidates.jsonl` no Drive). Qualquer regra calibrada pode então ser reaplicada retroativamente sem gastar buscas.
2. **Padrão-ouro humano.** O critério é o julgamento humano, nunca uma regra do próprio sistema: título, transcrição e o próprio filtro não servem de gabarito.
3. **Um ponto de operação por uso.** O mesmo filtro serve a usos com custos de erro diferentes.
4. **Ajustar no desenvolvimento, medir uma vez no teste, congelar antes de aplicar.**

## Etapas

| # | Etapa | Instrumento | Custo |
|---|---|---|---|
| 1 | Conjunto de candidatos: calibração (38 alertas) e amostra de silêncio (120) | Notebook de coleta retrospectiva, fase `calibracao+amostra` | cerca de 3 execuções diárias |
| 2 | Variantes de consulta nos 38 alertas de calibração: sem UF, "chuva + Município", município entre aspas, julgadas em conjunto (*pooling*) | Notebook, fase `variantes` | cerca de 114 buscas |
| 3 | Amostra estratificada de cerca de 700 pares em 7 estratos, com pesos | `scripts/build_annotation_sample.py` | — |
| 4 | Anotação: perigo × episódio × lugar | `docs/calibracao/livro_de_codigos.md`; 2 codificadores, 150 pares em dupla | cerca de 8 h + 2 h |
| 5 | Confiabilidade: alfa de Krippendorff por dimensão (meta ≥ 0,80) e adjudicação | script de análise (a fazer) | — |
| 6 | Modelos comparados, com divisão desenvolvimento/teste **por episódio** | idem | — |
| 7 | Pontos de operação e ablação de cada regra | idem | — |
| 8 | Congelamento das regras e limiares no protocolo (v0.4) e reprocessamento do histórico | pipeline v0.4 | — |

Os modelos comparados na etapa 6 são três:
1. Regras atuais.
2. Regras com os defeitos corrigidos.
3. Regressão logística com atributos interpretáveis: município no título ou na descrição, estado/UF, termos de perigo por família, impacto, outro estado citado, defasagem de publicação.

### Pontos de operação (etapa 7)

| Uso | Critério |
|---|---|
| Corpus do episódio regional (H1) | Recuperação ≥ 0,90 com precisão ≥ 0,80 |
| Flag e indicador municipal (H2) | Precisão ≥ 0,90; recuperação reportada |
| Medida de silêncio | Reportada com a probabilidade de silêncio verdadeiro, combinando a recuperação do filtro com a sensibilidade da busca medida na calibração |

### Estimativa com pesos

Precisão e recuperação são estimadas na população de candidatos com os pesos dos estratos. O estrato E6 (rejeitados sem menção e sem termo de perigo) funciona como teste de elusão: estima os falsos negativos que sobram.

## Trilhas paralelas

- **Comentários.** Padrão-ouro de cerca de 600 comentários estratificados por categoria prevista, incluindo os que o modelo não classificou. Ele define limiares por categoria e o que conta como "comentário válido", o que afeta o critério dos 50 comentários.
- **Painel de canais.** `playlistItems.list` (1 unidade a cada 50 vídeos) sobre canais regionais, montado por bola de neve a partir dos canais já encontrados. O estudo mede quanto da cobertura relevante o painel capta. O painel complementa a busca, sem substituí-la: no lote 1, os 221 vídeos que citam o município vêm de 140 canais, e 101 deles têm um único vídeo.
- **Cota.** O limite de 100 buscas por dia é ajustável. Pedir o aumento pelo formulário de auditoria do YouTube ou pelo Researcher Program.

## Referências

- Efstratiou, A. (2025). *I'm sorry Dave, I'm afraid I can't return that: On YouTube Search API use in research* (arXiv:2506.04422).
- Gritta, M., Pilehvar, M. T., Limsopatham, N., & Collier, N. (2018). What's missing in geographical parsing? *Language Resources and Evaluation, 52*(2), 603–623.
- King, G., Lam, P., & Roberts, M. E. (2017). Computer-assisted keyword and document set discovery from unstructured text. *American Journal of Political Science, 61*(4), 971–988.
- Krippendorff, K. (2018). *Content analysis: An introduction to its methodology* (4th ed.). SAGE.
- Olteanu, A., Castillo, C., Diaz, F., & Vieweg, S. (2014). CrisisLex: A lexicon for collecting and filtering microblogged communications in crises. *ICWSM, 8*(1), 376–385.
- Voorhees, E. M., & Harman, D. K. (Eds.). (2005). *TREC: Experiment and evaluation in information retrieval*. MIT Press.
- Webber, W. (2013). Approximate recall confidence intervals. *ACM Transactions on Information Systems, 31*(1), Artigo 2.
