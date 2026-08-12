# Schema de dados — `src/data/events.json`

Este documento descreve o formato dos objetos de evento consumidos pelo dashboard. Serve de referência para gerar novos JSONs (ex: dados operacionais LIVE) mantendo compatibilidade com a camada de UI.

## Estrutura de topo

O arquivo é um array JSON com um objeto por evento. Ordem não importa (o dashboard ordena internamente conforme o caso de uso).

```
[ Event, Event, ... ]
```

## Objeto `Event`

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | string | Identificador único do evento (ex: `"pernambuco_pilot_2026"`). Usado para roteamento e junções. |
| `municipio` | string | Nome legível do município/território (ex: `"Petrópolis"`, `"Rio Grande do Sul"`). |
| `uf` | string (2 chars) | Sigla da UF (ex: `"PE"`, `"RJ"`). |
| `tipo` | string | Descrição curta do tipo de ameaça (ex: `"Movimento de massa"`, `"Chuvas intensas"`). |
| `nivel` | string | Nível do alerta CEMADEN: `"Moderado"`, `"Alto"`, `"Muito Alto"`. |
| `data_alerta` | string | Data de abertura do alerta em formato `dd/mm/yyyy`. |
| `codibge` | string | Código IBGE de 7 dígitos do município. Usado para junções com bases externas. |
| `lat`, `lon` | number | Coordenadas do município do alerta. Usadas pelo `BrazilMap` para posicionar o pin. |
| `regime` | string | `"out_of_fold"` (evento não visto no treino) ou `"in_sample_exploratory"` (evento visto no treino). Determina badge visual e texto interpretativo. |
| `n_comments` | integer | Total de comentários no corpus deste evento. |
| `n_videos` | integer | Número de vídeos únicos do YouTube coletados. |
| `unlabeled` | integer | Comentários que não receberam nenhuma predição positiva. |
| `unlabeled_pct` | number | O mesmo em percentual (0–100). |
| `date_range` | array de 2 strings | Primeira e última data de coleta, formato `yyyy-mm-dd`. |
| `distribution` | array de `Category` | Contagens agregadas por categoria BERTimbau (8 categorias). |
| `timeline` | array de `TimelinePoint` | Série diária de volume de comentários. |
| `videos` | array de `Video` | Agregados por vídeo, ordenados por número de comentários (descendente). |
| `all_samples` | objeto `{categoryKey: [Sample]}` | Top-N amostras por categoria, ordenadas por score BERTimbau. |

## `Category` (item de `distribution`)

```json
{
  "key": "responsabilizacao_governanca",
  "label": "Responsabilização / governança",
  "count": 370,
  "pct": 35.3
}
```

Ordem canônica das 8 categorias (deve ser mantida em qualquer novo JSON):

1. `solidariedade_oracao_luto` — Solidariedade / oração / luto
2. `ajuda_resgate_doacoes` — Ajuda / resgate / doações
3. `responsabilizacao_governanca` — Responsabilização / governança
4. `infraestrutura_ocupacao_risco` — Infraestrutura / ocupação de risco
5. `clima_chuva_meio_ambiente` — Clima / chuva / meio ambiente
6. `experiencia_pessoal_local` — Experiência pessoal / local
7. `alerta_prevencao_cobranca` — Alerta / prevenção / cobrança
8. `critica_midia_informacao` — Crítica à mídia / informação

## `TimelinePoint`

```json
{ "date": "18/02/23", "count": 3 }
```

Formato da data: `dd/mm/yy` (não `dd/mm/yyyy` — o chart trunca melhor assim no eixo X).

## `Video`

```json
{
  "video_id": "rX6gxn3U4oI",
  "n_comments": 99,
  "total_likes": 254,
  "first_comment": "19/02/2023",
  "top_categories": [
    { "label": "Solidariedade", "count": 63 },
    { "label": "Clima/chuva", "count": 20 },
    { "label": "Responsabilização", "count": 8 }
  ]
}
```

- `video_id`: usado para construir URLs de YouTube e thumbnails
- `top_categories`: sempre no máximo 3 elementos, categorias com contagem zero excluídas
- `label` em `top_categories` usa rótulos curtos (`"Solidariedade"`, não `"Solidariedade / oração / luto"`) para caber no card

## `Sample`

```json
{
  "text": "Texto do comentário verbatim, até 400 chars.",
  "likes": 21,
  "score": 0.998,
  "date": "01/05/2026",
  "video_id": "abc123XYZ"
}
```

- `text`: comentário verbatim, truncado em 400 caracteres, identificadores de autor já suprimidos no CSV fonte
- `score`: probabilidade sigmoide de saída do BERTimbau para aquela categoria (0–1)
- `video_id`: usado para link "vídeo de origem" no modal
- `all_samples[categoryKey]` guarda até 20 amostras por categoria, ordenadas por `score` descendente

## Regime — regra de decisão

O campo `regime` deve refletir o checkpoint que foi usado para gerar as predições:

- Se o evento **estava no conjunto de treino** do checkpoint → `"in_sample_exploratory"`
- Se o evento **era o hold-out** do fold LOEO usado → `"out_of_fold"`

Predições in-sample são reportadas como evidência de viabilidade metodológica. Apenas out-of-fold constitui medição cientificamente validada. Esta distinção é exibida visualmente por badge no cabeçalho de cada evento.

## Compatibilidade forward

Ao gerar novos JSONs (ex: para a rota LIVE futura), qualquer campo *adicional* pode ser incluído sem quebrar o dashboard. Campos *obrigatórios* (todos os listados acima) devem estar presentes ou o componente correspondente pode falhar.

Se um novo campo é adicionado e usado por componente novo, atualizar também este documento e o `eventsRepository.js`.
