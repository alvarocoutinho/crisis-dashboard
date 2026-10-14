# Livro de códigos — relevância de vídeos para alertas do CEMADEN (v1, 14/10/2026)

**Unidade:** o par **alerta × vídeo**. Cada linha da planilha mostra o alerta (município, UF, tipo de evento e hora de abertura) e um vídeo (título, canal, data, descrição, trechos da transcrição quando houver, e o link).

Você julga **o que o vídeo trata em relação a este alerta**. Não julga a qualidade do vídeo nem se o filtro do sistema acertou: você não vê a decisão do sistema, de propósito.

Responda as três dimensões de forma independente.

## 1. `perigo` — o vídeo trata de um evento hidrológico ou de movimento de massa?

| Valor | Quando |
|---|---|
| `sim` | Chuva forte, temporal, enchente, alagamento, inundação, cheia de rio, enxurrada, deslizamento, desabamento ou queda de barreira causados por chuva. Também conta a previsão ou o alerta *desse* tipo de evento, e as consequências diretas (desabrigados, resgate, obras emergenciais). |
| `nao` | Outro assunto, mesmo trágico: acidente de trânsito, incêndio, crime, futebol, obituário, política sem relação com o evento. Também: desabamento de prédio **sem** chuva como causa apontada. |
| `incerto` | O material disponível não permite decidir. Use pouco e explique em `observacao`. |

Exemplos:
- "Ônibus tomba na Serra de Petrópolis e deixa mortos" → `nao`. É acidente de trânsito, mesmo que houvesse neblina.
- "Chuva agrava erosão e parte de ponte desaba em Santa Bárbara d'Oeste" → `sim`.
- "Morre a atriz Glória Menezes" → `nao`.

## 2. `episodio` — trata **deste** episódio, ou seja, da chuva em curso na data do alerta?

| Valor | Quando |
|---|---|
| `sim` | Fala do evento em curso na janela do alerta (do dia anterior até cerca de 3 dias depois da abertura), inclusive a previsão imediata. |
| `nao` | Outro episódio: tragédia de anos anteriores, aniversário de desastre, documentário genérico sobre risco, matéria de outra semana. |
| `incerto` | Não dá para situar no tempo. |

A data de publicação ajuda, mas não decide sozinha: um vídeo publicado no dia pode tratar de uma tragédia antiga. Se `perigo = nao`, marque `episodio = nao`.

## 3. `lugar` — qual o escopo geográfico em relação ao município do alerta?

| Valor | Quando |
|---|---|
| `municipio` | Mostra ou relata condições, impactos ou ações **no município do alerta**, inclusive bairros e distritos dele, mesmo junto com outras cidades ("deslizamentos em Gaspar e Blumenau" vale para o alerta de Blumenau). |
| `regiao_vizinho` | Trata da região (Grande SP, Vale do Taquari, Baixada) ou de municípios vizinhos sem relatar nada no município do alerta. |
| `estado_outro` | Só o estado em geral, ou outro lugar sem relação. |
| `indeterminado` | Não dá para saber onde. |

**Cuidados:**
- **Homônimos.** "Pelotas" em espanhol (bolas), "Santos" (o time de futebol), "Registro", "Ribeira" (o rio): o nome aparecer não basta. O vídeo precisa tratar do município.
- **Rios e vales.** "Rio Ribeira", "Vale do Taquari" e "Bacia do Itajaí" não equivalem ao município.
- **Capital paulista.** "SP" ou "São Paulo" sozinhos são ambíguos. Só marque `municipio` para alerta da capital se o vídeo tratar da cidade (bairros, zonas, "capital").
- **Lista sem conteúdo.** Se o município aparece só numa lista de cidades em alerta, sem nada relatado sobre ele, marque `regiao_vizinho`.

## 4. `usou_transcricao`

Marque `sim` se a sua decisão dependeu dos trechos da transcrição ou de assistir ao vídeo. Marque `nao` se título e descrição bastaram.

## Procedimento

1. **Treino:** a planilha `anotacao_treino.xlsx` tem 30 pares. Eles não entram na análise. Discuta as divergências do treino com o pesquisador antes de começar.
2. **Às cegas:** cada codificador trabalha sozinho, sem ver os rótulos do outro nem a decisão do sistema.
3. **Ordem:** siga a ordem da planilha, que é aleatória. Não ordene nem filtre antes de terminar.
4. **Ritmo:** cerca de 40 segundos por par. Abra o vídeo só quando título, descrição e trechos não bastarem.
5. **Confiabilidade:** o alfa de Krippendorff é calculado por dimensão nos pares duplicados. A meta é ≥ 0,80; abaixo de 0,67 o livro de códigos é revisto, uma única vez.
6. **Adjudicação:** as divergências são resolvidas pelo pesquisador e registradas. O rótulo final fica na chave.

## Proteção de dados

- Os títulos são públicos, mas a planilha fica no Drive do projeto e não vai ao repositório.
- Não copie comentários nem nomes de usuários para fora da planilha.
- Quem codifica assina termo de confidencialidade e consta na equipe do projeto no CEP.
