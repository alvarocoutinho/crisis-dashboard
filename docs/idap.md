# IDAP — alertas da Defesa Civil à população (CAP 1.2)

## O que é

A IDAP (Interface de Divulgação de Alertas Públicos, MIDR/SEDEC) é por onde as Defesas Civis estaduais e municipais e a Nacional cadastram os alertas enviados à população por SMS, *cell broadcast*, Google e outros canais. O feed público entrega cada alerta no padrão **CAP 1.2**:
- identificador oficial;
- emissor e horários;
- evento, severidade, urgência e certeza;
- texto enviado;
- área, como polígonos e, às vezes, geocódigos IBGE.

- **Feed:** `https://idapfile.mdr.gov.br/idap/api/rss/cap`, em Atom com CAP embutido. É o endereço registrado na OMM. O guia do Fórum SBTVD cita também `idapfile.mi.gov.br`.
- **Norma:** a Portaria MIDR nº 2.458/2026, art. 10, determina que os alertas sejam armazenados em CAP e permaneçam públicos para consulta.

## Para o projeto

O CEMADEN alerta a Defesa Civil. A IDAP registra **se e quando a Defesa Civil alertou a população**, e para qual área. É o elo intermediário da cadeia *alerta → ação* que o ODRD estuda. O cruzamento com os alertas do CEMADEN está planejado (ver Próximos passos).

Ressalva metodológica: um registro CAP comprova que o alerta foi **cadastrado e publicado**. Não comprova que um aparelho o recebeu.

## Primeira captura (14/10/2026, 16h29 de Brasília)

- **Alertas:** 73, com identificadores de 193712 a 193784 **sem lacunas**. Todos com `msgType=Alert`, `status=Actual` e `sender=CENAD-SEDEC`.
- **Emissores:** Defesas Civis estaduais de SP, PR, MG, AM, SC, GO, MT, MS e RJ; as municipais de Blumenau, Belo Horizonte, Barra Mansa e Barueri; e a Nacional. A cobertura é nacional.
- **Área:**
  - polígono em 72 de 73 alertas;
  - Rosana (193713) tem só "mapa", sem polígono nem geocódigo;
  - geocódigo IBGE em 18;
  - um polígono veio sem o ponto de fechamento, e o coletor fecha o anel;
  - de 1 a 85 polígonos por alerta, até 265 mil vértices; os maiores são de áreas estaduais.
- **Canal:** todos com `CHANNEL-LIST=Google`. Ainda não se sabe se o feed traz só os alertas enviados ao Google ou todos.

## Janela do feed: ~12 h (inferência)

O alerta 193711 (emitido às 04h12) aparecia numa consulta às 16h05 e já não estava na captura das 16h25. Nessa captura, o mais antigo era o 193712, das 05h48. Isso é compatível com uma janela de cerca de 12 h por horário de emissão. O guia do Fórum SBTVD fala em 24 h.

- **Estado da evidência:** duas capturas. O coletor registra a janela de cada captura (`horas_cobertas`, `min_id`, `max_id` em `data/idap/capturas.csv`), e a regra real sairá dessa série.
- **Consequência:** a coleta é de hora em hora. Um alerta que fique mais de ~12 h sem ser coletado se perde. As lacunas na numeração (`data/idap/lacunas.csv`) mostram se isso aconteceu.

## Coletor (`idap.yml`, de hora em hora)

| Camada | Onde | Conteúdo |
|---|---|---|
| Arquivo bruto | Release `idap-arquivo`, um `idap_cap_AAAA-MM-DD.jsonl.gz` por dia de emissão | XML CAP original, geometria em precisão total |
| Catálogo | `data/idap/alertas.csv` | uma linha por alerta: atributos, texto, UFs, IBGE, área, caixa envolvente; sem geometria |
| Capturas | `data/idap/capturas.csv` | cada consulta: status, tamanho, hash, janela, novos, lacunas |
| Painel | `public/data/idap/dias/AAAA-MM-DD.geojson` e `indice.json` | geometria simplificada para exibição |

**Geometria do painel:**
1. As partes de cada alerta são unidas e simplificadas, com tolerância de 300 m ou 1/400 do lado equivalente da área, o que for maior.
2. As coordenadas são arredondadas para cerca de 11 m.
3. Para análise espacial, use o arquivo bruto.

**Ordem de segurança:** o arquivo bruto é publicado antes do commit do catálogo. Se a publicação falhar, o job falha e a hora seguinte recoleta.

**UFs:** inferidas, nesta ordem:
1. pelos geocódigos IBGE;
2. pelos sufixos "/UF" da descrição da área;
3. pelo nome do emissor.

## Fontes complementares (a avaliar)

- **Dados abertos do MIDR:** há um conjunto "IDAP – Interface de Divulgação de Alertas Públicos", com arquivo anual (ex.: `Alertas Idap 2023.csv`), em `dadosabertos.mdr.gov.br`. Ainda não verificado daqui, porque o portal recusa acesso automatizado. É a rota provável para o histórico anterior a 14/10/2026.
- **SEDEC:** o pedido formal do acervo CAP completo (idap.cenad@mdr.gov.br ou Fala.BR) tem precedente: o TCU usou o histórico da IDAP no processo TC 006.390/2024-2.

## Próximos passos

1. **Mapa no painel:** em construção.
2. **Cruzamento CEMADEN × IDAP:** a Defesa Civil alertou a população do município do alerta do CEMADEN? Quando, em relação à abertura? Com que severidade? O cruzamento usa geocódigo IBGE quando houver e, nos outros casos, interseção do polígono com a malha municipal do IBGE.
3. **Histórico:** baixar os arquivos anuais dos dados abertos.
