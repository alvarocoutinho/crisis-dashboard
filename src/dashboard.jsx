import React, { useState, useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, Legend
} from "recharts";
import {
  AlertTriangle, MapPin, MessageSquare, Video, Users,
  Info, ChevronRight, VolumeX, FileWarning, Beaker,
  Layers, Activity, PlayCircle, ExternalLink,
  BarChart3, Film, X, Filter, ArrowLeft
} from "lucide-react";
import * as d3 from "d3";
import {
  getAllEvents,
  getEventById,
  getEventSummaries,
  getUFsWithEvents,
  getEventsByUFs,
} from "./services/eventsRepository";

// Janelas fixas de atualização (frozen framing rule)
const WINDOWS = [
  { label: "+2h", h: 2 }, { label: "+6h", h: 6 },
  { label: "+12h", h: 12 }, { label: "+24h", h: 24 },
  { label: "+48h", h: 48 }, { label: "+72h", h: 72 },
];

// =========================================================================
// MAPA REAL DO BRASIL (d3-geo + GeoJSON dos estados)
// =========================================================================

function BrazilMap({ selectedId, onSelect, events }) {
  const [geo, setGeo] = useState(null);
  const [status, setStatus] = useState("loading");

  useEffect(() => {
    const url = "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/brazil-states.geojson";
    fetch(url)
      .then(r => { if (!r.ok) throw new Error("fetch failed"); return r.json(); })
      .then(data => { setGeo(data); setStatus("ok"); })
      .catch(() => setStatus("error"));
  }, []);

  const width = 380, height = 400;
  const ufsComEventos = useMemo(() => new Set(events.map(e => e.uf)), [events]);

  const { pathGen, projection } = useMemo(() => {
    if (!geo) return { pathGen: null, projection: null };
    const proj = d3.geoMercator().fitSize([width, height], geo);
    return { pathGen: d3.geoPath().projection(proj), projection: proj };
  }, [geo]);

  return (
    <div className="bg-white rounded-lg border border-stone-300 p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-stone-800 flex items-center gap-2">
          <MapPin size={16} /> Eventos monitorados
        </h2>
        <span className="text-xs text-stone-500">{events.length} {events.length === 1 ? "evento" : "eventos"} · {ufsComEventos.size} {ufsComEventos.size === 1 ? "UF" : "UFs"}</span>
      </div>
      <div className="relative bg-stone-50 rounded border border-stone-200 overflow-hidden" style={{ height }}>
        {status === "loading" && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-stone-500">
            Carregando mapa dos estados brasileiros...
          </div>
        )}
        {status === "error" && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-stone-500 p-4 text-center">
            Não foi possível carregar o GeoJSON online.<br />
            <span className="text-stone-400">Verifique conexão ou execute o build local.</span>
          </div>
        )}
        {status === "ok" && geo && pathGen && (
          <svg width={width} height={height} className="w-full h-full">
            <g>
              {geo.features.map((f, i) => {
                const uf = f.properties.sigla || f.properties.SIGLA_UF || f.properties.name;
                const hasEvent = ufsComEventos.has(uf);
                return (
                  <path
                    key={i}
                    d={pathGen(f)}
                    fill={hasEvent ? "#78716c" : "#e7e5e4"}
                    stroke="#ffffff"
                    strokeWidth={0.6}
                  />
                );
              })}
            </g>
            <g>
              {events.map(ev => {
                const [x, y] = projection([ev.lon, ev.lat]);
                const isSelected = ev.id === selectedId;
                return (
                  <g key={ev.id} onClick={() => onSelect(ev.id)} style={{ cursor: "pointer" }}>
                    <circle
                      cx={x} cy={y}
                      r={isSelected ? 8 : 5}
                      fill="#dc2626"
                      stroke="white"
                      strokeWidth={1.5}
                      opacity={isSelected ? 1 : 0.85}
                    />
                    {isSelected && (
                      <circle cx={x} cy={y} r={12} fill="none" stroke="#dc2626" strokeWidth={1.5} opacity={0.6}>
                        <animate attributeName="r" from="8" to="16" dur="1.8s" repeatCount="indefinite" />
                        <animate attributeName="opacity" from="0.6" to="0" dur="1.8s" repeatCount="indefinite" />
                      </circle>
                    )}
                  </g>
                );
              })}
            </g>
          </svg>
        )}
      </div>
      <div className="mt-4 space-y-1.5">
        {events.length === 0 && (
          <div className="px-3 py-4 text-center text-xs text-stone-500 italic border border-dashed border-stone-300 rounded">
            Nenhum evento com os filtros atuais.
          </div>
        )}
        {events.map(ev => {
          const isSelected = ev.id === selectedId;
          return (
            <button
              key={ev.id}
              onClick={() => onSelect(ev.id)}
              className={`w-full text-left px-3 py-2 rounded border transition-colors flex items-center justify-between gap-2 ${
                isSelected
                  ? "bg-stone-900 text-white border-stone-900"
                  : "bg-white border-stone-200 hover:border-stone-400 text-stone-800"
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium truncate">
                  {ev.municipio} — {ev.uf}
                </div>
                <div className={`text-xs truncate ${isSelected ? "text-stone-300" : "text-stone-500"}`}>
                  {ev.tipo} · {ev.data_alerta} · {ev.n_comments.toLocaleString("pt-BR")} comentários
                </div>
              </div>
              <ChevronRight size={14} className="flex-shrink-0" />
            </button>
          );
        })}
      </div>
      <div className="mt-4 pt-3 border-t border-stone-200 text-xs text-stone-500">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2 h-2 rounded-full bg-red-500" /> Município do alerta CEMADEN
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-sm bg-stone-500" /> UFs com eventos no corpus
        </div>
      </div>
    </div>
  );
}

// =========================================================================
// COMPONENTES DE PAINEL
// =========================================================================

function KPI({ icon: Icon, label, value, sub }) {
  return (
    <div className="bg-white rounded border border-stone-200 p-3">
      <div className="flex items-center gap-1.5 text-xs text-stone-500 mb-1">
        <Icon size={12} /> {label}
      </div>
      <div className="text-2xl font-semibold text-stone-900 leading-none">{value}</div>
      {sub && <div className="text-xs text-stone-500 mt-1">{sub}</div>}
    </div>
  );
}

function EventPanel({ event }) {
  const [tab, setTab] = useState("analise");
  const alertColor = event.nivel === "Muito Alto" ? "bg-red-600" :
                     event.nivel === "Alto" ? "bg-orange-500" : "bg-yellow-400";

  return (
    <div className="space-y-4">
      {/* Cabeçalho */}
      <div className="bg-white rounded-lg border border-stone-300 p-5">
        <div className="flex items-start justify-between gap-4 mb-3">
          <div>
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium text-white ${alertColor}`}>
                <AlertTriangle size={11} /> {event.nivel}
              </span>
              <span className="text-xs text-stone-500">codibge {event.codibge}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-stone-100 border border-stone-200 text-stone-700">
                {event.uf}
              </span>
              {event.regime === "out_of_fold" ? (
                <span className="text-xs px-2 py-0.5 rounded bg-emerald-100 border border-emerald-300 text-emerald-900 inline-flex items-center gap-1" title="Evento não visto no treino do checkpoint LOEO_pernambuco — predição out-of-fold">
                  <Beaker size={10} /> Out-of-fold (LOEO)
                </span>
              ) : (
                <span className="text-xs px-2 py-0.5 rounded bg-amber-100 border border-amber-300 text-amber-900 inline-flex items-center gap-1" title="Evento visto no treino do checkpoint LOEO_pernambuco — predições in-sample, evidência exploratória">
                  <Beaker size={10} /> In-sample exploratório
                </span>
              )}
            </div>
            <h2 className="text-xl font-semibold text-stone-900">{event.municipio}</h2>
            <p className="text-sm text-stone-600">{event.tipo} · alerta CEMADEN em {event.data_alerta}</p>
          </div>
          <div className="text-right text-xs text-stone-500">
            <div>Coleta: {event.date_range[0]} → {event.date_range[1]}</div>
          </div>
        </div>

        <div className="mt-4">
          <div className="text-xs font-medium text-stone-600 mb-2">
            Janelas fixas de atualização a partir do alerta
          </div>
          <div className="flex gap-1.5 flex-wrap">
            {WINDOWS.map(w => (
              <span key={w.label} className="px-2.5 py-1 text-xs bg-stone-100 border border-stone-200 rounded text-stone-700">
                {w.label}
              </span>
            ))}
          </div>
          <p className="text-xs text-stone-500 mt-2 italic">
            Painel exibe série diária. Em produção, agregações ocorrem nas janelas fixas acima
            (polling a cada 4h — não tempo real).
          </p>
        </div>
      </div>

      {/* Abas */}
      <div className="flex gap-1 border-b border-stone-300">
        {[
          { id: "analise", label: "Análise", icon: BarChart3 },
          { id: "videos", label: `Vídeos coletados (${event.n_videos})`, icon: Film },
        ].map(t => {
          const Icon = t.icon;
          const isActive = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium flex items-center gap-2 border-b-2 transition-colors -mb-px ${
                isActive
                  ? "border-stone-900 text-stone-900"
                  : "border-transparent text-stone-500 hover:text-stone-800"
              }`}
            >
              <Icon size={14} /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "videos" ? <VideoTab event={event} /> : <AnalysisTab event={event} />}
    </div>
  );
}

// Conteúdo original refatorado como componente da aba Análise
function AnalysisTab({ event }) {
  const [openCategory, setOpenCategory] = useState(null);

  return (
    <div className="space-y-4">
      {/* KPIs */}
      <div className="grid grid-cols-4 gap-3">
        <KPI icon={MessageSquare} label="Comentários coletados" value={event.n_comments.toLocaleString("pt-BR")} />
        <KPI icon={Video} label="Vídeos únicos" value={event.n_videos} />
        <KPI icon={FileWarning} label="Sem predição positiva" value={`${event.unlabeled_pct}%`} sub={`${event.unlabeled.toLocaleString("pt-BR")} comentários`} />
        <KPI icon={Users} label="Anotação humana" value="pendente" sub="Experimento 5" />
      </div>

      {/* Timeline */}
      <div className="bg-white rounded-lg border border-stone-300 p-5">
        <h3 className="text-sm font-semibold text-stone-800 mb-1 flex items-center gap-2">
          <Activity size={14} /> Curva temporal de reação
        </h3>
        <p className="text-xs text-stone-500 mb-4">
          Volume diário de comentários. Notar o pico próximo ao alerta e a cauda longa —
          objeto central de análise do projeto (cauda por reativação cruzada com novos eventos).
        </p>
        <div style={{ height: 200 }}>
          <ResponsiveContainer>
            <LineChart data={event.timeline} margin={{ left: 0, right: 10, top: 5, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#57534e" }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 11, fill: "#57534e" }} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
              <Line type="monotone" dataKey="count" stroke="#0c0a09" strokeWidth={2} dot={{ r: 2 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Distribuição */}
      <div className="bg-white rounded-lg border border-stone-300 p-5">
        <h3 className="text-sm font-semibold text-stone-800 mb-1 flex items-center gap-2">
          <Layers size={14} /> Distribuição de predições — BERTimbau v0.1
        </h3>
        <p className="text-xs text-stone-500 mb-4">
          Predições multilabel do classificador. Cada comentário pode receber 0, 1 ou mais
          categorias.{" "}
          {event.regime === "out_of_fold" ? (
            <span className="text-emerald-700"><strong>Regime out-of-fold:</strong> Pernambuco 2026 é o hold-out do LOEO — evento não visto no treino; as predições são out-of-fold e permitem avaliar transferibilidade entre eventos.</span>
          ) : (
            <span className="text-amber-800"><strong>Regime in-sample exploratório:</strong> este evento estava no conjunto de treino do checkpoint LOEO_pernambuco. Predições demonstram viabilidade metodológica, não constituem medição validada.</span>
          )}{" "}
          <em>Clique em qualquer barra para ver comentários com maior score do modelo nessa categoria.</em>
        </p>
        <div style={{ height: 260 }}>
          <ResponsiveContainer>
            <BarChart data={event.distribution} layout="vertical" margin={{ left: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
              <XAxis type="number" tick={{ fontSize: 11, fill: "#57534e" }} />
              <YAxis type="category" dataKey="label" tick={{ fontSize: 10, fill: "#57534e" }} width={200} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 4 }} />
              <Bar
                dataKey="count"
                fill="#44403c"
                cursor="pointer"
                onClick={(data) => setOpenCategory(data.key)}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Amostras */}
      <div className="bg-white rounded-lg border border-stone-300 p-5">
        <h3 className="text-sm font-semibold text-stone-800 mb-1">
          Amostras auditáveis por categoria
        </h3>
        <p className="text-xs text-stone-500 mb-4">
          Prévia com os 2 comentários de <strong>maior score</strong> por categoria BERTimbau
          (0–1, mais próximo de 1 = mais confiança do modelo).{" "}
          <em>Clique em qualquer categoria para expandir e ver os 20 exemplos de maior score</em>{" "}
          — material para auditoria humana (Experimento 5).
        </p>
        <div className="space-y-4">
          {event.distribution.map(cat => {
            const samples = event.all_samples[cat.key] || [];
            const preview = samples.slice(0, 2);
            return (
              <div key={cat.key}>
                <button
                  onClick={() => setOpenCategory(cat.key)}
                  className="w-full text-left group flex items-center justify-between gap-3 mb-1.5 hover:bg-stone-50 -mx-2 px-2 py-1 rounded transition-colors"
                >
                  <div className="text-xs font-medium text-stone-700 flex items-center gap-2">
                    <span className="group-hover:underline">{cat.label}</span>
                    <span className="text-stone-400">·</span>
                    <span className="text-stone-500">{cat.count.toLocaleString("pt-BR")} comentários</span>
                  </div>
                  <span className="text-xs text-stone-500 group-hover:text-stone-900 flex items-center gap-1 flex-shrink-0">
                    ver {samples.length} exemplos <ChevronRight size={12} />
                  </span>
                </button>
                <div className="space-y-1.5">
                  {preview.map((s, i) => (
                    <div key={i} className="px-3 py-2 rounded border bg-stone-50 border-stone-200 text-sm">
                      <div className="text-stone-800">"{s.text}"</div>
                      <div className="text-xs text-stone-500 mt-1 flex items-center gap-3 flex-wrap">
                        {s.score !== undefined && (
                          <span className="font-mono">score {s.score.toFixed(3)}</span>
                        )}
                        <span>👍 {s.likes.toLocaleString("pt-BR")}</span>
                        {s.date && <span>· {s.date}</span>}
                      </div>
                    </div>
                  ))}
                  {samples.length === 0 && (
                    <div className="px-3 py-2 rounded border border-dashed border-stone-300 text-xs text-stone-500 italic">
                      Nenhum comentário com predição positiva nesta categoria neste evento.
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Modal de amostras expandidas */}
      {openCategory && (
        <SamplesModal
          event={event}
          categoryKey={openCategory}
          onClose={() => setOpenCategory(null)}
        />
      )}

      {/* Silêncio digital como categoria */}
      <div className="bg-white rounded-lg border-2 border-dashed border-stone-400 p-5">
        <div className="flex items-start gap-3">
          <VolumeX className="text-stone-700 flex-shrink-0" size={20} />
          <div>
            <h3 className="text-sm font-semibold text-stone-800 mb-1">
              Déficit de escuta — categoria dedicada
            </h3>
            <p className="text-xs text-stone-600 leading-relaxed">
              Em produção, este painel exibirá municípios de <strong>alta vulnerabilidade</strong> (Urban
              Adaptation Index) e <strong>alta ARI</strong> que receberam alerta CEMADEN e retornaram
              <strong> zero coleta</strong> nas janelas fixas. Este silêncio digital <em>não é falha do
              pipeline</em> — é o objeto central do estudo. Vulnerabilidade estratifica o déficit de escuta:
              onde falta capacidade de "acesso à encenação" (Wisner et al., 2004; Beck, 2009), o alerta
              chega, o dano acontece, e a esfera pública digital permanece muda.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// =========================================================================
// MODAL DE AMOSTRAS EXPANDIDAS
// =========================================================================

function SamplesModal({ event, categoryKey, onClose }) {
  const cat = event.distribution.find(c => c.key === categoryKey);
  const samples = event.all_samples[categoryKey] || [];

  // Fechar com ESC
  useEffect(() => {
    const handler = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  if (!cat) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-lg shadow-2xl max-w-3xl w-full max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header do modal */}
        <div className="flex items-start justify-between gap-4 p-5 border-b border-stone-200">
          <div>
            <div className="text-xs text-stone-500 mb-1">
              {event.municipio} — {event.uf} · {event.data_alerta}
            </div>
            <h2 className="text-lg font-semibold text-stone-900">{cat.label}</h2>
            <div className="text-xs text-stone-600 mt-1">
              {cat.count.toLocaleString("pt-BR")} comentários com predição positiva nesta categoria ({cat.pct}% do corpus)
              · exibindo os {samples.length} maiores scores do modelo
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-stone-400 hover:text-stone-800 transition-colors flex-shrink-0 p-1"
            aria-label="Fechar"
          >
            <X size={20} />
          </button>
        </div>

        {/* Aviso ético */}
        <div className="bg-amber-50 border-b border-amber-200 px-5 py-2.5 text-xs text-amber-900 flex items-start gap-2">
          <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
          <span>
            Comentários exibidos em forma verbatim para auditoria. <strong>Identificadores de
            autor foram suprimidos</strong> — não é possível vincular estas manifestações a
            perfis. Predições BERTimbau v0.1 são <em>hipóteses de mensuração</em>, sujeitas a
            falsos positivos até validação humana (Experimento 5).
          </span>
        </div>

        {/* Lista de amostras */}
        <div className="overflow-y-auto flex-1 p-5">
          {samples.length === 0 ? (
            <div className="text-center text-sm text-stone-500 py-8 italic">
              Nenhum comentário deste evento recebeu predição positiva nesta categoria.
            </div>
          ) : (
            <div className="space-y-2">
              {samples.map((s, i) => (
                <div key={i} className="px-3 py-2.5 rounded border bg-stone-50 border-stone-200">
                  <div className="text-sm text-stone-800 leading-relaxed">"{s.text}"</div>
                  <div className="text-xs text-stone-500 mt-2 flex items-center gap-3 flex-wrap">
                    {s.score !== undefined && (
                      <span className="font-mono px-1.5 py-0.5 bg-stone-200 rounded text-stone-700">
                        score {s.score.toFixed(3)}
                      </span>
                    )}
                    <span>👍 {s.likes.toLocaleString("pt-BR")}</span>
                    {s.date && <span>· {s.date}</span>}
                    {s.video_id && (
                      <a
                        href={`https://www.youtube.com/watch?v=${s.video_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-stone-600 hover:text-stone-900 hover:underline flex items-center gap-1"
                      >
                        <ExternalLink size={10} /> vídeo de origem
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-stone-200 text-xs text-stone-500 flex items-center justify-between">
          <span>Pressione <kbd className="px-1.5 py-0.5 bg-stone-100 border border-stone-300 rounded font-mono text-[10px]">ESC</kbd> para fechar</span>
          <span>ODRD · PoC v0.1</span>
        </div>
      </div>
    </div>
  );
}

// =========================================================================
// ABA DE VÍDEOS COLETADOS
// =========================================================================

function VideoTab({ event }) {
  // Dados por vídeo virão do CSV agregado (pré-computados). Enquanto o
  // arquivo não é integrado, exibimos placeholder honesto.
  const videos = event.videos || null;

  if (!videos || videos.length === 0) {
    return (
      <div className="bg-white rounded-lg border-2 border-dashed border-stone-400 p-8">
        <div className="max-w-2xl mx-auto text-center">
          <Film className="mx-auto text-stone-400 mb-3" size={36} />
          <h3 className="text-sm font-semibold text-stone-800 mb-2">
            Aba de vídeos — aguardando integração dos agregados por vídeo
          </h3>
          <p className="text-xs text-stone-600 leading-relaxed mb-4">
            O corpus deste evento contém <strong>{event.n_videos} vídeos únicos do YouTube</strong>{" "}
            coletados via YouTube Data API v3 (canal oficial autorizado, nenhum web-scraping).
            Cada vídeo será exibido aqui com <em>thumbnail</em>, contagem de comentários no
            corpus, engajamento total (curtidas) e as três categorias preditas pelo BERTimbau mais
            frequentes. Os agregados por <code className="bg-stone-100 px-1 rounded">video_id</code>{" "}
            serão gerados a partir do CSV consolidado do pipeline v2.4 e embutidos nesta camada
            de visualização — atualização manual, por design (dados vêm do pipeline, não de um
            backend live).
          </p>
          <div className="text-xs text-stone-500 border-t border-stone-200 pt-3 mt-3">
            <strong>Nota técnica.</strong> O CSV fonte contém <code className="bg-stone-100 px-1 rounded">video_id</code>{" "}
            e IDs de comentário mas não títulos, canais ou <em>views</em> — o link para o YouTube
            será construído como <code className="bg-stone-100 px-1 rounded">youtube.com/watch?v={"{"}video_id{"}"}</code>{" "}
            e a <em>thumbnail</em> como <code className="bg-stone-100 px-1 rounded">img.youtube.com/vi/{"{"}video_id{"}"}/mqdefault.jpg</code>.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-lg border border-stone-300 p-5">
        <h3 className="text-sm font-semibold text-stone-800 mb-1 flex items-center gap-2">
          <Video size={16} /> Vídeos coletados neste evento
        </h3>
        <p className="text-xs text-stone-500 mb-4">
          {event.n_videos} vídeos únicos do YouTube compõem o corpus deste evento. Cada vídeo
          é apresentado com contagem de comentários coletados, engajamento total no corpus
          (soma de curtidas) e as três categorias preditas pelo modelo mais frequentes.
          Ordenação por número de comentários (proxy de mobilização discursiva no corpus).
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {videos.map(v => (
            <VideoCard key={v.video_id} v={v} />
          ))}
        </div>
      </div>
    </div>
  );
}

function VideoCard({ v }) {
  const thumbUrl = `https://img.youtube.com/vi/${v.video_id}/mqdefault.jpg`;
  const ytUrl = `https://www.youtube.com/watch?v=${v.video_id}`;

  return (
    <a
      href={ytUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="group block bg-stone-50 rounded border border-stone-200 hover:border-stone-500 hover:shadow-sm transition-all overflow-hidden"
    >
      <div className="relative bg-stone-200" style={{ paddingBottom: "56.25%" }}>
        <img
          src={thumbUrl}
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
          onError={(e) => { e.currentTarget.style.display = "none"; }}
          loading="lazy"
        />
        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 bg-black/40 transition-opacity">
          <PlayCircle size={40} className="text-white" />
        </div>
        <div className="absolute top-2 right-2 bg-black/70 text-white text-xs px-1.5 py-0.5 rounded flex items-center gap-1">
          <ExternalLink size={10} />
        </div>
      </div>
      <div className="p-3">
        <div className="flex items-center justify-between text-xs text-stone-600 mb-1.5">
          <span className="flex items-center gap-1"><MessageSquare size={11} /> {v.n_comments.toLocaleString("pt-BR")}</span>
          <span>👍 {v.total_likes.toLocaleString("pt-BR")}</span>
          <span className="text-stone-500">{v.first_comment}</span>
        </div>
        <div className="text-xs text-stone-500 mb-2 font-mono truncate">{v.video_id}</div>
        <div className="flex flex-wrap gap-1">
          {v.top_categories.map((c, i) => (
            <span key={i} className="text-xs px-1.5 py-0.5 rounded bg-stone-200 text-stone-700">
              {c.label} · {c.count}
            </span>
          ))}
        </div>
      </div>
    </a>
  );
}

// =========================================================================
// COMPARAÇÃO TRANSVERSAL
// =========================================================================

function ComparisonSection({ events }) {
  // Se filtro deixou < 2 eventos, não faz sentido comparar
  if (events.length < 2) {
    return (
      <div className="bg-white rounded-lg border border-stone-300 p-5 mt-4">
        <h3 className="text-sm font-semibold text-stone-800 mb-1">
          Comparação transversal entre eventos
        </h3>
        <p className="text-xs text-stone-500 italic">
          Selecione ao menos 2 UFs no filtro para ver a comparação transversal.
        </p>
      </div>
    );
  }

  // Reshape para gráfico agrupado — categorias vêm do primeiro evento (schema é o mesmo)
  const cats = events[0].distribution.map(d => ({ key: d.key, label: d.label }));
  const chartData = cats.map(cat => {
    const row = { category: cat.label.split(" / ")[0] };
    events.forEach(ev => {
      const found = ev.distribution.find(d => d.key === cat.key);
      row[ev.municipio.split(" ")[0]] = found ? found.pct : 0;
    });
    return row;
  });

  const colors = ["#78350f", "#7c2d12", "#065f46", "#1e3a8a", "#4c1d95", "#831843"];

  // Se todos os 6 eventos estão selecionados, exibe o box do achado; se não, oculta
  const showFinding = events.length === 6;

  return (
    <div className="bg-white rounded-lg border border-stone-300 p-5 mt-4">
      <h3 className="text-sm font-semibold text-stone-800 mb-1">
        Comparação transversal entre eventos
      </h3>
      <p className="text-xs text-stone-500 mb-3">
        Percentual de comentários com predição positiva BERTimbau em cada categoria, por evento.
        Comparação sujeita à assimetria de regimes: <strong>Pernambuco 2026 é out-of-fold</strong>{" "}
        (único evento avaliado em regime out-of-fold), os demais eventos são in-sample exploratórios.
      </p>
      {showFinding && (
        <div className="bg-emerald-50 border border-emerald-200 rounded p-3 text-xs text-emerald-900 mb-4 leading-relaxed">
          <strong>Achado corroborado em predição out-of-fold:</strong> Pernambuco 2026
          apresenta perfil discursivo estruturalmente distinto — responsabilização/governança em{" "}
          <strong>35,3%</strong> (o mais alto entre os 6 eventos, vs. 11,3–20,6% nos demais) e
          solidariedade em apenas <strong>21,8%</strong> (vs. 41,9–59,6%). Este padrão foi
          detectado inicialmente no dashboard v3 sobre <em>weak labels</em> e é agora corroborado
          pelas predições do classificador em regime out-of-fold. Duas hipóteses
          concorrentes seguem em aberto: (a) janela temporal curta (17 dias) capturou apenas
          fase político-crítica; (b) diferença qualitativa de repertório discursivo mobilizado.
          Distinguir as duas exige coleta prospectiva contínua.
        </div>
      )}
      <div style={{ height: 340 }}>
        <ResponsiveContainer>
          <BarChart data={chartData} margin={{ left: 0, right: 10, top: 10, bottom: 60 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
            <XAxis dataKey="category" tick={{ fontSize: 10, fill: "#57534e" }} angle={-25} textAnchor="end" height={80} />
            <YAxis tick={{ fontSize: 11, fill: "#57534e" }} label={{ value: "% do corpus", angle: -90, position: "insideLeft", style: { fontSize: 11, fill: "#57534e" } }} />
            <Tooltip contentStyle={{ fontSize: 11, borderRadius: 4 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {events.map((ev, i) => (
              <Bar key={ev.id} dataKey={ev.municipio.split(" ")[0]} fill={colors[i % colors.length]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// =========================================================================
// HEADER / FOOTER
// =========================================================================

function Header() {
  return (
    <header className="border-b border-stone-300 bg-white">
      <div className="max-w-7xl mx-auto px-6 py-5 flex items-start justify-between gap-6">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 rounded-md bg-stone-800 text-white flex items-center justify-center text-xs font-semibold">ODRD</div>
          <div>
            <h1 className="text-xl font-semibold text-stone-900 leading-tight group-hover:underline">
              Observatório Digital de Riscos e Desastres
            </h1>
            <p className="text-xs text-stone-600">
              Escuta digital territorializada · reação pública observável a alertas hidrometeorológicos
              · <em>iniciativa em desenvolvimento</em>
            </p>
          </div>
        </Link>
        <div className="flex flex-col items-end gap-1 text-xs">
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-100 text-amber-900 border border-amber-300">
            <Beaker size={12} /> Prova de conceito · v0.1 · TRL 3–4
          </span>
          <span className="text-stone-500 text-right">
            NEPAM/Unicamp · CEPID CLIMARES · parceria CEMADEN
          </span>
        </div>
      </div>
      <div className="bg-stone-50 border-t border-stone-200">
        <div className="max-w-7xl mx-auto px-6 py-2.5 text-xs text-stone-600 flex items-start gap-2">
          <Info size={14} className="mt-0.5 flex-shrink-0" />
          <span>
            Sistema <strong>complementar</strong> à infraestrutura de alertas do CEMADEN (que instrumenta perigo e emissão do alerta).
            Este painel instrumenta a camada de <strong>reação pública digital observável</strong> após o alerta —
            não mede percepção de risco, não emite veredictos automáticos, não opera em tempo real.
          </span>
        </div>
      </div>
      <div className="bg-amber-50 border-t border-amber-200">
        <div className="max-w-7xl mx-auto px-6 py-2.5 text-xs text-amber-900 flex items-start gap-2">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <span>
            <strong>Regimes de predição.</strong> As distribuições vêm do classificador
            BERTimbau v0.1 (fine-tuned neuralmind/bert-base-portuguese-cased) treinado por
            protocolo <em>Leave-One-Event-Out</em>. Pernambuco 2026 é <strong>out-of-fold</strong>{" "}
            — evento não visto no treino, usado para avaliar transferibilidade entre eventos. Os outros 5 eventos
            são <strong>in-sample exploratórios</strong> — evidência de viabilidade metodológica,
            não medição validada. Anotação humana pendente (Experimento 5).
          </span>
        </div>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="border-t border-stone-300 bg-stone-50 mt-8">
      <div className="max-w-7xl mx-auto px-6 py-4 text-xs text-stone-600 space-y-1.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-medium text-stone-800">Marcadores desta prova de conceito:</span>
          <span>PoC v0.1</span> <span>·</span>
          <span>TRL 3–4</span> <span>·</span>
          <span>BERTimbau LOEO (Pernambuco = out-of-fold)</span> <span>·</span>
          <span>thresholds 0.5 (não calibrados)</span> <span>·</span>
          <span>anotação humana pendente</span> <span>·</span>
          <span>polling a cada 4h (não tempo real)</span>
        </div>
        <div className="text-stone-500">
          Dados de coleta: YouTube Data API v3 (canal oficial autorizado). Alertas: CEMADEN PED.
          Junção por codibge. Nenhum web-scraping. Nenhuma classificação retroalimenta
          treinamento do modelo. Mapa base: GeoJSON de estados brasileiros (click_that_hood, MIT).
          Atualização dos dados exibidos: <strong>manual, por design</strong> — as agregações
          vêm do pipeline v2.4 rodando no Colab/Google Drive, não de um <em>backend</em> online.
          Coordenação: Álvaro Luz Alves Coutinho (NEPAM/PPGA&amp;S/Unicamp), sob supervisão da
          Profa. Leila da Costa Ferreira, no âmbito do CEPID CLIMARES (Eixo 7).
        </div>
      </div>
    </footer>
  );
}

// =========================================================================
// APP
// =========================================================================

export default function Dashboard() {
  const availableUFs = useMemo(() => getUFsWithEvents(), []);
  const [selectedUFs, setSelectedUFs] = useState(() => new Set(availableUFs));
  const [selectedId, setSelectedId] = useState("rs_2024");

  const filteredEvents = useMemo(
    () => getEventsByUFs(selectedUFs),
    [selectedUFs]
  );

  // Se o evento selecionado sumiu do filtro, escolher o primeiro disponível
  useEffect(() => {
    if (filteredEvents.length === 0) return;
    if (!filteredEvents.find(e => e.id === selectedId)) {
      setSelectedId(filteredEvents[0].id);
    }
  }, [filteredEvents, selectedId]);

  const selected = filteredEvents.find(e => e.id === selectedId);

  const toggleUF = (uf) => {
    setSelectedUFs(prev => {
      const next = new Set(prev);
      if (next.has(uf)) next.delete(uf);
      else next.add(uf);
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-stone-100 font-sans">
      <Header />
      <main className="max-w-7xl mx-auto px-6 py-6">
        {/* Breadcrumb */}
        <div className="mb-4">
          <Link to="/" className="text-xs text-stone-500 hover:text-stone-900 inline-flex items-center gap-1">
            <ArrowLeft size={12} /> Voltar
          </Link>
        </div>

        {/* Barra de filtros */}
        <div className="bg-white rounded-lg border border-stone-300 p-3 mb-4 flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 text-xs font-medium text-stone-700 flex-shrink-0">
            <Filter size={12} /> Filtrar por UF:
          </div>
          {availableUFs.map(uf => {
            const isActive = selectedUFs.has(uf);
            return (
              <button
                key={uf}
                onClick={() => toggleUF(uf)}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-stone-800 text-white"
                    : "bg-stone-100 text-stone-500 hover:bg-stone-200"
                }`}
              >
                {uf}
              </button>
            );
          })}
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-stone-500">
              {filteredEvents.length} de {getAllEvents().length} eventos
            </span>
            <button
              onClick={() => setSelectedUFs(new Set(availableUFs))}
              className="text-xs text-stone-600 hover:text-stone-900 underline"
              disabled={selectedUFs.size === availableUFs.length}
            >
              todas
            </button>
          </div>
        </div>

        {/* Grid principal ou estado vazio */}
        {filteredEvents.length === 0 ? (
          <div className="bg-white rounded-lg border-2 border-dashed border-stone-300 p-12 text-center">
            <div className="max-w-md mx-auto">
              <Filter size={28} className="mx-auto text-stone-400 mb-3" />
              <h3 className="text-sm font-semibold text-stone-800 mb-2">
                Nenhum evento com os filtros atuais
              </h3>
              <p className="text-xs text-stone-600">
                Selecione ao menos uma UF acima para ver eventos.
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-12 gap-6">
              <aside className="col-span-4">
                <BrazilMap
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  events={filteredEvents}
                />
              </aside>
              <section className="col-span-8">
                {selected && <EventPanel event={selected} />}
              </section>
            </div>
            <ComparisonSection events={filteredEvents} />
          </>
        )}
      </main>
      <Footer />
    </div>
  );
}
