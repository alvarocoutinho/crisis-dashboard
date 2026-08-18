# Changelog

Todas as mudanças relevantes deste projeto são documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o versionamento segue [SemVer](https://semver.org/lang/pt-BR/).

---

## [1.0.0] — 2026-08-18

Freeze pré-institucional. Estabelece linha de base tecnológica anterior a qualquer vínculo formal Unicamp ou financiamento FAPESP — funciona como *Background IP* para eventual arquitetura futura em camadas (Core / Research Adapter / Commercial Adapter). Ver [ODRD_decisoes_PI_v1_pre_FAPESP.md](./docs/ODRD_decisoes_PI_v1_pre_FAPESP.md) para o raciocínio estratégico.

### Adicionado

- `LICENSE` dual — PolyForm Noncommercial 1.0.0 (Parte A, verbatim) + reserva de uso comercial (Parte B). Uso acadêmico, defesa civil, ONGs, governo e pesquisa liberado; uso comercial requer negociação separada com o titular.
- `README.md` v1.0 substituindo o boilerplate Vite — contexto científico, arquitetura, cadências operacionais, como rodar, estrutura do repo, dados e ética, coordenação institucional.
- `CHANGELOG.md` (este arquivo) — histórico consolidado v0.1 → v0.2 → v1.0.
- `FlagTimeline` no `AlertCard` — trilha visual das transições operacionais do alerta (`alerta` → `acompanhamento` → `prioritario`) com pills coloridos, duração entre transições e cauda "há X" indicando tempo no estágio atual.
- `PipelineHealthPanel` — separação semântica entre "Última verificação" (`state.last_cemaden_check_at`) e "Última coleta" (`max(alert.last_collection_at)`); grid de KPIs vai de 4 para 5 colunas em `md+`.
- `formatDuration()` helper em `Live.jsx` — formatação compacta de duração (min/h/d/mês) reutilizado pelo `FlagTimeline` e pelo `PipelineHealthPanel`.

### Alterado

- Header do `/live`: modelo de cadência tier-based antigo ("6h/12h/24h/48h por nível CEMADEN") substituído pelo modelo v0.2 (verificação 6h + coleta por flag 24h/12h/6h).
- Rodapé e nota de timeline em `dashboard.jsx`: "polling a cada 4h" → "6h" (reconciliação com o cron real).
- `LiveMap`: SVG passa a usar `viewBox` + `preserveAspectRatio="xMidYMid meet"` em vez de `width`/`height` fixos, corrigindo o corte lateral do mapa quando o container tem largura inferior a 380px.

### Pendências conhecidas

- `<TODO>` de email de contato na Parte B do `LICENSE` — resolver antes de publicar o Zenodo.
- DOI Zenodo do freeze — a preencher no `README.md` após execução do A8 (freeze scripts + release GitHub + depósito Zenodo).
- Reconciliação do PDF FAPESP com o modelo v0.2 (cadência, Reforma três flags) — deliberadamente adiada para pós-submissão, conforme regra registrada.
- Validação humana dos filtros de aderência (peça central do protocolo).
- Framework de anonimização LGPD para amostras de comentários.
- Aprovação CEP institucional formal.
- *Thresholds* calibrados por classe (hoje: 0.5 uniforme).

---

## [0.2.0] — 2026-08-17

**Reforma das três flags** — reescrita do modelo operacional de observação. Abandona a taxonomia CEMADEN (`Moderado`/`Alto`/`Muito Alto`) como *driver* de cadência de coleta e adota um sistema de *flags* orientado pelo comportamento empírico do sinal digital observado.

Justificativa: o modelo censitário anterior (365 dias de janela estendida para todo alerta, cadência por tier CEMADEN) não escalava — projeção de ~3.500 alertas Moderado simultâneos em janela estendida durante o verão estouraria cota YouTube, storage Drive e usabilidade do dashboard. Além disso, ancorar o critério de continuidade da observação na taxonomia institucional CEMADEN é epistemologicamente frágil: o critério deve ser endógeno ao objeto científico (o próprio sinal digital), não exógeno.

Reforma pactuada com a Profa. Leila incluindo definição operacional dos limiares.

### Adicionado

- Sistema de três *flags* operacionais como *drive* único de cadência de coleta (`nivel_cemaden` passa a ser metadado):
  - `alerta` (24h) — alerta CEMADEN aberto sem vídeo aderente ainda
  - `acompanhamento` (12h) — primeiro vídeo aderente identificado no YouTube (via `score_video` do faa_poc)
  - `prioritario` (6h) — ≥50 comentários não-FP (`n_model_labels ≥ 1`) em ≥2 vídeos distintos
- Schema v0.2 (`docs/state-schema-v0.2.md`): alertas ganham `flag`, `flag_history`, `n_videos_aderentes`, `n_comments_valid`, `videos_with_valid_comments`, `last_new_data_at`, `last_new_comment_at`; state ganha bucket `archived_alerts` e campo `last_cemaden_check_at`.
- `scripts/migrate_state_v0_1_to_v0_2.py` — migração idempotente com backup automático em `src/data/backups/`.
- `src/data/alertas_agregados.csv` — log agregado mensal por `codibge + ano_mes + evento + nivel_cemaden`, preserva denominador para H2 (silêncio) sem custo de storage por alerta.
- `odrd_bridge/state_manager.py` reescrito (356 → 714 linhas): `CADENCE_HOURS_BY_FLAG`, `promote_flag_if_eligible`, `archive_exhausted`, `bump_aggregate_log`, `load_aggregate_log`, `save_aggregate_log`; nova assinatura de `merge_new_alerts_from_cemaden` distinguindo `closed_to_extended` de `closed_to_puro`.
- `FlagFilterChips` no `/live` substituindo `TierFilterChips`; ordenação de cards por `sortAlertsByFlag` (prioritário no topo).
- Badge de *flag* no `AlertCard` como pill colorido (violeta / ciano / cinza-neutro), separado do dot de gravidade CEMADEN.
- Fallback para `GitHub Actions Artifacts` (retenção 90d) como camada de storage após colapso da service account no Drive.

### Alterado

- Cadência de coleta desacoplada da taxonomia CEMADEN. `nivel_cemaden` mantido como metadado descritivo, sem função operacional.
- Janela estendida deixa de ser censitária 365d — passa a ser regra temporal cronológica por flag (14d em `acompanhamento`, 28d em `prioritario` sem novo comentário → arquivo completo).
- `build_live.py` refatorado para aceitar `state` (fonte-de-verdade) e `previous_live` (preserva conteúdo entre ciclos); três *paths* de resolução por alerta (coletado no ciclo / não coletado com histórico / sem histórico).
- `pipeline.py` bump para `PIPELINE_VERSION = "0.2.0"`; `build_live_json` chamado incondicionalmente ao fim de todo run.
- Mapa `/live`: dots continuam colorindo por `priority_tier` (gravidade CEMADEN institucional — vermelho/laranja/amarelo), mas cards e filtros usam `flag` (estágio operacional ODRD — palette dedicada). Modelo dual explicitando a dupla natureza do projeto.

### Corrigido

- **Bug crítico do `build_live` em runs sem coleta:** `live.json` era reconstruído a partir de `alerts_log.csv` do faa_poc, que não existe em runs de verificação sem coleta — resultado: dashboard esvaziado. Corrigido com o *refactor* acima.
- Google Drive service account 403 (`Service Accounts do not have storage quota`) — Google desabilitou storage quota para service accounts em Drives pessoais. *Workaround*: substituição por GitHub Actions Artifacts (18 linhas no YAML, zero mudança em Python). Migração para storage definitivo pós-freeze.
- `priority_tier="acompanhamento"` residual em alertas migrados de v0.1 (semântica antiga) — helper `_normalize_priority_tier` normaliza na apresentação; script one-shot `scripts/normalize_priority_tier_v0_2.py` limpa em disco.
- Sincronia de commits: bug diagnosticado onde `Live.jsx` (Etapa 5) foi commitado sem o `build_live.py` correspondente. Corrigido; regra registrada: nomear anexos com nome final do arquivo, não com sufixo `_v2`.

### Removido

- Regra de fechamento 365d (censo temporal); função `close_extended_alert` marcada como *deprecated* com *no-op* de proteção.
- Configuração de upload direto para Google Drive (secrets preservados, env vars comentadas — reativar quando storage definitivo for decidido).

### Segurança

- `close_missing=False` quando consulta CEMADEN falha — previne fechamento em massa de alertas ativos por indisponibilidade transitória do PED (identificado durante dry-runs da v0.1).
- `load_state` v0.2 passa a rejeitar `state.json` v0.1 com mensagem explícita exigindo migração prévia.

---

## [0.1.0] — 2026-08-13 a 2026-08-16

**Primeira versão operacional autônoma.** Consolida dashboard demonstrativo com predições BERTimbau reais + pipeline automatizado no GitHub Actions.

Primeira coleta autônoma em produção: 16/08/2026 ~15:34 UTC, processando alertas em 6 municípios do Rio Grande do Sul — todos com 100% de silêncio digital observável (confirmado como operacionalização de H2).

### Adicionado

- **Camada 1:** Substituição de *weak labels* por predições BERTimbau reais. Checkpoint `alvarocoutinho/bertimbau-weaklabels-odrd` (subfolder `best_model`) uploadado no HuggingFace. Protocolo *Leave-One-Event-Out* com Pernambuco 2026 como *hold-out* (*out-of-fold*). Badges de regime por evento no dashboard (verde "Out-of-fold" para Pernambuco, âmbar "In-sample exploratório" para os demais).
- **Camada 2:** Separação de dados (`src/data/events.json`, ~614KB) e UI (`src/dashboard.jsx`, ~36KB). Camada de acesso via `src/services/eventsRepository.js` com 9 funções (`getAllEvents`, `getEventById`, `getVideosForEvent`, etc.). Schema formal em `docs/data-schema.md`.
- **Camada 3:** Roteamento com `react-router-dom` — Landing (`/`), Archive (`/archive`, dashboard histórico), Live (`/live`, escuta ativa). `vercel.json` com *rewrite* obrigatório para SPA routing. Filtro por UF no `/archive` com chips clicáveis (5 UFs no corpus). Filtro por macrorregião IBGE atuando como agregador acima do filtro UF. Aba de estudos acadêmicos por evento (`academic_studies` em `events.json`).
- **Camada 4:** Adaptador do pipeline operacional (`odrd_bridge/build_live.py`) alimentando a rota `/live` com dado real do pipeline.
- **Camada 5:** Pipeline automatizado completo — `.github/workflows/pipeline.yml` com cron `0 */6 * * *` + `workflow_dispatch`. Módulos: `odrd_bridge/bertimbau.py`, `build_live.py`, `state_manager.py`, `gdrive.py`; orquestrador `scripts/pipeline.py`. Service account Google Cloud (`odrd-pipeline-bot`) com Drive folder `ODRD-piloto-tecnico`. 5 GitHub Secrets registrados.
- `Live.jsx` completo com mapa D3, dots tier-colored (convenção CEMADEN), painel de saúde do pipeline (KPIs), banner de silêncio observável, seções de coleta prioritária e acompanhamento.

### Alterado

- Nomenclatura do projeto: "From Alert to Action" → "Observatório Digital de Riscos e Desastres (ODRD)".
- `dashboard.jsx`: 447KB → 36KB (redução de 92%) via separação dados/UI.
- Ordenação de amostras: por curtidas → por score do modelo (predição BERTimbau).

### Corrigido

- Seis bugs identificados durante dry-runs iterativos do pipeline:
  1. BERTimbau requer `subfolder='best_model'` em `AutoTokenizer.from_pretrained()`
  2. CEMADEN: função é `fetch_alerts(config)`, não `fetch_active_alerts()`
  3. CEMADEN retornando lista vazia em falha fechava todos os alertas ativos — bug de segurança corrigido com `close_missing=False`
  4. `FileNotFoundError` quando faa_poc não produz CSVs em silêncio total — helper `_read_csv_or_empty()`
  5. Google Drive scope `drive.file` não acessa pastas compartilhadas — trocar para `drive`
  6. `alerts_log.csv` era sobrescrito por alerta em cada iteração do faa_poc; `metadata.json` passa a ler de `state.json` (fonte canônica)
- Regra crítica registrada: `lucide-react` não exporta `Youtube` — usar `Video`. Bug já se repetiu duas vezes antes desta versão.

### Achado científico

- Comparação *weak label* → predição BERTimbau para Pernambuco 2026 (*out-of-fold*): perfil discursivo estruturalmente distinto — responsabilização/governança elevada (35,3%), solidariedade baixa (21,8%, contra 41,9–59,6% nos demais eventos). Padrão robusto confirmado por predição cientificamente válida (não artefato do *weak label*).

---

[1.0.0]: https://github.com/alvarocoutinho/crisis-dashboard/releases/tag/v1.0.0
[0.2.0]: https://github.com/alvarocoutinho/crisis-dashboard/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alvarocoutinho/crisis-dashboard/releases/tag/v0.1.0
