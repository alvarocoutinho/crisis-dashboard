# ODRD Core — Freeze v1.0.0

Este documento sumariza o freeze da versão 1.0.0 do ODRD.

## Referência Git

- **Commit SHA (HEAD):** `f63dcca5dc07a88a9c3f8e1dc795cbae989e1e67`
- **Data do commit (UTC):** 2026-08-20T12:07:49-03:00
- **Tag:** `v1.0.0` (criar após review)

## Pacote

- **Arquivo:** `ODRD-core-v1.0.0.zip`
- **SHA-256:** `d729a90ccd9055f18cfaae1a68a78e665492fae3de4fa525d4767d77f3f6ade7`
- **Tamanho:** 4,011,773 bytes (3.83 MiB)
- **Arquivos incluídos:** 816

## Verificação

Para verificar a integridade do pacote:

```bash
# Linux/Mac
sha256sum -c ODRD-core-v1.0.0.sha256

# Windows (PowerShell)
Get-FileHash ODRD-core-v1.0.0.zip -Algorithm SHA256
```

O hash acima deve coincidir com o conteúdo de `ODRD-core-v1.0.0.sha256`.

## Reprodutibilidade

Para reconstruir o pacote a partir do repositório no commit `f63dcca5dc07a88a9c3f8e1dc795cbae989e1e67`:

```bash
git checkout f63dcca5dc07a88a9c3f8e1dc795cbae989e1e67
python scripts/freeze_v1.py
```

O ZIP resultante deve ter exatamente o mesmo hash SHA-256. Determinismo é
obtido por: ordenação alfabética estável das entradas, timestamp fixo (data
do commit HEAD), compressão de nível fixo, exclusão de artefatos não-fonte.

## Contexto de PI

Este freeze estabelece linha de base tecnológica anterior a qualquer vínculo
institucional Unicamp ou financiamento FAPESP. Ver `docs/ODRD_decisoes_PI_v1_pre_FAPESP.md`
para o raciocínio estratégico.

- **Licença:** dual — PolyForm Noncommercial 1.0.0 (Parte A) + reserva de uso
  comercial (Parte B). Ver `LICENSE` na raiz do pacote.
- **DOI Zenodo:** a preencher após depósito.

## Freeze executado em

2026-08-20T15:17:24Z
