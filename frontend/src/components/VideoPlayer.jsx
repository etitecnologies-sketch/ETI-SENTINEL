import { useState, useEffect, useRef } from 'react';

/**
 * Componente para exibição de vídeo RTSP via HLS
 * @param {Object} props
 * @param {string} props.url - URL do stream (WebRTC ou HLS)
 * @param {string} props.name - Nome da câmera
 * @param {boolean} props.isWebRTC - Se é um stream WebRTC
 */
export default function VideoPlayer({ url, name, isWebRTC }) {
  const videoRef = useRef(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!url) return;
    
    setLoading(true);
    setError(false);

    if (isWebRTC) {
        // Para WebRTC, o MediaMTX fornece uma página/stream que pode ser carregada via iframe 
        // ou via player especializado. Para simplificar e garantir funcionamento,
        // vamos usar o iframe do próprio MediaMTX que já resolve o handshake WebRTC.
        return;
    }

    // Fallback HLS
    if (videoRef.current && videoRef.current.canPlayType('application/vnd.apple.mpegurl')) {
      videoRef.current.src = url;
    } 
    // Caso contrário, poderíamos usar hls.js (mas vamos assumir suporte ou fallback simples por enquanto)
    else {
      // Nota: Em um cenário real, usaríamos a biblioteca hls.js aqui
      videoRef.current.src = url;
    }
  }, [url]);

  return (
    <div className="relative bg-slate-900 rounded-lg overflow-hidden aspect-video border border-slate-800 group">
      {isWebRTC ? (
        <iframe
          src={url}
          className="w-full h-full border-none"
          allow="autoplay; fullscreen"
          onLoad={() => setLoading(false)}
        />
      ) : (
        <video
          ref={videoRef}
          autoPlay
          muted
          playsInline
          className="w-full h-full object-cover"
          onCanPlay={() => setLoading(false)}
          onError={() => {
            setError(true);
            setLoading(false);
          }}
        />
      )}
      
      {/* Overlay de Nome */}
      <div className="absolute top-0 left-0 right-0 p-2 bg-gradient-to-b from-black/70 to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
        <span className="text-white text-xs font-bold uppercase tracking-wider">{name || 'Câmera IP'}</span>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-slate-950 text-slate-500 text-center p-4">
          <svg className="w-12 h-12 mb-2 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
          </svg>
          <span className="text-xs font-semibold uppercase tracking-widest">Sinal Indisponível</span>
          <span className="text-[10px] mt-1 opacity-50">{url}</span>
        </div>
      )}

      {/* Live Badge */}
      <div className="absolute bottom-2 right-2 flex items-center gap-1.5 bg-black/40 backdrop-blur-md px-2 py-1 rounded-md">
        <span className="flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-red-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
        </span>
        <span className="text-[10px] font-bold text-white/90 uppercase tracking-tighter">LIVE</span>
      </div>
    </div>
  );
}
