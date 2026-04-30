import React, { useState, useEffect, useCallback } from 'react';
import VideoPlayer from './VideoPlayer';
import { Camera, LayoutGrid, Maximize2, RefreshCw } from 'lucide-react';

/**
 * Grid de Câmeras em Tempo Real
 */
export default function VideoGrid() {
  const [streams, setStreams] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cols, setCols] = useState(2);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const apiBase = import.meta.env.VITE_API_URL || '';
      const response = await fetch(`${apiBase}/collector/rtsp-config`);
      const data = await response.json();

      const allStreams = [];
      data.forEach(device => {
        const streams = device.streams || [];
        streams.forEach(s => {
          if (s.enabled) {
            const sid = `${device.device_id}_ch${s.channel}`;
            allStreams.push({
              ...s,
              deviceName: device.name,
              webrtcUrl: `http://localhost:8889/${sid}`,
              hlsUrl: `http://localhost:8888/${sid}/index.m3u8`
            });
          }
        });
      });
      setStreams(allStreams);
    } catch (e) {
      console.error("Erro ao carregar streams:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-lg">
            <Camera className="w-6 h-6 text-blue-500" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white uppercase tracking-wider">Mosaico de Câmeras</h2>
            <p className="text-xs text-slate-500">Visualização em tempo real via HLS</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="flex bg-slate-900 rounded-lg p-1 border border-slate-800">
            {[1, 2, 3].map(n => (
              <button
                key={n}
                onClick={() => setCols(n)}
                className={`p-1.5 rounded-md transition-all ${cols === n ? 'bg-blue-600 text-white' : 'text-slate-500 hover:text-slate-300'}`}
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
            ))}
          </div>
          <button 
            onClick={load}
            className="p-2 bg-slate-900 border border-slate-800 rounded-lg text-slate-400 hover:text-white transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {streams.length === 0 && !loading ? (
        <div className="flex flex-col items-center justify-center py-20 bg-slate-900/30 border border-dashed border-slate-800 rounded-2xl">
          <Camera className="w-12 h-12 text-slate-700 mb-4" />
          <h3 className="text-slate-400 font-bold uppercase tracking-widest">Nenhuma câmera configurada</h3>
          <p className="text-xs text-slate-600 mt-2">Habilite o monitoramento RTSP nos dispositivos para ver o mosaico.</p>
        </div>
      ) : (
        <div className={`grid gap-4 grid-cols-1 ${cols === 2 ? 'md:grid-cols-2' : cols === 3 ? 'md:grid-cols-2 lg:grid-cols-3' : ''}`}>
          {streams.map((stream, idx) => (
            <VideoPlayer 
              key={`${stream.deviceName}-${idx}`}
              url={stream.webrtcUrl || stream.hlsUrl}
              name={`${stream.deviceName} - ${stream.name}`}
              isWebRTC={!!stream.webrtcUrl}
            />
          ))}
        </div>
      )}

      {/* Footer Info */}
      <div className="flex items-center gap-4 py-4 px-6 bg-blue-500/5 border border-blue-500/10 rounded-xl">
        <div className="flex h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
        <span className="text-[10px] font-bold text-blue-400 uppercase tracking-widest">
          Processamento Local: {streams.length} streams ativos
        </span>
      </div>
    </div>
  );
}
