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
| 4 | Anotação: perigo × episódio × lugar, com a fonte da decisão; 50 pares re-rotulados assistindo ao vídeo | `docs/calibracao/livro_de_codigos.md`; 2 codificadores, 150 pares em dupla; 2 anotadores de IA | cerca de 8 h + 2 h + 1 h |
| 5 | Confiabilidade: alfa de Krippendorff por dimensão (meta ≥ 0,80) e adjudicação | `scripts/analyze_annotation.py` | — |
| 6 | Modelos comparados, com divisão desenvolvimento/teste **por episódio** | script de modelagem (a fazer) | — |
| 7 | Pontos de operação e ablação de cada regra | idem | — |
| 8 | Congelamento das regras e limiares no protocolo (v0.4) e reprocessamento do histórico | pipeline v0.4 | — |

Os modelos comparados na etapa 6 são três:
1. Regras atuais.
2. Regras com os defeitos corrigidos.
3. Regressão logística com atributos interpretáveis: município no título ou na descrição, estado/UF, termos de perigo por família, impacto, outro estado citado, defasagem de publicação, formato do vídeo (v0.3.4).

### Pontos de operação (etapa 7)

| Uso | Critério |
|---|---|
| Corpus do episódio regional (H1) | Recuperação ≥ 0,90 com precisão ≥ 0,80 |
| Flag e indicador municipal (H2) | Precisão ≥ 0,90; recuperação reportada |
| Medida de silêncio | Reportada com a probabilidade de silêncio verdadeiro, combinando a recuperação do filtro com a sensibilidade da busca medida na calibração |

### Estimativa com pesos

Precisão e recuperação são estimadas na população de candidatos com os pesos dos estratos. O estrato E6 (rejeitados sem menção e sem termo de perigo) funciona como teste de elusão: estima os falsos negativos que sobram.

## Anotadores de IA (sem API paga: subagentes nesta conversa do Claude)

O desenho tem quatro anotadores:
- **Humano 1:** forma o gabarito.
- **Humano 2:** codifica os 150 pares em dupla, mede a confiabilidade e entra na adjudicação.
- **IA-metadados:** vê o mesmo material que os humanos. É a candidata a substituir o humano 2 no monitoramento mensal.
- **IA-transcrição:** vê só a fala transcrita. Aproxima o "assistir ao vídeo" nos pares que têm legenda.

A IA nunca entra no gabarito nem na adjudicação.

**Procedimento:**
1. `build_annotation_sample.py` grava em `ia/prompts/` um arquivo por lote (60 pares na condição de metadados, 8 na de transcrição, porque as transcrições são longas), com o prompt congelado (`prompt_ia_v1.md`) e o livro de códigos na íntegra. `ia/manifesto.json` guarda os hashes SHA-256 de ambos.
2. **Isolamento.** Antes das rodadas de IA, a chave (`anotacao_chave.csv`) e as planilhas humanas saem do ambiente de trabalho e ficam só no Drive. Só a pasta `ia/prompts/` fica disponível.
3. **Execução.** Cada lote vai para um subagente novo, com o texto do lote embutido no pedido e a instrução de não usar ferramentas. A resposta bruta é gravada em `ia/resultados/rodada1/<lote>.jsonl`.
4. **Ajuste do prompt.** Só nos lotes `treino_*`, e antes de qualquer lote `amostra_*`. Depois disso o prompt fica congelado; qualquer mudança vira uma v2, com a medição refeita.
5. **Rodada 2 (autoconsistência).** Os mesmos lotes vão para subagentes novos e as respostas são gravadas em `ia/resultados/rodada2/`.
6. **Registro.** `ia/execucao.json` guarda, por lote, a data, o modelo configurado na sessão e o identificador do subagente.

**Piloto de 14/10/2026** (30 pares de treino do lote 1, condição metadados, um subagente):
- **Formato:** 30 de 30 respostas em JSON válido, com justificativa citando o título.
- **Custo:** cerca de 85 mil tokens, quase todo fixo por subagente; daí os lotes de 60.
- **Lugar inferido pelo canal.** A IA marcou como municipais dois vídeos de Juquitiba que só citam o bairro (Favela do Justino), deduzindo o município pelo nome do canal ("JUQUITIBA A CIDADE QUE DEU CERTO"). O filtro atual não usa o canal. É um atributo candidato para a v0.4.
- **Falsos negativos do filtro atual que a IA marca como municipais:** São Bernardo do Campo ("Chuva forte provoca deslizamento de terra em São Bernardo do Campo"), Registro, Iporanga e Blumenau, todos sem a UF no título.
- **Três ambiguidades do livro, a resolver no treino antes da v1.1, valendo para humanos e IA:**
  1. desabamento de prédio durante o episódio de chuva sem causa declarada no título (os desabamentos da Penha): `nao` ou `incerto`?
  2. rio com o nome da cidade ("Rio Jaguarão acima da cota"): a IA marcou `regiao_vizinho` pela regra dos rios;
  3. "Chuvas em SP" para um alerta da capital: a IA marcou `indeterminado`.

  Esses pares são de treino. Ajustar o livro a partir deles é permitido; ajustar a partir da amostra, não.
- **Decisões do pesquisador (14/10), que formam o livro v1.1:**
  1. o desabamento durante o episódio conta como `perigo = sim`, mesmo sem causa declarada;
  2. o rio com o nome da cidade só vale `municipio` se o vídeo indicar a cidade;
  3. "SP" sozinho para alerta da capital vale `regiao_vizinho` e entra no episódio regional.
- **Consequência da regra 1 para a H2:** a cobertura dos desabamentos da Penha (obra irregular) entra no corpus. Ela concentra comentários de responsabilização sobre a obra, e não sobre a chuva. A análise da H2 deve testar a sensibilidade com e sem esses vídeos.

**Limitação a declarar:** pela interface de conversa não se controla a temperatura, e a versão do modelo que atende pode mudar. Isso compromete a reprodutibilidade exata. Por isso a autoconsistência entre a rodada 1 e a rodada 2 é obrigatória, e as respostas brutas são guardadas. Se a IA for usada depois em produção (monitoramento), o caminho reprodutível é a API, com o modelo fixado.

**Análise:** `scripts/analyze_annotation.py` produz:
- o alfa de Krippendorff por dimensão para cada comparação, com IC95% por bootstrap: H1×H2, IA×gabarito, rodada 1×rodada 2, IA-metadados×IA-transcrição e metadados×assistindo;
- precisão e recuperação ponderadas do filtro atual e de cada IA, para os alvos municipal e regional;
- a proporção de pares relevantes por estrato;
- precisão e recuperação do filtro atual por formato do vídeo (`short`, `longo`, `ao_vivo`).

### Formato do vídeo (v0.3.4)

Desde 14/10/2026, cada vídeo traz `formato`, obtido pela API oficial: duração, proporção do player e dados de transmissão. A definição de Short é a do YouTube: vertical ou quadrado com até 3 minutos.
- **Por que importa:** Short, vídeo longo e live diferem em distribuição (feed de Shorts × busca), produção (cortes e repostagens) e dinâmica de comentários.
- **Na H2:** o volume de comentários não é comparável entre formatos, então os indicadores são reportados também por formato.
- **No estudo de calibração:** o formato fica na chave, não na planilha, e é reportado como variável de análise. Não é estrato de amostragem, porque o desenho já estava fixado. Se algum formato ficar com menos de 30 pares relevantes no gabarito, a estimativa dele é declarada exploratória.
- **Para a v0.4:** é atributo candidato do modelo. Títulos de Shorts são curtos e cheios de hashtags.

O cálculo do alfa foi verificado contra o exemplo canônico de Krippendorff (α nominal = 0,743).

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
