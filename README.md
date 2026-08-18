# Observatório Digital de Riscos e Desastres (ODRD)

Plataforma ponta a ponta de observação da **reação pública digital observável** a alertas hidrometeorológicos no Brasil. Acopla o Painel de Alertas do CEMADEN à coleta de comentários públicos no YouTube e classifica o discurso em oito funções comunicacionais via BERTimbau *fine-tuned*.

**Dashboard em produção:** <https://crisis-dashboard-alco5.vercel.app/>
**Versão:** v1.0.0 (freeze pré-institucional — ver [CHANGELOG.md](./CHANGELOG.md))
**Licença:** dual — [PolyForm Noncommercial 1.0.0](./LICENSE) para uso não-comercial; uso comercial reservado.

---

## Escopo científico

O ODRD é o **instrumento de escuta** do CEPID CLIMARES / Eixo 7 (Educação e Difusão de Conhecimento) — complementar, não substitutivo, à infraestrutura de emissão do CEMADEN. Instrumenta a lacuna entre alerta e reação pública documentada em Marchezini (2018), Sulaiman & Aledo (2016) e no debate sobre *last-mile* em sistemas de alerta.

**O que o sistema mede:** presença/ausência, volume e composição temática de manifestações digitais observáveis em janelas fixas após a publicação do alerta.

**O que o sistema NÃO mede:** percepção de risco (construto psicológico específico, Slovic 1987; Wachinger et al. 2013). Silêncio digital ≠ ausência de percepção — é dado positivo do protocolo, não falha do sistema.

Fundamentação teórica: sociologia do risco de Ulrich Beck e Anthony Giddens (via recepção brasileira em Ferreira, Guivant, Bosco), organizada operacionalmente pelo *Access Model* de Wisner, Blaikie, Cannon & Davis (2004).

---

## Arquitetura

O sistema tem dois componentes acoplados em um único repositório:

**Backend (Python / GitHub Actions).** Pipeline autônomo que executa a cada 6h (`cron: 0 */6 * * *`) mais gatilho manual (`workflow_dispatch`). Módulos principais em `odrd_bridge/`:

- `state_manager.py` — máquina de estado v0.2 com três *flags* operacionais (`alerta` / `acompanhamento` / `prioritario`) e regras de arquivamento por regra temporal
- `build_live.py` — reconstrói `src/data/live.json` a partir de `state.json` (fonte-de-verdade) preservando dados históricos entre ciclos
- `bertimbau.py` — inferência do classificador (`alvarocoutinho/bertimbau-weaklabels-odrd`, subfolder `best_model`) sobre comentários coletados
- `gdrive.py` — upload opcional dos CSVs de coleta (atualmente desativado; artefatos vão para GitHub Actions Artifacts com retenção 90d)

Adaptadores em `faa_poc/` — integração com CEMADEN PED (alertas) e YouTube Data API v3 (comentários). Coleta exclusivamente via canais oficiais autorizados; nenhum *web-scraping*.

**Frontend (React 19 + Vite 8 + Tailwind 4).** SPA hospedado no Vercel com três rotas:

- `/` — Landing institucional
- `/archive` — Corpus retrospectivo de 6 eventos (39.488 comentários, 566 vídeos) com predições BERTimbau LOEO
- `/live` — Escuta prospectiva: mapa geográfico + cards de alerta com trilha de *flags*, cadência por estágio, silêncio observável, distribuição temática

O contrato de dados entre backend e frontend é o schema documentado em [`docs/data-schema.md`](./docs/data-schema.md) e [`docs/state-schema-v0.2.md`](./docs/state-schema-v0.2.md).

---

## Cadências operacionais (v0.2)

Verificação do painel CEMADEN: **a cada 6h** (cron do pipeline).

Coleta de dados por estágio operacional (drive único, `nivel_cemaden` como metadado):

| Flag | Cadência | Gatilho de entrada |
|---|---|---|
| `alerta` | 24h | Alerta aberto no CEMADEN, sem vídeo aderente ainda |
| `acompanhamento` | 12h | Primeiro vídeo aderente identificado no YouTube |
| `prioritario` | 6h | ≥50 comentários não-FP em ≥2 vídeos distintos |

Arquivamento por regra temporal cronológica (não por ciclos):

- `alerta` fechado no CEMADEN sem migrar → incrementa log agregado, sai do state
- `acompanhamento` sem novo dado por 14 dias → arquivo completo
- `prioritario` sem novo comentário por 28 dias → arquivo completo

---

## Como rodar

### Dashboard local

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # build de produção → dist/
```

### Pipeline (Python)

Rodagem local para desenvolvimento (não recomendada para produção — o pipeline é projetado para GitHub Actions):

```bash
python -m venv .venv
source .venv/bin/activate            # Linux/Mac
.venv\Scripts\activate               # Windows
pip install -r requirements-pipeline.txt

# Variáveis de ambiente requeridas
export YOUTUBE_API_KEY=...
export HF_TOKEN=...
export PED_EMAIL=...                 # credenciais CEMADEN PED
export PED_PASSWORD=...

python scripts/pipeline.py --dry-run  # não persiste state/live
```

Em produção, o pipeline roda no GitHub Actions com *secrets* registrados; ver [`.github/workflows/pipeline.yml`](./.github/workflows/pipeline.yml) e [`docs/pipeline-setup.md`](./docs/pipeline-setup.md).

---

## Estrutura do repositório

```
crisis-dashboard/
├── src/                        # Frontend React
│   ├── App.jsx  Landing.jsx  Live.jsx  dashboard.jsx
│   ├── data/                   # events.json (corpus histórico) + live.json (state atual)
│   └── services/               # eventsRepository.js — camada de acesso a dados
├── odrd_bridge/                # Backend Python — pipeline v0.2
├── faa_poc/                    # Adaptadores CEMADEN + YouTube (frozen)
├── scripts/                    # Orquestrador + scripts de migração
├── docs/                       # Schemas de dados e state, setup do pipeline
├── .github/workflows/          # pipeline.yml (cron 6h + manual)
├── LICENSE                     # PolyForm-NC-1.0.0 + reserva de uso comercial
├── CHANGELOG.md                # Histórico de versões
└── README.md                   # Este arquivo
```

---

## Dados, ética e limites

- **Fontes:** CEMADEN PED (alertas), YouTube Data API v3 (comentários), IBGE (códigos de município), AdaptaBrasil/MCTI (vulnerabilidade territorial).
- **LGPD e CNS 510/2016:** o corpus atual é de comentários públicos em vídeos públicos; comentários verbatim não são publicados em interfaces indexáveis do dashboard. Framework de anonimização em desenvolvimento para amostras a publicar.
- **CEP:** aprovação institucional pendente (Unicamp); coleta prospectiva científica só inicia após aprovação. Modo atual do pipeline: `pilot_mode: true`.
- **Classificador:** BERTimbau *fine-tuned* sobre *weak labels*, validado via *Leave-One-Event-Out* com Pernambuco 2026 como *hold-out* (*out-of-fold*). Demais eventos do corpus são in-sample exploratórios. *Thresholds* atuais em 0.5 (calibração validada pendente). Nenhuma predição do modelo retroalimenta seu próprio treinamento.
- **Repositório privado por design nesta fase.** Reavaliação pós-freeze v1.0 e submissão FAPESP.

---

## Como citar

DOI Zenodo do freeze v1.0.0: **a preencher após [A8 — freeze scripts]**.

Enquanto o DOI não é emitido, cite como:

> Coutinho, Á. L. A. (2026). *Observatório Digital de Riscos e Desastres (ODRD) — v1.0.0*. NEPAM/Unicamp. https://github.com/alvarocoutinho/crisis-dashboard

---

## Coordenação e vínculo institucional

**Álvaro Luz Alves Coutinho** — NEPAM / PPGA&S, Universidade Estadual de Campinas (Unicamp)
**Supervisão:** Profa. Leila da Costa Ferreira
**Contexto institucional:** CEPID CLIMARES / Eixo 7 · parceria científica com CEMADEN

Contato para licenciamento comercial: ver [LICENSE](./LICENSE), Parte B.

---

## Aviso institucional

Este sistema é **complementar** à infraestrutura de alertas do CEMADEN. Não emite alertas, não substitui canal de emergência e não fornece diagnóstico de risco. Instrumenta exclusivamente a camada de observação da reação pública digital *ex post* à publicação do alerta.
