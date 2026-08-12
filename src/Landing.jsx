import { Link } from "react-router-dom";
import { Archive, Radio, ChevronRight, Beaker, Info } from "lucide-react";
import { getAllEvents } from "./services/eventsRepository";

export default function Landing() {
  const nEvents = getAllEvents().length;
  const totalComments = getAllEvents().reduce((s, e) => s + e.n_comments, 0);

  return (
    <div className="min-h-screen bg-stone-100 font-sans flex flex-col">
      {/* Header */}
      <header className="border-b border-stone-300 bg-white">
        <div className="max-w-6xl mx-auto px-6 py-5 flex items-start justify-between gap-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-md bg-stone-800 text-white flex items-center justify-center text-xs font-semibold">
              ODRD
            </div>
            <div>
              <h1 className="text-xl font-semibold text-stone-900 leading-tight">
                Observatório Digital de Riscos e Desastres
              </h1>
              <p className="text-xs text-stone-600">
                Escuta digital territorializada · reação pública observável a alertas hidrometeorológicos
                · <em>iniciativa em desenvolvimento</em>
              </p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1 text-xs">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-100 text-amber-900 border border-amber-300">
              <Beaker size={12} /> Prova de conceito · v0.1 · TRL 3–4
            </span>
            <span className="text-stone-500 text-right">
              NEPAM/Unicamp · CEPID CLIMARES · parceria CEMADEN
            </span>
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 max-w-6xl mx-auto px-6 py-12 w-full">
        <div className="max-w-3xl mb-10">
          <p className="text-base text-stone-700 leading-relaxed">
            Este observatório desenvolve um protocolo de escuta do discurso público digital em português,
            ancorado à abertura de alertas geo-hidrológicos do CEMADEN. Duas frentes complementares:
            um <strong>arquivo retrospectivo</strong> de eventos consumados e a <strong>escuta ativa</strong>{" "}
            de alertas em acompanhamento.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Card ARQUIVO */}
          <Link
            to="/archive"
            className="group bg-white rounded-lg border border-stone-300 hover:border-stone-900 hover:shadow-md transition-all p-6 flex flex-col"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded bg-stone-100 flex items-center justify-center">
                <Archive size={20} className="text-stone-700" />
              </div>
              <ChevronRight size={18} className="text-stone-400 group-hover:text-stone-900 transition-colors" />
            </div>
            <h2 className="text-lg font-semibold text-stone-900 mb-2">Arquivo</h2>
            <p className="text-sm text-stone-600 leading-relaxed flex-1">
              {nEvents} eventos históricos consolidados ({totalComments.toLocaleString("pt-BR")} comentários).
              Predições BERTimbau v0.1 sob protocolo Leave-One-Event-Out. Pernambuco 2026 é o hold-out
              out-of-fold; os demais 5 eventos são in-sample exploratórios.
            </p>
            <div className="mt-4 pt-4 border-t border-stone-100 text-xs text-stone-500">
              Análise pós-evento · dados retrospectivos · atualização manual
            </div>
          </Link>

          {/* Card LIVE */}
          <Link
            to="/live"
            className="group bg-white rounded-lg border border-stone-300 hover:border-stone-900 hover:shadow-md transition-all p-6 flex flex-col"
          >
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded bg-emerald-50 flex items-center justify-center relative">
                <Radio size={20} className="text-emerald-700" />
              </div>
              <ChevronRight size={18} className="text-stone-400 group-hover:text-stone-900 transition-colors" />
            </div>
            <h2 className="text-lg font-semibold text-stone-900 mb-2">Live</h2>
            <p className="text-sm text-stone-600 leading-relaxed flex-1">
              Alertas CEMADEN em acompanhamento pelo pipeline de escuta. Coleta prospectiva iniciada
              a partir da abertura do alerta, com atualização em janelas fixas (+2h, +6h, +12h, +24h,
              +48h, +72h).
            </p>
            <div className="mt-4 pt-4 border-t border-stone-100 text-xs text-stone-500">
              Escuta ativa · polling 4h · nenhum alerta em curso no momento
            </div>
          </Link>
        </div>

        {/* Aviso institucional */}
        <div className="mt-10 bg-stone-50 border border-stone-200 rounded-lg p-4 text-xs text-stone-600 flex items-start gap-3 max-w-3xl">
          <Info size={14} className="mt-0.5 flex-shrink-0" />
          <span>
            Sistema <strong>complementar</strong> à infraestrutura de alertas do CEMADEN. Não emite
            alertas, não emite veredictos automáticos, não substitui canal de emergência ou de
            atendimento. Anotação humana pendente (Experimento 5); classificações vigentes constituem
            hipóteses geradoras, sujeitas a validação.
          </span>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-stone-300 bg-stone-50">
        <div className="max-w-6xl mx-auto px-6 py-4 text-xs text-stone-500">
          Coordenação: Álvaro Luz Alves Coutinho (NEPAM/PPGA&amp;S/Unicamp), sob supervisão da
          Profa. Leila da Costa Ferreira, no âmbito do CEPID CLIMARES (Eixo 7).
        </div>
      </footer>
    </div>
  );
}
