import React from 'react';
import { Sun, Zap, Battery, ArrowUpRight, ArrowDownRight, Activity } from 'lucide-react';
import MetricCard from './MetricCard';

/**
 * Dashboard Solar especializado
 */
export default function SolarDashboard({ data = {} }) {
  const {
    power_w = 0,
    energy_today_kwh = 0,
    energy_month_kwh = 0,
    energy_total_kwh = 0,
    voltage_pv = 0,
    voltage_ac = 0,
    current_ac = 0,
    temperature_c = 0,
    status = 'active'
  } = data;

  const getStatusColor = (s) => {
    switch(s) {
      case 'active': return '#22c55e';
      case 'warning': return '#f59e0b';
      case 'fault': return '#ef4444';
      default: return '#64748b';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-yellow-500/10 rounded-lg">
            <Sun className="w-6 h-6 text-yellow-500" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white uppercase tracking-wider">Monitoramento Solar</h2>
            <p className="text-xs text-slate-500">Dados em tempo real da usina fotovoltaica</p>
          </div>
        </div>
        <div className="flex items-center gap-2 px-3 py-1 bg-slate-900 border border-slate-800 rounded-full">
          <div className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: getStatusColor(status) }} />
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{status === 'active' ? 'Operação Normal' : status}</span>
        </div>
      </div>

      {/* Grid Principal */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard 
          title="Potência Atual" 
          value={`${power_w} W`} 
          icon={<Zap className="w-4 h-4" />} 
          color="#3b9eff"
          trend="+5.2%"
        />
        <MetricCard 
          title="Geração Hoje" 
          value={`${energy_today_kwh} kWh`} 
          icon={<Sun className="w-4 h-4" />} 
          color="#eab308"
        />
        <MetricCard 
          title="Geração Mês" 
          value={`${energy_month_kwh} kWh`} 
          icon={<Activity className="w-4 h-4" />} 
          color="#a78bfa"
        />
        <MetricCard 
          title="Temperatura" 
          value={`${temperature_c} °C`} 
          icon={<Activity className="w-4 h-4" />} 
          color="#f43f5e"
        />
      </div>

      {/* Grid Detalhado */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Gauge de Potência (Simulado via CSS) */}
        <div className="lg:col-span-1 bg-slate-900/50 border border-slate-800 rounded-2xl p-6 flex flex-col items-center justify-center relative overflow-hidden">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-8">Fluxo de Energia</div>
          
          <div className="relative w-48 h-48">
            <svg className="w-full h-full transform -rotate-90">
              <circle
                cx="96"
                cy="96"
                r="88"
                stroke="currentColor"
                strokeWidth="12"
                fill="transparent"
                className="text-slate-800"
              />
              <circle
                cx="96"
                cy="96"
                r="88"
                stroke="currentColor"
                strokeWidth="12"
                fill="transparent"
                strokeDasharray={552}
                strokeDashoffset={552 - (552 * Math.min(power_w / 5000, 1))}
                className="text-blue-500 transition-all duration-1000 ease-out"
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-black text-white">{power_w}</span>
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-tighter">Watts</span>
            </div>
          </div>

          <div className="mt-8 grid grid-cols-2 gap-8 w-full">
            <div className="flex flex-col items-center">
              <span className="text-[10px] font-bold text-slate-500 uppercase mb-1">Tensão PV</span>
              <span className="text-lg font-bold text-white">{voltage_pv}V</span>
            </div>
            <div className="flex flex-col items-center">
              <span className="text-[10px] font-bold text-slate-500 uppercase mb-1">Tensão AC</span>
              <span className="text-lg font-bold text-white">{voltage_ac}V</span>
            </div>
          </div>
        </div>

        {/* Info adicional */}
        <div className="lg:col-span-2 bg-slate-900/50 border border-slate-800 rounded-2xl p-6">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-6">Histórico e Eficiência</div>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-slate-950/50 rounded-xl border border-slate-800/50">
              <div className="flex items-center gap-4">
                <div className="p-2 bg-green-500/10 rounded-lg"><ArrowUpRight className="w-5 h-5 text-green-500" /></div>
                <div>
                  <div className="text-xs font-bold text-slate-400 uppercase">Economia Total Estimada</div>
                  <div className="text-xl font-black text-white">R$ {(energy_total_kwh * 0.85).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[10px] font-bold text-slate-500 uppercase">Tarifa Ref.</div>
                <div className="text-sm font-bold text-slate-300">R$ 0,85/kWh</div>
              </div>
            </div>

            <div className="flex items-center justify-between p-4 bg-slate-950/50 rounded-xl border border-slate-800/50">
              <div className="flex items-center gap-4">
                <div className="p-2 bg-blue-500/10 rounded-lg"><Battery className="w-5 h-5 text-blue-500" /></div>
                <div>
                  <div className="text-xs font-bold text-slate-400 uppercase">Total Gerado Acumulado</div>
                  <div className="text-xl font-black text-white">{energy_total_kwh.toLocaleString('pt-BR')} kWh</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
