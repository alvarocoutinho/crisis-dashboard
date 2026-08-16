# Pipeline ODRD — Guia de Setup

Este documento leva você do zero à automação ativa. Ordem importa — cada passo depende dos anteriores.

**Tempo estimado**: 45 minutos na primeira vez (30 min de Google Cloud + 15 min de GitHub).

---

## Pré-requisitos

- [ ] Conta Google (a mesma que já usa Drive)
- [ ] Conta GitHub com acesso ao repo `crisis-dashboard`
- [ ] Todos os arquivos das levas 1 e 2 já commitados no repo
- [ ] Pasta `faa_poc/` copiada do `from_alert_to_action_poc_v1` para dentro do `crisis-dashboard/`

---

## Parte 1 — Google Cloud: criar Service Account

Objetivo: criar uma "conta de máquina" que o GitHub Actions vai usar para escrever no seu Google Drive sem precisar do seu login pessoal.

### 1.1 Criar projeto no Google Cloud

1. Acesse https://console.cloud.google.com
2. No menu superior, clique no seletor de projetos → **NEW PROJECT**
3. Nome: `odrd-pipeline` (ou similar)
4. Organização: deixe como está (ou "No organization" se for Google pessoal)
5. Clique **CREATE**. Aguarde 30 segundos.
6. Selecione o projeto recém-criado no seletor superior

### 1.2 Habilitar Google Drive API

1. Menu ☰ → **APIs & Services** → **Library**
2. Buscar "Google Drive API"
3. Clicar em "Google Drive API" → **ENABLE**
4. Aguardar ~1 minuto

### 1.3 Criar Service Account

1. Menu ☰ → **IAM & Admin** → **Service Accounts**
2. Clicar **+ CREATE SERVICE ACCOUNT** no topo
3. Preencher:
   - **Service account name**: `odrd-pipeline-bot`
   - **Service account ID**: preenchido automaticamente (`odrd-pipeline-bot`)
   - **Description**: `Bot que escreve corpus do ODRD em pasta compartilhada do Drive`
4. Clicar **CREATE AND CONTINUE**
5. Pular **Grant this service account access to project** (não precisa)
6. Pular **Grant users access to this service account** (não precisa)
7. Clicar **DONE**

### 1.4 Gerar chave JSON da Service Account

1. Na lista de Service Accounts, clique no `odrd-pipeline-bot@...` recém-criado
2. Aba **KEYS** → **ADD KEY** → **Create new key**
3. Tipo: **JSON** → **CREATE**
4. Um arquivo `.json` será baixado automaticamente para seu computador
5. **Guarde este arquivo em local seguro** — se perder, precisa gerar outra chave. Se vazar, revogar imediatamente.
6. Abra o arquivo e copie o valor do campo `client_email` — algo como `odrd-pipeline-bot@odrd-pipeline.iam.gserviceaccount.com`

### 1.5 Criar pasta no seu Drive e compartilhar

Este passo é o que dá acesso à Service Account. Ela NÃO vê nada do seu Drive por padrão — só o que você compartilha explicitamente.

1. Abra https://drive.google.com (logado na SUA conta pessoal)
2. Clique **+ New** → **New folder** → nome: `ODRD-piloto-tecnico`
3. Clique com botão direito na pasta → **Share** (ou **Compartilhar**)
4. Cole o e-mail da Service Account que copiou no passo 1.4
5. Permissão: **Editor**
6. **Desmarque** "Notify people" (não faz sentido notificar bot)
7. Clique **Share**

Confirmação: a Service Account agora tem acesso apenas a esta pasta específica. O resto do seu Drive permanece inacessível a ela.

### 1.6 Preparar a chave para GitHub Secrets

O JSON tem quebras de linha na chave privada que às vezes o GitHub Secrets estraga. Faça codificação base64 para evitar problemas:

**No Windows PowerShell:**
```powershell
$json = Get-Content "C:\caminho\para\odrd-pipeline-xxxxx.json" -Raw
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)) | Set-Clipboard
Write-Host "Base64 copiado para o clipboard. Cole no GitHub Secret."
```

**No Linux/macOS:**
```bash
base64 -w 0 ~/Downloads/odrd-pipeline-xxxxx.json | pbcopy   # macOS
base64 -w 0 ~/Downloads/odrd-pipeline-xxxxx.json | xclip   # Linux
```

O `gdrive.py` do pipeline tenta base64 primeiro, JSON cru como fallback — ambos funcionam.

---

## Parte 2 — GitHub Secrets

Objetivo: cadastrar todas as credenciais como secrets criptografados no repo.

### 2.1 Acessar Secrets do repo

1. Abra o repo `crisis-dashboard` no GitHub
2. **Settings** (aba superior direita) → **Secrets and variables** → **Actions**
3. Aba **Secrets** (não Variables)

### 2.2 Cadastrar cada secret

Clique **New repository secret** para cada um dos abaixo:

| Nome do Secret | Valor |
|---|---|
| `YOUTUBE_API_KEY` | Sua YouTube Data API v3 key (a mesma do Colab) |
| `HF_TOKEN` | Token HuggingFace com escopo `Read` (o mesmo do Colab) |
| `PED_EMAIL` | E-mail cadastrado no CEMADEN PED |
| `PED_PASSWORD` | Senha do PED |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Base64 do JSON da Service Account (do passo 1.6) |

`GITHUB_TOKEN` **não precisa cadastrar** — GitHub fornece automaticamente por workflow.

### 2.3 Verificação

Ao cadastrar, GitHub mostra apenas nome + data. Valor nunca é exibido de novo. Se digitou errado, delete e cadastre de novo — GitHub não permite edição.

---

## Parte 3 — Ativar o workflow

### 3.1 Confirmar estrutura de arquivos no repo

Antes de ativar, confirme que os arquivos estão nos lugares certos. No terminal local do repo:

```powershell
# PowerShell
Get-ChildItem -Recurse -File | Where-Object {
  $_.FullName -match '(pipeline\.py|pipeline\.yml|gdrive\.py|state_manager\.py|build_live\.py|bertimbau\.py|requirements-pipeline\.txt|faa_poc)'
} | Select-Object FullName
```

Estrutura esperada:
```
crisis-dashboard/
├── .github/workflows/pipeline.yml
├── faa_poc/                          (copiado do poc_v1)
│   ├── cemaden.py
│   ├── youtube.py
│   ├── pipeline.py                   (do faa_poc, não confundir)
│   └── ...
├── odrd_bridge/
│   ├── __init__.py
│   ├── bertimbau.py
│   ├── build_live.py
│   ├── gdrive.py
│   └── state_manager.py
├── scripts/
│   └── pipeline.py                   (o entrypoint)
├── src/data/
│   ├── events.json
│   ├── live.json                     (do piloto de 15/08)
│   └── state.json                    (do piloto de 15/08)
└── requirements-pipeline.txt
```

Commit tudo se ainda não fez:
```powershell
git add .github/ odrd_bridge/ scripts/ faa_poc/ requirements-pipeline.txt
git commit -m "feat: pipeline ODRD com GitHub Actions"
git push origin main
```

### 3.2 Primeiro run: manual em dry-run

**Não deixe o cron rodar ainda.** Primeiro run deve ser manual em dry-run para validar sem risco de commit ruim.

1. Abra o repo no GitHub
2. Aba **Actions**
3. Sidebar esquerda: clique em **ODRD Pipeline**
4. Botão **Run workflow** (direita)
5. Preencha:
   - `dry_run`: **✓ marque** como true
   - `limit_alerts`: `2`
6. Clicar **Run workflow**

Aguarde ~5 minutos. Aba Actions vai mostrar o job rodando.

### 3.3 Ler os logs do primeiro run

Ao terminar, clique no run → clique em **run-pipeline** → expanda cada step.

**Sinais de sucesso**:
- ✓ Todos os steps verdes
- Step "Executar pipeline" mostra logs como o do Colab: `CEMADEN devolveu N alertas`, `alertas novos: [...]`, `--dry-run: NÃO persistindo`
- Step "Interpretar exit code": `status=success` (ou `status=maintenance` se algo parcial)
- Step "Commit condicional": **pulado** por causa de `!inputs.dry_run`

**Sinais para investigar**:
- ✗ Step "Executar pipeline" vermelho → ler traceback nos logs
- Step "Cache do checkpoint HuggingFace": primeira vez sempre é cache miss, download completo ~437MB (~1-2 min)
- Se aparecer "Pasta 'ODRD-piloto-tecnico' não encontrada" → você pulou passo 1.5 ou compartilhou com e-mail errado

### 3.4 Segundo run: manual sem dry-run

Se o primeiro run passou limpo:

1. Aba Actions → Run workflow
2. `dry_run`: **desmarque** (false)
3. `limit_alerts`: `2` (ainda conservador)
4. Run workflow

Aguarde ~7 minutos. Ao terminar:

- Verifique que houve **novo commit** na main pelo bot `odrd-pipeline[bot]`
- Verifique que `src/data/live.json` e `state.json` foram atualizados
- Vercel deve rebuildar automaticamente em ~90 segundos
- Abra `crisis-dashboard-alco5.vercel.app/live` e valide visualmente

Verifique também no Google Drive:
- Pasta `ODRD-piloto-tecnico/` deve ter subpastas `2026/08/alerta_XXX/`
- Cada uma com `metadata.json`, `collection_log.jsonl`, e (se houve dados) `comments_raw.jsonl` etc.

### 3.5 Ativar cron automático

Se os passos 3.3 e 3.4 passaram sem problema, **o cron já está ativo** — o workflow YAML tem `on: schedule: cron: '0 */6 * * *'`, então dispara sozinho a partir do próximo horário (00h/06h/12h/18h UTC).

**Não há botão de "ativar"** — commitar o `pipeline.yml` na main é o que ativa.

**Para desativar temporariamente** (ex: você vai viajar e não quer commits em travar): abra o repo → Actions → ODRD Pipeline → menu **...** → **Disable workflow**. Reativar depois é botão único.

---

## Parte 4 — Manutenção e monitoramento

### 4.1 Sinais que o pipeline está saudável

Você deveria ver, ao longo de um dia normal:

- 4 novos commits do bot na `main` (00h, 06h, 12h, 18h UTC = 21h, 03h, 09h, 15h BRT)
- Mensagens no padrão `✓ pipeline: success @ YYYY-MM-DD HH:MM UTC`
- Zero issues abertas com label `pipeline-failure`
- Google Drive crescendo com novos snapshots

### 4.2 Sinais de problema

- **Mensagem começando com `⚠ pipeline: maintenance`**: execução parcial. Investigar logs, mas não urgente — próximo cron pode se recuperar.
- **Issue automática aberta com label `pipeline-failure`**: falha catastrófica, live.json NÃO foi commitado. Você precisa agir: ler logs do run linkado, corrigir causa, fazer manual retry via workflow_dispatch.
- **Sem commits do bot por >8h**: cron parou de disparar. Verificar aba Actions.

### 4.3 Custos e cotas

- **GitHub Actions**: 4 runs/dia × ~5min = ~600 min/mês. Free tier de repo privado é 2000 min/mês. **75% de folga.**
- **YouTube Data API**: cota diária de 10.000 unidades. Uso estimado: ~200 unidades por alerta processado × ~5 alertas × 4 ciclos = 4.000/dia. **60% de folga.**
- **Google Drive Storage**: cada snapshot ~1-100KB. 30 alertas/mês × 4 arquivos × ~50KB = ~6MB/mês. Free tier é 15GB. **Praticamente irrelevante.**
- **HuggingFace Hub**: apenas download do checkpoint (~437MB) uma vez a cada ~7 dias (quando o cache do GitHub Actions expira). Grátis para modelos privados neste volume.

### 4.4 O que fazer se algo mudar

- **Rotação de credenciais**: cadastre nova YouTube API key/HF token/PED password → atualize o secret correspondente no GitHub. Não precisa mexer em código.
- **Novo alerta muito importante fora do cron**: Actions → Run workflow (com dry_run desmarcado) → executa em <5min.
- **Bug descoberto no pipeline**: corrige localmente, commita `main`, próximo cron usa a versão nova. Ou dispara manual para testar.
- **Aprovação do CEP finalmente sair**: mude `pilot_mode: false` no `build_live.py` (dois lugares: assinatura de função e chamadas explícitas). Refletirá na UI removendo o badge amarelo.

---

## Parte 5 — Diagnóstico de problemas comuns

### "Pasta 'ODRD-piloto-tecnico' não encontrada"

Causa: Service Account não tem acesso à pasta.

Solução:
1. Confirme que criou a pasta no seu Drive pessoal (passo 1.5)
2. Confirme que compartilhou com o `client_email` correto (não com seu email pessoal)
3. Confirme que o nome da pasta é *exatamente* `ODRD-piloto-tecnico` (ou o valor de `GDRIVE_FOLDER_NAME`)
4. Aguarde 1 minuto após compartilhar — Google às vezes leva alguns segundos para propagar

### "consulta ao CEMADEN falhou"

Causa: painel CEMADEN offline ou mudou schema.

Solução: pipeline continua com state anterior (não corrompe). Aguardar próximo cron. Se persistir >24h, investigar manualmente rodando `curl` no `CEMADEN_ALERTS_URL`.

### "ImportError: cannot import name 'X' from 'faa_poc.Y'"

Causa: mudou versão do `faa_poc` sem atualizar `pipeline.py`.

Solução: verificar se copiou o `faa_poc/` correto para o repo. Se atualizou o `faa_poc`, verificar assinaturas de função.

### Cache do HuggingFace estourando

Se cache do actions/cache atingir limite (10GB por repo), rotacionar a `key` do cache no `pipeline.yml`:

```yaml
key: hf-bertimbau-weaklabels-odrd-v0.2.0   # bump manual
```

### Cota YouTube esgotada antes de fim de dia

Cadência de 6h × múltiplos alertas simultâneos pode estourar. Duas soluções:

- Curto prazo: skip o próximo cron via GitHub Actions "Disable workflow" e reativar após reset (07h UTC = meia-noite Pacific)
- Longo prazo: reduzir `MAX_VIDEOS_PER_ALERT` no `pipeline.py` (default 10, pode ir para 5)

---

## Referências

- Documentação Google Drive API: https://developers.google.com/drive/api/guides/about-sdk
- Escopo `drive.file`: https://developers.google.com/drive/api/guides/api-specific-auth
- YouTube Data API cotas: https://developers.google.com/youtube/v3/getting-started#quota
- GitHub Actions cron: https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#schedule
- Concurrency control: https://docs.github.com/en/actions/using-jobs/using-concurrency
