import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { MapContainer, TileLayer, GeoJSON, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { ArrowLeft, Megaphone, Info, AlertTriangle, MapPin, X } from "lucide-react";

// ============================================================
// /idap — alertas da Defesa Civil à população (IDAP, CAP 1.2)
// Dados: public/data/idap/indice.json + dias/AAAA-MM-DD.geojson,
// gerados de hora em hora pelo workflow idap.yml.
// ============================================================

const BASE = "/data/idap";

const SEVERITY_META = {
  Extreme: { label: "Extrema", color: "#991b1b", fill: "#dc2626", chip: "bg-red-50 text-red-800 border-red-200" },
  Severe: { label: "Severa", color: "#9a3412", fill: "#f97316", chip: "bg-orange-50 text-orange-800 border-orange-200" },
  Moderate: { label: "Moderada", color: "#854d0e", fill: "#eab308", chip: "bg-yellow-50 text-yellow-800 border-yellow-200" },
  Minor: { label: "Menor", color: "#075985", fill: "#38bdf8", chip: "bg-sky-50 text-sky-800 border-sky-200" },
  Unknown: { label: "Desconhecida", color: "#44403c", fill: "#a8a29e", chip: "bg-stone-50 text-stone-700 border-stone-200" },
};
const SEVERITY_ORDER = ["Extreme", "Severe", "Moderate", "Minor", "Unknown"];
const sevMeta = (s) => SEVERITY_META[s] ?? SEVERITY_META.Unknown;

const JANELAS = [
  { horas: 24, label: "24 h" },
  { horas: 72, label: "3 dias" },
  { horas: 168, label: "7 dias" },
];

const fmtBRT = (iso, opts = {}) =>
  iso
    ? new Date(iso).toLocaleString("pt-BR", {
        timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit",
        hour: "2-digit", minute: "2-digit", ...opts,
      })
    : "—";

function vigencia(p, agora) {
  const ini = p.onset_utc ? Date.parse(p.onset_utc) : Date.parse(p.sent_utc);
  const fim = p.expires_utc ? Date.parse(p.expires_utc) : null;
  if (fim && agora > fim) return "encerrado";
  if (ini && agora < ini) return "previsto";
  return "vigente";
}

// relógio do painel: atualiza a cada minuto (vigência e atraso da coleta)
function useAgora() {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setAgora(Date.now()), 60e3);
    return () => clearInterval(t);
  }, []);
  return agora;
}

function useIdap(horas) {
  const [indice, setIndice] = useState(null);
  const [erro, setErro] = useState(false);
  const [carga, setCarga] = useState({ horas: null, features: [] });

  useEffect(() => {
    let vivo = true;
    fetch(`${BASE}/indice.json`, { cache: "no-cache" })
      .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then((idx) => { if (vivo) setIndice(idx); })
      .catch(() => vivo && setErro(true));
    return () => { vivo = false; };
  }, []);

  useEffect(() => {
    if (!indice) return;
    let vivo = true;
    const limite = Date.now() - horas * 3600e3;
    // dias de emissão (Brasília) que podem conter alertas da janela: folga de 1 dia
    const corte = new Date(limite - 86400e3).toISOString().slice(0, 10);
    const dias = (indice.dias ?? []).filter((d) => d.dia >= corte);
    Promise.all(dias.map((d) => fetch(`${BASE}/${d.arquivo}`, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : { features: [] }))))
      .then((fcs) => {
        if (!vivo) return;
        const todas = fcs.flatMap((fc) => fc.features ?? []);
        setCarga({ horas, features: todas.filter((f) => Date.parse(f.properties.sent_utc) >= limite) });
      })
      .catch(() => vivo && setErro(true));
    return () => { vivo = false; };
  }, [indice, horas]);

  const status = erro ? "error" : carga.horas === horas ? "ok" : "loading";
  return { indice, features: carga.horas === horas ? carga.features : [], status };
}

function FitTo({ bbox }) {
  const map = useMap();
  useEffect(() => {
    if (bbox) map.flyToBounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]], { padding: [30, 30], maxZoom: 10, duration: 0.6 });
  }, [bbox, map]);
  return null;
}

function SeverityBadge({ severity }) {
  const m = sevMeta(severity);
  return <span className={`inline-block px-1.5 py-px rounded border text-[10px] font-medium ${m.chip}`}>{m.label}</span>;
}

function SaudeColeta({ indice, agora }) {
  if (!indice) return null;
  const ultima = indice.ultima_captura_ok ? Date.parse(indice.ultima_captura_ok) : null;
  const atrasoH = ultima ? (agora - ultima) / 3600e3 : null;
  const atrasada = atrasoH === null || atrasoH > 3;
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-xs px-3 py-2 rounded border ${atrasada ? "bg-amber-50 border-amber-200 text-amber-900" : "bg-white border-stone-200 text-stone-600"}`}>
      <span>
        Última captura com sucesso: <strong>{fmtBRT(indice.ultima_captura_ok)}</strong>
        {atrasada && " — coleta atrasada; alertas recentes podem faltar"}
      </span>
      <span>Capturas nas últimas 24 h: {indice.capturas_24h_ok}/{indice.capturas_24h}</span>
      <span>Alertas arquivados: {indice.total_alertas?.toLocaleString("pt-BR")}</span>
      <span title="Números de identificador CAP ausentes entre o menor e o maior arquivados. Podem ser alertas perdidos (fora da janela do feed) ou não publicados no feed.">
        Lacunas na numeração: {indice.ids_faltantes_total}
      </span>
      <span>Arquivo desde {fmtBRT(indice.primeira_captura, { year: "numeric", hour: undefined, minute: undefined })}</span>
    </div>
  );
}

function Detalhe({ f, onClose, agora }) {
  const p = f.properties;
  return (
    <div className="bg-white rounded-lg border border-stone-300 p-4 text-sm">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <SeverityBadge severity={p.severity} />
            <span className="text-[11px] text-stone-500">{vigencia(p, agora)}</span>
          </div>
          <h3 className="font-semibold text-stone-900 leading-snug">{p.event}</h3>
          <p className="text-xs text-stone-600">{p.sender_name}</p>
        </div>
        <button onClick={onClose} className="p-1 rounded hover:bg-stone-100 text-stone-500" aria-label="Fechar">
          <X size={16} />
        </button>
      </div>
      {p.headline && <p className="text-stone-800 mb-2">{p.headline}</p>}
      <p className="text-stone-800 whitespace-pre-line mb-2">{p.description}</p>
      {p.instruction && (
        <p className="text-stone-700 bg-stone-50 border border-stone-200 rounded p-2 text-xs whitespace-pre-line mb-2">
          <strong>Orientação:</strong> {p.instruction}
        </p>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-stone-600">
        <dt>Emitido</dt><dd>{fmtBRT(p.sent_utc, { year: "numeric", second: "2-digit" })}</dd>
        <dt>Vigência</dt><dd>{fmtBRT(p.onset_utc)} → {fmtBRT(p.expires_utc)}</dd>
        <dt>Urgência · certeza</dt><dd>{p.urgency} · {p.certainty}</dd>
        <dt>Área</dt><dd>{p.area_desc || "—"}{p.area_km2 ? ` · ~${Math.round(p.area_km2).toLocaleString("pt-BR")} km²` : ""}</dd>
        <dt>UF</dt><dd>{(p.ufs ?? []).join(", ") || "—"}</dd>
        <dt>Identificador CAP</dt><dd className="font-mono">{p.identifier}</dd>
        {p.msg_type !== "Alert" && (<><dt>Tipo</dt><dd>{p.msg_type} {p.references && `(ref. ${p.references})`}</dd></>)}
      </dl>
      {!f.geometry && (
        <p className="mt-2 text-xs text-amber-800 flex items-center gap-1">
          <AlertTriangle size={12} /> O CAP deste alerta não traz polígono nem geocódigo.
        </p>
      )}
    </div>
  );
}

export default function Idap() {
  const [horas, setHoras] = useState(24);
  const { indice, features, status } = useIdap(horas);
  const [sevs, setSevs] = useState(() => new Set(SEVERITY_ORDER));
  const [uf, setUf] = useState("");
  const [sel, setSel] = useState(null);
  const agora = useAgora();

  const ufs = useMemo(() => [...new Set(features.flatMap((f) => f.properties.ufs ?? []))].sort(), [features]);
  const visiveis = useMemo(
    () => features
      .filter((f) => sevs.has(SEVERITY_META[f.properties.severity] ? f.properties.severity : "Unknown"))
      .filter((f) => !uf || (f.properties.ufs ?? []).includes(uf))
      .sort((a, b) => Date.parse(b.properties.sent_utc) - Date.parse(a.properties.sent_utc)),
    [features, sevs, uf]
  );
  // no mapa: áreas maiores por baixo, para as pequenas continuarem clicáveis
  const noMapa = useMemo(
    () => ({ type: "FeatureCollection", features: visiveis.filter((f) => f.geometry).sort((a, b) => (b.properties.area_km2 || 0) - (a.properties.area_km2 || 0)) }),
    [visiveis]
  );
  const chaveMapa = useMemo(() => noMapa.features.map((f) => f.id).join(",") + "|" + (sel?.id ?? ""), [noMapa, sel]);
  const contagem = useMemo(() => {
    const c = {};
    for (const f of features) { const s = SEVERITY_META[f.properties.severity] ? f.properties.severity : "Unknown"; c[s] = (c[s] ?? 0) + 1; }
    return c;
  }, [features]);
  const nVigentes = visiveis.filter((f) => vigencia(f.properties, agora) === "vigente").length;
  const listaRef = useRef(null);

  const toggleSev = (s) => setSevs((prev) => { const n = new Set(prev); n.has(s) ? n.delete(s) : n.add(s); return n; });

  const estilo = (f) => {
    const m = sevMeta(f.properties.severity);
    const ativo = vigencia(f.properties, agora) !== "encerrado";
    const selecionado = sel && f.id === sel.id;
    return {
      color: selecionado ? "#0c0a09" : m.color,
      weight: selecionado ? 3 : 1.2,
      dashArray: ativo ? null : "4 3",
      fillColor: m.fill,
      fillOpacity: selecionado ? 0.45 : ativo ? 0.28 : 0.1,
    };
  };

  return (
    <div className="min-h-screen bg-stone-100 font-sans flex flex-col">
      <header className="border-b border-stone-300 bg-white">
        <div className="max-w-7xl mx-auto px-6 py-5 flex items-center gap-3">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-md bg-stone-800 text-white flex items-center justify-center text-xs font-semibold">ODRD</div>
            <div>
              <h1 className="text-xl font-semibold text-stone-900 leading-tight group-hover:underline">Observatório Digital de Riscos e Desastres</h1>
              <p className="text-xs text-stone-600">NEPAM/Unicamp · CEPID CLIMARES</p>
            </div>
          </Link>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 pt-4 w-full">
        <Link to="/" className="text-xs text-stone-500 hover:text-stone-900 inline-flex items-center gap-1">
          <ArrowLeft size={12} /> Voltar
        </Link>
      </div>

      <main className="flex-1 max-w-7xl mx-auto px-6 py-6 w-full">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-10 h-10 rounded bg-red-50 flex items-center justify-center">
            <Megaphone size={20} className="text-red-700" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-stone-900 leading-tight">Alertas à população</h2>
            <p className="text-sm text-stone-600">Defesas Civis do Brasil · IDAP, padrão CAP 1.2 · coleta de hora em hora</p>
          </div>
        </div>

        <div className="mb-4"><SaudeColeta indice={indice} agora={agora} /></div>

        {/* Filtros */}
        <div className="flex flex-wrap items-center gap-2 mb-4 text-xs">
          <div className="inline-flex rounded border border-stone-300 bg-white overflow-hidden">
            {JANELAS.map((j) => (
              <button key={j.horas} onClick={() => { setHoras(j.horas); setSel(null); }}
                className={`px-3 py-1.5 ${horas === j.horas ? "bg-stone-900 text-white" : "text-stone-700 hover:bg-stone-50"}`}>
                {j.label}
              </button>
            ))}
          </div>
          {SEVERITY_ORDER.filter((s) => contagem[s]).map((s) => {
            const m = SEVERITY_META[s];
            const on = sevs.has(s);
            return (
              <button key={s} onClick={() => toggleSev(s)}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded border ${on ? "bg-white border-stone-400 text-stone-900" : "bg-stone-50 border-stone-200 text-stone-400"}`}>
                <span className="w-2.5 h-2.5 rounded-sm" style={{ background: on ? m.fill : "#d6d3d1" }} />
                {m.label} <span className="tabular-nums text-stone-500">{contagem[s]}</span>
              </button>
            );
          })}
          <select value={uf} onChange={(e) => { setUf(e.target.value); setSel(null); }}
            className="px-2 py-1.5 rounded border border-stone-300 bg-white text-stone-700">
            <option value="">Todas as UFs</option>
            {ufs.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
          <span className="text-stone-500 ml-auto">
            {visiveis.length} alertas · {nVigentes} vigentes agora
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] gap-4">
          {/* Mapa */}
          <div className="bg-white rounded-lg border border-stone-300 overflow-hidden h-[560px] relative">
            {status === "error" && (
              <div className="absolute inset-0 z-[500] flex items-center justify-center bg-white/80 text-sm text-stone-600">
                Não foi possível carregar os alertas.
              </div>
            )}
            <MapContainer center={[-14.5, -52]} zoom={4} minZoom={3} className="h-full w-full" scrollWheelZoom>
              {/* Fundo OSM padrão (sem chave), dessaturado em CSS para não competir com os
                  polígonos. Os tiles da CARTO passaram a exigir chave de API (out/2026). */}
              <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                maxZoom={19}
                className="basemap-suave"
              />
              <GeoJSON
                key={chaveMapa}
                data={noMapa}
                style={estilo}
                onEachFeature={(f, layer) => {
                  layer.bindTooltip(`${sevMeta(f.properties.severity).label} · ${f.properties.event}<br/>${fmtBRT(f.properties.sent_utc)} · ${f.properties.sender_name}`, { sticky: true });
                  layer.on("click", () => {
                    setSel(f);
                    listaRef.current?.querySelector(`[data-id="${CSS.escape(f.id)}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
                  });
                }}
              />
              <FitTo bbox={sel?.properties.bbox} />
            </MapContainer>
          </div>

          {/* Lista / detalhe */}
          <div className="flex flex-col gap-3 min-h-0">
            {sel && <Detalhe f={sel} onClose={() => setSel(null)} agora={agora} />}
            <div ref={listaRef} className="bg-white rounded-lg border border-stone-300 overflow-y-auto" style={{ maxHeight: sel ? 260 : 560 }}>
              {status === "loading" && <p className="p-4 text-sm text-stone-500">Carregando…</p>}
              {status === "ok" && visiveis.length === 0 && (
                <p className="p-4 text-sm text-stone-500">Nenhum alerta nesta janela com os filtros atuais.</p>
              )}
              {visiveis.map((f) => {
                const p = f.properties;
                const v = vigencia(p, agora);
                return (
                  <button key={f.id} data-id={f.id} onClick={() => setSel(f)}
                    className={`w-full text-left px-3 py-2 border-b border-stone-100 hover:bg-stone-50 ${sel?.id === f.id ? "bg-stone-100" : ""}`}>
                    <div className="flex items-center gap-2 text-[11px] text-stone-500 mb-0.5">
                      <SeverityBadge severity={p.severity} />
                      <span>{fmtBRT(p.sent_utc)}</span>
                      <span className={v === "vigente" ? "text-emerald-700" : ""}>{v}</span>
                      {!f.geometry && <span className="text-amber-700 inline-flex items-center gap-0.5"><MapPin size={10} />sem polígono</span>}
                      <span className="ml-auto">{(p.ufs ?? []).join(" ")}</span>
                    </div>
                    <div className="text-xs text-stone-900 font-medium truncate">{p.event} · {p.sender_name}</div>
                    <div className="text-xs text-stone-600 line-clamp-2">{p.description}</div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="mt-6 bg-stone-50 border border-stone-200 rounded-lg p-4 text-xs text-stone-600 flex items-start gap-3">
          <Info size={14} className="mt-0.5 flex-shrink-0" />
          <div className="space-y-1">
            <p>
              <strong>Fonte:</strong> feed público da IDAP (Interface de Divulgação de Alertas Públicos, MIDR/SEDEC), padrão CAP 1.2.
              Cada registro comprova que o alerta foi <strong>cadastrado e publicado</strong>; não comprova que chegou a um aparelho.
            </p>
            <p>
              O feed só mantém algumas horas de alertas (≈12 h observadas). Este painel mostra o que o coletor arquivou;
              lacunas na numeração indicam alertas que podem ter saído do feed antes da coleta.
              Polígonos simplificados para exibição (tolerância ≥ 300 m); a geometria original fica no arquivo bruto.
              Contorno tracejado: alerta já encerrado.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
