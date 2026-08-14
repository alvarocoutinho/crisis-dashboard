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
