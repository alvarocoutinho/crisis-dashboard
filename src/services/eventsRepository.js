/**
 * Events Repository
 * -----------------
 * Camada de acesso a dados. Todos os componentes do dashboard consomem
 * dados apenas por meio destas funções — nunca importando o JSON direto.
 *
 * Implementação atual: leitura estática de src/data/events.json (Vite
 * serializa o JSON no bundle no build). Se um dia trocarmos por HTTP API,
 * basta reimplementar sem tocar em componente algum.
 */

import eventsData from "../data/events.json";

/**
 * Retorna todos os eventos.
 */
export function getAllEvents() {
  return eventsData;
}

/**
 * Retorna um evento pelo id.
 */
export function getEventById(id) {
  return eventsData.find((ev) => ev.id === id);
}

/**
 * Retorna vídeos coletados para um evento.
 */
export function getVideosForEvent(eventId) {
  const ev = getEventById(eventId);
  return ev?.videos ?? [];
}

/**
 * Retorna amostras (top-N por score) de uma categoria em um evento.
 */
export function getSamplesForCategory(eventId, categoryKey) {
  const ev = getEventById(eventId);
  return ev?.all_samples?.[categoryKey] ?? [];
}

/**
 * Retorna a distribuição de predições por categoria de um evento.
 */
export function getDistributionForEvent(eventId) {
  const ev = getEventById(eventId);
  return ev?.distribution ?? [];
}

/**
 * Retorna série temporal diária de volume de comentários.
 */
export function getTimelineForEvent(eventId) {
  const ev = getEventById(eventId);
  return ev?.timeline ?? [];
}

/**
 * Retorna estudos acadêmicos cadastrados manualmente para um evento.
 * Array vazio significa "nenhum estudo cadastrado ainda" (estado explícito,
 * não erro).
 */
export function getAcademicStudiesForEvent(eventId) {
  const ev = getEventById(eventId);
  return ev?.academic_studies ?? [];
}

/**
 * Metadados enxutos para listagem/mapa.
 */
export function getEventSummaries() {
  return eventsData.map((ev) => ({
    id: ev.id,
    municipio: ev.municipio,
    uf: ev.uf,
    tipo: ev.tipo,
    nivel: ev.nivel,
    data_alerta: ev.data_alerta,
    codibge: ev.codibge,
    lat: ev.lat,
    lon: ev.lon,
    regime: ev.regime,
    n_comments: ev.n_comments,
    n_videos: ev.n_videos,
  }));
}

/**
 * Retorna a lista ordenada de UFs distintas que têm evento no arquivo.
 * Útil para popular o filtro por UF sem hardcode.
 */
export function getUFsWithEvents() {
  const ufs = new Set(eventsData.map((ev) => ev.uf));
  return Array.from(ufs).sort();
}

/**
 * Filtra eventos por conjunto de UFs. Se o Set for vazio, retorna vazio
 * (comportamento consistente: "nenhuma UF marcada = nenhum evento").
 */
export function getEventsByUFs(ufSet) {
  if (!ufSet || ufSet.size === 0) return [];
  return eventsData.filter((ev) => ufSet.has(ev.uf));
}

/**
 * Mapeamento UF → macrorregião IBGE.
 * Fonte: divisão regional oficial do IBGE (Norte, Nordeste, Centro-Oeste,
 * Sudeste, Sul). Estático — a divisão não muda com frequência.
 */
export const UF_TO_MACRORREGIAO = {
  AC: "Norte", AP: "Norte", AM: "Norte", PA: "Norte", RO: "Norte", RR: "Norte", TO: "Norte",
  AL: "Nordeste", BA: "Nordeste", CE: "Nordeste", MA: "Nordeste", PB: "Nordeste",
  PE: "Nordeste", PI: "Nordeste", RN: "Nordeste", SE: "Nordeste",
  DF: "Centro-Oeste", GO: "Centro-Oeste", MT: "Centro-Oeste", MS: "Centro-Oeste",
  ES: "Sudeste", MG: "Sudeste", RJ: "Sudeste", SP: "Sudeste",
  PR: "Sul", RS: "Sul", SC: "Sul",
};

/**
 * Ordem canônica das macrorregiões (norte → sul, padrão IBGE).
 */
export const MACRORREGIOES_ORDER = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"];

/**
 * Retorna as macrorregiões que têm ≥1 UF com evento no arquivo,
 * na ordem canônica. Útil para renderizar apenas chips relevantes.
 */
export function getMacrorregioesWithEvents() {
  const regioes = new Set(
    getUFsWithEvents().map((uf) => UF_TO_MACRORREGIAO[uf]).filter(Boolean)
  );
  return MACRORREGIOES_ORDER.filter((r) => regioes.has(r));
}

/**
 * Retorna as UFs presentes no dataset que pertencem a uma dada macrorregião.
 * Base para o comportamento "clique na região = toggle todas as UFs dela".
 */
export function getUFsInMacrorregiao(macrorregiao) {
  return getUFsWithEvents().filter((uf) => UF_TO_MACRORREGIAO[uf] === macrorregiao);
}
