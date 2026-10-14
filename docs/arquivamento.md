# Arquivamento dos dados (regime provisório, desde 14/10/2026)

## Classes de dados

| Classe | Exemplos | Onde fica |
|---|---|---|
| **A. Públicos institucionais** | XML CAP da IDAP, retratos do painel do CEMADEN, catálogos | Repositório (`data/idap`, `data/cemaden`) e Release `idap-arquivo` |
| **B. Derivados sem identificação** | contagens, IDs de vídeo, flags, rótulos, `state.json`, `live.json` | Repositório |
| **C. Conteúdo do YouTube** | comentários (texto), títulos, descrições, candidatos, transcrições | Artifacts **cifrados** do pipeline, juntados num **backup mensal cifrado** |

## Por que cifrar

O repositório é público. No GitHub, artifacts podem ser baixados por qualquer pessoa logada com acesso de leitura ao repositório, e num repositório público isso é qualquer pessoa logada. Os artifacts do pipeline levam o texto dos comentários, que é dado pessoal (LGPD). Até a v0.3.3, levavam também o nome dos autores.

Desde 14/10/2026:
- o pipeline cifra os CSVs (7z, AES-256, com os nomes dos arquivos também cifrados) antes de enviar o artifact;
- sem o segredo `BACKUP_PASSPHRASE`, o pipeline não envia nada;
- os artifacts antigos, de 18/08 a 14/10, **não são cifrados**. Devem ser apagados depois que o primeiro backup for baixado e conferido (ver abaixo).

## Backup mensal (`backup-mensal.yml`)

- **Quando roda:** todo dia 1, às 09h17 (horário de Brasília), ou manualmente.
- **O que faz:**
  1. baixa todos os artifacts do pipeline ainda válidos (até 90 dias);
  2. cifra o conjunto em `odrd-backup-AAAA-MM.7z`, com a mesma senha;
  3. testa a integridade do pacote;
  4. publica o pacote como artifact por 90 dias;
  5. commita o manifesto em `data/backups/manifesto_AAAA-MM.csv`, com nomes, datas, tamanhos e hashes, sem conteúdo.
- **Sobreposição:** cada backup inclui tudo dos últimos 90 dias, então dois backups seguidos se sobrepõem. Esquecer de baixar um mês não perde dados. Esquecer três meses seguidos perde.

### Rotina do pesquisador (todo mês)

1. **Baixar:** Actions → "ODRD Backup mensal dos dados brutos" → execução do dia 1 → baixar `odrd-backup-AAAA-MM`.
2. **Conferir:** comparar o SHA-256 do `.7z` com o do arquivo `.sha256` que vem junto. No Windows: `certutil -hashfile odrd-backup-AAAA-MM.7z SHA256`.
3. **Guardar em dois lugares,** por exemplo o Google Drive pessoal e um HD externo. Como o pacote é cifrado, guardá-lo em conta pessoal não expõe os comentários.
4. **Para abrir:** use o 7-Zip (Windows) com a senha. No Colab: `!7z x arquivo.7z -pSENHA`.
5. **Só no primeiro mês, depois de conferir:** rodar o workflow manualmente com `apagar_originais = APAGAR`. Isso apaga os artifacts não cifrados listados no manifesto daquele mês.

**A senha (`BACKUP_PASSPHRASE`) é a única forma de abrir os backups.** Guarde-a num gerenciador de senhas. Sem ela, os dados são irrecuperáveis.

## Destino definitivo (pendente)

O destino definitivo da classe C é uma conta institucional (Unicamp, ou o centro de pesquisa ou o CEMADEN, quando houver vínculo), com Drive compartilhado. Não foi usada a conta USP, porque ela será desativada na mudança de instituição.

Quando houver conta institucional, o pipeline volta a enviar para o Drive (`odrd_bridge/gdrive.py`, com `supportsAllDrives`), e os backups mensais acumulados são migrados para lá.

## Pendências de conformidade

- **YouTube API, Developer Policies III.E.4:** dados obtidos sem autorização do usuário só podem ser guardados temporariamente, por até 30 dias. A guarda prolongada para pesquisa depende do **YouTube Researcher Program**, cujos termos permitem fixar os dados num ponto no tempo para concluir a análise.
- **Retenção:** o texto dos comentários fica só no armazenamento restrito e cifrado, pelo tempo da pesquisa. Só são publicados agregados e métricas derivadas.
