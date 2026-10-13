import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Archive as ArchiveIcon, BookOpen, ChevronLeft, Inbox, Clock } from "lucide-react";
import Dashboard from "./dashboard";
import { FlagTimeline, formatDuration } from "./Live";
import { FLAG_META } from "./services/eventsRepository";
import liveData from "./data/live.json";

// ============================================================
// /archive — wrapper com dois tabs:
//   1. Corpus científico (dashboard histórico dos 6 eventos retrospectivos)
//   2. Arquivo do pipeline (alertas arquivados por regra temporal em v0.2+)
// Tab default = corpus (preserva URL/experiência atual).
// ============================================================
export default function Archive() {
  const [tab, setTab] = useState("corpus");

  return (
    <div className="min-h-screen bg-stone-50">
      {/* Barra de tabs no topo — visualmente leve para não competir com o
          header institucional de cada view */}
      <div className="bg-white border-b border-stone-200 sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-4 py-2 flex items-center gap-1">
          <Link
            to="/"
            className="p-1.5 rounded hover:bg-stone-100 text-stone-500 mr-2"
            aria-label="Voltar à landing"
          >
            <ChevronLeft size={18} />
          </Link>
          <TabButton
            active={tab === "corpus"}
            onClick={() => setTab("corpus")}
            icon={BookOpen}
            label="Corpus científico"
            hint="6 eventos históricos anotados"
          />
          <TabButton
            active={tab === "pipeline"}
            onClick={() => setTab("pipeline")}
            icon={ArchiveIcon}
            label="Arquivo do pipeline"
            hint="Alertas arquivados por regra temporal"
            count={(liveData.archived_alerts ?? []).length}
          />
        </div>
      </div>

      {/* Conteúdo do tab ativo */}
      {tab === "corpus" ? <Dashboard /> : <ArchivedPipelineView />}
    </div>
  );
}

function TabButton({ active, onClick, icon: Icon, label, hint, count }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
        active
          ? "bg-stone-900 text-white"
          : "text-stone-600 hover:bg-stone-100"
      }`}
      title={hint}
    >
      <Icon size={16} />
      <span className="font-medium">{label}</span>
      {typeof count === "number" && (
        <span
          className={`text-xs tabular-nums ${
            active ? "text-stone-300" : "text-stone-400"
          }`}
        >
          ({count})
        </span>
      )}
    </button>
  );
}

// ============================================================
// View: Arquivo do pipeline
// ============================================================
function ArchivedPipelineView() {
  const archived = liveData.archived_alerts ?? [];

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-6 space-y-4">
      {/* Header institucional */}
      <div className="bg-white rounded-lg border border-stone-300 p-5">
        <div className="flex items-start gap-3 mb-3">
          <div className="p-2 bg-stone-100 rounded">
            <ArchiveIcon size={20} className="text-stone-700" />
          </div>
          <div className="flex-1">
            <h1 className="text-xl font-semibold text-stone-900">
              Arquivo do pipeline
            </h1>
            <p className="text-sm text-stone-600 mt-1">
              Alertas CEMADEN arquivados pelo pipeline ODRD (v0.2+) por{" "}
              <strong>regra temporal cronológica</strong> — não por decisão
              humana, não por reclassificação institucional.
            </p>
          </div>
        </div>

        {/* Regras de arquivamento sempre visíveis (empty state honesto) */}
        <div className="bg-stone-50 border border-stone-200 rounded p-3 text-xs text-stone-700 space-y-1">
          <div className="font-semibold text-stone-800 mb-1">
            Regras de arquivamento
          </div>
          <div>
            <span className="inline-block w-2 h-2 rounded-full bg-zinc-500 mr-1.5 align-middle" />
            <strong>Alerta</strong> fechado no CEMADEN sem gerar sinal digital
            (nenhum vídeo aderente) → sai do state e incrementa o log agregado;{" "}
            <em>não aparece aqui</em> (não há entry rico a preservar).
          </div>
          <div>
            <span className="inline-block w-2 h-2 rounded-full bg-cyan-600 mr-1.5 align-middle" />
            <strong>Acompanhamento</strong> sem novo dado (vídeo ou comentário)
            por <strong>14 dias</strong> → arquivo completo aqui.
          </div>
          <div>
            <span className="inline-block w-2 h-2 rounded-full bg-violet-600 mr-1.5 align-middle" />
            <strong>Prioritário</strong> sem novo comentário por{" "}
            <strong>28 dias</strong> → arquivo completo aqui.
          </div>
        </div>
      </div>

      {/* Lista de arquivados ou empty state */}
      {archived.length === 0 ? <ArchiveEmptyState /> : (
        <div className="space-y-3">
          {archived.map((a) => (
            <ArchivedAlertCard key={a.id} alert={a} />
          ))}
        </div>
      )}
    </div>
  );
}

function ArchiveEmptyState() {
  return (
    <div className="bg-white rounded-lg border border-dashed border-stone-300 p-8 text-center">
      <div className="inline-flex p-3 bg-stone-100 rounded-full mb-3">
        <Inbox size={24} className="text-stone-500" />
      </div>
      <div className="text-base font-medium text-stone-800 mb-1">
        Nenhum alerta arquivado até o momento
      </div>
      <p className="text-sm text-stone-600 max-w-xl mx-auto">
        Silêncio protocolar — não é falha do sistema. Alertas só migram para
        este arquivo depois de cumprir as regras temporais acima. Enquanto
        estiverem em observação ativa, aparecem em{" "}
        <Link to="/live" className="text-stone-900 underline">
          /live
        </Link>
        .
      </p>
    </div>
  );
}

// ============================================================
// Card de alerta arquivado — reusa FlagTimeline, adapta o resto
// para o contexto "alerta encerrado" (sem próxima coleta, com motivo
// de arquivamento em destaque).
// ============================================================
function ArchivedAlertCard({ alert }) {
  const flagMeta = FLAG_META[alert.flag_final] ?? FLAG_META.alerta;

  const openedDate = alert.opened_at ? new Date(alert.opened_at) : null;
  const archivedDate = alert.archived_at ? new Date(alert.archived_at) : null;
  const totalDuration =
    openedDate && archivedDate ? archivedDate - openedDate : null;

  return (
    <div className="bg-white rounded-lg border border-stone-300 overflow-hidden">
      {/* Header */}
      <div className="p-4 bg-stone-50 border-b border-stone-200 flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-stone-900">
              {alert.municipio}/{alert.uf}
            </h3>
            <span
              className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold text-white ${flagMeta.bgClass}`}
              title="Flag operacional no momento do arquivamento"
            >
              <span
                className="rounded-full inline-block bg-white"
                style={{ width: 5, height: 5 }}
              />
              {flagMeta.label}
            </span>
          </div>
          <div className="text-xs text-stone-600 mt-1">
            {alert.tipo ?? "—"} · {alert.nivel ?? "—"}
            {totalDuration != null && (
              <>
                {" · "}
                <span className="text-stone-500">
                  em observação por {formatDuration(totalDuration)}
                </span>
              </>
            )}
          </div>
        </div>
        <div className="text-xs text-stone-500 text-right tabular-nums">
          <div>
            aberto{" "}
            {openedDate?.toLocaleString("pt-BR", {
              day: "2-digit", month: "2-digit", year: "numeric",
              hour: "2-digit", minute: "2-digit",
            })}
          </div>
          <div>
            arquivado{" "}
            {archivedDate?.toLocaleString("pt-BR", {
              day: "2-digit", month: "2-digit", year: "numeric",
              hour: "2-digit", minute: "2-digit",
            })}
          </div>
        </div>
      </div>

      {/* Corpo */}
      <div className="p-4">
        <FlagTimeline history={alert.flag_history} />

        {/* Motivo do arquivamento */}
        <div className="bg-stone-50 border border-stone-200 rounded p-3 mb-3">
          <div className="flex items-start gap-2">
            <Clock size={14} className="text-stone-500 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-stone-700">
              <span className="font-medium text-stone-900">
                Motivo do arquivamento:
              </span>{" "}
              {alert.archive_reason ?? "—"}
            </div>
          </div>
        </div>

        {/* Contadores finais */}
        <div className="grid grid-cols-3 gap-3">
          <FinalMetric label="Comentários coletados" value={alert.n_comments_valid ?? 0} />
          <FinalMetric
            label="Vídeos (citam o município)"
            value={`${alert.n_videos_aderentes ?? 0} (${alert.n_videos_municipais ?? 0})`}
          />
          <FinalMetric
            label="Último comentário"
            value={
              alert.last_new_comment_at
                ? new Date(alert.last_new_comment_at).toLocaleDateString("pt-BR", {
                    day: "2-digit", month: "2-digit", year: "numeric",
                  })
                : "—"
            }
            small
          />
        </div>
      </div>
    </div>
  );
}

function FinalMetric({ label, value, small = false }) {
  return (
    <div className="bg-stone-50 rounded p-3 text-center">
      <div className="text-xs text-stone-500 mb-1">{label}</div>
      <div
        className={`font-semibold text-stone-900 tabular-nums ${
          small ? "text-sm" : "text-xl"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
