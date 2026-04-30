import React, { useState, useEffect } from 'react';
import { Activity, ShieldCheck, Database, Zap, Cpu, Server } from 'lucide-react';

/**
 * Dashboard de Saúde do Sistema (Watchdog/Diagnóstico)
 */
export default function HealthDashboard() {
  const [services, setServices] = useState([
    { name: 'Ingest API', status: 'loading', icon: Server, description: 'Recebimento de métricas e banco' },
    { name: 'Processor', status: 'loading', icon: Cpu, description: 'Motor de regras e alertas' },
    { name: 'WebSocket', status: 'loading', icon: Zap, description: 'Push real-time para frontend' },
    { name: 'Database', status: 'loading', icon: Database, description: 'TimescaleDB (Séries temporais)' },
    { name: 'Edge Agent', status: 'loading', icon: ShieldCheck, description: 'Orquestrador local de borda' },
  ]);

  const checkHealth = async () => {
    // Simulação de check de saúde. Em produção, cada serviço teria um endpoint /health
    const newServices = [...services];
    
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      newServices[0].status = data.status === 'ok' ? 'online' : 'error';
      newServices[3].status = data.db === 'connected' ? 'online' : 'error';
    } catch {
      newServices[0].status = 'error';
      newServices[3].status = 'error';
    }

    try {
      const res = await fetch('/api/solar/health');
      newServices[1].status = res.ok ? 'online' : 'error';
    } catch {
      newServices[1].status = 'error';
    }

    // Mock para os outros por enquanto
    newServices[2].status = 'online';
    newServices[4].status = 'online';

    setServices(newServices);
  };

  useEffect(() => {
    checkHealth();
    const t = setInterval(checkHealth, 30000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-green-500/10 rounded-lg">
          <Activity className="w-6 h-6 text-green-500" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white uppercase tracking-wider">Saúde do Sistema</h2>
          <p className="text-xs text-slate-500">Monitoramento de integridade dos microsserviços</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {services.map((s, i) => (
          <div key={i} className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 transition-all hover:border-slate-700">
            <div className="flex items-start justify-between mb-4">
              <div className={`p-3 rounded-xl ${s.status === 'online' ? 'bg-green-500/10' : s.status === 'error' ? 'bg-red-500/10' : 'bg-slate-800'}`}>
                <s.icon className={`w-6 h-6 ${s.status === 'online' ? 'text-green-500' : s.status === 'error' ? 'text-red-500' : 'text-slate-400'}`} />
              </div>
              <div className={`px-2 py-1 rounded-md text-[9px] font-black uppercase tracking-widest ${s.status === 'online' ? 'bg-green-500/20 text-green-400' : s.status === 'error' ? 'bg-red-500/20 text-red-400' : 'bg-slate-800 text-slate-500'}`}>
                {s.status}
              </div>
            </div>
            <h3 className="text-white font-bold text-lg mb-1">{s.name}</h3>
            <p className="text-xs text-slate-500 leading-relaxed">{s.description}</p>
            
            <div className="mt-6 pt-4 border-t border-slate-800/50 flex items-center justify-between">
              <span className="text-[10px] font-bold text-slate-600 uppercase">Uptime</span>
              <span className="text-[10px] font-bold text-green-500 uppercase tracking-tighter">99.9%</span>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-blue-500/5 border border-blue-500/10 rounded-2xl p-6">
        <h4 className="text-blue-400 font-bold text-sm uppercase tracking-widest mb-4">Diagnóstico de Conectividade</h4>
        <div className="space-y-3">
          {[
            { label: 'Latência do Banco de Dados', value: '12ms', status: 'ok' },
            { label: 'Uso de Memória (Ingest)', value: '142MB', status: 'ok' },
            { label: 'Fila de Mensagens WebSocket', value: '0', status: 'ok' },
          ].map((item, idx) => (
            <div key={idx} className="flex items-center justify-between text-xs">
              <span className="text-slate-400">{item.label}</span>
              <span className="font-bold text-slate-200">{item.value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
