# Observação horária do CEMADEN

## Por quê

O pipeline consulta o painel de alertas do CEMADEN (`wsAlertas2`) a cada 6 h e só registra os alertas abertos naquele instante. Um alerta que abre e fecha entre duas consultas nunca entra no state, então não gera coleta no YouTube nem aparece no painel.

Nos dados até 14/10/2026, nenhum alerta observado durou menos de 13 h; a mediana foi de cerca de 100 h. Isso é coerente com duas explicações, e hoje não dá para distinguir entre elas:
1. o CEMADEN emite quase só alertas longos;
2. o pipeline perde os curtos (viés de sobrevivência).

## O que faz

O workflow `cemaden-horario.yml` roda no minuto 41 de cada hora e executa `scripts/observe_cemaden.py`. Ele lê o painel inteiro, sem filtro de nível ou evento, e grava em `data/cemaden/`:

| Arquivo | Conteúdo |
|---|---|
| `alertas_observados.csv` | uma linha por alerta: primeira e última observação, níveis vistos, reaberturas, duração mínima e máxima, se está no escopo do pipeline e se o pipeline chegou a vê-lo (`visto_no_state`) |
| `capturas.csv` | uma linha por consulta: status, total, no escopo, novos, fechados, fechados sem passar pelo pipeline, níveis, hash |
| `snapshots/AAAA-MM.jsonl` | o JSON bruto de cada consulta cujo conteúdo mudou |

**Duração:**
- **Mínima:** da abertura (`datahoracriacao`) à última consulta em que o alerta estava aberto.
- **Máxima:** da abertura à primeira consulta em que já não estava.
- **Resolução:** 1 h.

**Indicador principal:** alertas no escopo do pipeline (moderado ou acima; risco hidrológico ou movimentos de massa) que fecharam sem nunca entrar no state.
- **Se ficar em zero por algumas semanas:** a consulta de 6 em 6 h é suficiente.
- **Se não ficar em zero:** o pipeline precisa passar a usar este catálogo como fonte de alertas novos. Isso fica para depois da medição.

Só observa: não altera o state nem gasta cota do YouTube.

## Limite

Alertas que abrem e fecham dentro de uma mesma hora continuam invisíveis. A série de capturas mostra a distribuição de duração, e daí se estima o quanto isso pesa.
