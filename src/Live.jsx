import { useState, useMemo, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Radio, AlertTriangle, Info, Beaker, Clock,
  ArrowLeft, Activity, Archive, MapPin, Filter,
  CheckCircle2, XCircle, VolumeX, Video, ExternalLink,
  FlaskConical, TrendingUp
} from "lucide-react";
import * as d3 from "d3";
import {
  getLiveData,
  getLiveAlerts,
  getPipelineState,
  getPriorityCollectionAlerts,
  getExtendedWindowAlerts,
  TIER_ORDER,
  TIER_META,
  getTierMeta,
  FLAG_ORDER,
  FLAG_META,
  getFlagMeta,
  getFlagsInLive,
  sortAlertsByFlag,
} from "./services/eventsRepository";

// ============================================================
// Mapa: dots coloridos por priority_tier, sem seleção
// ============================================================
function LiveMap({ alerts }) {
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
  const ufsComAlerta = useMemo(() => new Set(alerts.map(a => a.uf)), [alerts]);

  const { pathGen, projection } = useMemo(() => {
    if (!geo) return { pathGen: null, projection: null };
    const proj = d3.geoMercator().fitSize([width, height], geo);
    return { pathGen: d3.geoPath().projection(proj), projection: proj };
  }, [geo]);

  // Ordenar por tier para dots menores ficarem por baixo
  const alertsOrdered = useMemo(
    () => [...alerts].sort((a, b) => {
      const orderA = TIER_ORDER.indexOf(a.priority_tier);
      const orderB = TIER_ORDER.indexOf(b.priority_tier);
      return orderB - orderA; // mais críticos por cima
    }),
    [alerts]
  );

  return (
    <div className="bg-white rounded-lg border border-stone-300 p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-stone-800 flex items-center gap-2">
          <MapPin size={16} /> Alertas em observação
        </h2>
        <span className="text-xs text-stone-500">
          {alerts.length} {alerts.length === 1 ? "alerta" : "alertas"} · {ufsComAlerta.size} {ufsComAlerta.size === 1 ? "UF" : "UFs"}
        </span>
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
                const hasAlert = ufsComAlerta.has(uf);
                return (
                  <path
                    key={i}
                    d={pathGen(f)}
                    fill={hasAlert ? "#78716c" : "#e7e5e4"}
                    stroke="#ffffff"
                    strokeWidth={0.6}
                  />
                );
              })}
            </g>
            <g>
              {alertsOrdered.map(a => {
                if (a.lat == null || a.lon == null) return null;
                const [x, y] = projection([a.lon, a.lat]);
                const meta = getTierMeta(a.priority_tier);
                return (
                  <g key={a.id}>
                    <circle cx={x} cy={y} r={meta.dotRadius + 2} fill="white" opacity={0.9} />
                    <circle
                      cx={x}
                      cy={y}
                      r={meta.dotRadius}
                      fill={meta.color}
                      stroke="white"
                      strokeWidth={1.5}
                    >
                      <title>{a.municipio}/{a.uf} · {meta.label}</title>
                    </circle>
                  </g>
                );
              })}
            </g>
          </svg>
        )}
      </div>
      {/* Legenda */}
      <div className="flex flex-wrap gap-3 mt-3 text-xs">
        {TIER_ORDER.map(t => {
          const meta = TIER_META[t];
          return (
            <div key={t} className="flex items-center gap-1.5">
              <span
                className="rounded-full inline-block"
                style={{
                  width: (meta.dotRadius * 2),
                  height: (meta.dotRadius * 2),
                  backgroundColor: meta.color,
                }}
              />
              <span className="text-stone-600">{meta.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// Header do /live — badges pilot/dry_run
// ============================================================
function Header({ liveData }) {
  return (
    <header className="border-b border-stone-300 bg-white">
      <div className="max-w-7xl mx-auto px-6 py-5 flex items-start justify-between gap-6">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 rounded-md bg-stone-800 text-white flex items-center justify-center text-xs font-semibold">
            ODRD
          </div>
          <div>
            <h1 className="text-xl font-semibold text-stone-900 leading-tight group-hover:underline">
              Observatório Digital de Riscos e Desastres
            </h1>
            <p className="text-xs text-stone-600">
              Escuta digital territorializada · reação pública observável a alertas hidrometeorológicos
            </p>
          </div>
        </Link>
        <div className="flex flex-col items-end gap-1 text-xs">
          {liveData.pilot_mode && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-100 text-amber-900 border border-amber-300 font-medium">
              <FlaskConical size={12} /> Piloto técnico · dados fora do corpus científico
            </span>
          )}
          {liveData.dry_run && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-purple-100 text-purple-900 border border-purple-300">
              <Beaker size={12} /> Modo de teste · dados replicados de alerta histórico
            </span>
          )}
          <span className="text-stone-500 text-right">
            NEPAM/Unicamp · CEPID CLIMARES · parceria CEMADEN
          </span>
        </div>
      </div>
      <div className="bg-stone-50 border-t border-stone-200">
        <div className="max-w-7xl mx-auto px-6 py-2.5 text-xs text-stone-600 flex items-start gap-2">
          <Info size={14} className="mt-0.5 flex-shrink-0" />
          <span>
            Sistema <strong>complementar</strong> à infraestrutura de alertas do CEMADEN.
            Este painel instrumenta a camada de <strong>reação pública digital observável</strong> após
            o alerta — <strong>cadência declarada, não tempo real</strong>: janelas fixas de 6h (Muito Alto),
            12h (Alto), 24h (Moderado), 48h (Acompanhamento).
          </span>
        </div>
      </div>
    </header>
  );
}

// ============================================================
// Painel de saúde do pipeline (KPIs + banner condicional)
// ============================================================
function PipelineHealthPanel({ liveData, state }) {
  const lastRunDate = new Date(state.last_run_at);
  const now = new Date();
  const hoursSinceLastRun = (now - lastRunDate) / (1000 * 60 * 60);

  // Alarme: pipeline sem executar há mais de 2× a menor cadência (12h = 2×6h)
  const isStale = hoursSinceLastRun > 12;

  // Formatação amigável
  const generatedAtFmt = new Date(liveData.generated_at).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });

  return (
    <div className="space-y-3 mb-4">
      {/* Banner de falha se stale */}
      {isStale && (
        <div className="bg-red-50 border border-red-300 rounded-lg p-4 flex items-start gap-3">
          <XCircle size={20} className="text-red-600 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-red-900">
              Pipeline sem atualização há {Math.floor(hoursSinceLastRun)}h
            </div>
            <div className="text-xs text-red-700 mt-1">
              Última execução: {generatedAtFmt}. Verificar workflow GitHub Actions.
            </div>
          </div>
        </div>
      )}

      {/* Painel de status */}
      <div className="bg-white rounded-lg border border-stone-300 p-5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPI
            icon={Activity}
            label="Alertas em observação"
            value={liveData.alerts.length}
          />
          <KPI
            icon={Clock}
            label="Última coleta"
            value={generatedAtFmt}
            small
          />
          <KPI
            icon={TrendingUp}
            label="Cota YouTube (dia)"
            value={`${state.youtube_quota.used_today.toLocaleString("pt-BR")}`}
            sub={`de 10.000 · reset ${new Date(state.youtube_quota.reset_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`}
          />
          <KPI
            icon={CheckCircle2}
            label="Status pipeline"
            value={state.last_run_status === "success" ? "OK" : state.last_run_status}
            sub={`v${state.pipeline_version}`}
            ok={state.last_run_status === "success"}
          />
        </div>
      </div>
    </div>
  );
}

function KPI({ icon: Icon, label, value, sub, small, ok }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-xs text-stone-500 mb-1">
        <Icon size={12} /> {label}
      </div>
      <div className={`${small ? "text-sm" : "text-2xl"} font-semibold text-stone-900 leading-tight`}>
        {value}
      </div>
      {sub && <div className={`text-xs mt-0.5 ${ok === false ? "text-red-600" : "text-stone-500"}`}>{sub}</div>}
    </div>
  );
}

// ============================================================
// Chips de filtro por flag (v0.2: partição operacional ODRD)
// ============================================================
function FlagFilterChips({ availableFlags, selectedFlags, onToggle, alertCounts }) {
  return (
    <div className="bg-white rounded-lg border border-stone-300 p-3 mb-4 flex items-center gap-3 flex-wrap">
      <div className="flex items-center gap-1.5 text-xs font-medium text-stone-700 flex-shrink-0">
        <Filter size={12} /> Filtrar por estágio:
      </div>
      {availableFlags.map(flag => {
        const meta = FLAG_META[flag];
        const isActive = selectedFlags.has(flag);
        const count = alertCounts[flag] ?? 0;
        return (
          <button
            key={flag}
            onClick={() => onToggle(flag)}
            title={meta.description}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors inline-flex items-center gap-1.5 ${
              isActive
                ? `${meta.bgClass} text-white`
                : "bg-stone-100 text-stone-500 hover:bg-stone-200"
            }`}
          >
            <span
              className="rounded-full inline-block"
              style={{
                width: 8,
                height: 8,
                backgroundColor: isActive ? "white" : meta.color,
              }}
            />
            {meta.label} ({count})
          </button>
        );
      })}
    </div>
  );
}

// ============================================================
// Card de um alerta live
// ============================================================
function AlertCard({ alert }) {
  const tierMeta = getTierMeta(alert.priority_tier);
  const flagMeta = getFlagMeta(alert.flag);
  const nextCollectionFmt = alert.next_collection_at
    ? new Date(alert.next_collection_at).toLocaleString("pt-BR", {
        day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
      })
    : "—";
  const openedFmt = alert.alert_opened_at
    ? new Date(alert.alert_opened_at).toLocaleString("pt-BR", {
        day: "2-digit", month: "2-digit", year: "numeric",
        hour: "2-digit", minute: "2-digit",
      })
    : "—";

  // Silence banner
  const isSilent = alert.collection_health?.status === "silent";
  const silenceType = alert.collection_health?.silence_type;

  return (
    <div className={`bg-white rounded-lg border ${flagMeta.borderClass} overflow-hidden`}>
      {/* Header: cor de fundo pela FLAG (estágio ODRD); dot pela gravidade CEMADEN */}
      <div className={`${flagMeta.lightBgClass} border-b ${flagMeta.borderClass} px-4 py-3`}>
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span
              className="rounded-full flex-shrink-0"
              title={`Gravidade CEMADEN: ${tierMeta.label}`}
              style={{ width: 14, height: 14, backgroundColor: tierMeta.color }}
            />
            <div>
              <div className="text-base font-semibold text-stone-900">
                {alert.municipio}/{alert.uf}
              </div>
              <div className="text-xs text-stone-600 mt-0.5">
                {alert.tipo} · {alert.nivel} · aberto em {openedFmt}
              </div>
            </div>
          </div>
          <div className="text-right text-xs">
            {/* Badge da flag (estágio operacional ODRD) — drive de cadência */}
            <div className={`font-semibold ${flagMeta.textClass}`}>
              {flagMeta.label} · {flagMeta.cadenceHours}h
            </div>
            <div className="text-stone-500">próxima coleta {nextCollectionFmt}</div>
          </div>
        </div>
      </div>

      {/* Corpo */}
      <div className="p-4">
        {/* Silence banner */}
        {isSilent && (
          <div className="bg-stone-50 border border-stone-200 rounded p-3 mb-3 flex items-start gap-2">
            <VolumeX size={16} className="text-stone-500 flex-shrink-0 mt-0.5" />
            <div className="text-xs text-stone-700">
              <div className="font-medium">Silêncio digital observável</div>
              <div className="text-stone-600 mt-0.5">
                {silenceType === "no_videos_found" && "Nenhum vídeo aderente encontrado nas buscas ao YouTube neste ciclo."}
                {silenceType === "videos_without_comments" && "Vídeos aderentes encontrados, porém sem comentários coletáveis."}
                {silenceType === "api_error" && "Falha técnica na API do YouTube — reportado como erro, não como silêncio."}
                {silenceType === "quota_exceeded" && "Cota YouTube esgotada — coleta reprogramada."}
                {" "}
                <em>Dado positivo do protocolo</em> — não é falha do sistema.
              </div>
            </div>
          </div>
        )}

        {/* KPIs mini */}
        <div className="grid grid-cols-3 gap-3 mb-3">
          <MiniStat label="Comentários" value={alert.n_comments} />
          <MiniStat label="Vídeos" value={alert.n_videos} />
          <MiniStat
            label="Não classificados"
            value={alert.n_comments > 0 ? `${alert.unlabeled_pct}%` : "—"}
          />
        </div>

        {/* Distribuição mini (só se há dados) */}
        {alert.n_comments > 0 && (
          <div className="mb-3">
            <div className="text-xs font-medium text-stone-700 mb-2">
              Distribuição por categoria
            </div>
            <div className="space-y-1">
              {alert.distribution
                .filter(c => c.count > 0)
                .sort((a, b) => b.count - a.count)
                .map(cat => (
                  <div key={cat.key} className="flex items-center gap-2 text-xs">
                    <div className="w-40 truncate text-stone-600" title={cat.label}>
                      {cat.label}
                    </div>
                    <div className="flex-1 bg-stone-100 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-stone-700 h-full"
                        style={{ width: `${Math.max(cat.pct, 2)}%` }}
                      />
                    </div>
                    <div className="w-16 text-right text-stone-700 tabular-nums">
                      {cat.count} · {cat.pct}%
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Vídeos coletados (thumbs mini) */}
        {alert.videos.length > 0 && (
          <div>
            <div className="text-xs font-medium text-stone-700 mb-2 flex items-center gap-1.5">
              <Video size={12} /> Vídeos coletados
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {alert.videos.slice(0, 4).map(v => (
                <a
                  key={v.video_id}
                  href={`https://www.youtube.com/watch?v=${v.video_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 p-2 rounded border border-stone-200 hover:border-stone-400 hover:bg-stone-50 transition-colors"
                >
                  <img
                    src={`https://img.youtube.com/vi/${v.video_id}/default.jpg`}
                    alt=""
                    className="w-16 h-12 object-cover rounded flex-shrink-0 bg-stone-100"
                  />
                  <div className="min-w-0 flex-1 text-xs">
                    <div className="text-stone-800 font-medium truncate">
                      {v.video_id}
                    </div>
                    <div className="text-stone-500">
                      {v.n_comments} coment. · {v.total_likes} likes
                    </div>
                  </div>
                  <ExternalLink size={10} className="text-stone-400 flex-shrink-0" />
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Estado vazio se não é silent mas também não tem dados */}
        {!isSilent && alert.n_comments === 0 && alert.n_videos === 0 && (
          <div className="text-xs text-stone-500 italic text-center py-4">
            Coleta iniciada. Dados aparecerão no próximo ciclo.
          </div>
        )}
      </div>
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div className="bg-stone-50 rounded p-2 text-center">
      <div className="text-xs text-stone-500">{label}</div>
      <div className="text-lg font-semibold text-stone-900 tabular-nums">{value}</div>
    </div>
  );
}

// ============================================================
// Seção de alertas (prioritária ou acompanhamento)
// ============================================================
function AlertsSection({ title, subtitle, icon: Icon, alerts, emptyMessage }) {
  if (alerts.length === 0 && !emptyMessage) return null;

  return (
    <section className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={18} className="text-stone-700" />
        <h2 className="text-lg font-semibold text-stone-900">{title}</h2>
        <span className="text-sm text-stone-500">({alerts.length})</span>
      </div>
      {subtitle && <p className="text-xs text-stone-600 mb-3">{subtitle}</p>}
      {alerts.length === 0 ? (
        <div className="bg-stone-50 border border-dashed border-stone-300 rounded-lg p-6 text-center text-sm text-stone-500">
          {emptyMessage}
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map(a => <AlertCard key={a.id} alert={a} />)}
        </div>
      )}
    </section>
  );
}

// ============================================================
// Footer
// ============================================================
function Footer() {
  return (
    <footer className="border-t border-stone-300 bg-stone-50 mt-8">
      <div className="max-w-7xl mx-auto px-6 py-4 text-xs text-stone-500">
        Coordenação: Álvaro Luz Alves Coutinho (NEPAM/PPGA&amp;S/Unicamp), sob supervisão da
        Profa. Leila da Costa Ferreira, no âmbito do CEPID CLIMARES (Eixo 7).
      </div>
    </footer>
  );
}

// ============================================================
// Componente principal
// ============================================================
export default function Live() {
  const liveData = getLiveData();
  const state = getPipelineState();
  const availableFlags = useMemo(() => getFlagsInLive(), []);

  // Default: todas as flags ativas (usuário pode desmarcar)
  const [selectedFlags, setSelectedFlags] = useState(
    () => new Set(availableFlags)
  );

  const toggleFlag = (flag) => {
    setSelectedFlags(prev => {
      const next = new Set(prev);
      if (next.has(flag)) next.delete(flag);
      else next.add(flag);
      return next;
    });
  };

  // Contagens por flag (todas, não filtradas — para os chips mostrarem total)
  const alertCounts = useMemo(() => {
    const counts = {};
    for (const f of FLAG_ORDER) counts[f] = 0;
    for (const a of liveData.alerts) {
      counts[a.flag] = (counts[a.flag] ?? 0) + 1;
    }
    return counts;
  }, [liveData]);

  // Filtrar alertas pelas flags selecionadas E separar por seção (v0.2: por observation_status)
  // Ordenar por flag dentro de cada seção (prioritario > acompanhamento > alerta)
  const priorityAlerts = useMemo(
    () => getPriorityCollectionAlerts()
      .filter(a => selectedFlags.has(a.flag))
      .sort(sortAlertsByFlag),
    [selectedFlags]
  );
  const extendedAlerts = useMemo(
    () => getExtendedWindowAlerts()
      .filter(a => selectedFlags.has(a.flag))
      .sort(sortAlertsByFlag),
    [selectedFlags]
  );

  const alertsOnMap = useMemo(
    () => liveData.alerts.filter(a => selectedFlags.has(a.flag)),
    [liveData, selectedFlags]
  );

  return (
    <div className="min-h-screen bg-stone-100 font-sans flex flex-col">
      <Header liveData={liveData} />

      {/* Breadcrumb */}
      <div className="max-w-7xl mx-auto px-6 pt-4 w-full">
        <Link to="/" className="text-xs text-stone-500 hover:text-stone-900 inline-flex items-center gap-1">
          <ArrowLeft size={12} /> Voltar
        </Link>
      </div>

      <main className="flex-1 max-w-7xl mx-auto px-6 py-6 w-full">
        {/* Título da rota */}
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded bg-emerald-50 flex items-center justify-center">
            <Radio size={20} className="text-emerald-700" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-stone-900 leading-tight">
              Escuta ativa
            </h2>
            <p className="text-sm text-stone-600">
              Alertas CEMADEN em observação prospectiva
            </p>
          </div>
        </div>

        {/* Estado inicial (Estado A do plano): sem alertas nenhum */}
        {liveData.alerts.length === 0 ? (
          <div className="bg-white rounded-lg border-2 border-dashed border-stone-300 p-12 text-center">
            <div className="max-w-md mx-auto">
              <div className="w-16 h-16 rounded-full bg-stone-100 flex items-center justify-center mx-auto mb-4">
                <Radio size={28} className="text-stone-400" />
              </div>
              <h3 className="text-base font-semibold text-stone-800 mb-2">
                Aguardando primeiro alerta
              </h3>
              <p className="text-sm text-stone-600 leading-relaxed">
                O pipeline consulta o Painel de Alertas Vigentes do CEMADEN a cada 6 horas.
                Quando um alerta for aberto, aparecerá aqui automaticamente.
              </p>
              <div className="mt-6 pt-6 border-t border-stone-200 text-xs text-stone-500 leading-relaxed">
                Eventos históricos consolidados estão disponíveis no{" "}
                <Link to="/archive" className="text-stone-900 underline hover:no-underline inline-flex items-center gap-1">
                  <Archive size={11} /> Arquivo
                </Link>.
              </div>
            </div>
          </div>
        ) : (
          <>
            <PipelineHealthPanel liveData={liveData} state={state} />

            {/* Grid: mapa à esquerda, filtro + seções à direita */}
            <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-4 mb-4">
              <div>
                <LiveMap alerts={alertsOnMap} />
              </div>
              <div className="min-w-0">
                <FlagFilterChips
                  availableFlags={availableFlags}
                  selectedFlags={selectedFlags}
                  onToggle={toggleFlag}
                  alertCounts={alertCounts}
                />

                {/* Seção A — Coleta prioritária (alertas ativos CEMADEN) */}
                <AlertsSection
                  title="Coleta prioritária"
                  subtitle="Alertas CEMADEN em vigência ativa — cadência por estágio ODRD (24h alerta / 12h acompanhamento / 6h prioritário)."
                  icon={AlertTriangle}
                  alerts={priorityAlerts}
                  emptyMessage="Nenhum alerta ativo nos estágios selecionados."
                />

                {/* Seção B — Janela estendida (CEMADEN fechou, sinal digital persiste) */}
                <AlertsSection
                  title="Janela estendida"
                  subtitle="Alertas fechados no CEMADEN mas ainda com sinal digital observável — mantidos em observação até esgotamento temporal (14d em acompanhamento, 28d em prioritário)."
                  icon={Activity}
                  alerts={extendedAlerts}
                  emptyMessage="Nenhum alerta em janela estendida atualmente."
                />
              </div>
            </div>
          </>
        )}
      </main>

      <Footer />
    </div>
  );
}
