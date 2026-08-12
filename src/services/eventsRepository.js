/**
 * Events Repository
 * -----------------
 * Camada de acesso a dados. Todos os componentes do dashboard consomem
 * dados apenas por meio destas funções — nunca importando o JSON direto.
 *
 * Motivo: se um dia trocarmos a fonte (JSON local → HTTP API → banco),
 * basta reimplementar as funções abaixo sem tocar em componente algum.
 *
 * Implementação atual: leitura estática de src/data/events.json.
 * Vite serializa o JSON no bundle no momento do build (não há fetch em runtime).
 */

import eventsData from "../data/events.json";

/**
 * Retorna todos os eventos.
 * @returns {Array<Event>}
 */
export function getAllEvents() {
  return eventsData;
}

/**
 * Retorna um evento pelo id, ou undefined se não existir.
 * @param {string} id — ex: "pernambuco_pilot_2026"
 * @returns {Event | undefined}
 */
export function getEventById(id) {
  return eventsData.find((ev) => ev.id === id);
}

/**
 * Retorna o array de vídeos coletados para um evento.
 * @param {string} eventId
 * @returns {Array<Video>} — vazio se evento não existir
 */
export function getVideosForEvent(eventId) {
  const ev = getEventById(eventId);
  return ev?.videos ?? [];
}

/**
 * Retorna as amostras (top-N com maior score BERTimbau) de uma categoria
 * em um evento específico.
 * @param {string} eventId
 * @param {string} categoryKey — ex: "responsabilizacao_governanca"
 * @returns {Array<Sample>} — vazio se evento ou categoria não existirem
 */
export function getSamplesForCategory(eventId, categoryKey) {
  const ev = getEventById(eventId);
  return ev?.all_samples?.[categoryKey] ?? [];
}

/**
 * Retorna a distribuição de predições (contagens por categoria) de um evento.
 * @param {string} eventId
 * @returns {Array<{key, label, count, pct}>}
 */
export function getDistributionForEvent(eventId) {
  const ev = getEventById(eventId);
  return ev?.distribution ?? [];
}

/**
 * Retorna a série temporal diária de volume de comentários para um evento.
 * @param {string} eventId
 * @returns {Array<{date, count}>}
 */
export function getTimelineForEvent(eventId) {
  const ev = getEventById(eventId);
  return ev?.timeline ?? [];
}

/**
 * Metadados enxutos para listagem/mapa: id, municipio, uf, tipo, nivel,
 * data_alerta, codibge, lat, lon, regime, n_comments. Sem samples nem videos.
 * Útil para componentes que só precisam de overview (ex: BrazilMap, EventList).
 * @returns {Array<EventSummary>}
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
