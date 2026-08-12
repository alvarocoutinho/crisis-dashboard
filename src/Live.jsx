import { Link } from "react-router-dom";
import {
  Radio, AlertTriangle, Info, Beaker, Clock,
  ArrowLeft, Activity, Archive
} from "lucide-react";

/**
 * Live — página de escuta ativa.
 *
 * Estado atual: vazio (nenhum alerta CEMADEN em acompanhamento pelo pipeline).
 * O layout aqui é intencionalmente austero: não desenhar antecipadamente
 * a UI de alerta ativo, para evitar decisões arquiteturais apressadas sobre
 * campos que ainda serão definidos pelo pipeline v2.4 quando alimentar
 * esta rota via Camada 4 (adaptador Python).
 */
export default function Live() {
  return (
    <div className="min-h-screen bg-stone-100 font-sans flex flex-col">
      {/* Header */}
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
              Sistema <strong>complementar</strong> à infraestrutura de alertas do CEMADEN
              (que instrumenta perigo e emissão do alerta). Este painel instrumenta a camada de{" "}
              <strong>reação pública digital observável</strong> após o alerta — não mede
              percepção de risco, não emite veredictos automáticos, não opera em tempo real.
            </span>
          </div>
        </div>
      </header>

      {/* Breadcrumb */}
      <div className="max-w-7xl mx-auto px-6 pt-4 w-full">
        <Link to="/" className="text-xs text-stone-500 hover:text-stone-900 inline-flex items-center gap-1">
          <ArrowLeft size={12} /> Voltar
        </Link>
      </div>

      {/* Main */}
      <main className="flex-1 max-w-7xl mx-auto px-6 py-6 w-full">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded bg-emerald-50 flex items-center justify-center">
            <Radio size={20} className="text-emerald-700" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-stone-900 leading-tight">
              Escuta ativa
            </h2>
            <p className="text-sm text-stone-600">
              Alertas CEMADEN em acompanhamento pelo pipeline v2.4
            </p>
          </div>
        </div>

        {/* Painel de status */}
        <div className="bg-white rounded-lg border border-stone-300 p-6 mb-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="flex items-center gap-1.5 text-xs text-stone-500 mb-1">
                <Activity size={12} /> Alertas em curso
              </div>
              <div className="text-3xl font-semibold text-stone-900">0</div>
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-xs text-stone-500 mb-1">
                <Clock size={12} /> Cadência de polling
              </div>
              <div className="text-3xl font-semibold text-stone-900">4h</div>
            </div>
            <div>
              <div className="flex items-center gap-1.5 text-xs text-stone-500 mb-1">
                <AlertTriangle size={12} /> Fonte
              </div>
              <div className="text-base font-medium text-stone-900 pt-1">Painel de Alertas CEMADEN</div>
            </div>
          </div>
        </div>

        {/* Estado vazio */}
        <div className="bg-white rounded-lg border-2 border-dashed border-stone-300 p-12 text-center">
          <div className="max-w-md mx-auto">
            <div className="w-16 h-16 rounded-full bg-stone-100 flex items-center justify-center mx-auto mb-4">
              <Radio size={28} className="text-stone-400" />
            </div>
            <h3 className="text-base font-semibold text-stone-800 mb-2">
              Nenhum alerta em acompanhamento
            </h3>
            <p className="text-sm text-stone-600 leading-relaxed">
              O pipeline consulta o Painel de Alertas Vigentes do CEMADEN a cada 4 horas.
              Quando um alerta for aberto, aparecerá aqui em até uma janela de polling,
              e a escuta digital iniciará automaticamente.
            </p>
            <div className="mt-6 pt-6 border-t border-stone-200 text-xs text-stone-500 leading-relaxed">
              Enquanto isso, os eventos históricos consolidados estão disponíveis no{" "}
              <Link to="/archive" className="text-stone-900 underline hover:no-underline inline-flex items-center gap-1">
                <Archive size={11} /> Arquivo
              </Link>.
            </div>
          </div>
        </div>

        {/* Nota metodológica */}
        <div className="mt-4 bg-stone-50 border border-stone-200 rounded-lg p-4 text-xs text-stone-600 flex items-start gap-3">
          <Info size={14} className="mt-0.5 flex-shrink-0" />
          <span>
            Quando ativa, esta tela exibirá cada alerta com seus metadados CEMADEN (município,
            nível, tipo, timestamps), o estado da coleta em janelas fixas (+2h, +6h, +12h, +24h,
            +48h, +72h) e a caracterização preliminar da reação pública digital observável.
            A integração com o pipeline <code className="bg-stone-100 px-1 rounded">from_alert_to_action_v2_4.py</code>{" "}
            será feita na Camada 4 do roadmap (adaptador CSV → JSON no schema documentado).
          </span>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-stone-300 bg-stone-50 mt-8">
        <div className="max-w-7xl mx-auto px-6 py-4 text-xs text-stone-500">
          Coordenação: Álvaro Luz Alves Coutinho (NEPAM/PPGA&amp;S/Unicamp), sob supervisão da
          Profa. Leila da Costa Ferreira, no âmbito do CEPID CLIMARES (Eixo 7).
        </div>
      </footer>
    </div>
  );
}
