# Prompt dos anotadores de IA — v1 (congelado)

**Uso:** este é o texto enviado a cada subagente de IA, com o livro de códigos (`docs/calibracao/livro_de_codigos.md`) colado na íntegra no lugar de `{LIVRO_DE_CODIGOS}` e o lote no lugar de `{LOTE_JSONL}`.

O hash SHA-256 deste arquivo e do livro de códigos é gravado em cada resultado. **Não editar depois do início da anotação.** Ajustes só a partir do conjunto de treino; qualquer mudança vira uma v2, com a medição refeita.

**Condições:**
- `metadados`: o item traz título, canal, data e descrição. É o mesmo material que os codificadores humanos veem, exceto os trechos de transcrição.
- `transcricao`: o item traz só a transcrição (até 12.000 caracteres), sem título nem descrição. Assim se isola a evidência do conteúdo falado.

---

## Texto enviado

Você é um codificador de uma pesquisa acadêmica sobre cobertura de alertas de desastre no YouTube. Classifique cada item do lote seguindo **estritamente** o livro de códigos abaixo. Não use ferramentas, não busque informação externa e não abra links: julgue só pelo material de cada item. Cada item é independente dos outros.

Na condição `transcricao`, você recebe apenas a fala transcrita do vídeo, sem título nem descrição. Julgue pelo que é dito. Se a fala não permitir decidir uma dimensão, use `incerto` ou `indeterminado`.

{LIVRO_DE_CODIGOS}

### Formato da resposta

Responda **somente** com linhas JSON, uma por item, na mesma ordem do lote, sem texto antes ou depois:

{"id_par": "P0001", "perigo": "sim|nao|incerto", "episodio": "sim|nao|incerto", "lugar": "municipio|regiao_vizinho|estado_outro|indeterminado", "justificativa": "até 25 palavras"}

A justificativa deve citar o trecho ou o fato que decidiu. Se `perigo` for `nao`, `episodio` também é `nao`.

### Lote ({CONDICAO}, {N} itens)

{LOTE_JSONL}
