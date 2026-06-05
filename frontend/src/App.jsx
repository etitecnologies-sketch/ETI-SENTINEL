import { useState, useEffect, useCallback, useMemo, Component } from 'react';
import { io } from 'socket.io-client';
import {
  LayoutDashboard,
  Users,
  Server,
  Zap,
  Bell,
  ClipboardList,
  Sun,
  RefreshCw,
  LogOut,
  Menu,
  Camera,
  Activity,
  LayoutGrid,
  Workflow,
  Shield,
} from 'lucide-react';
import VideoPlayer from './components/VideoPlayer';
import VideoGrid from './components/VideoGrid';
import SolarDashboard from './components/SolarDashboard';
import HealthDashboard from './components/HealthDashboard';
import MetricCard from './components/MetricCard';
import MetricChart from './components/MetricChart';
import DashboardEti from './pages/DashboardEti';
import TopologyEti from './pages/TopologyEti';

// Error Boundary para evitar tela branca total
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, background: '#070d18', color: '#e2eaf5', height: '100vh', fontFamily: "'Rajdhani','Segoe UI',sans-serif" }}>
          <h1 style={{ color: '#ef4444' }}>❌ Erro Crítico no Frontend</h1>
          <pre style={{ background: '#0b1525', padding: 20, borderRadius: 8, overflow: 'auto', border: '1px solid rgba(59,158,255,0.12)' }}>
            {this.state.error?.toString()}
          </pre>
          <button 
            style={{ padding: '10px 20px', background: '#3b9eff', border: 'none', borderRadius: 8, cursor: 'pointer', marginTop: 20, color: '#fff', fontWeight: 800, letterSpacing: '0.06em' }}
            onClick={() => { localStorage.clear(); window.location.href = '/'; }}
          >
            Limpar Cache e Reiniciar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// Hook para detectar tela mobile
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);
  return isMobile;
}

const sanitizeBaseUrl = (raw) => {
  let s = String(raw || "").trim();
  s = s.replace(/`/g, "").trim();
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    s = s.slice(1, -1).trim();
  }
  if (!s) return s;
  if (s.startsWith("http://") || s.startsWith("https://")) return s.replace(/\/$/, "");
  if (s.includes(".")) return ("https://" + s).replace(/\/$/, "");
  return s.replace(/\/$/, "");
};

const getInitialAPI = () => {
  // 1. Prioridade para override manual via URL (ex: ?api=https://...)
  const urlParams = new URLSearchParams(window.location.search);
  const urlApi = urlParams.get("api");
  if (urlApi && urlApi.length > 5) return sanitizeBaseUrl(urlApi);

  // 2. Verifica se há uma URL salva no localStorage
  const savedApi = localStorage.getItem("ETI_API_URL");
  if (savedApi && savedApi.length > 5) return sanitizeBaseUrl(savedApi);

  // 3. Verifica variável de ambiente do Vite
  const envApi = import.meta.env.VITE_API_URL;
  if (envApi && envApi.length > 5) return sanitizeBaseUrl(envApi);
  
  const h = window.location.hostname;
  
  // 4. Localhost
  if (h === "localhost" || h === "127.0.0.1") return "http://localhost:3000";
  
  // 5. Railway Auto-detect (Melhorado para ser genérico)
  if (h.includes("railway.app")) {
    const parts = h.split(".");
    const subdomain = parts[0];
    // Se o usuário está no frontend-xxx.up.railway.app, tenta achar o ingest-api-xxx.up.railway.app
    if (subdomain.includes("frontend")) {
      return "https://" + subdomain.replace("frontend", "ingest-api") + ".up.railway.app";
    }
    return window.location.origin + "/api";
  }
  
  // 6. Fallback final: Mesma origem
  return sanitizeBaseUrl(window.location.origin);
};

function LogoMark({ size = 52 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 110" fill="none">
      <defs>
        <linearGradient id="sg" x1="0" y1="0" x2="100" y2="110" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#1e3a5f" />
          <stop offset="100%" stopColor="#0a1628" />
        </linearGradient>
        <linearGradient id="bg2" x1="0" y1="0" x2="100" y2="110" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#60c8ff" />
          <stop offset="50%" stopColor="#3b9eff" />
          <stop offset="100%" stopColor="#0069cc" />
        </linearGradient>
        <linearGradient id="eg" x1="30" y1="40" x2="70" y2="70" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#60c8ff" />
          <stop offset="100%" stopColor="#1a7fff" />
        </linearGradient>
        <filter id="gf">
          <feGaussianBlur stdDeviation="2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <path d="M50 4 L90 20 L90 58 Q90 88 50 106 Q10 88 10 58 L10 20 Z" fill="url(#sg)" />
      <path
        d="M50 4 L90 20 L90 58 Q90 88 50 106 Q10 88 10 58 L10 20 Z"
        fill="none"
        stroke="url(#bg2)"
        strokeWidth="3"
        filter="url(#gf)"
      />
      <line x1="50" y1="10" x2="50" y2="100" stroke="#3b9eff" strokeWidth="0.8" opacity="0.5" />
      <circle cx="65" cy="30" r="1.5" fill="#00c9a7" opacity="0.8" />
      <circle cx="72" cy="38" r="1.5" fill="#00c9a7" opacity="0.8" />
      <circle cx="68" cy="46" r="1.5" fill="#00c9a7" opacity="0.6" />
      <line x1="65" y1="30" x2="72" y2="38" stroke="#00c9a7" strokeWidth="0.8" opacity="0.5" />
      <line x1="72" y1="38" x2="68" y2="46" stroke="#00c9a7" strokeWidth="0.8" opacity="0.5" />
      <ellipse cx="50" cy="57" rx="22" ry="13" fill="none" stroke="url(#eg)" strokeWidth="2" filter="url(#gf)" />
      <path d="M28 57 Q50 38 72 57 Q50 76 28 57 Z" fill="#0d2040" opacity="0.7" />
      <circle cx="50" cy="57" r="9" fill="none" stroke="#3b9eff" strokeWidth="1.5" />
      <circle cx="50" cy="57" r="6" fill="url(#eg)" opacity="0.9" />
      <circle cx="50" cy="57" r="3.5" fill="#0a1628" />
      <circle cx="48" cy="55" r="1.2" fill="#fff" opacity="0.8" />
    </svg>
  );
}

function PulsingDot({ color }) {
  return (
    <span style={{ position: 'relative', display: 'inline-flex', width: 10, height: 10, flexShrink: 0 }}>
      <span style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: color, opacity: 0.4, animation: 'eti-ping 1.8s ease infinite' }} />
      <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, display: 'inline-block' }} />
    </span>
  );
}

function StatusBadge({ status }) {
  const m = {
    ok: { bg: 'rgba(0,201,167,.1)', text: '#00c9a7', border: 'rgba(0,201,167,.3)', label: 'Online' },
    warning: { bg: 'rgba(245,158,11,.1)', text: '#f59e0b', border: 'rgba(245,158,11,.3)', label: 'Atenção' },
    critical: { bg: 'rgba(239,68,68,.1)', text: '#ef4444', border: 'rgba(239,68,68,.3)', label: 'Crítico' },
  };
  const s = m[status] || m.ok;
  return (
    <span
      style={{
        background: s.bg,
        color: s.text,
        border: `1px solid ${s.border}`,
        fontSize: 11,
        fontWeight: 700,
        padding: '3px 10px',
        borderRadius: 999,
        letterSpacing: '0.04em',
        whiteSpace: 'nowrap',
      }}
    >
      {s.label}
    </span>
  );
}

function MiniBar({ value, color }) {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const c = v > 85 ? '#ef4444' : v > 60 ? '#f59e0b' : color;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 120 }}>
      <div style={{ flex: 1, height: 5, background: 'rgba(255,255,255,0.06)', borderRadius: 99, overflow: 'hidden' }}>
        <div style={{ width: `${v}%`, height: '100%', background: c, borderRadius: 99, boxShadow: `0 0 6px ${c}80` }} />
      </div>
      <span style={{ fontSize: 11, color: '#4a7fa8', width: 34, textAlign: 'right' }}>{v}%</span>
    </div>
  );
}

function timeAgoPtBR(date) {
  const d = date instanceof Date ? date : new Date(date);
  const ms = Date.now() - d.getTime();
  if (!Number.isFinite(ms)) return '—';
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s atrás`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min atrás`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h atrás`;
  const days = Math.floor(h / 24);
  return `${days}d atrás`;
}

const API = sanitizeBaseUrl(getInitialAPI());

console.log("🚀 DEBUG API URL:", `|${API}|`); // O pipe | ajuda a ver se tem espaço sobrando

const getToken = () => localStorage.getItem("token");
const setToken = (t) => localStorage.setItem("token", t);
const removeToken = () => localStorage.removeItem("token");

async function api(path, opts = {}) {
  const token = getToken();

  try {
    const base = API;
    const url = `${base}${path}`;
    console.log(`📡 Chamando API: ${url}`);
    
    const res = await fetch(url, {
      ...opts,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(opts.headers || {}),
      },
    });

    if (res.status === 401) {
      removeToken();
      // Em vez de redirecionar para uma URL física /login, vamos recarregar a página
      // O App.jsx ao recarregar verá que não tem token e mostrará a AuthPage
      window.location.href = "/"; 
      return;
    }

    const raw = await res.text();
    let data;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      data = { error: raw || `HTTP ${res.status}` };
    }

    if (!res.ok) {
      console.error(`API Error [${res.status}] ${path}:`, data);
      throw data || { error: `HTTP ${res.status}` };
    }
    return data;
  } catch (err) {
    console.error(`Fetch Error ${path}:`, err);
    if (err?.name === "TypeError" && String(err?.message || "").includes("Failed to fetch")) {
      throw {
        error: `Failed to fetch. Verifique se a API está acessível em ${API} e se VITE_API_URL/ETI_API_URL não tem aspas/crases.`,
      };
    }
    throw err;
  }
}

const DEVICE_TYPES = [
  { value: "server",      label: "Servidor",    icon: "🖥️" },
  { value: "camera",      label: "Câmera IP",   icon: "📷" },
  { value: "router",      label: "Roteador",    icon: "🌐" },
  { value: "switch",      label: "Switch",      icon: "🔀" },
  { value: "routerboard", label: "RouterBoard", icon: "📡" },
  { value: "unifi",       label: "ETI SENTINEL", icon: "📶" },
  { value: "firewall",    label: "Firewall",    icon: "🛡️" },
  { value: "printer",     label: "Impressora",  icon: "🖨️" },
  { value: "iot",         label: "IoT",         icon: "💡" },
  { value: "workstation", label: "Workstation", icon: "💻" },
  { value: "dvr",         label: "DVR",         icon: "📹" },
  { value: "nvr",         label: "NVR",         icon: "🎥" },
  { value: "other",       label: "Outro",       icon: "📦" },
];

const EXPRESSIONS = [
  { value: "cpu",          label: "CPU Usage (%)" },
  { value: "memory",       label: "Memória (%)" },
  { value: "disk_percent", label: "Disco (%)" },
  { value: "latency_ms",   label: "Latência (ms)" },
  { value: "load_avg",     label: "Load Average" },
  { value: "temperature",  label: "Temperatura (°C)" },
  { value: "solar",        label: "☀️ Energia Solar", icon: "🔋" },
];

const PLANS = [
  { value: "basic",      label: "Basic",      color: "#64748b" },
  { value: "pro",        label: "Pro",        color: "#3b9eff" },
  { value: "enterprise", label: "Enterprise", color: "#a78bfa" },
];

const deviceIcon  = (t) => DEVICE_TYPES.find((d) => d.value === t)?.icon || "📦";
const deviceLabel = (t) => DEVICE_TYPES.find((d) => d.value === t)?.label || "Outro";
const planColor   = (p) => PLANS.find((x) => x.value === p)?.color || "#64748b";

// ── Styles ────────────────────────────────────────────────────
const S = {
  app: { 
    minHeight: "100vh", 
    background: "#070d18", 
    color: "#e2eaf5", 
    fontFamily: "'Rajdhani','Segoe UI',sans-serif", 
    display: "flex",
    position: "relative"
  },
  sidebar: { 
    width: 248, 
    background: "#0b1525", 
    borderRight: "1px solid rgba(59,158,255,0.1)", 
    display: "flex", 
    flexDirection: "column", 
    padding: 0, 
    flexShrink: 0,
    boxShadow: "10px 0 30px rgba(0,0,0,0.35)"
  },
  logo: { padding: "28px 20px 22px", borderBottom: "1px solid rgba(59,158,255,0.08)", background: "linear-gradient(180deg,rgba(59,158,255,0.05) 0%,transparent 100%)" },
  logoTitle: { 
    fontSize: 18,
    fontWeight: 800,
    color: "#3b9eff",
    letterSpacing: "0.07em",
    lineHeight: 1.1,
    textTransform: "uppercase",
    fontFamily: "'Exo 2',sans-serif",
    textShadow: "none"
  },
  logoSub: { fontSize: 9, color: "#2a5070", fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase", marginTop: 4 },
  navSection: { fontSize: 9, color: "#1e3a5a", fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", padding: "0 10px", margin: "18px 0 8px" },
  navItem: (a) => ({ 
    display: "flex",
    alignItems: "center",
    gap: 10,
    width: "100%",
    padding: "10px 12px",
    borderRadius: 8,
    border: a ? "1px solid rgba(59,158,255,0.25)" : "1px solid transparent",
    background: a ? "rgba(59,158,255,0.09)" : "transparent",
    color: a ? "#3b9eff" : "#3a5c7a",
    fontWeight: a ? 700 : 500,
    fontSize: 14,
    fontFamily: "'Rajdhani',sans-serif",
    letterSpacing: "0.04em",
    marginBottom: 2,
    textAlign: "left",
    position: "relative",
    boxShadow: "none",
    cursor: "pointer",
    userSelect: "none",
    transition: "background 0.15s ease, border-color 0.15s ease, color 0.15s ease"
  }),
  main: { flex: 1, overflow: "auto", padding: "32px 32px", background: "#070d18" },
  pageTitle: { 
    fontSize: 28, 
    fontWeight: 700, 
    color: "#fff", 
    marginBottom: 6, 
    letterSpacing: 1,
    textTransform: "uppercase",
    textShadow: "none"
  },
  pageSub: { fontSize: 12, color: "#64748b", marginBottom: 30, letterSpacing: 0.5 },
  grid: (cols) => ({ 
    display: "grid", 
    gridTemplateColumns: window.innerWidth < 768 ? "1fr" : `repeat(${cols}, 1fr)`, 
    gap: 20, 
    marginBottom: 20 
  }),
  card: { background: "#0d1929", border: "1px solid rgba(59,158,255,0.1)", borderRadius: 12, padding: 22 },
  statCard: (c) => ({ 
    background: "#0d1929",
    border: `1px solid ${c}20`, 
    borderRadius: 16, 
    padding: 24,
    boxShadow: "none",
    transition: "transform 0.2s ease"
  }),
  statVal: (c) => ({ 
    fontSize: 36, 
    fontWeight: 800, 
    color: c, 
    lineHeight: 1,
    textShadow: "none"
  }),
  statLabel: { fontSize: 11, color: "#64748b", marginTop: 8, textTransform: "uppercase", letterSpacing: 1.5, fontWeight: 600 },
  badge: (c) => ({ 
    display: "inline-flex", 
    alignItems: "center", 
    gap: 4, 
    padding: "4px 10px", 
    borderRadius: 6, 
    fontSize: 10, 
    fontWeight: 700, 
    background: `${c}15`, 
    color: c, 
    border: `1px solid ${c}40`,
    textTransform: "uppercase",
    letterSpacing: 0.5,
    boxShadow: "none"
  }),
  btn: (v = "primary") => ({ 
    padding: "10px 20px", 
    borderRadius: 8, 
    border: v === "ghost" ? "1px solid rgba(59, 158, 255, 0.18)" : "1px solid transparent", 
    cursor: "pointer", 
    fontSize: 12, 
    fontWeight: 700, 
    fontFamily: "inherit", 
    background: v === "primary" ? "#3b9eff" : v === "danger" ? "#ef4444" : v === "purple" ? "#a78bfa" : "rgba(59, 158, 255, 0.08)", 
    color: v === "ghost" ? "#3b9eff" : "#fff", 
    transition: "all 0.2s ease",
    textTransform: "uppercase",
    letterSpacing: 1,
    boxShadow: "none"
  }),
  btnSm: (v = "ghost") => ({ 
    padding: "6px 14px", 
    borderRadius: 6, 
    border: "1px solid rgba(59, 158, 255, 0.18)", 
    cursor: "pointer", 
    fontSize: 10, 
    fontWeight: 600, 
    fontFamily: "inherit", 
    background: v === "danger" ? "rgba(239, 68, 68, 0.12)" : "rgba(59, 158, 255, 0.08)", 
    color: v === "danger" ? "#ef4444" : "#3b9eff",
    transition: "all 0.2s ease",
    textTransform: "uppercase",
    letterSpacing: 0.5
  }),
  input: { 
    width: "100%", 
    background: "#0b1525", 
    border: "1px solid rgba(59, 158, 255, 0.18)", 
    borderRadius: 8, 
    padding: "12px 16px", 
    color: "#e2eaf5", 
    fontSize: 13, 
    fontFamily: "inherit", 
    boxSizing: "border-box", 
    outline: "none",
    transition: "border-color 0.2s ease"
  },
  select: { 
    width: "100%", 
    background: "#0b1525", 
    border: "1px solid rgba(59, 158, 255, 0.18)", 
    borderRadius: 8, 
    padding: "12px 16px", 
    color: "#e2eaf5", 
    fontSize: 13, 
    fontFamily: "inherit", 
    boxSizing: "border-box", 
    outline: "none",
    transition: "border-color 0.2s ease"
  },
  label: { fontSize: 11, color: "#64748b", marginBottom: 6, display: "block", textTransform: "uppercase", letterSpacing: 1, fontWeight: 700 },
  fg: { marginBottom: 20 },
  table: { width: "100%", borderCollapse: "separate", borderSpacing: "0 8px", fontSize: 13 },
  th: { padding: "12px 16px", textAlign: "left", color: "#1e3a5a", fontSize: 10, textTransform: "uppercase", letterSpacing: 1.5, fontWeight: 700, borderBottom: "1px solid rgba(59,158,255,0.08)" },
  td: { padding: "16px", background: "#0d1929", borderTop: "1px solid rgba(59,158,255,0.06)", borderBottom: "1px solid rgba(59,158,255,0.06)", color: "#b8cfe8" },
  modal: { position: "fixed", inset: 0, background: "rgba(7,13,24,0.72)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 },
  modalBox: { 
    background: "#0b1525", 
    border: "1px solid rgba(59,158,255,0.18)", 
    borderRadius: 20, 
    padding: window.innerWidth < 768 ? 20 : 32, 
    width: "95%",
    maxWidth: 600, 
    maxHeight: "90vh", 
    overflowY: "auto",
    boxShadow: "0 20px 60px rgba(0,0,0,0.55)"
  },
  modalTitle: { fontSize: 20, fontWeight: 800, color: "#fff", marginBottom: 24, textTransform: "uppercase", letterSpacing: 1, display: "flex", alignItems: "center", gap: 10 },
  sectionTitle: { fontSize: 10, fontWeight: 800, color: "#3b9eff", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.14em" },
  divider: { borderTop: "1px solid rgba(59,158,255,0.08)", margin: "24px 0" },
  tag: { display: "inline-flex", alignItems: "center", gap: 6, background: "rgba(59,158,255,0.07)", color: "#3b9eff", border: "1px solid rgba(59,158,255,0.18)", borderRadius: 8, padding: "4px 10px", fontSize: 10, fontWeight: 700, marginRight: 6, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.08em" },
  eventCard: (severity) => ({
    padding: "16px 20px",
    borderRadius: 14,
    background: severity === "critical" ? "rgba(239, 68, 68, 0.08)" : "rgba(15, 23, 42, 0.5)",
    border: `1px solid ${severity === "critical" ? "rgba(239, 68, 68, 0.25)" : "rgba(59,158,255,0.10)"}`,
    marginBottom: 12,
    display: "flex",
    gap: 16,
    alignItems: "center",
    transition: "transform 0.2s ease, box-shadow 0.2s ease",
    boxShadow: "none",
    cursor: "default"
  }),
};

// ── Components ────────────────────────────────────────────────
function Bar({ value, color = "#3b9eff" }) {
  const p = Math.min(value || 0, 100);
  return (
    <div style={{ height: 4, borderRadius: 2, background: "rgba(255,255,255,0.05)", position: "relative", overflow: "hidden", marginTop: 4 }}>
      <div style={{ 
        position: "absolute", 
        left: 0, 
        top: 0, 
        bottom: 0, 
        width: `${p}%`, 
        background: p > 85 ? "#ef4444" : p > 60 ? "#f59e0b" : color, 
        borderRadius: 2, 
        transition: "width 0.5s cubic-bezier(0.4, 0, 0.2, 1)",
        boxShadow: `0 0 8px ${p > 85 ? "#ef4444" : p > 60 ? "#f59e0b" : color}aa`
      }} />
    </div>
  );
}

function TagInput({ value = [], onChange }) {
  const [input, setInput] = useState("");
  const add = (e) => {
    if ((e.key === "Enter" || e.key === ",") && input.trim()) {
      e.preventDefault();
      const tag = input.trim().toLowerCase().replace(/[^a-z0-9-_]/g, "");
      if (tag && !value.includes(tag)) onChange([...value, tag]);
      setInput("");
    }
  };
  return (
    <div>
      <div style={{ marginBottom: 5, display: "flex", flexWrap: "wrap" }}>
        {value.map((t) => (
          <span key={t} style={S.tag}># {t}
            <span style={{ cursor: "pointer" }} onClick={() => onChange(value.filter((x) => x !== t))}>×</span>
          </span>
        ))}
      </div>
      <input style={S.input} placeholder="Tag + Enter" value={input}
        onChange={(e) => setInput(e.target.value)} onKeyDown={add} />
    </div>
  );
}

// ── Login ─────────────────────────────────────────────────────
function AuthPage({ onLogin }) {
  const [step, setStep] = useState(null);
  const [form, setForm] = useState({ username: "", password: "" });
  const [err, setErr] = useState(""); const [loading, setLoading] = useState(false);
  const [showApiInput, setShowApiInput] = useState(false);
  const [showDiag, setShowDiag] = useState(false);
  const [tempApi, setTempApi] = useState(API);
  const [diagStatus, setDiagStatus] = useState("");

  const getDiagInfo = () => ({
    "API Atual": API,
    "VITE_API_URL": import.meta.env.VITE_API_URL || "Não definida",
    "Ambiente": import.meta.env.MODE,
    "Hostname": window.location.hostname,
    "Status Local": diagStatus || "Aguardando teste..."
  });

  const testConnection = async () => {
    setDiagStatus("⏳ Testando...");
    try {
      const start = Date.now();
      const res = await fetch(`${API}/auth/status`, { mode: 'cors' });
      const end = Date.now();
      if (res.ok) {
        setDiagStatus(`✅ OK (${end - start}ms)`);
      } else {
        setDiagStatus(`❌ Erro HTTP: ${res.status}`);
      }
    } catch (e) {
      setDiagStatus(`❌ Falha na rede: ${e.message}`);
    }
  };

  const updateApi = () => {
    if (tempApi && tempApi.length > 5) {
      localStorage.setItem("ETI_API_URL", tempApi);
      window.location.reload();
    }
  };

  useEffect(() => {
    const checkStatus = async () => {
      // 1. Prioridade absoluta para a URL da barra de endereços do navegador (Fallback manual)
      const urlParams = new URLSearchParams(window.location.search);
      const manualApi = urlParams.get("api");
      let finalApi = API;

      if (manualApi) {
        finalApi = manualApi.replace(/["'`\s\n\r]/g, "").trim().replace(/\/$/, "");
        console.log("🛠️ Usando API Manual via URL:", finalApi);
      }

      console.log(`[App] Verificando status da API em: ${finalApi}/auth/status`);
      
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 25000);

        const res = await fetch(`${finalApi}/auth/status`, { 
          signal: controller.signal,
          headers: { "Accept": "application/json" }
        });
        clearTimeout(timeoutId);

        if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
        
        const d = await res.json();
        setStep(d.setupDone ? "login" : "setup");
        setErr(""); 
      } catch (e) {
        console.error("[App] API Connection Error:", e);
        const msg =
          e?.name === "AbortError"
            ? `❌ Timeout ao conectar na API. No Railway isso pode acontecer no primeiro boot (cold start) ou se a API estiver reiniciando. Teste ${finalApi}/health e verifique se a variável DATABASE_URL está configurada.`
            : `❌ Erro de Conexão: ${e.message}. Verifique se o link ${finalApi} está correto.`;
        setErr(msg);
        setStep("login");
      }
    };
    checkStatus();
  }, []);

  const submit = async () => {
    setLoading(true); setErr("");
    try {
      if (step === "setup") {
        await api("/auth/setup", { method: "POST", body: JSON.stringify(form) });
        setStep("login"); return;
      }
      const d = await api("/auth/login", { method: "POST", body: JSON.stringify(form) });
      setToken(d.token);
      onLogin(d.role, d.client_id, d.access_level);
    } catch (e) { setErr(e.error || "Erro"); }
    finally { setLoading(false); }
  };

  if (!step && !err) return <div style={{ ...S.app, alignItems: "center", justifyContent: "center", color: "#3b9eff", fontFamily: 'Rajdhani', fontSize: 20 }}>Carregando...</div>;

  return (
    <div style={{ ...S.app, alignItems: "center", justifyContent: "center" }}>
      <div style={{ 
        ...S.card, 
        width: "90%",
        maxWidth: 380, 
        textAlign: "center", 
        padding: window.innerWidth < 768 ? "30px 20px" : 40,
        border: "1px solid rgba(59,158,255,0.18)",
        boxShadow: "0 20px 60px rgba(0,0,0,0.45)"
      }}>
        <div style={{ fontSize: 42, marginBottom: 16, display: 'flex', justifyContent: 'center' }}>
          <LogoMark size={52} />
        </div>
        <div style={{ ...S.logoTitle, fontSize: 28, marginBottom: 4 }}>ETI SENTINEL</div>
        <div style={{ ...S.logoSub, fontSize: 12, marginBottom: 32 }}>MONITORAMENTO INTELIGENTE</div>
        
        {step ? (
          <>
            <div style={S.fg}>
              <label style={S.label}>Usuário</label>
              <input style={S.input} placeholder="Seu usuário" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </div>
            <div style={S.fg}>
              <label style={S.label}>Senha</label>
              <input style={S.input} type="password" placeholder="Sua senha" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} onKeyDown={(e) => e.key === "Enter" && submit()} />
            </div>
          </>
        ) : (
          <div style={{ padding: '20px 0', color: '#4a6080' }}>
            Aguardando resposta do servidor...
          </div>
        )}
        
        {err && <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 16, fontWeight: 700, background: 'rgba(239,68,68,0.10)', padding: 10, borderRadius: 10, border: '1px solid rgba(239,68,68,0.18)' }}>⚠️ {err}</div>}
        
        {step && (
          <button style={{ ...S.btn("primary"), width: "100%", marginTop: 10, height: 45 }} onClick={submit} disabled={loading}>
            {loading ? "PROCESSANDO..." : step === "setup" ? "CRIAR CONTA MASTER" : "INICIAR SESSÃO"}
          </button>
        )}

        <div style={{ marginTop: 24, fontSize: 11, color: "#4a6080", letterSpacing: 1 }}>
          SISTEMA DE MONITORAMENTO 24/7
        </div>
      </div>
    </div>
  );
}

// ── Client Modal ──────────────────────────────────────────────
const EMPTY_CLIENT = {
  name: "", document: "", email: "", phone: "", address: "",
  city: "", state: "", plan: "basic", status: "active",
  telegram_token: "", telegram_chat_id: "", alert_email: "", notes: "",
  wa_instance: "", wa_token: "", wa_number: "",
};

function ClientModal({ client, onSave, onClose, onProvision }) {
  const [form, setForm] = useState(client ? { ...EMPTY_CLIENT, ...client } : { ...EMPTY_CLIENT });
  const [tab, setTab] = useState("info");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    if (!form.name) return setErr("Nome obrigatório");
    setLoading(true); setErr("");
    try {
      let saved;
      if (client?.id) saved = await api(`/clients/${client.id}`, { method: "PUT", body: JSON.stringify(form) });
      else saved = await api("/clients", { method: "POST", body: JSON.stringify(form) });

      if (saved?.collector_key && typeof onProvision === "function") {
        onProvision({
          client_id: saved.id,
          collector_key: saved.collector_key,
          collector_key_rotated_at: saved.collector_key_rotated_at || null,
        });
      }
      onSave();
    } catch (e) { 
      console.error("Save Client Error:", e);
      setErr(e.error || e.message || "Erro ao salvar cliente no banco de dados"); 
    }
    finally { setLoading(false); }
  };

  const tabs = ["info", "contato", ...(client?.id ? ["edge"] : []), "alertas", "notas"];
  const tabLabel = { info: "📋 Info", contato: "📞 Contato", edge: "🔑 Edge", alertas: "🔔 Alertas", notas: "📝 Notas" };

  return (
    <div style={S.modal} onClick={onClose}>
      <div style={S.modalBox} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalTitle}>{client?.id ? "✏️ Editar Cliente" : "➕ Novo Cliente"}</div>

        <div style={{ display: "flex", gap: 6, marginBottom: 18 }}>
          {tabs.map((t) => (
            <button key={t} style={{ ...S.btn(tab === t ? "primary" : "ghost"), fontSize: 10, padding: "5px 10px" }}
              onClick={() => setTab(t)}>{tabLabel[t]}</button>
          ))}
        </div>

        {tab === "info" && (
          <>
            <div style={S.grid(2)}>
              <div style={S.fg}><label style={S.label}>Nome *</label><input style={S.input} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Empresa ABC Ltda" /></div>
              <div style={S.fg}><label style={S.label}>CNPJ/CPF</label><input style={S.input} value={form.document} onChange={(e) => set("document", e.target.value)} placeholder="00.000.000/0001-00" /></div>
            </div>
            <div style={S.grid(2)}>
              <div style={S.fg}>
                <label style={S.label}>Plano</label>
                <select style={S.select} value={form.plan} onChange={(e) => set("plan", e.target.value)}>
                  {PLANS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <div style={S.fg}>
                <label style={S.label}>Status</label>
                <select style={S.select} value={form.status} onChange={(e) => set("status", e.target.value)}>
                  <option value="active">✅ Ativo</option>
                  <option value="suspended">⏸ Suspenso</option>
                  <option value="cancelled">❌ Cancelado</option>
                </select>
              </div>
            </div>
          </>
        )}

        {tab === "contato" && (
          <>
            <div style={S.grid(2)}>
              <div style={S.fg}><label style={S.label}>Email</label><input style={S.input} value={form.email} onChange={(e) => set("email", e.target.value)} placeholder="contato@empresa.com" /></div>
              <div style={S.fg}><label style={S.label}>Telefone</label><input style={S.input} value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="(65) 99999-9999" /></div>
            </div>
            <div style={S.fg}><label style={S.label}>Endereço</label><input style={S.input} value={form.address} onChange={(e) => set("address", e.target.value)} placeholder="Rua das Flores, 123" /></div>
            <div style={S.grid(2)}>
              <div style={S.fg}><label style={S.label}>Cidade</label><input style={S.input} value={form.city} onChange={(e) => set("city", e.target.value)} placeholder="Paraíso do Tocantins" /></div>
              <div style={S.fg}><label style={S.label}>Estado</label><input style={S.input} value={form.state} onChange={(e) => set("state", e.target.value)} placeholder="TO" /></div>
            </div>
          </>
        )}

        {tab === "edge" && client?.id && (
          <>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, marginBottom: 14, fontSize: 10, color: "#4a6080" }}>
              🔐 A chave `COLLECTOR_KEY` autentica os Edge Agents deste cliente. Ao rotacionar, você precisa atualizar os Edges (Local A/B/C).
            </div>

            <div style={S.grid(2)}>
              <div style={S.fg}>
                <label style={S.label}>CLIENT_ID</label>
                <input style={{ ...S.input, fontFamily: "monospace" }} value={String(client.id)} readOnly />
              </div>
              <div style={S.fg}>
                <label style={S.label}>Status da COLLECTOR_KEY</label>
                <input
                  style={{ ...S.input, fontFamily: "monospace" }}
                  value={client.collector_key_set ? "configurada" : "não configurada"}
                  readOnly
                />
              </div>
            </div>
            <div style={S.fg}>
              <label style={S.label}>Última rotação</label>
              <input
                style={{ ...S.input, fontFamily: "monospace" }}
                value={client.collector_key_rotated_at ? String(client.collector_key_rotated_at) : "—"}
                readOnly
              />
            </div>

            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button
                style={S.btn("primary")}
                onClick={async () => {
                  if (!confirm("Rotacionar a COLLECTOR_KEY deste cliente? Os Edges antigos vão parar até serem atualizados.")) return;
                  const r = await api(`/clients/${client.id}/collector-key/rotate`, { method: "POST" });
                  if (r?.collector_key && typeof onProvision === "function") {
                    onProvision({
                      client_id: client.id,
                      collector_key: r.collector_key,
                      collector_key_rotated_at: r.collector_key_rotated_at || null,
                    });
                  }
                }}
              >
                Gerar/Rotacionar COLLECTOR_KEY
              </button>
            </div>
          </>
        )}

        {tab === "alertas" && (
          <>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, marginBottom: 14, fontSize: 10, color: "#4a6080" }}>
              💡 Configure os canais de alerta para este cliente (Telegram e WhatsApp)
            </div>
            
            <div style={S.sectionTitle}>✈️ Telegram</div>
            <div style={S.grid(2)}>
              <div style={S.fg}><label style={S.label}>Token do Bot</label><input style={S.input} value={form.telegram_token || ""} onChange={(e) => set("telegram_token", e.target.value)} placeholder="1234567890:AAH..." /></div>
              <div style={S.fg}><label style={S.label}>Chat ID</label><input style={S.input} value={form.telegram_chat_id || ""} onChange={(e) => set("telegram_chat_id", e.target.value)} placeholder="123456789" /></div>
            </div>

            <div style={S.divider} />
            <div style={S.sectionTitle}>💬 WhatsApp (Twilio)</div>
            <div style={S.grid(2)}>
              <div style={S.fg}><label style={S.label}>Account SID (opcional)</label><input style={S.input} value={form.wa_instance || ""} onChange={(e) => set("wa_instance", e.target.value)} placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" /></div>
              <div style={S.fg}><label style={S.label}>Auth Token (opcional)</label><input style={S.input} value={form.wa_token || ""} onChange={(e) => set("wa_token", e.target.value)} placeholder="Seu Auth Token" /></div>
            </div>
            <div style={S.fg}><label style={S.label}>Número de Destino (com DDD e DDI)</label><input style={S.input} value={form.wa_number || ""} onChange={(e) => set("wa_number", e.target.value)} placeholder="+5565999999999" /></div>
            <div style={{ fontSize: 9, color: "#3a5070", marginTop: -10, marginBottom: 8 }}>
              Se o Account SID/Auth Token estiverem vazios, o sistema usa as credenciais globais do Twilio.
            </div>

            <div style={S.divider} />
            <div style={S.fg}><label style={S.label}>Email para Alertas</label><input style={S.input} value={form.alert_email || ""} onChange={(e) => set("alert_email", e.target.value)} placeholder="alertas@empresa.com" /></div>
          </>
        )}

        {tab === "notas" && (
          <div style={S.fg}>
            <label style={S.label}>Notas / Observações</label>
            <textarea style={{ ...S.input, minHeight: 100, resize: "vertical" }} value={form.notes || ""} onChange={(e) => set("notes", e.target.value)} placeholder="Informações sobre o cliente, contrato, observações..." />
          </div>
        )}

        {err && <div style={{ color: "#ef4444", fontSize: 11, marginBottom: 10 }}>⚠️ {err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button style={S.btn("ghost")} onClick={onClose}>Cancelar</button>
          <button style={S.btn("primary")} onClick={save} disabled={loading}>{loading ? "..." : "Salvar Cliente"}</button>
        </div>
      </div>
    </div>
  );
}

// ── Clients Page ──────────────────────────────────────────────
function ClientsPage() {
  const [clients, setClients] = useState([]);
  const [modal, setModal] = useState(null);
  const [userModal, setUserModal] = useState(null);
  const [provision, setProvision] = useState(null);
  const [newUser, setNewUser] = useState({ username: "", password: "", access_level: 1 });
  const [userErr, setUserErr] = useState("");
  const [userLoading, setUserLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [hoverId, setHoverId] = useState(null);

  const load = () => api("/clients").then(setClients).catch(() => {});
  useEffect(() => { load(); }, []);

  const del = async (id) => {
    if (!confirm("Remover este cliente e todos os seus devices?")) return;
    await api(`/clients/${id}`, { method: "DELETE" });
    load();
  };

  const createUser = async () => {
    if (!newUser.username || !newUser.password) return;
    setUserLoading(true);
    setUserErr("");
    try {
      await api(`/clients/${userModal}/users`, { method: "POST", body: JSON.stringify(newUser) });
      setUserModal(null);
      setNewUser({ username: "", password: "", access_level: 1 });
    } catch (e) {
      setUserErr(e?.error || e?.message || "Erro ao criar acesso");
    } finally {
      setUserLoading(false);
    }
  };

  const suggestUsername = (client) => {
    const base = String(client?.name || "cliente").toLowerCase();
    const slug = base
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 18);
    const id = client?.id ? String(client.id) : "";
    return (slug ? `${slug}_${id}` : `cliente_${id}`) || "";
  };

  const filtered = clients.filter((c) =>
    (c.name || "").toLowerCase().includes((search || "").toLowerCase()) ||
    (c.city || "").toLowerCase().includes((search || "").toLowerCase())
  );

  const statusColor = { active: "#22c55e", suspended: "#f59e0b", cancelled: "#ef4444" };
  const statusLabel = { active: "● ativo", suspended: "⏸ suspenso", cancelled: "✕ cancelado" };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={S.pageTitle}>🏢 Clientes</div>
          <div style={S.pageSub}>Gerenciar clientes — {clients.length} cadastrado(s)</div>
        </div>
        <button style={{ ...S.btn("primary") }} onClick={() => setModal("new")}>+ Novo Cliente</button>
      </div>

      <div style={{ ...S.card, marginBottom: 24, display: "flex", gap: 10, background: "#0d1929", border: "1px solid rgba(59,158,255,0.08)" }}>
        <input style={{ ...S.input, maxWidth: 300 }} placeholder="🔍 Buscar cliente..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <span style={{ fontSize: 12, color: "#3b9eff", alignSelf: "center", fontWeight: 700 }}>{filtered.length} resultado(s)</span>
      </div>

      <div style={{ ...S.card, overflowX: "auto", padding: 0 }}>
        <table style={{ ...S.table, margin: 0, borderSpacing: 0 }}>
          <thead>
            <tr>{["Cliente", "Plano", "Status", "Devices", "Online", "Offline", "Cidade", "Ações"].map((h) => (
              <th key={h} style={{ ...S.th, padding: "16px 20px" }}>{h}</th>
            ))}</tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr><td colSpan={8} style={{ ...S.td, textAlign: "center", color: "#3a5070", padding: 40 }}>Nenhum cliente cadastrado</td></tr>
            )}
            {filtered.map((c, i) => (
              <tr
                key={c.id}
                onMouseEnter={() => setHoverId(c.id)}
                onMouseLeave={() => setHoverId(null)}
                style={{
                  background: hoverId === c.id
                    ? "rgba(59,158,255,0.06)"
                    : i % 2 === 0
                      ? "transparent"
                      : "rgba(11,21,37,0.35)",
                  transition: "background 0.2s, box-shadow 0.2s",
                  boxShadow: "none",
                }}
              >
                <td style={{ ...S.td, border: "none", padding: "16px 20px" }}>
                  <div style={{ fontWeight: 800, color: "#f1f5f9", fontSize: 14 }}>{c.name}</div>
                  <div style={{ fontSize: 11, color: "#64748b", fontFamily: "monospace", marginTop: 2 }}>{c.document || "—"}</div>
                </td>
                <td style={{ ...S.td, border: "none" }}><span style={S.badge(planColor(c.plan))}>{c.plan}</span></td>
                <td style={{ ...S.td, border: "none" }}><span style={S.badge(statusColor[c.status] || "#64748b")}>{statusLabel[c.status] || c.status}</span></td>
                <td style={{ ...S.td, border: "none", color: "#3b9eff", fontWeight: 800, fontSize: 16 }}>{c.device_count || 0}</td>
                <td style={{ ...S.td, border: "none", color: "#22c55e", fontWeight: 800, fontSize: 16 }}>{c.online_count || 0}</td>
                <td style={{ ...S.td, border: "none", color: c.offline_count > 0 ? "#ef4444" : "#3a5070", fontWeight: 800, fontSize: 16 }}>{c.offline_count || 0}</td>
                <td style={{ ...S.td, border: "none", color: "#94a3b8", fontSize: 12 }}>{c.city || "—"}</td>
                <td style={{ ...S.td, border: "none" }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button style={S.btnSm()} onClick={() => setModal(c)} title="Editar">✏️</button>
                    <button
                      style={S.btnSm()}
                      onClick={() => {
                        setUserErr("");
                        setUserLoading(false);
                        setNewUser({ username: suggestUsername(c), password: "", access_level: 1 });
                        setUserModal(c.id);
                      }}
                      title="Criar usuário"
                    >
                      👤
                    </button>
                    <button style={S.btnSm("danger")} onClick={() => del(c.id)}>🗑️</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(modal === "new" || (modal && modal.id)) && (
        <ClientModal
          client={modal === "new" ? null : modal}
          onSave={() => { load(); setModal(null); }}
          onClose={() => setModal(null)}
          onProvision={(p) => setProvision(p)}
        />
      )}

      {provision && (
        <div style={S.modal} onClick={() => setProvision(null)}>
          <div style={{ ...S.modalBox, width: 520 }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalTitle}>🔑 Chave do Edge (gerada agora)</div>
            <div style={{ fontSize: 11, color: "#93a4bf", marginBottom: 12 }}>
              Esta chave aparece apenas uma vez. Copie e salve com segurança.
            </div>
            <div style={S.fg}>
              <label style={S.label}>Config para o `.env` do Edge</label>
              <textarea
                style={{ ...S.input, minHeight: 140, resize: "vertical", fontFamily: "monospace" }}
                readOnly
                value={
                  `INGEST_API_URL=${API}\n` +
                  `CLIENT_ID=${provision.client_id}\n` +
                  `COLLECTOR_KEY=${provision.collector_key}\n` +
                  `AGENT_ID=LOCAL_A\n`
                }
              />
            </div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button style={S.btn("ghost")} onClick={() => setProvision(null)}>Fechar</button>
              <button
                style={S.btn("primary")}
                onClick={async () => {
                  const txt =
                    `INGEST_API_URL=${API}\n` +
                    `CLIENT_ID=${provision.client_id}\n` +
                    `COLLECTOR_KEY=${provision.collector_key}\n` +
                    `AGENT_ID=LOCAL_A\n`;
                  try {
                    await navigator.clipboard.writeText(txt);
                    alert("Copiado para a área de transferência");
                  } catch {
                    alert("Não foi possível copiar automaticamente. Copie manualmente.");
                  }
                }}
              >
                Copiar
              </button>
            </div>
          </div>
        </div>
      )}

      {userModal && (
        <div style={S.modal} onClick={() => setUserModal(null)}>
          <div style={{ ...S.modalBox, width: 360 }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalTitle}>👤 Criar Acesso do Cliente</div>
            <form autoComplete="off">
              <input style={{ display: "none" }} name="username" autoComplete="username" />
              <input style={{ display: "none" }} type="password" name="password" autoComplete="current-password" />

              <div style={S.fg}>
                <label style={S.label}>Usuário</label>
                <input
                  style={S.input}
                  name="client_username"
                  autoComplete="off"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                  placeholder="cliente_abc"
                />
              </div>
              <div style={S.fg}>
                <label style={S.label}>Senha</label>
                <input
                  style={S.input}
                  name="client_password"
                  autoComplete="new-password"
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                  placeholder="••••••••"
                />
              </div>
            </form>
            <div style={S.fg}>
              <label style={S.label}>Nível de acesso (RBAC)</label>
              <select
                style={S.select}
                value={newUser.access_level}
                onChange={(e) => setNewUser({ ...newUser, access_level: parseInt(e.target.value) || 1 })}
              >
                <option value={1}>Nível 1 — Métricas TI/Solar</option>
                <option value={2}>Nível 2 — Vídeo ao vivo (ONVIF/RTSP)</option>
                <option value={3}>Nível 3 — Gravações/Exportação (futuro)</option>
              </select>
            </div>
            {userErr && <div style={{ color: "#ef4444", fontSize: 11, marginBottom: 10 }}>⚠️ {userErr}</div>}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button style={S.btn("ghost")} onClick={() => setUserModal(null)}>Cancelar</button>
              <button style={S.btn("primary")} onClick={createUser} disabled={userLoading}>{userLoading ? "..." : "Criar Acesso"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Device Modal ──────────────────────────────────────────────
const EMPTY_DEVICE = {
  name: "", description: "", location: "", device_type: "other",
  ip_address: "", tags: [], snmp_community: "public", snmp_version: "2c",
  ssh_user: "", ssh_port: 22, monitor_ping: true, monitor_snmp: false,
  monitor_agent: true, ddns_address: "", monitor_port: 0, notes: "", client_id: null,
  mac_address: "", serial_number: "", ai_enabled: false,
};

function DeviceModal({ device, clients, userRole, userClientId, canVideo, onSave, onClose }) {
  const [form, setForm] = useState(device 
    ? { ...EMPTY_DEVICE, ...device, tags: device.tags || [] } 
    : { ...EMPTY_DEVICE }
  );
  const [onvif, setOnvif] = useState({
    enabled: false,
    host: "",
    port: 80,
    username: "",
    password: "",
    password_set: false,
    passwordTouched: false,
    passwordCleared: false,
    channel_map_text: "{}",
  });
  const [onvifLoaded, setOnvifLoaded] = useState(false);
  const [rtsp, setRtsp] = useState({
    enabled: false,
    username: "",
    password: "",
    password_set: false,
    passwordTouched: false,
    passwordCleared: false,
    streams_text: "[]",
  });
  const [rtspLoaded, setRtspLoaded] = useState(false);
  const [rtspBulk, setRtspBulk] = useState({ open: false, start: 1, end: 32, pattern: "Canal {ch}", pad: 0, overwrite: false });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setOnvifField = (k, v) => setOnvif((o) => ({ ...o, [k]: v }));
  const setRtspField = (k, v) => setRtsp((o) => ({ ...o, [k]: v }));

  const applyRtspBulkNames = () => {
    try {
      const arr = JSON.parse(rtsp.streams_text || "[]");
      if (!Array.isArray(arr)) throw new Error("streams must be an array");
      const start = Math.max(1, parseInt(rtspBulk.start || 1, 10) || 1);
      const end = Math.max(start, parseInt(rtspBulk.end || start, 10) || start);
      const pad = Math.max(0, Math.min(6, parseInt(rtspBulk.pad || 0, 10) || 0));
      const pattern = String(rtspBulk.pattern || "Canal {ch}");
      const overwrite = rtspBulk.overwrite === true;

      const out = arr.map((s) => {
        if (!s || typeof s !== "object" || Array.isArray(s)) return s;
        const ch = parseInt(s.channel, 10);
        if (!Number.isFinite(ch) || ch < start || ch > end) return s;
        const curName = (s.name ?? "");
        if (!overwrite && String(curName).trim()) return s;
        const chStr = pad > 0 ? String(ch).padStart(pad, "0") : String(ch);
        const name = pattern.replaceAll("{ch}", chStr);
        return { ...s, name };
      });

      setRtspField("streams_text", JSON.stringify(out, null, 2));
      setRtspBulk((b) => ({ ...b, open: false }));
    } catch (e) {
      setErr("Streams (JSON) inválido para aplicar nomes em lote");
    }
  };

  useEffect(() => {
    let alive = true;
    if (!canVideo || !device?.id) return;
    api(`/devices/${device.id}/onvif`)
      .then((d) => {
        if (!alive) return;
        setOnvif({
          enabled: !!d.enabled,
          host: d.host || "",
          port: d.port || 80,
          username: d.username || "",
          password: "",
          password_set: !!d.password_set,
          passwordTouched: false,
          passwordCleared: false,
          channel_map_text: JSON.stringify(d.channel_map || {}, null, 2),
        });
        setOnvifLoaded(true);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [device?.id]);

  useEffect(() => {
    let alive = true;
    if (!canVideo || !device?.id) return;
    api(`/devices/${device.id}/rtsp`)
      .then((d) => {
        if (!alive) return;
        setRtsp({
          enabled: !!d.enabled,
          username: d.username || "",
          password: "",
          password_set: !!d.password_set,
          passwordTouched: false,
          passwordCleared: false,
          streams_text: JSON.stringify(d.streams || [], null, 2),
        });
        setRtspLoaded(true);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [device?.id]);

  const save = async () => {
    if (!form.name) return setErr("Nome obrigatório");
    setLoading(true); setErr("");
    
    // Garante que a porta seja um número inteiro
    const payload = {
      ...form,
      monitor_port: parseInt(form.monitor_port) || 0
    };

    try {
      let saved;
      if (device?.id) saved = await api(`/devices/${device.id}`, { method: "PUT", body: JSON.stringify(payload) });
      else saved = await api("/devices", { method: "POST", body: JSON.stringify(payload) });

      const id = device?.id || saved?.id;

      if (!canVideo) {
        onSave();
        return;
      }

      const wantsOnvif =
        !!onvif.enabled ||
        !!(onvif.host || "").trim() ||
        !!(onvif.username || "").trim() ||
        !!onvif.passwordTouched ||
        !!onvif.passwordCleared ||
        (onvif.channel_map_text || "").trim() !== "{}";

      if (id && (onvifLoaded || wantsOnvif)) {
        let channel_map = {};
        try { channel_map = JSON.parse(onvif.channel_map_text || "{}"); } catch { throw { error: "channel_map inválido (JSON)" }; }
        const body = {
          enabled: !!onvif.enabled,
          host: (onvif.host || "").trim(),
          port: parseInt(onvif.port) || 80,
          username: onvif.username || "",
          channel_map,
        };
        if (onvif.passwordCleared) body.password = "";
        else if (onvif.passwordTouched) body.password = onvif.password || "";
        await api(`/devices/${id}/onvif`, { method: "PUT", body: JSON.stringify(body) });
      }

      const wantsRtsp =
        !!rtsp.enabled ||
        !!(rtsp.username || "").trim() ||
        !!rtsp.passwordTouched ||
        !!rtsp.passwordCleared ||
        (rtsp.streams_text || "").trim() !== "[]";

      if (id && (rtspLoaded || wantsRtsp)) {
        let streams = [];
        try { streams = JSON.parse(rtsp.streams_text || "[]"); } catch { throw { error: "streams inválido (JSON)" }; }
        if (streams && typeof streams === "object" && !Array.isArray(streams)) streams = [streams];
        if (!Array.isArray(streams)) streams = [];
        const body = {
          enabled: !!rtsp.enabled,
          username: rtsp.username || "",
          streams,
        };
        if (rtsp.passwordCleared) body.password = "";
        else if (rtsp.passwordTouched) body.password = rtsp.password || "";
        await api(`/devices/${id}/rtsp`, { method: "PUT", body: JSON.stringify(body) });
      }
      onSave();
    } catch (e) { setErr(e?.error || e?.detail || e?.message || "Erro ao salvar dados"); }
    finally { setLoading(false); }
  };

  return (
    <div style={S.modal} onClick={onClose}>
      <div style={S.modalBox} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalTitle}>{device?.id ? "✏️ Editar Device" : "➕ Novo Device"}</div>

        {userRole === "superadmin" && clients && (
          <div style={S.fg}>
            <label style={S.label}>Cliente</label>
            <select style={S.select} value={form.client_id || ""} onChange={(e) => set("client_id", e.target.value ? parseInt(e.target.value) : null)}>
              <option value="">Sem cliente</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        )}

        <div style={S.grid(2)}>
          <div style={S.fg}><label style={S.label}>Nome *</label><input style={S.input} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Camera-Entrada" /></div>
          <div style={S.fg}>
            <label style={S.label}>Tipo</label>
            <select
              style={S.select}
              value={form.device_type}
              onChange={(e) => {
                const v = e.target.value;
                set("device_type", v);
                if (!["camera", "dvr", "nvr"].includes(v)) set("ai_enabled", false);
              }}
            >
              {DEVICE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.icon} {t.label}</option>)}
            </select>
          </div>
        </div>
        <div style={S.grid(2)}>
          <div style={S.fg}><label style={S.label}>Endereço IP / DDNS</label><input style={S.input} value={form.ip_address} onChange={(e) => set("ip_address", e.target.value)} placeholder="192.168.1.100 ou ddns.net" /></div>
          <div style={S.fg}><label style={S.label}>Localização</label><input style={S.input} value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="Bloco A / Rack 2" /></div>
        </div>
        <div style={S.fg}><label style={S.label}>Descrição</label><input style={S.input} value={form.description} onChange={(e) => set("description", e.target.value)} /></div>
        
        <div style={S.grid(2)}>
          <div style={{...S.fg, border: "1px solid rgba(59,158,255,0.18)", padding: "10px", borderRadius: "10px", background: "rgba(59,158,255,0.06)"}}>
            <label style={{...S.label, color: "#3b9eff"}}>🆔 MAC Address</label>
            <input style={S.input} value={form.mac_address} onChange={(e) => set("mac_address", e.target.value)} placeholder="00:11:22:33:44:55" />
          </div>
          <div style={{...S.fg, border: "1px solid #a78bfa33", padding: "10px", borderRadius: "8px", background: "rgba(167, 139, 250, 0.05)"}}>
            <label style={{...S.label, color: "#a78bfa"}}>🏷️ Serial Number (SN)</label>
            <input style={S.input} value={form.serial_number} onChange={(e) => set("serial_number", e.target.value)} placeholder="SN123456789" />
          </div>
        </div>

        <div style={S.fg}><label style={S.label}>Tags</label><TagInput value={form.tags} onChange={(v) => set("tags", v)} /></div>

        <div style={S.divider} />
        <div style={S.sectionTitle}>Monitoramento & Redirecionamento</div>
        <div style={{ display: "flex", gap: 18, marginBottom: 12 }}>
          {[["monitor_agent","Agente"],["monitor_ping","Ping/ICMP"],["monitor_snmp","SNMP"]].map(([k,l]) => (
            <label key={k} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#94a3b8", cursor: "pointer" }}>
              <input type="checkbox" checked={form[k]} onChange={(e) => set(k, e.target.checked)} />{l}
            </label>
          ))}
          {canVideo && ["camera", "dvr", "nvr"].includes(form.device_type) && (
            <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#94a3b8", cursor: "pointer" }}>
              <input type="checkbox" checked={!!form.ai_enabled} onChange={(e) => set("ai_enabled", e.target.checked)} />
              IA (Analíticos)
            </label>
          )}
        </div>

        <div style={S.grid(2)}>
          <div style={S.fg}>
            <label style={S.label}>Endereço DDNS Intelbras / No-IP</label>
            <input style={S.input} value={form.ddns_address} onChange={(e) => set("ddns_address", e.target.value)} placeholder="ex: camera1.ddns-intelbras.com.br" />
          </div>
          <div style={S.fg}>
            <label style={S.label}>Porta de Serviço (TCP)</label>
            <input style={S.input} type="number" value={form.monitor_port} onChange={(e) => set("monitor_port", e.target.value)} placeholder="ex: 37777" />
          </div>
        </div>

        {form.monitor_snmp && (
          <div style={S.grid(2)}>
            <div style={S.fg}><label style={S.label}>SNMP Community</label><input style={S.input} value={form.snmp_community} onChange={(e) => set("snmp_community", e.target.value)} /></div>
            <div style={S.fg}><label style={S.label}>SNMP Versão</label>
              <select style={S.select} value={form.snmp_version} onChange={(e) => set("snmp_version", e.target.value)}>
                <option value="1">v1</option><option value="2c">v2c</option><option value="3">v3</option>
              </select>
            </div>
          </div>
        )}
        <div style={S.grid(2)}>
          <div style={S.fg}><label style={S.label}>Usuário SSH</label><input style={S.input} value={form.ssh_user} onChange={(e) => set("ssh_user", e.target.value)} placeholder="admin" /></div>
          <div style={S.fg}><label style={S.label}>Porta SSH</label><input style={S.input} type="number" value={form.ssh_port} onChange={(e) => set("ssh_port", parseInt(e.target.value)||22)} /></div>
        </div>
        <div style={S.fg}><label style={S.label}>Notas</label><textarea style={{ ...S.input, minHeight: 50, resize: "vertical" }} value={form.notes} onChange={(e) => set("notes", e.target.value)} /></div>

        <div style={S.divider} />
        {canVideo ? (
          <>
            <div style={S.sectionTitle}>ONVIF (Eventos & Vídeo)</div>
            <div style={{ display: "flex", gap: 18, marginBottom: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#94a3b8", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={onvif.enabled}
                  onChange={(e) => setOnvifField("enabled", e.target.checked)}
                />
                Habilitar ONVIF
              </label>
            </div>

            <div style={S.grid(2)}>
              <div style={S.fg}>
                <label style={S.label}>Host ONVIF</label>
                <input style={S.input} value={onvif.host} onChange={(e) => setOnvifField("host", e.target.value)} placeholder="192.168.1.100" />
              </div>
              <div style={S.fg}>
                <label style={S.label}>Porta ONVIF</label>
                <input style={S.input} type="number" value={onvif.port} onChange={(e) => setOnvifField("port", e.target.value)} placeholder="80" />
              </div>
            </div>
            <div style={S.grid(2)}>
              <div style={S.fg}>
                <label style={S.label}>Usuário ONVIF</label>
                <input style={S.input} value={onvif.username} onChange={(e) => setOnvifField("username", e.target.value)} placeholder="admin" />
              </div>
              <div style={S.fg}>
                <label style={S.label}>Senha ONVIF</label>
                <input
                  style={S.input}
                  type="password"
                  value={onvif.password}
                  onChange={(e) => setOnvif((o) => ({ ...o, password: e.target.value, passwordTouched: true, passwordCleared: false }))}
                  placeholder={onvif.password_set ? "•••••• (já salva)" : "••••••"}
                />
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 6 }}>
                  <button
                    type="button"
                    style={S.btnSm("ghost")}
                    onClick={() => setOnvif((o) => ({ ...o, password: "", passwordTouched: false, passwordCleared: true, password_set: false }))}
                  >
                    Limpar senha
                  </button>
                </div>
              </div>
            </div>
            <div style={S.fg}>
              <label style={S.label}>Channel Map (JSON)</label>
              <textarea
                style={{ ...S.input, minHeight: 80, resize: "vertical", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}
                value={onvif.channel_map_text}
                onChange={(e) => setOnvifField("channel_map_text", e.target.value)}
                placeholder='{"VideoSourceToken_1": 1}'
              />
            </div>

            <div style={S.divider} />
            <div style={S.sectionTitle}>RTSP (Perda/Travamento de Vídeo)</div>
            <div style={{ display: "flex", gap: 18, marginBottom: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#94a3b8", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={rtsp.enabled}
                  onChange={(e) => setRtspField("enabled", e.target.checked)}
                />
                Habilitar RTSP Monitor
              </label>
            </div>
            <div style={S.grid(2)}>
              <div style={S.fg}>
                <label style={S.label}>Usuário RTSP (opcional)</label>
                <input style={S.input} value={rtsp.username} onChange={(e) => setRtspField("username", e.target.value)} placeholder="admin" />
              </div>
              <div style={S.fg}>
                <label style={S.label}>Senha RTSP (opcional)</label>
                <input
                  style={S.input}
                  type="password"
                  value={rtsp.password}
                  onChange={(e) => setRtsp((o) => ({ ...o, password: e.target.value, passwordTouched: true, passwordCleared: false }))}
                  placeholder={rtsp.password_set ? "•••••• (já salva)" : "••••••"}
                />
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 6 }}>
                  <button
                    type="button"
                    style={S.btnSm("ghost")}
                    onClick={() => setRtsp((o) => ({ ...o, password: "", passwordTouched: false, passwordCleared: true, password_set: false }))}
                  >
                    Limpar senha
                  </button>
                </div>
              </div>
            </div>
            <div style={S.fg}>
              <label style={S.label}>Streams (JSON)</label>
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: -4, marginBottom: 8 }}>
                <button type="button" style={S.btnSm("ghost")} onClick={() => setRtspBulk((b) => ({ ...b, open: true }))}>
                  Renomear canais (lote)
                </button>
              </div>
              <textarea
                style={{ ...S.input, minHeight: 110, resize: "vertical", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}
                value={rtsp.streams_text}
                onChange={(e) => setRtspField("streams_text", e.target.value)}
                placeholder='[{"channel":1,"name":"Canal 1","url":"rtsp://192.168.1.100:554/...","timeout_seconds":8,"interval_seconds":30,"transport":"tcp"}]'
              />
            </div>

            {rtspBulk.open && (
              <div style={S.modal} onClick={() => setRtspBulk((b) => ({ ...b, open: false }))}>
                <div style={{ ...S.modalBox, width: 560 }} onClick={(e) => e.stopPropagation()}>
                  <div style={S.modalTitle}>🧩 Renomear canais (lote)</div>
                  <div style={{ fontSize: 11, color: "#93a4bf", marginBottom: 12 }}>
                    Isso só altera o campo `name` dos streams já existentes no JSON. O servidor ignora streams sem `url`.
                  </div>

                  <div style={S.grid(3)}>
                    <div style={S.fg}>
                      <label style={S.label}>Canal início</label>
                      <input style={S.input} value={rtspBulk.start} onChange={(e) => setRtspBulk((b) => ({ ...b, start: e.target.value }))} placeholder="1" />
                    </div>
                    <div style={S.fg}>
                      <label style={S.label}>Canal fim</label>
                      <input style={S.input} value={rtspBulk.end} onChange={(e) => setRtspBulk((b) => ({ ...b, end: e.target.value }))} placeholder="32" />
                    </div>
                    <div style={S.fg}>
                      <label style={S.label}>Zero pad (opcional)</label>
                      <input style={S.input} value={rtspBulk.pad} onChange={(e) => setRtspBulk((b) => ({ ...b, pad: e.target.value }))} placeholder="0" />
                    </div>
                  </div>

                  <div style={S.fg}>
                    <label style={S.label}>Padrão de nome</label>
                    <input
                      style={{ ...S.input, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}
                      value={rtspBulk.pattern}
                      onChange={(e) => setRtspBulk((b) => ({ ...b, pattern: e.target.value }))}
                      placeholder="Canal {ch}"
                    />
                    <div style={{ fontSize: 10, color: "#3a5070", marginTop: 6 }}>
                      Use `{ch}` no texto (ex: `Camera {ch}` ou `Entrada {ch}`).
                    </div>
                  </div>

                  <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#94a3b8", cursor: "pointer" }}>
                    <input type="checkbox" checked={rtspBulk.overwrite} onChange={(e) => setRtspBulk((b) => ({ ...b, overwrite: e.target.checked }))} />
                    Sobrescrever nomes já preenchidos
                  </label>

                  <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 14 }}>
                    <button style={S.btn("ghost")} onClick={() => setRtspBulk((b) => ({ ...b, open: false }))}>Cancelar</button>
                    <button style={S.btn("primary")} onClick={applyRtspBulkNames}>Aplicar</button>
                  </div>
                </div>
              </div>
            )}
          </>
        ) : (
          <div style={{ background: "rgba(59,158,255,0.06)", border: "1px solid rgba(59,158,255,0.12)", borderRadius: 12, padding: 14, color: "#b8cfe8", fontSize: 12 }}>
            Acesso restrito. Para configurar ONVIF/RTSP, o usuário precisa de nível 2 (vídeo ao vivo).
          </div>
        )}

        {err && <div style={{ color: "#ef4444", fontSize: 11, marginBottom: 10 }}>⚠️ {err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button style={S.btn("ghost")} onClick={onClose}>Cancelar</button>
          <button style={S.btn("primary")} onClick={save} disabled={loading}>{loading ? "..." : "Salvar"}</button>
        </div>
      </div>
    </div>
  );
}

// ── Devices Page ──────────────────────────────────────────────
function DevicesPage({ userRole, userClientId, canVideo }) {
  const [devices, setDevices] = useState([]);
  const [clients, setClients] = useState([]);
  const [modal, setModal] = useState(null);
  const [tokenModal, setTokenModal] = useState(null);
  const [filter, setFilter] = useState({ type: "", status: "", client: "", search: "" });
  const [testing, setTesting] = useState(null);

  const load = useCallback(() => {
    api("/devices").then((data) => {
      setDevices(Array.isArray(data) ? data : []);
    }).catch(() => {});
    if (userRole === "superadmin") api("/clients").then(setClients).catch(() => {});
  }, [userRole]);

  useEffect(() => { 
    load(); 
    const t = setInterval(load, 2000); // REFRESH CADA 2 SEGUNDOS (MODO REAL-TIME)
    return () => clearInterval(t); 
  }, [load]);

  const del = async (id) => { if (!confirm("Remover este dispositivo?")) return; await api(`/devices/${id}`, { method: "DELETE" }); load(); };
  const regenToken = async (id) => { const d = await api(`/devices/${id}/regenerate-token`, { method: "POST" }); setTokenModal(d.token); load(); };
  const testConn = async (id) => {
    setTesting(id);
    try {
      const res = await api(`/devices/${id}/test`, { method: "POST" });
      alert(res.message);
      load();
    } catch (e) {
      alert("Erro ao testar: " + (e.error || e.message));
    } finally {
      setTesting(null);
    }
  };

  const filtered = devices.filter((d) => {
    if (filter.type && d.device_type !== filter.type) return false;
    if (filter.status && d.status !== filter.status) return false;
    if (filter.client && String(d.client_id) !== filter.client) return false;
    if (filter.search && !(d.name || "").toLowerCase().includes(filter.search.toLowerCase()) && !(d.ip_address||"").includes(filter.search)) return false;
    return true;
  });

  const isMobile = useIsMobile();

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={S.pageTitle}>📡 Dispositivos</div>
          <div style={S.pageSub}>Gerenciamento de Monitoramento Cloud & Local</div>
        </div>
        <button style={S.btn("primary")} onClick={() => setModal("new")}>+ Novo Dispositivo</button>
      </div>

      <div style={{ ...S.card, marginBottom: 24, display: "flex", gap: 12, flexWrap: "wrap", background: "#0d1929", border: "1px solid rgba(59,158,255,0.08)" }}>
        <input style={{ ...S.input, maxWidth: 200 }} placeholder="🔍 Buscar..." value={filter.search} onChange={(e) => setFilter({ ...filter, search: e.target.value })} />
        <select style={{ ...S.select, maxWidth: 150 }} value={filter.type} onChange={(e) => setFilter({ ...filter, type: e.target.value })}>
          <option value="">Todos os tipos</option>
          {DEVICE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.icon} {t.label}</option>)}
        </select>
        <select style={{ ...S.select, maxWidth: 120 }} value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
          <option value="">Todos status</option>
          <option value="online">🟢 Online</option>
          <option value="offline">🔴 Offline</option>
        </select>
        {userRole === "superadmin" && (
          <select style={{ ...S.select, maxWidth: 180 }} value={filter.client} onChange={(e) => setFilter({ ...filter, client: e.target.value })}>
            <option value="">Todos clientes</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        )}
      </div>

      <div style={{ 
        display: "grid", 
        gridTemplateColumns: isMobile ? "1fr" : "repeat(auto-fill, minmax(340px, 1fr))", 
        gap: 24 
      }}>
        {filtered.length === 0 && (
          <div style={{ gridColumn: "1/-1", textAlign: "center", padding: 60, color: "#4a6080" }}>
            Nenhum dispositivo encontrado com os filtros atuais.
          </div>
        )}
        {filtered.map((d) => (
          <div key={d.id} style={{ 
            ...S.card, 
            padding: 24, 
            border: `1px solid ${d.status === "online" ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
            boxShadow: "none"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 20 }}>
              <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                <div style={{ width: 46, height: 46, borderRadius: 12, background: d.status === "online" ? "rgba(34, 197, 94, 0.1)" : "rgba(239, 68, 68, 0.1)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, border: `1px solid ${d.status === "online" ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)"}` }}>
                  {deviceIcon(d.device_type)}
                </div>
                <div>
                  <div style={{ fontWeight: 800, color: "#fff", fontSize: 16, letterSpacing: 0.5 }}>{d.name}</div>
                  <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600 }}>{d.location || "Sem localização"}</div>
                </div>
              </div>
              <span style={S.badge(d.status === "online" ? "#22c55e" : "#ef4444")}>
                {d.status === "online" ? "● Online" : "● Offline"}
              </span>
            </div>

            <div style={{ background: "rgba(11,21,37,0.65)", borderRadius: 12, padding: 16, marginBottom: 20, border: "1px solid rgba(59,158,255,0.08)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontSize: 10, color: "#64748b", fontWeight: 700 }}>{d.ddns_address ? "DDNS" : "IP / VPN"}</span>
                <span style={{ fontSize: 11, color: d.ddns_address ? "#3b9eff" : "#a78bfa", fontFamily: "monospace", fontWeight: 700 }}>{d.ddns_address || d.ip_address || "—"}</span>
              </div>
              
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginTop: "10px", marginBottom: "10px" }}>
                <div style={{ background: "rgba(59,158,255,0.07)", padding: "8px", borderRadius: "8px", border: "1px solid rgba(59,158,255,0.14)" }}>
                  <span style={{ fontSize: "9px", color: "#3b9eff", display: "block", textTransform: "uppercase", fontWeight: 800, marginBottom: 2 }}>MAC Address</span>
                  <span style={{ fontSize: "11px", color: "#fff", fontWeight: "700", fontFamily: "monospace" }}>{d.mac_address || "---"}</span>
                </div>
                <div style={{ background: "rgba(167, 139, 250, 0.08)", padding: "8px", borderRadius: "8px", border: "1px solid rgba(167, 139, 250, 0.15)" }}>
                  <span style={{ fontSize: "9px", color: "#a78bfa", display: "block", textTransform: "uppercase", fontWeight: 800, marginBottom: 2 }}>Serial Number</span>
                  <span style={{ fontSize: "11px", color: "#fff", fontWeight: "700", fontFamily: "monospace" }}>{d.serial_number || "---"}</span>
                </div>
              </div>

              {/* Status Solar (Se disponível) */}
              {(d.solar_voltage > 0 || d.battery_percent > 0) && (
                <div style={{ background: "rgba(234, 179, 8, 0.08)", padding: "12px", borderRadius: "10px", border: "1px solid rgba(234, 179, 8, 0.2)", marginTop: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontSize: 10, color: "#eab308", fontWeight: 800 }}>☀️ STATUS SOLAR</span>
                    <span style={{ fontSize: 14, color: "#fff", fontWeight: 800 }}>{d.battery_percent}%</span>
                  </div>
                  <div style={{ height: 6, background: "rgba(255,255,255,0.1)", borderRadius: 3, overflow: "hidden", marginBottom: 10 }}>
                    <div style={{ height: "100%", width: `${d.battery_percent}%`, background: d.battery_percent > 20 ? "#22c55e" : "#ef4444", transition: "width 0.5s ease" }} />
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                    <div>
                      <span style={{ fontSize: 9, color: "#94a3b8", display: "block", fontWeight: 700 }}>PAINEL</span>
                      <span style={{ fontSize: 12, color: "#fff", fontWeight: 700 }}>{d.solar_voltage}V</span>
                    </div>
                    <div>
                      <span style={{ fontSize: 9, color: "#94a3b8", display: "block", fontWeight: 700 }}>BATERIA</span>
                      <span style={{ fontSize: 12, color: "#fff", fontWeight: 700 }}>{d.battery_voltage}V</span>
                    </div>
                  </div>
                </div>
              )}

              {d.monitor_port > 0 && (
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, marginTop: 10 }}>
                  <span style={{ fontSize: 10, color: "#64748b", fontWeight: 700 }}>PORTA</span>
                  <span style={{ fontSize: 11, color: "#3b9eff", fontWeight: 800 }}>{d.monitor_port}</span>
                </div>
              )}
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: d.monitor_port > 0 ? 0 : 10 }}>
                <span style={{ fontSize: 10, color: "#64748b", fontWeight: 700 }}>LATÊNCIA</span>
                <span style={{ fontSize: 11, color: "#22c55e", fontWeight: 800 }}>{d.last_latency ? `${Math.round(d.last_latency)}ms` : "—"}</span>
              </div>
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 20, minHeight: 24 }}>
              {(d.tags || []).map((t) => <span key={t} style={{ ...S.tag, margin: 0 }}>#{t}</span>)}
            </div>

            <div style={{ display: "flex", gap: 10 }}>
              <button style={{ ...S.btnSm(), flex: 1, padding: "8px 0" }} onClick={() => setModal(d)}>✏️ EDITAR</button>
              <button style={{ ...S.btnSm(), flex: 1, padding: "8px 0" }} onClick={() => testConn(d.id)} disabled={testing === d.id}>
                {testing === d.id ? "..." : "📡 TESTAR"}
              </button>
              <div style={{ position: "relative" }}>
                <button style={{ ...S.btnSm(), padding: "8px 12px" }} onClick={() => {
                  const el = document.getElementById(`menu-${d.id}`);
                  el.style.display = el.style.display === "none" ? "block" : "none";
                }}>⋮</button>
                <div id={`menu-${d.id}`} style={{ 
                  display: "none", position: "absolute", bottom: "100%", right: 0, 
                  background: "#0b1525", border: "1px solid rgba(59,158,255,0.18)", 
                  borderRadius: 12, padding: 8, zIndex: 10, boxShadow: "0 10px 30px rgba(0,0,0,0.45)", marginBottom: 8
                }}>
                  <button style={{ ...S.btnSm(), display: "block", width: "100%", textAlign: "left", marginBottom: 6, border: "none", background: "transparent" }} onClick={() => regenToken(d.id)}>🔑 GERAR TOKEN</button>
                  <button style={{ ...S.btnSm("danger"), display: "block", width: "100%", textAlign: "left", border: "none", background: "transparent" }} onClick={() => del(d.id)}>🗑️ EXCLUIR DEVICE</button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {(modal === "new" || (modal && modal.id)) && (
        <DeviceModal
          device={modal === "new" ? null : modal}
          clients={clients}
          userRole={userRole}
          userClientId={userClientId}
          canVideo={!!canVideo}
          onSave={() => {
            load();
            setModal(null);
          }}
          onClose={() => setModal(null)}
        />
      )}
      {tokenModal && (
        <div style={S.modal} onClick={() => setTokenModal(null)}>
          <div style={{ ...S.modalBox, width: 380 }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalTitle}>🔑 Token do Device</div>
            <div style={{ ...S.input, wordBreak: "break-all", padding: 10, fontSize: 10, color: "#3b9eff", marginBottom: 14 }}>{tokenModal}</div>
            <button style={{ ...S.btn("primary"), width: "100%" }} onClick={() => { navigator.clipboard.writeText(tokenModal); setTokenModal(null); }}>📋 Copiar e Fechar</button>
          </div>
        </div>
      )}
    </div>
  );
}

function ScannerPage({ userRole, userClientId, canVideo }) {
  const [devices, setDevices] = useState([]);
  const [clients, setClients] = useState([]);
  const [modal, setModal] = useState(null);
  const [discovered, setDiscovered] = useState([]);
  const [showAdoptedDiscovered, setShowAdoptedDiscovered] = useState(false);
  const [discErr, setDiscErr] = useState("");
  const [discLoading, setDiscLoading] = useState(false);
  const [discNames, setDiscNames] = useState({});
  const isMobile = useIsMobile();

  const load = useCallback(() => {
    api("/devices").then((data) => {
      setDevices(Array.isArray(data) ? data : []);
    }).catch(() => {});
    if (userRole === "superadmin") api("/clients").then(setClients).catch(() => {});
  }, [userRole]);

  useEffect(() => { 
    load(); 
    const t = setInterval(load, 5000);
    return () => clearInterval(t); 
  }, [load]);

  const loadDiscovered = useCallback(() => {
    setDiscLoading(true);
    setDiscErr("");
    api("/discovered-devices")
      .then((data) => setDiscovered(Array.isArray(data) ? data : []))
      .catch((e) => setDiscErr(e?.error || e?.message || "Falha ao carregar descobertos"))
      .finally(() => setDiscLoading(false));
  }, []);

  useEffect(() => {
    loadDiscovered();
    const t = setInterval(loadDiscovered, 15000);
    return () => clearInterval(t);
  }, [loadDiscovered]);

  useEffect(() => {
    setDiscNames((prev) => {
      const next = { ...prev };
      for (const d of discovered) {
        if (next[d.id] != null) continue;
        const ip = String(d.ip_address || "");
        const defName = d.hostname || `${(d.guess_type || "device")}-${ip.replace(/\./g, "-")}`;
        next[d.id] = defName;
      }
      return next;
    });
  }, [discovered]);

  const existingIps = new Set(devices.map((d) => String(d.ip_address || "").trim()).filter(Boolean));
  const discoveredVisible = showAdoptedDiscovered
    ? discovered
    : discovered.filter((d) => !d.device_id && !existingIps.has(String(d.ip_address || "").trim()));

  const guessToDeviceType = (guess) => {
    const g = String(guess || "").toLowerCase().trim();
    if (g === "camera") return "camera";
    if (g === "nvr") return "nvr";
    if (g === "dvr") return "dvr";
    if (g === "router") return "router";
    if (g === "switch") return "switch";
    if (g === "server") return "server";
    return "other";
  };

  const openFinalize = (d) => {
    const ip = String(d.ip_address || "").trim();
    const portsArr = Array.isArray(d.open_ports) ? d.open_ports.map((p) => parseInt(p) || 0).filter(Boolean) : [];
    const monitor_port = portsArr.includes(37777) ? 37777 : portsArr.includes(8000) ? 8000 : 0;
    const name = String((discNames[d.id] ?? "")).trim();
    setModal({
      name,
      ip_address: ip,
      device_type: guessToDeviceType(d.guess_type),
      monitor_port,
      mac_address: d.mac_address || "",
      serial_number: d.serial_number || "",
      client_id: userRole === "superadmin" ? null : userClientId,
    });
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={S.pageTitle}>🔎 Scanner</div>
          <div style={S.pageSub}>Equipamentos descobertos na rede local. Finalize o cadastro para virar Device.</div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button style={S.btnSm()} onClick={loadDiscovered} disabled={discLoading}>{discLoading ? "..." : "Atualizar"}</button>
        </div>
      </div>

      <div style={{ ...S.card, marginBottom: 24, padding: 18, background: "#0d1929", border: "1px solid rgba(59,158,255,0.08)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <div>
            <div style={{ fontWeight: 800, color: "#fff", letterSpacing: 0.5 }}>🔎 Descobertos na rede local</div>
            <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600 }}>Encontrados pelo agente (varredura + ONVIF WS-Discovery).</div>
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#b8cfe8", cursor: "pointer", fontWeight: 700 }}>
              <input
                type="checkbox"
                style={{ accentColor: "#3b9eff", transform: "scale(1.1)" }}
                checked={showAdoptedDiscovered}
                onChange={(e) => setShowAdoptedDiscovered(e.target.checked)}
              />
              Mostrar adicionados
            </label>
          </div>
        </div>

        {discErr && <div style={{ color: "#ef4444", fontSize: 11, marginBottom: 10 }}>⚠️ {discErr}</div>}
        {discoveredVisible.length === 0 ? (
          <div style={{ color: "#4a6080", fontSize: 12, padding: "10px 0" }}>
            {discLoading ? "Carregando..." : "Nenhum equipamento descoberto nas últimas 24h."}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ color: "#64748b", textTransform: "uppercase", letterSpacing: "0.12em", fontSize: 9 }}>
                  <th style={{ textAlign: "left", padding: "10px 8px" }}>Nome</th>
                  <th style={{ textAlign: "left", padding: "10px 8px" }}>IP</th>
                  <th style={{ textAlign: "left", padding: "10px 8px" }}>Tipo</th>
                  <th style={{ textAlign: "left", padding: "10px 8px" }}>Portas</th>
                  <th style={{ textAlign: "left", padding: "10px 8px" }}>MAC</th>
                  <th style={{ textAlign: "left", padding: "10px 8px" }}>Último</th>
                  <th style={{ textAlign: "right", padding: "10px 8px" }}>Ação</th>
                </tr>
              </thead>
              <tbody>
                {discoveredVisible.map((d) => {
                  const ports = Array.isArray(d.open_ports) ? d.open_ports.join(", ") : "";
                  const adopted = !!d.device_id || existingIps.has(String(d.ip_address || "").trim());
                  const hasOnvif = !!(d.onvif_xaddrs && String(d.onvif_xaddrs).trim());
                  const nameVal = discNames[d.id] ?? "";
                  return (
                    <tr key={d.id} style={{ borderTop: "1px solid rgba(59,158,255,0.08)" }}>
                      <td style={{ padding: "10px 8px", minWidth: 220 }}>
                        <input
                          style={{ ...S.input, height: 34, fontSize: 12 }}
                          value={nameVal}
                          onChange={(e) => setDiscNames((p) => ({ ...p, [d.id]: e.target.value }))}
                          placeholder="Nome do dispositivo"
                          disabled={adopted}
                        />
                      </td>
                      <td style={{ padding: "10px 8px", color: "#fff", fontFamily: "monospace", fontWeight: 700 }}>{d.ip_address || "—"}</td>
                      <td style={{ padding: "10px 8px", color: "#cbd5e1", fontWeight: 700 }}>
                        {d.guess_type || "other"} {hasOnvif ? <span style={{ ...S.badge("#3b9eff"), marginLeft: 8 }}>ONVIF</span> : null}
                      </td>
                      <td style={{ padding: "10px 8px", color: "#94a3b8", fontFamily: "monospace" }}>{ports || "—"}</td>
                      <td style={{ padding: "10px 8px", color: "#94a3b8", fontFamily: "monospace" }}>{d.mac_address || "—"}</td>
                      <td style={{ padding: "10px 8px", color: "#94a3b8" }}>{d.last_seen ? timeAgoPtBR(d.last_seen) : "—"}</td>
                      <td style={{ padding: "10px 8px", textAlign: "right" }}>
                        {adopted ? (
                          <span style={S.badge("#22c55e")}>Adicionado</span>
                        ) : (
                          <button
                            style={S.btnSm("primary")}
                            onClick={() => openFinalize(d)}
                            disabled={!String((discNames[d.id] ?? "")).trim()}
                          >
                            Finalizar cadastro
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {(modal && !modal.id) && (
        <DeviceModal
          device={modal}
          clients={clients}
          userRole={userRole}
          userClientId={userClientId}
          canVideo={!!canVideo}
          onSave={() => {
            load();
            loadDiscovered();
            setModal(null);
          }}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────
function Dashboard({ userRole }) {
  const isMobile = useIsMobile();
  const [stats, setStats] = useState({ devices: 0, online: 0, offline: 0, clients: 0 });
  const [devices, setDevices] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [clients, setClients] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);

  const load = useCallback(() => {
    api("/stats").then(setStats).catch(() => {});
    api("/devices").then((data) => setDevices(Array.isArray(data) ? data : [])).catch(() => {});
    api("/alerts").then((data) => setAlerts(Array.isArray(data) ? data : [])).catch(() => {});
    if (userRole === "superadmin") api("/clients").then((data) => setClients(Array.isArray(data) ? data : [])).catch(() => {});
  }, [userRole]);

  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    const raw = import.meta.env.VITE_WS_URL || "";
    const wsUrl = raw.replace(/["'`\s]/g, "").trim().replace(/\/$/, "");
    if (!wsUrl) return;
    const socket = io(wsUrl, {
      transports: ["websocket", "polling"],
      timeout: 20000,
      reconnection: true,
      reconnectionDelay: 1000,
    });

    const onConnect = () => setWsConnected(true);
    const onDisconnect = () => setWsConnected(false);
    const onMetric = (m) => {
      const devId = m?.device_id;
      if (!devId) return;
      setDevices((prev) =>
        prev.map((d) =>
          d.id === devId
            ? {
                ...d,
                last_cpu: m.cpu ?? d.last_cpu,
                last_memory: m.memory ?? d.last_memory,
                last_latency: m.latency_ms ?? d.last_latency,
                last_seen: m.time ?? d.last_seen,
                status: m.status ?? d.status,
              }
            : d
        )
      );
    };

    socket.on("connect", onConnect);
    socket.on("disconnect", onDisconnect);
    socket.on("metric:all", onMetric);

    return () => {
      socket.off("connect", onConnect);
      socket.off("disconnect", onDisconnect);
      socket.off("metric:all", onMetric);
      socket.close();
    };
  }, []);

  const byType = DEVICE_TYPES.map((t) => ({ ...t, count: devices.filter((d) => d.device_type === t.value).length })).filter((t) => t.count > 0);
  const totalDevices = Math.max(1, stats.devices || devices.length || 1);
  const onlineRate = Math.round(((stats.online || 0) / Math.max(1, stats.devices || 1)) * 100);

  const typeColor = (value) => {
    if (value === "server") return "#3b9eff";
    if (value === "router") return "#00c9a7";
    if (value === "switch") return "#a78bfa";
    if (value === "camera" || value === "nvr" || value === "dvr") return "#60c8ff";
    return "#64748b";
  };

  const statTiles = [
    ...(userRole === "superadmin" ? [{ label: "Clientes", value: stats.clients, color: "#a78bfa", r: "167,139,250" }] : []),
    { label: "Total Devices", value: stats.devices, color: "#3b9eff", r: "59,158,255" },
    { label: "Online", value: stats.online, color: "#00c9a7", r: "0,201,167" },
    { label: "Offline", value: stats.offline, color: "#ef4444", r: "239,68,68" },
    { label: "Alertas 24h", value: alerts.length, color: "#f59e0b", r: "245,158,11" },
  ];

  const recentAlerts = alerts.slice(0, 3).map((a) => {
    const critical = a.alert_type === "offline";
    const title = a.trigger_name || (a.expression || "").toUpperCase() || "ALERTA";
    const host = a.device_name || a.host || "—";
    const val = a.value != null ? String(a.value) : "—";
    return {
      id: a.id,
      host,
      tipo: title,
      valor: val,
      tempo: a.fired_at ? timeAgoPtBR(a.fired_at) : "—",
      severity: critical ? "critical" : "warning",
    };
  });

  const onlineDevices = devices
    .filter((d) => d.status === "online")
    .slice()
    .sort((a, b) => (b.last_cpu || 0) - (a.last_cpu || 0))
    .slice(0, 10)
    .map((d) => {
      const cpu = Math.round(Number(d.last_cpu) || 0);
      const mem = Math.round(Number(d.last_memory) || 0);
      const status = cpu > 85 || mem > 85 ? "critical" : cpu > 60 || mem > 60 ? "warning" : "ok";
      return { nome: d.name, cliente: d.client_name || "—", cpu, mem, status };
    });

  return (
    <div style={{ padding: isMobile ? '0 8px' : 0 }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28, gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <h1 style={{ fontFamily: "'Exo 2',sans-serif", fontSize: 28, fontWeight: 800, letterSpacing: '0.06em', color: '#fff', textShadow: '0 0 30px rgba(59,158,255,0.15)' }}>DASHBOARD</h1>
            <div style={{ height: 2, width: 48, background: 'linear-gradient(90deg,#3b9eff,transparent)', marginTop: 4 }} />
          </div>
          <p style={{ marginTop: 4, color: '#2a5070', fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Visão geral em tempo real — ETI Sentinel</p>
        </div>
        <button
          onClick={load}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            background: 'rgba(59,158,255,0.08)',
            border: '1px solid rgba(59,158,255,0.28)',
            color: '#3b9eff',
            borderRadius: 8,
            padding: '10px 20px',
            fontWeight: 700,
            fontSize: 13,
            fontFamily: "'Rajdhani',sans-serif",
            letterSpacing: '0.08em',
            boxShadow: '0 0 18px rgba(59,158,255,0.08)',
          }}
        >
          <RefreshCw size={16} />
          ATUALIZAR
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? 'repeat(2,1fr)' : `repeat(${userRole === 'superadmin' ? 5 : 4},1fr)`, gap: 12, marginBottom: 20 }}>
        {statTiles.map((c) => (
          <div key={c.label} style={{ background: '#0d1929', border: `1px solid rgba(${c.r},0.15)`, borderRadius: 12, padding: isMobile ? '14px 14px' : '18px 18px', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', top: -20, right: -20, width: 80, height: 80, borderRadius: '50%', background: c.color, opacity: 0.05, filter: 'blur(18px)' }} />
            <div style={{ fontSize: 9, fontWeight: 700, color: '#1e3a5a', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 12 }}>{c.label}</div>
            <div style={{ fontSize: isMobile ? 30 : 36, fontWeight: 800, color: c.color, fontFamily: "'Exo 2',sans-serif", letterSpacing: '-0.02em', textShadow: `0 0 20px rgba(${c.r},0.35)` }}>{c.value}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1.1fr 1.1fr', gap: 12, marginBottom: 12 }}>
        <div style={{ background: '#0d1929', border: '1px solid rgba(59,158,255,0.1)', borderRadius: 12, padding: 22 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#3b9eff', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 18 }}>Saúde da Rede</div>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 18 }}>
            <div style={{ position: 'relative', width: 110, height: 110 }}>
              <svg viewBox="0 0 110 110" style={{ width: '100%', transform: 'rotate(-90deg)' }}>
                <defs>
                  <filter id="eti-gf2">
                    <feGaussianBlur stdDeviation="3" result="b" />
                    <feMerge>
                      <feMergeNode in="b" />
                      <feMergeNode in="SourceGraphic" />
                    </feMerge>
                  </filter>
                </defs>
                <circle cx="55" cy="55" r="44" fill="none" stroke="rgba(59,158,255,0.08)" strokeWidth="11" />
                <circle
                  cx="55"
                  cy="55"
                  r="44"
                  fill="none"
                  stroke="#00c9a7"
                  strokeWidth="11"
                  strokeDasharray={`${Math.round(onlineRate * 2.764)} 276.4`}
                  strokeLinecap="round"
                  filter="url(#eti-gf2)"
                />
              </svg>
              <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                <span style={{ fontSize: 26, fontWeight: 800, color: '#00c9a7', fontFamily: "'Exo 2',sans-serif", textShadow: '0 0 16px rgba(0,201,167,0.6)' }}>{onlineRate}%</span>
                <span style={{ fontSize: 9, color: '#1e3a5a', letterSpacing: '0.1em' }}>ONLINE</span>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-around' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#00c9a7', fontFamily: "'Exo 2',sans-serif" }}>{stats.online}</div>
              <div style={{ fontSize: 9, color: '#1e3a5a', letterSpacing: '0.1em' }}>ONLINE</div>
            </div>
            <div style={{ width: 1, background: 'rgba(59,158,255,0.08)' }} />
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: '#ef4444', fontFamily: "'Exo 2',sans-serif" }}>{stats.offline}</div>
              <div style={{ fontSize: 9, color: '#1e3a5a', letterSpacing: '0.1em' }}>OFFLINE</div>
            </div>
          </div>
        </div>

        <div style={{ background: '#0d1929', border: '1px solid rgba(59,158,255,0.1)', borderRadius: 12, padding: 22 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#3b9eff', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 18 }}>Devices por Tipo</div>
          {byType.length === 0 && <div style={{ fontSize: 12, color: '#2a5070' }}>Nenhum device</div>}
          {byType.map((d) => (
            <div key={d.value} style={{ marginBottom: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 13, color: '#5a7fa8', fontWeight: 500 }}>{d.label}</span>
                <span style={{ fontSize: 13, fontWeight: 700, color: typeColor(d.value) }}>{d.count}</span>
              </div>
              <div style={{ height: 5, background: 'rgba(255,255,255,0.04)', borderRadius: 99 }}>
                <div style={{ width: `${(d.count / totalDevices) * 100}%`, height: '100%', background: typeColor(d.value), borderRadius: 99, boxShadow: `0 0 8px ${typeColor(d.value)}55` }} />
              </div>
            </div>
          ))}
        </div>

        <div style={{ background: '#0d1929', border: '1px solid rgba(59,158,255,0.1)', borderRadius: 12, padding: 22 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: '#3b9eff', letterSpacing: '0.14em', textTransform: 'uppercase' }}>Alertas Recentes</div>
            <span style={{ background: 'rgba(239,68,68,0.1)', color: '#ef4444', border: '1px solid rgba(239,68,68,0.25)', fontSize: 9, fontWeight: 700, borderRadius: 999, padding: '2px 8px', letterSpacing: '0.08em' }}>{alerts.length} HOJE</span>
          </div>
          {recentAlerts.length === 0 && <div style={{ fontSize: 12, color: '#2a5070' }}>Nenhum alerta</div>}
          {recentAlerts.map((a, i) => (
            <div key={a.id || i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0', borderBottom: i < recentAlerts.length - 1 ? '1px solid rgba(59,158,255,0.05)' : 'none' }}>
              <PulsingDot color={a.severity === 'critical' ? '#ef4444' : '#f59e0b'} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#b8cfe8', letterSpacing: '0.03em', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.host}</div>
                <div style={{ fontSize: 11, color: '#2a5070', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.tipo} · {a.valor}</div>
              </div>
              <div style={{ fontSize: 10, color: '#1a3050', whiteSpace: 'nowrap' }}>{a.tempo}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ background: '#0d1929', border: '1px solid rgba(59,158,255,0.1)', borderRadius: 12, padding: 22 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18, gap: 12, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#3b9eff', letterSpacing: '0.14em', textTransform: 'uppercase' }}>Dispositivos em Tempo Real</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 10, color: wsConnected ? '#00c9a7' : '#f59e0b', fontWeight: 700, letterSpacing: '0.1em' }}>
            <PulsingDot color={wsConnected ? '#00c9a7' : '#f59e0b'} />
            {wsConnected ? 'AO VIVO' : 'SEM WS'}
          </div>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 760 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(59,158,255,0.08)' }}>
                {["Dispositivo", "Cliente", "CPU", "Memória", "Status"].map((h) => (
                  <th key={h} style={{ textAlign: 'left', fontSize: 9, fontWeight: 700, color: '#1e3a5a', textTransform: 'uppercase', letterSpacing: '0.14em', padding: '0 0 12px' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {onlineDevices.map((d, i) => (
                <tr key={`${d.nome}-${i}`} style={{ borderBottom: '1px solid rgba(59,158,255,0.04)' }}>
                  <td style={{ padding: '12px 0', fontSize: 14, fontWeight: 700, color: '#b8cfe8', letterSpacing: '0.04em', fontFamily: "'Exo 2',sans-serif" }}>{d.nome}</td>
                  <td style={{ padding: '12px 0', fontSize: 12, color: '#2a5070' }}>{d.cliente}</td>
                  <td style={{ padding: '12px 0' }}><MiniBar value={d.cpu} color="#3b9eff" /></td>
                  <td style={{ padding: '12px 0' }}><MiniBar value={d.mem} color="#a78bfa" /></td>
                  <td style={{ padding: '12px 0' }}><StatusBadge status={d.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {onlineDevices.length === 0 && (
          <div style={{ textAlign: 'center', padding: '26px 0', color: '#2a5070', fontSize: 12 }}>Aguardando dispositivos ficarem online...</div>
        )}
      </div>
    </div>
  );
}

// ── Events Page (Analíticos) ──────────────────────────────────
function EventsPage({ userRole }) {
  const [events, setEvents] = useState([]);
  const isMobile = useIsMobile();

  const load = useCallback(() => {
    api("/events").then((data) => setEvents(Array.isArray(data) ? data : [])).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  const getIcon = (type) => {
    const t = (type || "").toUpperCase();
    if (t.includes("PESSOA") || t.includes("HUMAN")) return "👤";
    if (t.includes("VEICULO") || t.includes("CARRO") || t.includes("CAR")) return "🚗";
    if (t.includes("VIDEO") || t.includes("PERDA")) return "⚠️";
    if (t.includes("DISCO") || t.includes("HD") || t.includes("DISK")) return "💾";
    return "🔔";
  };

  return (
    <div>
      <div style={S.pageTitle}>🎬 Central de Eventos</div>
      <div style={S.pageSub}>Analíticos de vídeo e hardware em tempo real</div>

      <div style={{ ...S.card, padding: isMobile ? 15 : 24 }}>
        {events.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: "#4a6080" }}>
            Nenhum evento detectado recentemente.
          </div>
        )}
        <div style={{ display: "flex", flexDirection: "column" }}>
          {events.map((e) => (
            <div key={e.id} style={S.eventCard(e.severity)}>
              <div style={{ fontSize: 24 }}>{getIcon(e.event_type)}</div>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ fontWeight: 700, color: "#fff", fontSize: 14 }}>
                    {e.event_type.replace(/_/g, " ")}
                  </div>
                  <div style={{ fontSize: 10, color: "#4a6080", fontFamily: "monospace" }}>
                    {new Date(e.time).toLocaleString("pt-BR")}
                  </div>
                </div>
                <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>
                  <span style={{ color: "#3b9eff", fontWeight: 700 }}>{e.device_name}</span>
                  {e.channel > 0 && ` • Canal ${e.channel}`}
                  {e.client_name && ` • ${e.client_name}`}
                </div>
                {e.description && (
                  <div style={{ fontSize: 11, color: "#64748b", marginTop: 4, fontStyle: "italic" }}>
                    "{e.description}"
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Alerts Page ───────────────────────────────────────────────
function AlertsPage({ userRole }) {
  const [alerts, setAlerts] = useState([]);
  const [filter, setFilter] = useState("all");
  const [clients, setClients] = useState([]);
  const [clientFilter2, setClientFilter2] = useState("");

  const load = () => {
    api("/alerts").then(setAlerts).catch(() => {});
    if (userRole === "superadmin") api("/clients").then(setClients).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);

  const filtered = alerts.filter((a) => {
    if (filter === "offline" && a.alert_type !== "offline") return false;
    if (filter === "threshold" && a.alert_type !== "threshold") return false;
    if (clientFilter2 && String(a.client_id) !== clientFilter2) return false;
    return true;
  });

  const TYPE_STYLE = {
    offline:   { bg:"rgba(239, 68, 68, 0.08)", border:"rgba(239, 68, 68, 0.25)", icon:"🔴", label:"Offline",   color:"#ef4444", shadow:"none" },
    threshold: { bg:"rgba(255, 174, 0, 0.06)", border:"rgba(255, 174, 0, 0.26)", icon:"🚨", label:"Threshold", color:"#ffae00", shadow:"0 0 14px rgba(255,174,0,0.14)" },
  };

  const METRIC_LABELS = {
    cpu: "CPU", memory: "Memória", disk_percent: "Disco",
    latency_ms: "Latência", load_avg: "Load Avg", offline: "Offline", temperature: "Temperatura"
  };
  const METRIC_UNITS = {
    cpu:"%", memory:"%", disk_percent:"%", latency_ms:"ms", load_avg:"", offline:"", temperature:"°C"
  };

  const counts = useMemo(() => ({
    all: alerts.length,
    offline: alerts.filter(a => a.alert_type === "offline").length,
    threshold: alerts.filter(a => a.alert_type === "threshold").length,
  }), [alerts]);

  return (
    <div style={{ padding: "8px 0" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16, marginBottom: 18 }}>
        <div>
          <div style={{ ...S.pageTitle, marginBottom: 6 }}>🚨 Alertas</div>
          <div style={{ ...S.pageSub, marginTop: 0 }}>Histórico de alertas — {alerts.length} total</div>
        </div>
        <button onClick={load} style={{ ...S.btn("ghost"), padding: "10px 16px", borderRadius: 12 }}>
          ↻ Atualizar
        </button>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 18, flexWrap: "wrap", alignItems: "center" }}>
        {[
          ["all", "TODOS", "#3b9eff", counts.all],
          ["offline", "OFFLINE", "#ef4444", counts.offline],
          ["threshold", "THRESHOLD", "#ffae00", counts.threshold],
        ].map(([k, label, c, n]) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            style={{
              background: filter === k ? `${c}22` : "rgba(13, 13, 22, 0.55)",
              border: `1px solid ${filter === k ? c : "rgba(255,255,255,0.06)"}`,
              color: filter === k ? c : "#94a3b8",
              borderRadius: 12,
              padding: "10px 18px",
              fontSize: 13,
              fontWeight: 800,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 10,
              boxShadow: "none",
              letterSpacing: "0.8px",
              textTransform: "uppercase",
            }}
          >
            <span style={{ width: 10, height: 10, borderRadius: 999, background: c }} />
            {label}
            <span style={{ background: filter === k ? `${c}44` : "rgba(255,255,255,0.10)", color: filter === k ? "#fff" : "#cbd5e1", borderRadius: 999, padding: "2px 10px", fontSize: 12, fontWeight: 900 }}>
              {n}
            </span>
          </button>
        ))}

        {userRole === "superadmin" && (
          <select
            style={{ ...S.select, maxWidth: 220, borderRadius: 12, height: 40 }}
            value={clientFilter2}
            onChange={(e) => setClientFilter2(e.target.value)}
          >
            <option value="">Todos os clientes</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        )}
      </div>

      {filtered.length === 0 && (
        <div style={{ textAlign: "center", padding: "70px 24px", background: "#0d1929", borderRadius: 24, border: "1px solid rgba(59,158,255,0.08)" }}>
          <div style={{ fontSize: 56, marginBottom: 14 }}>✅</div>
          <div style={{ color: "#fff", fontWeight: 900, fontSize: 20 }}>Nenhum alerta encontrado</div>
          <div style={{ color: "#94a3b8", fontSize: 14, marginTop: 6 }}>Sistema operando normalmente.</div>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {filtered.map((a) => {
          const t = TYPE_STYLE[a.alert_type] || TYPE_STYLE.threshold;
          const metricLabel = METRIC_LABELS[a.expression] || a.expression;
          const unit = METRIC_UNITS[a.expression] ?? "%";
          const valueNum = a.value != null ? Number(a.value) : null;
          const thresholdNum = a.threshold != null ? Number(a.threshold) : null;

          return (
            <div
              key={a.id}
              style={{
                background: t.bg,
                border: `1px solid ${t.border}`,
                borderRadius: 18,
                padding: "18px 20px",
                display: "flex",
                alignItems: "center",
                gap: 18,
                flexWrap: "wrap",
                boxShadow: t.shadow,
              }}
            >
              <div style={{ fontSize: 28, flexShrink: 0 }}>{t.icon}</div>

              <div style={{ flex: 1, minWidth: 260 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 16, fontWeight: 900, color: t.color, letterSpacing: "0.6px" }}>
                    {a.trigger_name || (a.alert_type === "offline" ? "DEVICE OFFLINE" : "ALERT TRIGGERED")}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 900, background: `${t.color}20`, color: t.color, borderRadius: 999, padding: "4px 10px", border: `1px solid ${t.color}40`, textTransform: "uppercase" }}>
                    {t.label}
                  </span>
                  {userRole === "superadmin" && (
                    <span style={{ fontSize: 11, fontWeight: 800, background: "rgba(59,158,255,0.10)", color: "#3b9eff", borderRadius: 999, padding: "4px 10px", border: "1px solid rgba(59,158,255,0.20)" }}>
                      {a.client_name || "—"}
                    </span>
                  )}
                </div>

                <div style={{ fontSize: 14, color: "#cbd5e1", fontWeight: 600, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                  <span style={{ color: "#fff", fontWeight: 900 }}>{a.device_name || "—"}</span>
                  {a.serial_number && (
                    <span style={{ fontSize: 12, background: "rgba(255,255,255,0.10)", padding: "3px 8px", borderRadius: 8, color: "#94a3b8", fontFamily: "monospace" }}>
                      SN: {a.serial_number}
                    </span>
                  )}
                  {a.mac_address && (
                    <span style={{ fontSize: 12, background: "rgba(255,255,255,0.10)", padding: "3px 8px", borderRadius: 8, color: "#94a3b8", fontFamily: "monospace" }}>
                      MAC: {a.mac_address}
                    </span>
                  )}
                  <code style={{ color: "#64748b", fontSize: 12, background: "rgba(0,0,0,0.30)", padding: "3px 8px", borderRadius: 8 }}>
                    {a.host}
                  </code>
                </div>

                {(a.device_location || a.device_description) && (
                  <div style={{ marginTop: 10, fontSize: 13, color: "#94a3b8", display: "flex", flexWrap: "wrap", gap: 10 }}>
                    {a.device_location && (
                      <span style={{ background: "rgba(0,242,255,0.08)", border: "1px solid rgba(0,242,255,0.18)", color: "#b6fbff", padding: "4px 10px", borderRadius: 999, fontWeight: 800 }}>
                        {a.device_location}
                      </span>
                    )}
                    {a.device_description && (
                      <span style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.10)", padding: "4px 10px", borderRadius: 12, color: "#e2e8f0", fontWeight: 700 }}>
                        {a.device_description}
                      </span>
                    )}
                  </div>
                )}

                <div style={{ marginTop: 10, fontSize: 12, color: "#64748b", fontWeight: 700, letterSpacing: "0.5px", textTransform: "uppercase" }}>
                  {metricLabel}
                </div>
              </div>

              {a.expression !== "offline" && valueNum != null && thresholdNum != null && (
                <div style={{ textAlign: "right", minWidth: 140, background: "rgba(0,0,0,0.22)", padding: "10px 14px", borderRadius: 14, border: "1px solid rgba(255,255,255,0.04)" }}>
                  <div style={{ fontSize: 22, fontWeight: 900, color: t.color, textShadow: `0 0 10px ${t.color}66` }}>
                    {Number.isFinite(valueNum) ? valueNum.toFixed(1) : "—"}<span style={{ fontSize: 14, opacity: 0.8 }}>{unit}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "#64748b", fontWeight: 800, marginTop: 2, textTransform: "uppercase" }}>
                    limite {Number.isFinite(thresholdNum) ? thresholdNum.toFixed(0) : "—"}{unit}
                  </div>
                </div>
              )}

              <div style={{ textAlign: "right", minWidth: 160, borderLeft: "1px solid rgba(255,255,255,0.06)", paddingLeft: 16 }}>
                <div style={{ fontSize: 14, color: "#cbd5e1", fontWeight: 800, marginBottom: 4 }}>
                  {new Date(a.fired_at).toLocaleDateString("pt-BR")}
                </div>
                <div style={{ fontSize: 13, color: "#64748b", fontFamily: "monospace" }}>
                  {new Date(a.fired_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Automation Page ───────────────────────────────────────────
const EVENT_SUGGESTIONS = [
  "video_loss","video_recovery","device_offline","device_online",
  "ai_person_detected","ai_fall_detected","ai_zone_intrusion","ai_line_crossing",
  "ai_crowd_alert","ai_loitering","ai_abandoned_object","ai_people_enter","ai_people_exit",
  "heartbeat_timeout",
];

function emptyCondition() { return { event_type: "", device_id: "", channel: "", severity: "" }; }
function emptyForm() {
  return {
    name: "", enabled: true, client_id: "",
    rule: {
      within_seconds: 30, cooldown_seconds: 300,
      if_all: [emptyCondition()], if_not: [], actions: ["notify"], message: "",
    },
  };
}

function ConditionRow({ cond, onChange, onRemove, canRemove }) {
  const inp = (field, val) => onChange({ ...cond, [field]: val });
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
      <input
        list="evt-suggestions" placeholder="event_type *" value={cond.event_type}
        onChange={(e) => inp("event_type", e.target.value)}
        style={{ ...S.input, flex: "1 1 160px", minWidth: 140, fontSize: 12, padding: "6px 10px" }}
      />
      <datalist id="evt-suggestions">{EVENT_SUGGESTIONS.map((e) => <option key={e} value={e} />)}</datalist>
      <input placeholder="device_id" type="number" value={cond.device_id}
        onChange={(e) => inp("device_id", e.target.value)}
        style={{ ...S.input, width: 90, fontSize: 12, padding: "6px 8px" }} />
      <input placeholder="canal" type="number" value={cond.channel}
        onChange={(e) => inp("channel", e.target.value)}
        style={{ ...S.input, width: 70, fontSize: 12, padding: "6px 8px" }} />
      <select value={cond.severity} onChange={(e) => inp("severity", e.target.value)}
        style={{ ...S.select, width: 90, fontSize: 12, padding: "6px 8px" }}>
        <option value="">qualquer</option>
        <option value="info">info</option>
        <option value="warn">warn</option>
        <option value="critical">critical</option>
      </select>
      {canRemove && (
        <button type="button" onClick={onRemove}
          style={{ ...S.btnSm("danger"), padding: "4px 8px", fontSize: 14, lineHeight: 1 }}>✕</button>
      )}
    </div>
  );
}

function AutomationPage({ userRole, userClientId }) {
  const [rules, setRules] = useState([]);
  const [clients, setClients] = useState([]);
  const [modal, setModal] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    api("/automation-rules").then((d) => setRules(Array.isArray(d) ? d : [])).catch(() => {});
    if (userRole === "superadmin") {
      api("/clients").then((d) => setClients(Array.isArray(d) ? d : [])).catch(() => {});
    }
  }, [userRole]);

  useEffect(() => { load(); }, [load]);

  const setRule = (patch) => setForm((f) => ({ ...f, rule: { ...f.rule, ...patch } }));

  const updateCond = (list, idx, val) => list.map((c, i) => i === idx ? val : c);
  const addCond = (list) => [...list, emptyCondition()];
  const removeCond = (list, idx) => list.filter((_, i) => i !== idx);

  const openNew = () => { setForm(emptyForm()); setModal({}); };
  const openEdit = (r) => {
    setForm({
      name: r.name, enabled: r.enabled, client_id: r.client_id || "",
      rule: {
        within_seconds: r.rule?.within_seconds ?? 30,
        cooldown_seconds: r.rule?.cooldown_seconds ?? 300,
        if_all: r.rule?.if_all?.length ? r.rule.if_all.map((c) => ({
          event_type: c.event_type || "", device_id: c.device_id ?? "", channel: c.channel ?? "", severity: c.severity || "",
        })) : [emptyCondition()],
        if_not: (r.rule?.if_not || []).map((c) => ({
          event_type: c.event_type || "", device_id: c.device_id ?? "", channel: c.channel ?? "", severity: c.severity || "",
        })),
        actions: r.rule?.actions || ["notify"],
        message: r.rule?.message || "",
      },
    });
    setModal(r);
  };

  const normConds = (list) => list
    .filter((c) => c.event_type.trim())
    .map((c) => {
      const out = { event_type: c.event_type.trim() };
      if (c.device_id !== "" && c.device_id !== null) out.device_id = parseInt(c.device_id);
      if (c.channel !== "" && c.channel !== null) out.channel = parseInt(c.channel);
      if (c.severity) out.severity = c.severity;
      return out;
    });

  const save = async () => {
    const ifAll = normConds(form.rule.if_all);
    if (!form.name.trim()) return alert("Nome obrigatório.");
    if (ifAll.length === 0) return alert("Adicione ao menos uma condição SE.");
    setSaving(true);
    try {
      const body = {
        name: form.name.trim(),
        enabled: form.enabled,
        client_id: form.client_id ? parseInt(form.client_id) : (userClientId || null),
        rule: {
          within_seconds: Number(form.rule.within_seconds) || 30,
          cooldown_seconds: Number(form.rule.cooldown_seconds) || 300,
          if_all: ifAll,
          if_not: normConds(form.rule.if_not),
          actions: ["notify"],
          message: form.rule.message.trim(),
        },
      };
      if (modal?.id) {
        await api(`/automation-rules/${modal.id}`, { method: "PUT", body: JSON.stringify(body) });
      } else {
        await api("/automation-rules", { method: "POST", body: JSON.stringify(body) });
      }
      setModal(null);
      load();
    } catch (e) {
      alert("Erro ao salvar: " + (e?.message || e));
    } finally {
      setSaving(false);
    }
  };

  const del = async (id) => {
    if (!confirm("Remover esta regra?")) return;
    await api(`/automation-rules/${id}`, { method: "DELETE" });
    load();
  };

  const toggle = async (r) => {
    await api(`/automation-rules/${r.id}`, {
      method: "PUT",
      body: JSON.stringify({ name: r.name, enabled: !r.enabled, rule: r.rule }),
    });
    load();
  };

  const condSummary = (rule) => {
    const parts = (rule?.if_all || []).map((c) => {
      let s = c.event_type || "?";
      if (c.device_id) s += ` dev=${c.device_id}`;
      if (c.channel !== undefined && c.channel !== "") s += ` ch=${c.channel}`;
      return s;
    });
    return parts.join(" + ") || "—";
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={S.pageTitle}>⚙️ Automação</div>
          <div style={S.pageSub}>Regras de automação — {rules.length} configurada(s)</div>
        </div>
        <button style={S.btn("primary")} onClick={openNew}>+ Nova Regra</button>
      </div>

      <div style={{ ...S.card, overflowX: "auto", padding: 0 }}>
        <table style={{ ...S.table, margin: 0, borderSpacing: 0 }}>
          <thead>
            <tr>
              {["Status","Nome","Condições SE","Janela","Cooldown", userRole === "superadmin" ? "Cliente" : null,"Ações"]
                .filter(Boolean).map((h) => <th key={h} style={{ ...S.th, padding: "14px 16px" }}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rules.length === 0 && (
              <tr><td colSpan={7} style={{ ...S.td, textAlign: "center", color: "#3a5070", padding: 40 }}>
                Nenhuma regra configurada — clique em "+ Nova Regra" para começar
              </td></tr>
            )}
            {rules.map((r, i) => (
              <tr key={r.id} style={{ background: i % 2 === 0 ? "transparent" : "rgba(11,21,37,0.35)" }}>
                <td style={{ ...S.td, border: "none", padding: "14px 16px" }}>
                  <span style={S.badge(r.enabled ? "#22c55e" : "#4a6080")}>{r.enabled ? "● ativo" : "○ inativo"}</span>
                </td>
                <td style={{ ...S.td, border: "none", fontWeight: 700, color: "#f1f5f9", fontSize: 14 }}>{r.name}</td>
                <td style={{ ...S.td, border: "none", color: "#94a3b8", fontSize: 12, maxWidth: 260 }}>
                  <span style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {condSummary(r.rule)}
                  </span>
                </td>
                <td style={{ ...S.td, border: "none", color: "#cbd5e1", textAlign: "center" }}>
                  {r.rule?.within_seconds ?? "—"}s
                </td>
                <td style={{ ...S.td, border: "none", color: "#cbd5e1", textAlign: "center" }}>
                  {r.rule?.cooldown_seconds ?? "—"}s
                </td>
                {userRole === "superadmin" && (
                  <td style={{ ...S.td, border: "none" }}>
                    <span style={{ fontSize: 11, color: "#3b9eff", fontWeight: 700 }}>
                      {clients.find((c) => c.id === r.client_id)?.name || `#${r.client_id || "—"}`}
                    </span>
                  </td>
                )}
                <td style={{ ...S.td, border: "none" }}>
                  <div style={{ display: "flex", gap: 6 }}>
                    <button style={S.btnSm(r.enabled ? "ghost" : "primary")} onClick={() => toggle(r)}>{r.enabled ? "⏸" : "▶️"}</button>
                    <button style={S.btnSm()} onClick={() => openEdit(r)}>✏️</button>
                    <button style={S.btnSm("danger")} onClick={() => del(r.id)}>🗑️</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal !== null && (
        <div style={S.modal} onClick={() => setModal(null)}>
          <div style={{ ...S.modalBox, width: 560, maxHeight: "90vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalTitle}>{modal?.id ? "✏️ Editar Regra" : "➕ Nova Regra de Automação"}</div>

            {/* Nome e status */}
            <div style={{ display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 14 }}>
              <div style={{ ...S.fg, flex: 1 }}>
                <label style={S.label}>Nome da regra *</label>
                <input style={S.input} value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Ex: Câmera perdida + pessoa detectada" />
              </div>
              <div style={{ ...S.fg, flexShrink: 0 }}>
                <label style={S.label}>Status</label>
                <select style={S.select} value={form.enabled ? "1" : "0"} onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.value === "1" }))}>
                  <option value="1">● Ativo</option>
                  <option value="0">○ Inativo</option>
                </select>
              </div>
            </div>

            {/* Janela e cooldown */}
            <div style={{ display: "flex", gap: 10, marginBottom: 14 }}>
              <div style={{ ...S.fg, flex: 1 }}>
                <label style={S.label}>Janela de tempo (segundos)</label>
                <input style={S.input} type="number" min={1} value={form.rule.within_seconds}
                  onChange={(e) => setRule({ within_seconds: e.target.value })} />
                <div style={{ fontSize: 10, color: "#3a5a80", marginTop: 3 }}>Eventos devem ocorrer dentro deste intervalo</div>
              </div>
              <div style={{ ...S.fg, flex: 1 }}>
                <label style={S.label}>Cooldown (segundos)</label>
                <input style={S.input} type="number" min={1} value={form.rule.cooldown_seconds}
                  onChange={(e) => setRule({ cooldown_seconds: e.target.value })} />
                <div style={{ fontSize: 10, color: "#3a5a80", marginTop: 3 }}>Intervalo mínimo entre ativações</div>
              </div>
            </div>

            {/* Condições SE */}
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <label style={{ ...S.label, marginBottom: 0 }}>SE todos ocorrerem *</label>
                <button type="button" style={S.btnSm("primary")} onClick={() => setRule({ if_all: addCond(form.rule.if_all) })}>+ Condição</button>
              </div>
              {form.rule.if_all.map((c, i) => (
                <ConditionRow key={i} cond={c}
                  onChange={(v) => setRule({ if_all: updateCond(form.rule.if_all, i, v) })}
                  onRemove={() => setRule({ if_all: removeCond(form.rule.if_all, i) })}
                  canRemove={form.rule.if_all.length > 1} />
              ))}
            </div>

            {/* Condições SE NÃO */}
            <div style={{ marginBottom: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <label style={{ ...S.label, marginBottom: 0, color: "#94a3b8" }}>MAS NÃO (opcional)</label>
                <button type="button" style={S.btnSm("ghost")} onClick={() => setRule({ if_not: addCond(form.rule.if_not) })}>+ Exceção</button>
              </div>
              {form.rule.if_not.length === 0 && (
                <div style={{ fontSize: 11, color: "#3a5070", fontStyle: "italic" }}>Nenhuma exceção — a regra dispara sempre que as condições acima forem atendidas</div>
              )}
              {form.rule.if_not.map((c, i) => (
                <ConditionRow key={i} cond={c}
                  onChange={(v) => setRule({ if_not: updateCond(form.rule.if_not, i, v) })}
                  onRemove={() => setRule({ if_not: removeCond(form.rule.if_not, i) })}
                  canRemove={true} />
              ))}
            </div>

            {/* Mensagem */}
            <div style={{ ...S.fg, marginBottom: 14 }}>
              <label style={S.label}>Mensagem (opcional)</label>
              <textarea style={{ ...S.input, height: 60, resize: "vertical", fontFamily: "monospace", fontSize: 12 }}
                value={form.rule.message}
                onChange={(e) => setRule({ message: e.target.value })}
                placeholder="Ex: ⚠️ Cam {e0.device_id} perdida e pessoa detectada" />
              <div style={{ fontSize: 10, color: "#3a5a80", marginTop: 3 }}>
                Variáveis: {"{e0.event_type}"} {"{e0.device_id}"} {"{e0.channel}"} {"{e0.severity}"}
              </div>
            </div>

            {/* Cliente (superadmin) */}
            {userRole === "superadmin" && (
              <div style={{ ...S.fg, marginBottom: 14 }}>
                <label style={S.label}>Cliente</label>
                <select style={S.select} value={form.client_id} onChange={(e) => setForm((f) => ({ ...f, client_id: e.target.value }))}>
                  <option value="">— selecione —</option>
                  {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
            )}

            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 4 }}>
              <button style={S.btn("ghost")} onClick={() => setModal(null)}>Cancelar</button>
              <button style={S.btn("primary")} onClick={save} disabled={saving}>{saving ? "Salvando..." : "Salvar Regra"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Triggers Page ─────────────────────────────────────────────
function TriggersPage({ userRole }) {
  const [triggers, setTriggers] = useState([]);
  const [clients, setClients] = useState([]);
  const [modal, setModal] = useState(null);
  const [form, setForm] = useState({ name: "", expression: "cpu", threshold: 80, enabled: true, device_type: "", tags: [], client_id: null });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const load = () => {
    api("/triggers").then(setTriggers).catch(() => {});
    if (userRole === "superadmin") api("/clients").then(setClients).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!form.name) return;
    try {
      if (modal?.id) await api(`/triggers/${modal.id}`, { method: "PUT", body: JSON.stringify(form) });
      else await api("/triggers", { method: "POST", body: JSON.stringify(form) });
      load(); setModal(null);
    } catch {}
  };

  const del = async (id) => { if (!confirm("Remover?")) return; await api(`/triggers/${id}`, { method: "DELETE" }); load(); };
  const toggle = async (t) => { await api(`/triggers/${t.id}`, { method: "PUT", body: JSON.stringify({ ...t, enabled: !t.enabled }) }); load(); };

  const openNew = () => { setForm({ name: "", expression: "cpu", threshold: 80, enabled: true, device_type: "", tags: [], client_id: null }); setModal({}); };
  const openEdit = (t) => { setForm({ ...t, tags: t.tags||[] }); setModal(t); };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div><div style={S.pageTitle}>⚡ Triggers</div><div style={S.pageSub}>Regras de alerta automático</div></div>
        <button style={S.btn("primary")} onClick={openNew}>+ Novo Trigger</button>
      </div>

      <div style={{ ...S.card, overflowX: "auto", padding: 0 }}>
        <table style={{ ...S.table, margin: 0, borderSpacing: 0 }}>
          <thead><tr>{["Status","Nome","Métrica","Limite",userRole==="superadmin"?"Cliente":null,"Ações"].filter(Boolean).map((h) => <th key={h} style={{ ...S.th, padding: "16px 20px" }}>{h}</th>)}</tr></thead>
          <tbody>
            {triggers.length === 0 && <tr><td colSpan={6} style={{ ...S.td, textAlign: "center", color: "#3a5070", padding: 40 }}>Nenhum trigger configurado</td></tr>}
            {triggers.map((t, i) => (
              <tr key={t.id} style={{ background: i % 2 === 0 ? "transparent" : "rgba(11,21,37,0.35)" }}>
                <td style={{ ...S.td, border: "none", padding: "16px 20px" }}><span style={S.badge(t.enabled?"#22c55e":"#4a6080")}>{t.enabled?"● ativo":"○ inativo"}</span></td>
                <td style={{ ...S.td, border: "none", fontWeight: 700, color: "#f1f5f9", fontSize: 14 }}>{t.name}</td>
                <td style={{ ...S.td, border: "none", color: "#cbd5e1" }}>{EXPRESSIONS.find((e) => e.value===t.expression)?.label||t.expression}</td>
                <td style={{ ...S.td, border: "none", color: "#f59e0b", fontWeight: 800, fontSize: 15 }}>{t.threshold}</td>
                {userRole === "superadmin" && <td style={{ ...S.td, border: "none" }}><span style={{ fontSize: 11, color: "#3b9eff", fontWeight: 700 }}>{clients.find((c) => c.id===t.client_id)?.name||"Todos"}</span></td>}
                <td style={{ ...S.td, border: "none" }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button style={S.btnSm(t.enabled ? "ghost" : "primary")} onClick={() => toggle(t)}>{t.enabled?"⏸":"▶️"}</button>
                    <button style={S.btnSm()} onClick={() => openEdit(t)}>✏️</button>
                    <button style={S.btnSm("danger")} onClick={() => del(t.id)}>🗑️</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal !== null && (
        <div style={S.modal} onClick={() => setModal(null)}>
          <div style={{ ...S.modalBox, width: 420 }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalTitle}>{modal?.id ? "✏️ Editar Trigger" : "➕ Novo Trigger"}</div>
            <div style={S.fg}><label style={S.label}>Nome *</label><input style={S.input} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="CPU Alta — Servidor" /></div>
            <div style={S.grid(2)}>
              <div style={S.fg}><label style={S.label}>Métrica</label>
                <select style={S.select} value={form.expression} onChange={(e) => set("expression", e.target.value)}>
                  {EXPRESSIONS.map((e) => <option key={e.value} value={e.value}>{e.label}</option>)}
                </select>
              </div>
              <div style={S.fg}><label style={S.label}>Limite</label><input style={S.input} type="number" value={form.threshold} onChange={(e) => set("threshold", parseFloat(e.target.value))} /></div>
            </div>
            {userRole === "superadmin" && (
              <div style={S.fg}><label style={S.label}>Aplicar ao cliente</label>
                <select style={S.select} value={form.client_id||""} onChange={(e) => set("client_id", e.target.value?parseInt(e.target.value):null)}>
                  <option value="">Todos os clientes</option>
                  {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
            )}
            <div style={S.fg}><label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#b8cfe8", cursor: "pointer", fontWeight: 700 }}><input type="checkbox" style={{ accentColor: "#3b9eff", transform: "scale(1.2)" }} checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Trigger ativo</label></div>
            <div style={{ display: "flex", gap: 12, justifyContent: "flex-end", marginTop: 24 }}>
              <button style={S.btn("ghost")} onClick={() => setModal(null)}>Cancelar</button>
              <button style={S.btn("primary")} onClick={save}>Salvar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Solar ─────────────────────────────────────────────────────
const BRANDS = [
  { value: "growatt",  label: "Growatt",           icon: "🟠" },
  { value: "fronius",  label: "Fronius",            icon: "🔵" },
  { value: "deye",     label: "Deye",               icon: "🟡" },
  { value: "solis",    label: "Solis",              icon: "🟤" },
  { value: "sma",      label: "SMA",                icon: "⚫" },
  { value: "goodwe",   label: "GoodWe",             icon: "🟢" },
  { value: "huawei",   label: "Huawei FusionSolar", icon: "🔴" },
  { value: "canadian", label: "Canadian Solar",     icon: "🍁" },
  { value: "saj",      label: "SAJ elekeeper",      icon: "🟡" },
  { value: "risen",    label: "Risen Energy",       icon: "🌟" },
  { value: "other",    label: "Outro (Genérico)",   icon: "☀️" },
];

const brandIcon  = (b) => BRANDS.find((x) => x.value === b)?.icon || "☀️";
const brandLabel = (b) => BRANDS.find((x) => x.value === b)?.label || b;

const EMPTY_INVERTER = {
  name: "", brand: "growatt", model: "", location: "",
  capacity_kwp: "", tariff_kwh: "0.85", client_id: null,
  growatt_user: "", growatt_pass: "", growatt_plant_id: "",
  fronius_ip: "", fronius_device_id: 1,
  solarman_token: "", solarman_app_id: "", solarman_logger_sn: "",
  sma_user: "", sma_pass: "", sma_plant_id: "",
  goodwe_user: "", goodwe_pass: "", goodwe_station_id: "",
  huawei_user: "", huawei_pass: "", huawei_station_id: "",
  saj_user: "", saj_pass: "", saj_plant_id: "",
  api_url: "", api_key: "", notes: "",
};

function InverterModal({ inverter, clients, userRole, onSave, onClose }) {
  const [form, setForm] = useState(inverter || { ...EMPTY_INVERTER });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    if (!form.name || !form.brand) return setErr("Nome e marca obrigatórios");
    setLoading(true); setErr("");
    try {
      if (inverter?.id) await api(`/solar/inverters/${inverter.id}`, { method: "PUT", body: JSON.stringify(form) });
      else await api("/solar/inverters", { method: "POST", body: JSON.stringify(form) });
      onSave();
    } catch (e) { setErr(e.error || "Erro ao salvar"); }
    finally { setLoading(false); }
  };

  const brand = form.brand;

  return (
    <div style={S.modal} onClick={onClose}>
      <div style={{ ...S.modalBox, width: 560 }} onClick={(e) => e.stopPropagation()}>
        <div style={S.modalTitle}>{inverter?.id ? "✏️ Editar Inversor" : "➕ Novo Inversor Solar"}</div>

        <div style={S.sectionTitle}>Identificação</div>
        {userRole === "superadmin" && clients && (
          <div style={S.fg}><label style={S.label}>Cliente</label>
            <select style={S.select} value={form.client_id||""} onChange={(e) => set("client_id", e.target.value ? parseInt(e.target.value) : null)}>
              <option value="">Sem cliente</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
        )}

        <div style={S.grid(2)}>
          <div style={S.fg}><label style={S.label}>Nome *</label>
            <input style={S.input} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Solar - Empresa ABC" />
          </div>
          <div style={S.fg}><label style={S.label}>Marca *</label>
            <select style={S.select} value={form.brand} onChange={(e) => set("brand", e.target.value)}>
              {BRANDS.map((b) => <option key={b.value} value={b.value}>{b.icon} {b.label}</option>)}
            </select>
          </div>
        </div>

        <div style={S.grid(2)}>
          <div style={S.fg}><label style={S.label}>Modelo</label>
            <input style={S.input} value={form.model} onChange={(e) => set("model", e.target.value)} placeholder="ex: MIN 5000TL-X" />
          </div>
          <div style={S.fg}><label style={S.label}>Localização</label>
            <input style={S.input} value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="ex: Telhado principal" />
          </div>
        </div>

        <div style={S.grid(2)}>
          <div style={S.fg}><label style={S.label}>Capacidade instalada (kWp)</label>
            <input style={S.input} type="number" value={form.capacity_kwp} onChange={(e) => set("capacity_kwp", e.target.value)} placeholder="ex: 5.5" />
          </div>
          <div style={S.fg}><label style={S.label}>Tarifa R$/kWh</label>
            <input style={S.input} type="number" step="0.01" value={form.tariff_kwh} onChange={(e) => set("tariff_kwh", e.target.value)} placeholder="0.85" />
            <span style={{ fontSize: 9, color: "#3a5070" }}>Usado para calcular receita</span>
          </div>
        </div>

        <div style={S.divider} />

        <div style={S.sectionTitle}>{brandIcon(brand)} Configuração {brandLabel(brand)}</div>

        {brand === "growatt" && (
          <>
            <div style={S.fg}><label style={S.label}>Usuário ShineServer</label>
              <input style={S.input} value={form.growatt_user} onChange={(e) => set("growatt_user", e.target.value)} placeholder="seu@email.com" />
            </div>
            <div style={S.fg}><label style={S.label}>Senha ShineServer</label>
              <input style={S.input} type="password" value={form.growatt_pass} onChange={(e) => set("growatt_pass", e.target.value)} placeholder="••••••••" />
            </div>
            <div style={S.fg}><label style={S.label}>Plant ID (opcional — deixe vazio para auto)</label>
              <input style={S.input} value={form.growatt_plant_id} onChange={(e) => set("growatt_plant_id", e.target.value)} placeholder="Auto detectado" />
            </div>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, fontSize: 10, color: "#4a6080" }}>
              💡 Acesse <b>server.growatt.com</b> para obter suas credenciais
            </div>
          </>
        )}

        {brand === "fronius" && (
          <>
            <div style={S.fg}><label style={S.label}>IP do Inversor na rede local</label>
              <input style={S.input} value={form.fronius_ip} onChange={(e) => set("fronius_ip", e.target.value)} placeholder="192.168.1.150" />
            </div>
            <div style={S.fg}><label style={S.label}>Device ID (padrão: 1)</label>
              <input style={S.input} type="number" value={form.fronius_device_id} onChange={(e) => set("fronius_device_id", parseInt(e.target.value)||1)} />
            </div>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, fontSize: 10, color: "#4a6080" }}>
              💡 O Fronius precisa estar na mesma rede. Acesse o IP pelo navegador para confirmar
            </div>
          </>
        )}

        {(brand === "deye" || brand === "solis") && (
          <>
            <div style={S.fg}><label style={S.label}>SolarmanPV Token</label>
              <input style={S.input} value={form.solarman_token} onChange={(e) => set("solarman_token", e.target.value)} placeholder="Token da API SolarmanPV" />
            </div>
            <div style={S.fg}><label style={S.label}>App ID</label>
              <input style={S.input} value={form.solarman_app_id} onChange={(e) => set("solarman_app_id", e.target.value)} placeholder="App ID SolarmanPV" />
            </div>
            <div style={S.fg}><label style={S.label}>Logger Serial Number</label>
              <input style={S.input} value={form.solarman_logger_sn} onChange={(e) => set("solarman_logger_sn", e.target.value)} placeholder="Número de série do datalogger" />
            </div>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, fontSize: 10, color: "#4a6080" }}>
              💡 Acesse <b>home.solarmanpv.com</b> → API → Gerar token. O Logger SN está no app ou no equipamento
            </div>
          </>
        )}

        {brand === "sma" && (
          <>
            <div style={S.fg}><label style={S.label}>IP do Inversor SMA (rede local)</label>
              <input style={S.input} value={form.api_url} onChange={(e) => set("api_url", e.target.value)} placeholder="192.168.1.151" />
            </div>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, fontSize: 10, color: "#4a6080" }}>
              💡 SMA Sunny Boy/Tripower com WebConnect. Habilite o acesso na interface web do inversor
            </div>
          </>
        )}

        {brand === "goodwe" && (
          <>
            <div style={S.fg}><label style={S.label}>Usuário SEMS Portal</label>
              <input style={S.input} value={form.goodwe_user} onChange={(e) => set("goodwe_user", e.target.value)} placeholder="seu@email.com" />
            </div>
            <div style={S.fg}><label style={S.label}>Senha SEMS Portal</label>
              <input style={S.input} type="password" value={form.goodwe_pass} onChange={(e) => set("goodwe_pass", e.target.value)} placeholder="••••••••" />
            </div>
            <div style={S.fg}><label style={S.label}>Station ID</label>
              <input style={S.input} value={form.goodwe_station_id} onChange={(e) => set("goodwe_station_id", e.target.value)} placeholder="ID da planta no SEMS" />
            </div>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, fontSize: 10, color: "#4a6080" }}>
              💡 Acesse <b>www.semsportal.com</b> para obter suas credenciais e Station ID
            </div>
          </>
        )}

        {brand === "huawei" && (
          <>
            <div style={S.fg}><label style={S.label}>Usuário FusionSolar</label>
              <input style={S.input} value={form.huawei_user} onChange={(e) => set("huawei_user", e.target.value)} placeholder="seu@email.com" />
            </div>
            <div style={S.fg}><label style={S.label}>Senha FusionSolar</label>
              <input style={S.input} type="password" value={form.huawei_pass} onChange={(e) => set("huawei_pass", e.target.value)} placeholder="••••••••" />
            </div>
            <div style={S.fg}><label style={S.label}>Station ID</label>
              <input style={S.input} value={form.huawei_station_id} onChange={(e) => set("huawei_station_id", e.target.value)} placeholder="ID da planta FusionSolar" />
            </div>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, fontSize: 10, color: "#4a6080" }}>
              💡 Acesse <b>intl.fusionsolar.huawei.com</b> para obter suas credenciais
            </div>
          </>
        )}

        {brand === "saj" && (
          <>
            <div style={S.sectionTitle}>⚙️ Configuração SAJ elekeeper</div>
            <div style={S.fg}><label style={S.label}>E-mail / Usuário elekeeper</label>
              <input style={S.input} value={form.saj_user||""} onChange={(e) => set("saj_user", e.target.value)} placeholder="seu@email.com" />
            </div>
            <div style={S.fg}><label style={S.label}>Senha elekeeper</label>
              <input style={S.input} type="password" value={form.saj_pass||""} onChange={(e) => set("saj_pass", e.target.value)} placeholder="••••••••" />
            </div>
            <div style={S.fg}><label style={S.label}>Plant ID (opcional — auto detectado)</label>
              <input style={S.input} value={form.saj_plant_id||""} onChange={(e) => set("saj_plant_id", e.target.value)} placeholder="Auto detectado" />
            </div>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, fontSize: 10, color: "#4a6080" }}>
              💡 Acesse <b>eop.saj-electric.com</b> e crie uma conta gratuita. Não precisa de instalador!
            </div>
          </>
        )}

        {(brand === "canadian" || brand === "risen" || brand === "other") && (
          <>
            <div style={S.fg}><label style={S.label}>URL da API (endpoint JSON)</label>
              <input style={S.input} value={form.api_url} onChange={(e) => set("api_url", e.target.value)} placeholder="http://192.168.1.100/api/data" />
            </div>
            <div style={S.fg}><label style={S.label}>API Key (se necessário)</label>
              <input style={S.input} value={form.api_key} onChange={(e) => set("api_key", e.target.value)} placeholder="Token ou chave de API" />
            </div>
            <div style={{ ...S.fg, background: "#0d1520", borderRadius: 6, padding: 10, fontSize: 10, color: "#4a6080" }}>
              💡 O sistema tentará extrair automaticamente: power_w, energy_today, energy_total da resposta JSON
            </div>
          </>
        )}

        <div style={S.divider} />
        <div style={S.fg}><label style={S.label}>Notas</label>
          <textarea style={{ ...S.input, minHeight: 50, resize: "vertical" }} value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Informações adicionais..." />
        </div>

        {err && <div style={{ color: "#ef4444", fontSize: 11, marginBottom: 10 }}>⚠️ {err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button style={S.btn("ghost")} onClick={onClose}>Cancelar</button>
          <button style={S.btn("primary")} onClick={save} disabled={loading}>{loading ? "..." : "Salvar Inversor"}</button>
        </div>
      </div>
    </div>
  );
}

function SolarPage({ userRole }) {
  const [inverters, setInverters] = useState([]);
  const [clients, setClients] = useState([]);
  const [summary, setSummary] = useState({ total_inverters: 0, total_power_w: 0, energy_today_kwh: 0, revenue_today: 0 });
  const [health, setHealth] = useState(null);
  const [modal, setModal] = useState(null);
  const [filter, setFilter] = useState({ brand: "", client: "" });

  const load = useCallback(() => {
    api("/solar/inverters").then(setInverters).catch(() => {});
    api("/solar/summary").then(setSummary).catch(() => {});
    api("/solar/health").then(setHealth).catch(() => {});
    if (userRole === "superadmin") api("/clients").then(setClients).catch(() => {});
  }, [userRole]);

  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);

  const del = async (id) => { if (!confirm("Remover inversor?")) return; await api(`/solar/inverters/${id}`, { method: "DELETE" }); load(); };

  const filtered = inverters.filter((inv) => {
    if (filter.brand && inv.brand !== filter.brand) return false;
    if (filter.client && String(inv.client_id) !== filter.client) return false;
    return true;
  });

  const statusColor = { generating: "#22c55e", idle: "#f59e0b", offline: "#ef4444", fault: "#ef4444", unknown: "#3a5070" };
  const statusLabel = { generating: "⚡ Gerando", idle: "😴 Aguardando", offline: "🔴 Offline", fault: "⚠️ Falha", unknown: "❓ Desconhecido" };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <div style={S.pageTitle}>☀️ Solar</div>
          <div style={S.pageSub}>Monitoramento de inversores fotovoltaicos</div>
        </div>
        <button style={S.btn("primary")} onClick={() => setModal("new")}>+ Novo Inversor</button>
      </div>

      <div style={S.grid(4)}>
        {[
          { label: "Inversores", value: summary.total_inverters, color: "#f59e0b", suffix: "" },
          { label: "Potência Atual", value: (summary.total_power_w/1000).toFixed(2), color: "#3b9eff", suffix: " kW" },
          { label: "Energia Hoje", value: (summary.energy_today_kwh||0).toFixed(2), color: "#22c55e", suffix: " kWh" },
          { label: "Receita Hoje", value: `R$ ${(summary.revenue_today||0).toFixed(2)}`, color: "#a78bfa", suffix: "" },
        ].map((s) => (
          <div key={s.label} style={S.statCard(s.color)}>
            <div style={S.statVal(s.color)}>{s.value}{s.suffix}</div>
            <div style={S.statLabel}>{s.label}</div>
          </div>
        ))}
      </div>

      {health && summary.total_inverters > 0 && health.with_data === 0 && (
        <div style={{ ...S.card, marginBottom: 16, border: "1px solid rgba(239, 68, 68, 0.35)", background: "rgba(127, 29, 29, 0.15)" }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: "#fecaca", marginBottom: 6 }}>AVISO: Sem métricas solares</div>
          <div style={{ fontSize: 11, color: "#fca5a5" }}>
            O coletor solar parece não estar rodando ou não consegue autenticar. Verifique o serviço Processor (solar_monitor.py) e as credenciais do inversor.
          </div>
        </div>
      )}

      {health && summary.total_inverters > 0 && health.with_data > 0 && health.reporting_15m === 0 && (
        <div style={{ ...S.card, marginBottom: 16, border: "1px solid rgba(245, 158, 11, 0.35)", background: "rgba(120, 53, 15, 0.15)" }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: "#fde68a", marginBottom: 6 }}>AVISO: Coleta solar atrasada</div>
          <div style={{ fontSize: 11, color: "#fdba74" }}>
            Existem métricas antigas, mas nenhum inversor reportou nos últimos 15 minutos. Confirme conectividade e credenciais (a API do fabricante pode estar fora).
          </div>
        </div>
      )}

      <div style={{ ...S.card, marginBottom: 16, display: "flex", gap: 10, flexWrap: "wrap" }}>
        <select style={{ ...S.select, maxWidth: 160 }} value={filter.brand} onChange={(e) => setFilter({ ...filter, brand: e.target.value })}>
          <option value="">Todas as marcas</option>
          {BRANDS.map((b) => <option key={b.value} value={b.value}>{b.icon} {b.label}</option>)}
        </select>
        {userRole === "superadmin" && (
          <select style={{ ...S.select, maxWidth: 180 }} value={filter.client} onChange={(e) => setFilter({ ...filter, client: e.target.value })}>
            <option value="">Todos os clientes</option>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        )}
        <span style={{ fontSize: 11, color: "#3a5070", alignSelf: "center" }}>{filtered.length} inversor(es)</span>
      </div>

      <div style={S.grid(3)}>
        {filtered.length === 0 && (
          <div style={{ ...S.card, gridColumn: "1/-1", textAlign: "center", padding: 40, color: "#3a5070" }}>
            ☀️ Nenhum inversor cadastrado. Clique em <b>+ Novo Inversor</b> para começar!
          </div>
        )}
        {filtered.map((inv) => {
          const status = inv.last_status || "unknown";
          const power  = (inv.last_power || 0) / 1000;
          const energy = inv.last_energy_today || 0;
          const revenue = inv.last_revenue_today || 0;
          const totalEnergy = inv.last_energy_total || 0;
          const totalRevenue = inv.last_revenue_total || 0;

          return (
            <div key={inv.id} style={{ ...S.card, border: `1px solid ${statusColor[status]}25` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
                <span style={{ fontSize: 22 }}>{brandIcon(inv.brand)}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9" }}>{inv.name}</div>
                  <div style={{ fontSize: 10, color: "#3a5070" }}>{brandLabel(inv.brand)} {inv.model ? `— ${inv.model}` : ""}</div>
                </div>
                <span style={S.badge(statusColor[status])}>{statusLabel[status] || status}</span>
              </div>

              {inv.location && <div style={{ fontSize: 10, color: "#3a5070", marginBottom: 10 }}>📍 {inv.location}</div>}
              {userRole === "superadmin" && inv.client_name && (
                <div style={{ fontSize: 10, color: "#3b9eff", marginBottom: 10 }}>🏢 {inv.client_name}</div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                {[
                  { label: "Potência", value: `${power.toFixed(2)} kW`, color: "#3b9eff", icon: "⚡" },
                  { label: "Hoje", value: `${energy.toFixed(2)} kWh`, color: "#22c55e", icon: "☀️" },
                  { label: "Receita Hoje", value: `R$ ${revenue.toFixed(2)}`, color: "#a78bfa", icon: "💰" },
                  { label: "Total", value: `${totalEnergy.toFixed(0)} kWh`, color: "#f59e0b", icon: "📊" },
                ].map((m) => (
                  <div key={m.label} style={{ background: "#080c14", borderRadius: 6, padding: 8 }}>
                    <div style={{ fontSize: 9, color: "#3a5070" }}>{m.icon} {m.label}</div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: m.color }}>{m.value}</div>
                  </div>
                ))}
              </div>

              <div style={{ background: "#0d1520", borderRadius: 6, padding: 8, marginBottom: 12, display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: 10, color: "#3a5070" }}>💵 Receita Total Acumulada</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#a78bfa" }}>R$ {totalRevenue.toFixed(2)}</span>
              </div>

              {inv.capacity_kwp > 0 && (
                <div style={{ fontSize: 10, color: "#3a5070", marginBottom: 10 }}>
                  🔋 Capacidade: <b style={{ color: "#94a3b8" }}>{inv.capacity_kwp} kWp</b>
                  {" | "}Tarifa: <b style={{ color: "#94a3b8" }}>R$ {inv.tariff_kwh}/kWh</b>
                </div>
              )}

              {inv.last_update && (
                <div style={{ fontSize: 9, color: "#3a5070", marginBottom: 10 }}>
                  🕐 {new Date(inv.last_update).toLocaleString("pt-BR")}
                </div>
              )}

              <div style={{ display: "flex", gap: 6 }}>
                <button style={{ ...S.btn("ghost"), fontSize: 10, flex: 1 }} onClick={() => setModal(inv)}>✏️ Editar</button>
                <button style={{ ...S.btnSm("danger") }} onClick={() => del(inv.id)}>🗑️</button>
              </div>
            </div>
          );
        })}
      </div>

      {(modal === "new" || (modal && modal.id)) && (
        <InverterModal
          inverter={modal === "new" ? null : modal}
          clients={clients}
          userRole={userRole}
          onSave={() => { load(); setModal(null); }}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  );
}

// ── Portal Admin — visão geral de clientes, OTA e feature flags ──────────────
const FEATURE_DEFS = [
  { key: "ENABLE_AI_ANALYTICS",      label: "IA Analytics (F3-F10)" },
  { key: "ENABLE_FIRE_DETECTION",    label: "🔥 Fogo/Fumaça (F11)" },
  { key: "ENABLE_TAMPER_DETECTION",  label: "🚫 Câmera Sabotada (F12)" },
  { key: "ENABLE_CLIP_RECORDING",    label: "📹 Clips de Vídeo" },
  { key: "ENABLE_DAILY_REPORT",      label: "📊 Relatório Diário" },
  { key: "ENABLE_OTA",               label: "🔄 Atualização OTA" },
  { key: "ENABLE_AI_NARRATIVE",      label: "🤖 Narrativa IA (F2)" },
  { key: "ENABLE_FALL_DETECTION",    label: "🚨 Queda (F10)" },
  { key: "ENABLE_PLATE_RECOGNITION", label: "🚗 Placas (F5)" },
  { key: "ENABLE_AUDIO_ANOMALY",     label: "🔊 Áudio Anômalo (F4)" },
];

function AdminOverviewPage() {
  const [clients, setClients]   = useState([]);
  const [manifests, setManifests] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [savingId, setSavingId] = useState(null);
  const [otaForm, setOtaForm]   = useState({ version: "", download_url: "", sha256: "", notes: "", required: false });
  const [otaSaving, setOtaSaving] = useState(false);
  const [otaErr, setOtaErr]     = useState("");
  const [featMap, setFeatMap]       = useState({});
  const [envPatchMap, setEnvPatchMap] = useState({});
  const [expandedEnvId, setExpandedEnvId] = useState(null);
  const [savingEnvId, setSavingEnvId]     = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [cls, mfs] = await Promise.all([
        api("/admin/clients-status"),
        api("/admin/ota-manifest"),
      ]);
      setClients(Array.isArray(cls) ? cls : []);
      setManifests(Array.isArray(mfs) ? mfs : []);
      const fm = {};
      const epm = {};
      (Array.isArray(cls) ? cls : []).forEach((c) => {
        fm[c.id]  = { ...(c.features  || {}) };
        epm[c.id] = { ...(c.env_patch || {}) };
      });
      setFeatMap(fm);
      setEnvPatchMap(epm);
    } catch { /* silent */ }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const saveFeatures = async (cid) => {
    setSavingId(cid);
    try { await api(`/admin/clients/${cid}/features`, { method: "PUT", body: JSON.stringify({ features: featMap[cid] || {} }) }); }
    catch { /* silent */ }
    setSavingId(null);
  };

  const saveEnvPatch = async (cid) => {
    setSavingEnvId(cid);
    try {
      const patch = {};
      Object.entries(envPatchMap[cid] || {}).forEach(([k, v]) => {
        if (v !== "" && v !== undefined && v !== null) patch[k] = String(v);
      });
      await api(`/admin/clients/${cid}/env-patch`, { method: "PUT", body: JSON.stringify({ env_patch: patch }) });
    } catch { /* silent */ }
    setSavingEnvId(null);
  };

  const setEnvVar = (cid, key, value) =>
    setEnvPatchMap((prev) => ({ ...prev, [cid]: { ...(prev[cid] || {}), [key]: value } }));

  const publishOta = async () => {
    if (!otaForm.version || !otaForm.download_url || !otaForm.sha256) {
      setOtaErr("Versão, URL e SHA256 são obrigatórios."); return;
    }
    setOtaSaving(true); setOtaErr("");
    try {
      await api("/admin/ota-manifest", { method: "PUT", body: JSON.stringify(otaForm) });
      await load();
      setOtaForm({ version: "", download_url: "", sha256: "", notes: "", required: false });
    } catch (e) { setOtaErr(e?.error || "Erro ao publicar manifest."); }
    setOtaSaving(false);
  };

  const deactivateOta = async (id) => {
    if (!confirm("Desativar este manifest?")) return;
    try { await api(`/admin/ota-manifest/${id}`, { method: "DELETE" }); await load(); }
    catch { /* silent */ }
  };

  const activeManifest = manifests.find((m) => m.active);
  const totalOnline    = clients.reduce((s, c) => s + (c.online_count || 0), 0);
  const totalOffline   = clients.reduce((s, c) => s + (c.offline_count || 0), 0);

  const fmtTs = (ts) => {
    if (!ts) return "—";
    const d = new Date(ts);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 120)  return `${Math.round(diff)}s atrás`;
    if (diff < 3600) return `${Math.round(diff / 60)}min atrás`;
    return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  };

  if (loading) return <div style={{ color: "#3b9eff", padding: 40 }}>Carregando...</div>;

  return (
    <div>
      <div style={S.pageTitle}>🛡 Portal Admin</div>
      <div style={S.pageSub}>Visão geral de clientes, feature flags e atualizações OTA</div>

      {/* Cards de resumo */}
      <div style={S.grid(4)}>
        {[
          ["Clientes", clients.length,  "#3b9eff"],
          ["Devices Online",  totalOnline,  "#00c9a7"],
          ["Devices Offline", totalOffline, totalOffline > 0 ? "#ef4444" : "#64748b"],
          ["Versão OTA Ativa", activeManifest ? `v${activeManifest.version}` : "—", "#a78bfa"],
        ].map(([label, val, color]) => (
          <div key={label} style={S.statCard(color)}>
            <div style={S.statVal(color)}>{val}</div>
            <div style={S.statLabel}>{label}</div>
          </div>
        ))}
      </div>

      {/* Tabela de clientes */}
      <div style={{ ...S.card, marginBottom: 28, padding: 0, overflowX: "auto" }}>
        <div style={{ padding: "16px 20px", borderBottom: "1px solid rgba(59,158,255,0.08)", fontWeight: 800, color: "#3b9eff", fontSize: 13, textTransform: "uppercase", letterSpacing: "0.08em" }}>
          🏢 Clientes — Status e Features
        </div>
        <table style={{ ...S.table, margin: 0, borderSpacing: 0 }}>
          <thead>
            <tr>
              {["Cliente", "Plano", "Online", "Offline", "Último Heartbeat", "Features", ""].map((h) => (
                <th key={h} style={{ ...S.th, padding: "12px 16px" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {clients.map((c) => (
              <>
                <tr key={c.id}>
                  <td style={{ ...S.td, border: "none", fontWeight: 800, color: "#f1f5f9" }}>{c.name}</td>
                  <td style={{ ...S.td, border: "none" }}><span style={S.badge("#3b9eff")}>{c.plan}</span></td>
                  <td style={{ ...S.td, border: "none", color: "#00c9a7", fontWeight: 800 }}>{c.online_count || 0}</td>
                  <td style={{ ...S.td, border: "none", color: (c.offline_count || 0) > 0 ? "#ef4444" : "#3a5070", fontWeight: 800 }}>{c.offline_count || 0}</td>
                  <td style={{ ...S.td, border: "none", fontSize: 12, color: "#64748b" }}>{fmtTs(c.last_heartbeat)}</td>
                  <td style={{ ...S.td, border: "none" }}>
                    <span style={{ ...S.badge("#00c9a7"), cursor: "default" }}>
                      {FEATURE_DEFS.filter((f) => featMap[c.id]?.[f.key]).length}/{FEATURE_DEFS.length} ativas
                    </span>
                  </td>
                  <td style={{ ...S.td, border: "none" }}>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button style={S.btnSm()} onClick={() => { setExpandedId(expandedId === c.id ? null : c.id); setExpandedEnvId(null); }}>
                        {expandedId === c.id ? "▲ Fechar" : "⚙ Features"}
                      </button>
                      <button style={{ ...S.btnSm(), background: "rgba(124,58,237,0.12)", color: "#a78bfa", borderColor: "rgba(124,58,237,0.3)" }} onClick={() => { setExpandedEnvId(expandedEnvId === c.id ? null : c.id); setExpandedId(null); }}>
                        {expandedEnvId === c.id ? "▲ Fechar" : "📡 Config .env"}
                      </button>
                    </div>
                  </td>
                </tr>
                {expandedId === c.id && (
                  <tr key={`feat-${c.id}`}>
                    <td colSpan={7} style={{ ...S.td, border: "none", background: "#0d1929", padding: "16px 20px" }}>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px 20px", marginBottom: 14 }}>
                        {FEATURE_DEFS.map((f) => (
                          <label key={f.key} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13, color: "#b8cfe8" }}>
                            <input
                              type="checkbox"
                              checked={!!(featMap[c.id]?.[f.key])}
                              onChange={(e) => setFeatMap((prev) => ({
                                ...prev,
                                [c.id]: { ...prev[c.id], [f.key]: e.target.checked ? "1" : "0" },
                              }))}
                            />
                            {f.label}
                          </label>
                        ))}
                      </div>
                      <button
                        style={{ ...S.btn("primary"), fontSize: 11, padding: "7px 18px" }}
                        onClick={() => saveFeatures(c.id)}
                        disabled={savingId === c.id}
                      >
                        {savingId === c.id ? "Salvando..." : "💾 Salvar Features"}
                      </button>
                    </td>
                  </tr>
                )}
                {expandedEnvId === c.id && (
                  <tr key={`env-${c.id}`}>
                    <td colSpan={7} style={{ ...S.td, border: "none", background: "#0a0f1e", padding: "20px 24px" }}>
                      <div style={{ fontSize: 11, fontWeight: 800, color: "#7c3aed", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
                        📡 Configuração Remota — {c.name}
                      </div>
                      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>
                        As variáveis abaixo serão enviadas ao agente na próxima verificação OTA (até 1h) e aplicadas automaticamente.
                      </div>

                      {/* Analíticos de Vídeo */}
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>Analíticos de Vídeo</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px 24px", marginBottom: 18 }}>
                        {[
                          { key: "ENABLE_AI_ANALYTICS",     label: "🤖 IA Analytics (câmeras)" },
                          { key: "ENABLE_FIRE_DETECTION",   label: "🔥 Fogo e Fumaça" },
                          { key: "ENABLE_TAMPER_DETECTION", label: "🚫 Câmera Sabotada" },
                          { key: "ENABLE_FALL_DETECTION",   label: "🚨 Queda de Pessoa" },
                          { key: "ENABLE_LOITERING",        label: "⏱️ Permanência Suspeita" },
                          { key: "ENABLE_HEATMAP",          label: "🌡️ Mapa de Calor" },
                          { key: "ENABLE_CLIP_RECORDING",   label: "📹 Gravação de Clips" },
                          { key: "ENABLE_DAILY_REPORT",     label: "📊 Relatório Diário" },
                          { key: "ENABLE_OTA",              label: "🔄 Atualização OTA" },
                        ].map(({ key, label }) => (
                          <label key={key} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 13, color: "#b8cfe8" }}>
                            <input
                              type="checkbox"
                              checked={(envPatchMap[c.id]?.[key] ?? "") === "1"}
                              onChange={(e) => setEnvVar(c.id, key, e.target.checked ? "1" : "0")}
                            />
                            {label}
                          </label>
                        ))}
                      </div>

                      {/* Parâmetros avançados */}
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>Parâmetros Avançados</div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12, marginBottom: 18 }}>
                        {[
                          { key: "AI_CLASSES",               label: "Classes detectadas",       placeholder: "person,car,motorcycle" },
                          { key: "AI_CONF_THRESHOLD",        label: "Confiança mínima (0-1)",   placeholder: "0.50" },
                          { key: "AI_EVENT_COOLDOWN_SECONDS",label: "Cooldown entre alertas (s)",placeholder: "300" },
                          { key: "AI_FRAME_EVERY_SECONDS",   label: "Intervalo de análise (s)", placeholder: "1.0" },
                          { key: "AI_PEOPLE_MAX_COUNT",      label: "Limite de lotação",        placeholder: "0 = desabilitado" },
                          { key: "LOG_LEVEL",                label: "Nível de log",             placeholder: "INFO / DEBUG / WARNING" },
                        ].map(({ key, label, placeholder }) => (
                          <div key={key}>
                            <label style={{ display: "block", fontSize: 11, color: "#64748b", marginBottom: 4 }}>{label}</label>
                            <input
                              style={{ ...S.input, fontSize: 12, fontFamily: "monospace", padding: "6px 10px" }}
                              value={envPatchMap[c.id]?.[key] ?? ""}
                              placeholder={placeholder}
                              onChange={(e) => setEnvVar(c.id, key, e.target.value)}
                            />
                          </div>
                        ))}
                      </div>

                      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                        <button
                          style={{ ...S.btn("primary"), background: "#7c3aed", fontSize: 11, padding: "7px 20px" }}
                          onClick={() => saveEnvPatch(c.id)}
                          disabled={savingEnvId === c.id}
                        >
                          {savingEnvId === c.id ? "Enviando..." : "🚀 Enviar para Agente"}
                        </button>
                        <span style={{ fontSize: 11, color: "#64748b" }}>
                          O agente aplicará as mudanças na próxima verificação (até 1h) e reiniciará automaticamente.
                        </span>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>

      {/* Painel OTA */}
      <div style={S.card}>
        <div style={{ fontWeight: 800, color: "#3b9eff", fontSize: 13, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 16 }}>
          🔄 OTA — Gerenciamento de Atualizações
        </div>

        {activeManifest && (
          <div style={{ background: "rgba(0,201,167,0.07)", border: "1px solid rgba(0,201,167,0.2)", borderRadius: 10, padding: "12px 16px", marginBottom: 20 }}>
            <div style={{ fontSize: 11, color: "#00c9a7", fontWeight: 800, textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>✅ Versão Ativa</div>
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
              <div><span style={{ color: "#64748b", fontSize: 11 }}>Versão: </span><strong style={{ color: "#f1f5f9" }}>v{activeManifest.version}</strong></div>
              <div><span style={{ color: "#64748b", fontSize: 11 }}>Obrigatória: </span><strong style={{ color: "#f1f5f9" }}>{activeManifest.required ? "Sim" : "Não"}</strong></div>
              <div><span style={{ color: "#64748b", fontSize: 11 }}>Publicado: </span><strong style={{ color: "#f1f5f9" }}>{fmtTs(activeManifest.created_at)}</strong></div>
            </div>
            {activeManifest.notes && <div style={{ marginTop: 6, fontSize: 12, color: "#64748b" }}>{activeManifest.notes}</div>}
          </div>
        )}

        <div style={{ fontSize: 12, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>Publicar Nova Versão</div>
        <div style={S.grid(2)}>
          <div style={S.fg}>
            <label style={S.label}>Versão (ex: 2.2.0)</label>
            <input style={S.input} value={otaForm.version} onChange={(e) => setOtaForm((f) => ({ ...f, version: e.target.value }))} placeholder="2.2.0" />
          </div>
          <div style={S.fg}>
            <label style={S.label}>URL de Download</label>
            <input style={S.input} value={otaForm.download_url} onChange={(e) => setOtaForm((f) => ({ ...f, download_url: e.target.value }))} placeholder="https://..." />
          </div>
        </div>
        <div style={S.fg}>
          <label style={S.label}>SHA256 do arquivo (64 chars hex)</label>
          <input style={{ ...S.input, fontFamily: "monospace", fontSize: 11 }} value={otaForm.sha256} onChange={(e) => setOtaForm((f) => ({ ...f, sha256: e.target.value }))} placeholder="a1b2c3d4..." />
        </div>
        <div style={S.grid(2)}>
          <div style={S.fg}>
            <label style={S.label}>Notas (opcional)</label>
            <input style={S.input} value={otaForm.notes} onChange={(e) => setOtaForm((f) => ({ ...f, notes: e.target.value }))} placeholder="Correções e melhorias..." />
          </div>
          <div style={{ ...S.fg, display: "flex", alignItems: "center", gap: 10, paddingTop: 24 }}>
            <input type="checkbox" id="required" checked={otaForm.required} onChange={(e) => setOtaForm((f) => ({ ...f, required: e.target.checked }))} />
            <label htmlFor="required" style={{ fontSize: 13, color: "#b8cfe8", cursor: "pointer" }}>Atualização obrigatória</label>
          </div>
        </div>
        {otaErr && <div style={{ color: "#ef4444", fontSize: 12, marginBottom: 10 }}>⚠️ {otaErr}</div>}
        <button style={{ ...S.btn("primary") }} onClick={publishOta} disabled={otaSaving}>
          {otaSaving ? "Publicando..." : "🚀 Publicar Versão"}
        </button>

        {manifests.length > 0 && (
          <>
            <div style={{ ...S.divider }} />
            <div style={{ fontSize: 11, color: "#64748b", fontWeight: 700, textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>Histórico</div>
            {manifests.slice(0, 8).map((m) => (
              <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                <span style={{ ...S.badge(m.active ? "#00c9a7" : "#64748b") }}>{m.active ? "ativo" : "inativo"}</span>
                <span style={{ fontWeight: 700, color: "#f1f5f9", fontSize: 13 }}>v{m.version}</span>
                <span style={{ fontSize: 11, color: "#64748b", flex: 1 }}>{fmtTs(m.created_at)}</span>
                {m.active && (
                  <button style={S.btnSm("danger")} onClick={() => deactivateOta(m.id)}>Desativar</button>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <NexusApp />
    </ErrorBoundary>
  );
}

function NexusApp() {
  const isMobile = useIsMobile();
  const [authed, setAuthed] = useState(!!getToken());
  const [userRole, setUserRole] = useState("superadmin");
  const [userClientId, setUserClientId] = useState(null);
  const [userAccessLevel, setUserAccessLevel] = useState(1);
  const [page, setPage] = useState("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((title, message, type = "info") => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, title, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
  }, []);

  const VALID_PAGES = useMemo(
    () =>
      new Set([
        "dashboard",
        "topology",
        "clients",
        "devices",
        "cameras",
        "scanner",
        "triggers",
        "automation",
        "alerts",
        "events",
        "solar",
        "health",
      ]),
    []
  );

  const pageFromHash = useCallback((hash) => {
    const raw = String(hash || "").trim();
    const p = raw.replace(/^#\/?/, "").toLowerCase();
    if (!p) return null;
    if (p === "topologia") return "topology";
    if (!VALID_PAGES.has(p)) return null;
    return p;
  }, [VALID_PAGES]);

  const hashFromPage = useCallback((p) => {
    const pageId = String(p || "dashboard");
    if (pageId === "topology") return "#/topologia";
    return `#/${pageId}`;
  }, []);

  useEffect(() => {
    if (!authed) return;
    const apply = () => {
      const next = pageFromHash(window.location.hash);
      if (!next) return;
      setPage((prev) => (prev === next ? prev : next));
    };
    apply();
    window.addEventListener("hashchange", apply);
    return () => window.removeEventListener("hashchange", apply);
  }, [authed, pageFromHash]);

  useEffect(() => {
    if (!authed) return;
    const nextHash = hashFromPage(page);
    if (window.location.hash !== nextHash) window.location.hash = nextHash;
  }, [authed, hashFromPage, page]);

  useEffect(() => {
    const raw = import.meta.env.VITE_WS_URL || "";
    const wsUrl = raw.replace(/["'`\s]/g, "").trim().replace(/\/$/, "");
    if (!wsUrl || !authed) return;

    const socket = io(wsUrl, {
      transports: ["websocket", "polling"],
    });

    socket.on("alert", (a) => {
      addToast("🚨 NOVO ALERTA", `${a.host}: ${a.trigger_name || a.expression}`, "danger");
    });

    socket.on("event", (e) => {
      addToast("🎬 EVENTO", `${e.device_name}: ${e.event_type}`, "info");
    });

    return () => socket.close();
  }, [authed, addToast]);

  useEffect(() => {
    if (authed) {
      api("/auth/me")
        .then((u) => {
          setUserRole(u.role);
          setUserClientId(u.client_id);
          setUserAccessLevel(Number(u.access_level || (u.role === "superadmin" ? 3 : 1)));
        })
        .catch(() => {});
    }
  }, [authed]);

  useEffect(() => {
    if (isMobile) setSidebarOpen(false);
  }, [page, isMobile]);

  if (!authed) {
    return (
      <AuthPage
        onLogin={(role, cid, lvl) => {
          setUserRole(role);
          setUserClientId(cid);
          setUserAccessLevel(Number(lvl || (role === "superadmin" ? 3 : 1)));
          setAuthed(true);
        }}
      />
    );
  }

  const isSuperAdmin = userRole === "superadmin";
  const canVideo = isSuperAdmin || userAccessLevel >= 2;
  const canRecord = isSuperAdmin || userAccessLevel >= 3;

  const NAV_SUPERADMIN = [
    { section: "MENU PRINCIPAL" },
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "topology", label: "Topologia", icon: LayoutGrid },
    { id: "clients", label: "Clientes", icon: Users },
    { id: "devices", label: "Devices", icon: Server },
    { id: "cameras", label: "Câmeras", icon: Camera },
    { id: "scanner", label: "Scanner", icon: RefreshCw },
    { id: "triggers", label: "Triggers", icon: Zap },
    { id: "automation", label: "Automação", icon: Workflow },
    { id: "alerts", label: "Alertas", icon: Bell },
    { id: "events", label: "Eventos", icon: ClipboardList },
    { id: "solar", label: "Solar", icon: Sun },
    { id: "health", label: "Saúde", icon: Activity },
    { section: "ADMINISTRAÇÃO" },
    { id: "admin", label: "Portal Admin", icon: Shield },
  ];

  const NAV_CLIENT = [
    { section: "MENU" },
    { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { id: "topology", label: "Topologia", icon: LayoutGrid },
    { id: "devices", label: "Devices", icon: Server },
    { id: "cameras", label: "Câmeras", icon: Camera },
    { id: "scanner", label: "Scanner", icon: RefreshCw },
    { id: "automation", label: "Automação", icon: Workflow },
    { id: "alerts", label: "Alertas", icon: Bell },
    { id: "events", label: "Eventos", icon: ClipboardList },
    { id: "solar", label: "Solar", icon: Sun },
    { id: "health", label: "Saúde", icon: Activity },
  ];

  const NAV = isSuperAdmin ? NAV_SUPERADMIN : NAV_CLIENT;

  const PAGES = {
    dashboard: <DashboardEti api={api} onToast={addToast} onGoTopology={() => setPage('topology')} />,
    topology: <TopologyEti api={api} onToast={addToast} canAdmin={canRecord} />,
    clients:   <ClientsPage />,
    devices:   <DevicesPage userRole={userRole} userClientId={userClientId} canVideo={canVideo} canRecord={canRecord} />,
    cameras:   <VideoGrid />,
    scanner:   <ScannerPage userRole={userRole} userClientId={userClientId} canVideo={canVideo} canRecord={canRecord} />,
    triggers:  <TriggersPage userRole={userRole} />,
    automation: <AutomationPage userRole={userRole} userClientId={userClientId} />,
    alerts:    <AlertsPage userRole={userRole} />,
    events:    <EventsPage userRole={userRole} />,
    solar: <SolarPage userRole={userRole} />,
    health: <HealthDashboard />,
    admin:  <AdminOverviewPage />,
  };

  const sidebarStyle = {
    ...S.sidebar,
    position: isMobile ? "fixed" : "relative",
    zIndex: 1001,
    height: "100vh",
    transform: isMobile ? (sidebarOpen ? "translateX(0)" : "translateX(-100%)") : "none",
    transition: "transform 0.3s ease-in-out",
    width: 248,
  };

  return (
    <div style={{...S.app, flexDirection: "row", overflow: "hidden"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Exo+2:wght@700;800&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        body{background:#070d18;color:#e2eaf5;font-family:'Rajdhani','Segoe UI',sans-serif}
        ::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:#0b1525}::-webkit-scrollbar-thumb{background:#1e3a5f;border-radius:4px}
        button{cursor:pointer}
        @keyframes eti-ping{0%{transform:scale(1);opacity:.5}75%,100%{transform:scale(2.2);opacity:0}}
        @media (max-width: 768px){.main-content{padding:70px 14px 20px !important}}
      `}</style>

      {isMobile && sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.5)",
            zIndex: 1000
          }}
        />
      )}

      <aside style={sidebarStyle}>
        <div style={S.logo}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
            <div style={{ flexShrink: 0 }}>
              <LogoMark size={52} />
            </div>
            <div>
              <div style={S.logoTitle}>
                <span style={{ color: '#b8cfe8' }}>ETI </span>
                <span style={{ color: '#3b9eff' }}>SENTINEL</span>
              </div>
              <div style={S.logoSub}>Monitoramento Inteligente</div>
            </div>
          </div>

          <div style={{ background: 'rgba(59,158,255,0.07)', border: '1px solid rgba(59,158,255,0.18)', borderRadius: 8, padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 30, height: 30, borderRadius: '50%', background: 'linear-gradient(135deg,#1a7fff,#004fa3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, color: '#fff', fontWeight: 800, flexShrink: 0 }}>S</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#3b9eff', letterSpacing: '0.04em' }}>{isSuperAdmin ? 'Superadmin' : 'Cliente'}</div>
              <div style={{ fontSize: 9, color: '#2a5070', letterSpacing: '0.06em' }}>v1.0.3 · nível {userAccessLevel}</div>
            </div>
            <PulsingDot color="#00c9a7" />
          </div>
        </div>

        <nav style={{ padding: '18px 10px', flex: 1, overflowY: 'auto' }}>
          {NAV.map((n, i) =>
            n.section ? (
              <div key={i} style={S.navSection}>{n.section}</div>
            ) : (
              <button key={n.id} onClick={() => setPage(n.id)} style={S.navItem(page === n.id)}>
                {page === n.id && <span style={{ position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)', width: 3, height: 20, background: '#3b9eff', borderRadius: '0 3px 3px 0', boxShadow: '0 0 8px #3b9eff' }} />}
                <span style={{ width: 20, display: 'inline-flex', justifyContent: 'center', opacity: page === n.id ? 1 : 0.75 }}>
                  <n.icon size={16} />
                </span>
                {n.label}
              </button>
            )
          )}
        </nav>

        <div style={{ padding: '14px 10px', borderTop: '1px solid rgba(59,158,255,0.07)' }}>
          <button
            onClick={() => {
              removeToken();
              setAuthed(false);
            }}
            style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 12px', borderRadius: 8, border: '1px solid rgba(239,68,68,0.15)', background: 'rgba(239,68,68,0.05)', color: '#ef4444', fontWeight: 700, fontSize: 14, fontFamily: "'Rajdhani',sans-serif", letterSpacing: '0.04em' }}
          >
            <LogOut size={16} />
            Sair
          </button>
        </div>
      </aside>

      <div style={{ ...S.main, padding: isMobile ? "70px 14px 20px" : "32px 32px" }} className="main-content">
        {isMobile && (
          <button
            onClick={() => setSidebarOpen(true)}
            style={{
              position: "fixed",
              top: 15,
              left: 15,
              zIndex: 999,
              background: "rgba(11, 21, 37, 0.92)",
              border: "1px solid rgba(59, 158, 255, 0.18)",
              color: "#3b9eff",
              padding: "8px 12px",
              borderRadius: 8,
              fontSize: 18,
              boxShadow: "none"
            }}
          >
            <Menu size={18} />
          </button>
        )}
        {PAGES[page] || PAGES.dashboard}
      </div>

      {/* Toasts Container */}
      <div style={{ position: "fixed", bottom: 20, right: 20, display: "flex", flexDirection: "column", gap: 10, zIndex: 2000 }}>
        {toasts.map((t) => (
          <div key={t.id} style={{
            background: t.type === "danger" ? "#ef4444" : "#3b9eff",
            color: "#fff",
            padding: "12px 20px",
            borderRadius: 12,
            boxShadow: "0 10px 30px rgba(0,0,0,0.3)",
            display: "flex",
            flexDirection: "column",
            minWidth: 260,
            animation: "toast-in 0.3s ease-out"
          }}>
            <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: 1, opacity: 0.8, marginBottom: 2 }}>{t.title}</div>
            <div style={{ fontSize: 13, fontWeight: 700 }}>{t.message}</div>
          </div>
        ))}
      </div>
      <style>{`
        @keyframes toast-in {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
