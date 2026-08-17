/**
 * Events Repository
 * -----------------
 * Camada de acesso a dados. Todos os componentes do dashboard consomem
 * dados apenas por meio destas funções — nunca importando o JSON direto.
 *
 * Implementação atual: leitura estática de src/data/events.json (Vite
 * serializa o JSON no bundle no build). Se um dia trocarmos por HTTP API,
 * basta reimplementar sem tocar em componente algum.
 *
 * Reforma três flags (v0.2, 17/08/2026):
 * - priority_tier passa a ser APENAS gravidade CEMADEN (muito_alto/alto/moderado).
 *   O valor "acompanhamento" foi removido do vocabulário de tier.
 * - flag (novo) é o drive operacional ODRD: "alerta" | "acompanhamento" | "prioritario".
 * - observation_status separa "active" (aberto no CEMADEN) de "extended"
 *   (fechado no CEMADEN mas ainda em observação porque flag != alerta).
 * - Coexistem: mapa colore por priority_tier (gravidade institucional CEMADEN);
 *   cards e filtros usam flag (estágio operacional ODRD).
 */

import eventsData from "../data/events.json";
import liveData from "../data/live.json";
import stateData from "../data/state.json";

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

// ============================================================
// LIVE — Coleta prospectiva ancorada em alertas CEMADEN
// ============================================================

/**
 * Retorna o objeto live.json completo (metadados + array de alertas).
 * O objeto tem os campos: generated_at, pipeline_version, pilot_mode,
 * dry_run, alerts.
 */
export function getLiveData() {
  return liveData;
}

/**
 * Retorna apenas o array de alertas ativos, no schema Event estendido
 * (com campos prospectivos observation_status, priority_tier, flag, etc.).
 */
export function getLiveAlerts() {
  return liveData?.alerts ?? [];
}

/**
 * Retorna um alerta live pelo id.
 */
export function getLiveAlertById(id) {
  return getLiveAlerts().find((a) => a.id === id);
}

/**
 * Retorna o state.json completo (estado operacional do pipeline).
 */
export function getPipelineState() {
  return stateData;
}

// ------------------------------------------------------------
// PRIORITY TIER — gravidade CEMADEN (muito_alto/alto/moderado)
// Usado para coloração de dots no mapa (metadado institucional).
// NÃO tem semântica operacional em v0.2 — cadência vem de FLAG.
// ------------------------------------------------------------

/**
 * Ordem canônica dos tiers de gravidade CEMADEN (mais crítico → menos).
 * Nota v0.2: "acompanhamento" foi REMOVIDO desta lista — agora é flag.
 */
export const TIER_ORDER = ["muito_alto", "alto", "moderado"];

/**
 * Metadata visual por tier de gravidade CEMADEN.
 * Cores casam com a convenção CEMADEN (vermelho/laranja/amarelo).
 */
export const TIER_META = {
  muito_alto: {
    label: "Muito Alto",
    color: "#dc2626",     // red-600
    bgClass: "bg-red-600",
    textClass: "text-red-700",
    borderClass: "border-red-300",
    lightBgClass: "bg-red-50",
    dotRadius: 8,
  },
  alto: {
    label: "Alto",
    color: "#ea580c",     // orange-600
    bgClass: "bg-orange-600",
    textClass: "text-orange-700",
    borderClass: "border-orange-300",
    lightBgClass: "bg-orange-50",
    dotRadius: 7,
  },
  moderado: {
    label: "Moderado",
    color: "#ca8a04",     // yellow-600
    bgClass: "bg-yellow-600",
    textClass: "text-yellow-700",
    borderClass: "border-yellow-300",
    lightBgClass: "bg-yellow-50",
    dotRadius: 6,
  },
};

/**
 * Fallback defensivo: se um alerta legado tem priority_tier="acompanhamento"
 * (resíduo v0.1), trata como moderado para renderização. Deveria ter sido
 * normalizado no build_live.py, mas defesa em profundidade.
 */
export function getTierMeta(tier) {
  return TIER_META[tier] ?? TIER_META.moderado;
}

// ------------------------------------------------------------
// FLAG — estágio operacional ODRD (alerta/acompanhamento/prioritario)
// Drive de cadência de coleta (24h/12h/6h). Base da organização dos cards.
// ------------------------------------------------------------

/**
 * Ordem canônica das flags (mais engajado → menos).
 * Determina ordem de exibição: prioritário aparece primeiro dentro de cada seção.
 */
export const FLAG_ORDER = ["prioritario", "acompanhamento", "alerta"];

/**
 * Metadata visual por flag. Palette DISTINTA da de priority_tier
 * (violeta/azul/cinza) para não competir com as cores CEMADEN
 * (vermelho/laranja/amarelo) no mesmo card.
 */
export const FLAG_META = {
  prioritario: {
    label: "Prioritário",
    shortLabel: "Prior.",
    color: "#7c3aed",       // violet-600
    bgClass: "bg-violet-600",
    textClass: "text-violet-700",
    borderClass: "border-violet-300",
    lightBgClass: "bg-violet-50",
    cadenceHours: 6,
    description: "≥50 comentários não-FP em ≥2 vídeos distintos",
  },
  acompanhamento: {
    label: "Acompanhamento",
    shortLabel: "Acomp.",
    color: "#0891b2",       // cyan-600
    bgClass: "bg-cyan-600",
    textClass: "text-cyan-700",
    borderClass: "border-cyan-300",
    lightBgClass: "bg-cyan-50",
    cadenceHours: 12,
    description: "Ao menos 1 vídeo aderente identificado",
  },
  alerta: {
    label: "Alerta",
    shortLabel: "Alerta",
    color: "#71717a",       // zinc-500
    bgClass: "bg-zinc-500",
    textClass: "text-zinc-700",
    borderClass: "border-zinc-300",
    lightBgClass: "bg-zinc-50",
    cadenceHours: 24,
    description: "Estado inicial — sem sinal digital ainda",
  },
};

/**
 * Fallback defensivo para alertas sem flag (legado ou dados corrompidos).
 */
export function getFlagMeta(flag) {
  return FLAG_META[flag] ?? FLAG_META.alerta;
}

/**
 * Retorna as flags presentes nos alertas live atuais, na ordem canônica.
 */
export function getFlagsInLive() {
  const flags = new Set(getLiveAlerts().map((a) => a.flag).filter(Boolean));
  return FLAG_ORDER.filter((f) => flags.has(f));
}

/**
 * Filtra alertas live por conjunto de flags.
 */
export function getLiveAlertsByFlags(flagSet) {
  if (!flagSet || flagSet.size === 0) return [];
  return getLiveAlerts().filter((a) => flagSet.has(a.flag));
}

/**
 * Comparador para ordenar alertas por flag (prioritario > acompanhamento > alerta).
 * Uso: alerts.sort(sortAlertsByFlag)
 */
export function sortAlertsByFlag(a, b) {
  const orderA = FLAG_ORDER.indexOf(a.flag);
  const orderB = FLAG_ORDER.indexOf(b.flag);
  return orderA - orderB;
}

// ------------------------------------------------------------
// Partição das seções — usa observation_status (v0.2)
// ------------------------------------------------------------

/**
 * Retorna alertas em observação ativa (CEMADEN ainda aberto).
 * Substitui a heurística v0.1 baseada em priority_tier.
 */
export function getPriorityCollectionAlerts() {
  return getLiveAlerts().filter((a) => a.observation_status === "active");
}

/**
 * Retorna alertas em janela estendida (CEMADEN fechado, mas flag != alerta
 * mantém em observação — em v0.2, alertas em flag=alerta que fecham somem
 * do dashboard e viram contador no log agregado).
 */
export function getExtendedWindowAlerts() {
  return getLiveAlerts().filter((a) => a.observation_status === "extended");
}
