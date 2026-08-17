# state.json — Schema v0.2 (Reforma das três flags)

**Status:** proposta canônica, aguardando aprovação para implementação.
**Substitui:** schema v0.1 (implícito, sem versão explícita).
**Motivação:** operacionalizar o desenho das três flags pactuado no wrap-up de 17/08/2026, emancipando o pipeline da taxonomia CEMADEN.

---

## 1. Mudanças de alto nível

- Novo campo `schema_version` no top-level (`"0.2"`).
- Novo bucket top-level `archived_alerts` (irmão de `active_alerts` e `extended_window_alerts`).
- Novo campo `last_cemaden_check_at` no top-level (para observabilidade — Prioridade 3).
- Cada alerta ganha **cinco campos novos** e mantém todos os campos v0.1 (compatibilidade retroativa com `build_live.py` e `Live.jsx` durante a transição).
- Nenhum campo v0.1 é removido nesta etapa. `priority_tier` permanece como metadado visual (espelho de `nivel_atual`); `flag` passa a ser o drive de cadência.

---

## 2. Schema top-level

```json
{
  "schema_version": "0.2",
  "pipeline_version": "0.2.0",
  "last_run_at": "2026-08-17T17:33:38Z",
  "last_run_status": "success",
  "last_run_duration_seconds": 1,
  "last_cemaden_check_at": "2026-08-17T17:33:38Z",
  "youtube_quota": {
    "used_today": 900,
    "reset_at": "2026-08-18T07:00:00Z"
  },
  "active_alerts": { "<alert_id>": { ... } },
  "extended_window_alerts": { "<alert_id>": { ... } },
  "archived_alerts": { "<alert_id>": { ... } }
}
```

**Semântica dos três buckets:**

- `active_alerts`: alerta ainda aberto no CEMADEN (`closed_at = null`). Pode ter qualquer `flag`.
- `extended_window_alerts`: fechado no CEMADEN (`closed_at != null`) mas ainda em observação. Só entra aqui se `flag ∈ {"acompanhamento", "prioritario"}` — ou seja, se em algum momento migrou. Alertas em `flag="alerta"` que fecham no CEMADEN não entram; são registrados no log agregado e removidos.
- `archived_alerts`: alerta que esgotou por regra temporal (`acompanhamento` sem dado novo por 14d, `prioritario` sem comentário novo por 28d). Metadados enxutos + `archived_at` + `archive_reason`. Dados de conteúdo (comentários) já estão no Drive; não há duplicação.

---

## 3. Schema por alerta

```json
{
  "codibge": "3550308",
  "municipio": "São Paulo",
  "uf": "SP",
  "nivel_atual": "Moderado",
  "priority_tier": "moderado",
  "flag": "acompanhamento",
  "flag_history": [
    {"flag": "alerta", "at": "2026-08-16T18:00:00Z"},
    {"flag": "acompanhamento", "at": "2026-08-16T18:33:51Z"}
  ],
  "opened_at": "2026-08-16T18:00:00Z",
  "last_seen_open_at": "2026-08-16T18:33:51Z",
  "closed_at": "2026-08-16T18:33:51Z",
  "transitions": [],
  "videos_collected": ["dQw4w9WgXcQ", "abc123def45"],
  "n_videos_aderentes": 2,
  "n_comments_valid": 0,
  "videos_with_valid_comments": [],
  "last_new_data_at": "2026-08-16T18:33:51Z",
  "last_new_comment_at": null,
  "last_collection_at": "2026-08-16T18:33:51Z",
  "next_collection_at": "2026-08-17T06:33:51Z"
}
```

### 3.1 Campos v0.1 preservados (14 campos)

Todos mantidos, sem mudança de semântica.

| Campo | Tipo | Semântica |
|---|---|---|
| `codibge` | string | IBGE 7-dígitos |
| `municipio` | string | Nome CEMADEN (Title Case) |
| `uf` | string | Sigla UF |
| `nivel_atual` | string | `"Moderado" \| "Alto" \| "Muito Alto"` — metadado CEMADEN |
| `priority_tier` | string | `"moderado" \| "alto" \| "muito_alto" \| "acompanhamento"` — **espelho visual** de `nivel_atual`; usado por `Live.jsx` para colorir dots. Sem semântica operacional em v0.2 |
| `opened_at` | ISO8601 | Abertura CEMADEN |
| `last_seen_open_at` | ISO8601 | Última vez que apareceu como ativo no CEMADEN |
| `closed_at` | ISO8601 ou null | Timestamp de fechamento CEMADEN |
| `transitions` | list | Trilha de mudanças de nível CEMADEN (Moderado→Alto etc). Não confundir com `flag_history` |
| `videos_collected` | list[str] | video_ids aderentes já coletados |
| `last_collection_at` | ISO8601 | Última coleta desta iteração |
| `next_collection_at` | ISO8601 | Próxima coleta prevista (agora derivada de `flag`, não de `priority_tier`) |

### 3.2 Campos novos (5 campos)

| Campo | Tipo | Semântica | Populado quando |
|---|---|---|---|
| `flag` | string | `"alerta" \| "acompanhamento" \| "prioritario"`. Drive único de cadência (24h / 12h / 6h). Sem regressão | Toda transição escreve aqui + em `flag_history` |
| `flag_history` | list[dict] | Trilha imutável de transições. Cada entrada `{"flag": str, "at": iso8601}`. Primeira entrada sempre `{"flag": "alerta", "at": opened_at}` | Append-only |
| `n_videos_aderentes` | int | Cumulativo desde `opened_at`. Redundante com `len(videos_collected)` mas explícito para dashboards e evitar recontagem | Incrementa quando `videos_collected` cresce |
| `n_comments_valid` | int | Cumulativo desde `opened_at`. Comentários com `n_model_labels ≥ 1` (score ≥ 0.5 em ≥1 das 8 classes) | Incrementa após cada coleta+predição |
| `videos_with_valid_comments` | list[str] | Set de video_ids que contribuíram com ≥1 comentário não-FP. Necessário para checar regra ≥2 vídeos distintos na promoção `acompanhamento → prioritario` sem reprocessar histórico | Union set a cada coleta+predição |
| `last_new_data_at` | ISO8601 ou null | `max(último novo vídeo aderente, último novo comentário coletado)`. Base da regra de arquivo de `acompanhamento` (14d) | Update a cada coleta que traz dado novo |
| `last_new_comment_at` | ISO8601 ou null | Último novo comentário coletado (não conta vídeo). Base da regra de arquivo de `prioritario` (28d) | Update a cada coleta que traz comentário |

### 3.3 Campos adicionais em `archived_alerts` (2 campos)

Alertas arquivados carregam todos os campos acima **mais**:

| Campo | Tipo | Semântica |
|---|---|---|
| `archived_at` | ISO8601 | Quando foi arquivado |
| `archive_reason` | string | `"acompanhamento_esgotado_14d" \| "prioritario_esgotado_28d"` |

---

## 4. Regras de transição (referência rápida)

```
alerta ──[primeiro vídeo aderente]──> acompanhamento
acompanhamento ──[n_comments_valid ≥ 50 AND len(videos_with_valid_comments) ≥ 2]──> prioritario

// arquivamento
alerta [closed_at != null] ────────────> log agregado + REMOVE do state
acompanhamento [now - last_new_data_at ≥ 14d] ──> archived_alerts + log agregado
prioritario [now - last_new_comment_at ≥ 28d] ──> archived_alerts + log agregado
```

**Sem regressão:** uma vez promovido a `prioritario`, não volta a `acompanhamento`.

**Cadências (drive único: `flag`):**
- `alerta`: 24h
- `acompanhamento`: 12h
- `prioritario`: 6h

---

## 5. Log agregado `src/data/alertas_agregados.csv`

Fica em `src/data/` ao lado dos demais artefatos canônicos (`state.json`, `live.json`, `events.json`). Semanticamente é dado científico (base de denominador de H2), não log de execução — nome "log agregado" é mantido por continuidade com o wrap-up de 17/08.

Chave composta: `(codibge, ano_mes, evento, nivel_cemaden)`. Uma linha por combinação. Contadores acumulam ao longo de eventos.

```csv
municipio,uf,codibge,ano_mes,evento,nivel_cemaden,n_emitidos,n_arquivados_alerta_puro,n_migrados_acompanhamento,n_migrados_prioritario,n_arquivados_completos
São Paulo,SP,3550308,2026-08,Risco Hidrológico,Moderado,3,2,1,0,0
```

**Regras de incremento (todas no bucket `ano_mes` do `opened_at` do alerta):**

- `n_emitidos += 1` na abertura do alerta
- `n_arquivados_alerta_puro += 1` se alerta fecha no CEMADEN sem ter migrado de `flag="alerta"`
- `n_migrados_acompanhamento += 1` na primeira transição `alerta → acompanhamento`
- `n_migrados_prioritario += 1` na primeira transição `acompanhamento → prioritario`
- `n_arquivados_completos += 1` quando alerta em `acompanhamento` ou `prioritario` vai para `archived_alerts` por regra temporal

**Nota:** contadores não fecham por linha (um alerta contribui para múltiplas colunas ao longo da vida). É log de eventos, não snapshot.

---

## 6. Migração v0.1 → v0.2 (política aprovada)

**D1 = B (agressiva) + D2 = 2 (preservar `priority_tier`).**

Aplicação retroativa da regra nova aos 12 alertas atuais:

1. Alertas com `videos_collected == []` E `closed_at != null` (fechados sem migrar): **removidos do state**, contam como `n_arquivados_alerta_puro` no log agregado do bucket `2026-08`.

2. Alertas com `videos_collected != []`: recebem `flag = "acompanhamento"`. Se estavam em `extended_window_alerts`, permanecem lá. Log agregado ganha `n_migrados_acompanhamento += 1`. `last_new_data_at = last_collection_at` (aproximação; primeiro vídeo real não é rastreável do state antigo).

3. Alertas ativos com `videos_collected == []`: `flag = "alerta"`. Permanecem em `active_alerts`. Log agregado ganha `n_emitidos += 1` (mesmo bucket).

4. Nenhum alerta atual atinge critério de `prioritario` (n_comments_valid é 0 por não termos histórico nos CSVs em nível de state; recontagem seria custosa e a próxima coleta com predição vai populá-lo naturalmente).

**Todos os alertas atuais ganham `n_emitidos += 1` no log agregado**, independente de terem migrado ou não — esta é a contagem de emissão, base de denominador para H2.

---

## 7. Compatibilidade com `build_live.py` e `Live.jsx`

**Esta etapa (migração + state_manager) não altera `build_live.py` nem `Live.jsx`.** Motivos:

- `build_live.py` lê `state.json` e produz `live.json` com o mesmo schema atual. Campos novos do state são ignorados por não serem lidos. Sem quebra.
- `Live.jsx` continua consumindo `live.json` no schema atual (`priority_tier`, `observation_status`). Como `priority_tier` foi preservado, dashboard funciona igual.
- Etapa 5 do plano (Live.jsx + eventsRepository) refatora frontend para consumir `flag`. Momento em que `build_live.py` também é atualizado para expor `flag` no `live.json`.

Ordem de risco crescente: migração (esta etapa) → state_manager → log agregado → build_live → Live.jsx. Cada etapa é reversível sem afetar a seguinte.
