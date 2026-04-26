import { useState, useEffect, useCallback, useMemo, Component } from 'react';

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
        <div style={{ padding: 40, background: '#050508', color: '#fff', height: '100vh', fontFamily: 'monospace' }}>
          <h1 style={{ color: '#ef4444' }}>❌ Erro Crítico no Frontend</h1>
          <pre style={{ background: '#1a1a25', padding: 20, borderRadius: 8, overflow: 'auto' }}>
            {this.state.error?.toString()}
          </pre>
          <button 
            style={{ padding: '10px 20px', background: '#38bdf8', border: 'none', borderRadius: 4, cursor: 'pointer', marginTop: 20 }}
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

const getInitialAPI = () => {
  // 1. Prioridade para override manual via URL (ex: ?api=https://...)
  const urlParams = new URLSearchParams(window.location.search);
  const urlApi = urlParams.get("api");
  if (urlApi && urlApi.length > 5) return urlApi;

  // 2. Verifica se há uma URL salva no localStorage
  const savedApi = localStorage.getItem("NEXUS_API_URL");
  if (savedApi && savedApi.length > 5) return savedApi;

  // 3. Verifica variável de ambiente do Vite
  const envApi = import.meta.env.VITE_API_URL;
  if (envApi && envApi.length > 5) return envApi;
  
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
  return window.location.origin;
};

const FuturisticLogo = ({ size = 42 }) => (
  <img
    src="/eti-sentinel-logo.jpg"
    alt="ETI SENTINEL"
    style={{
      width: size,
      height: size,
      marginRight: 12,
      filter: "drop-shadow(0 0 10px rgba(56, 189, 248, 0.55))",
      borderRadius: 10,
      objectFit: "cover",
    }}
  />
);

const API = getInitialAPI().replace(/\/$/, "");

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

    const data = await res.json();
    if (!res.ok) {
      console.error(`API Error [${res.status}] ${path}:`, data);
      throw data;
    }
    return data;
  } catch (err) {
    console.error(`Fetch Error ${path}:`, err);
    throw err;
  }
}

const DEVICE_TYPES = [
  { value: "server",      label: "Servidor",    icon: "🖥️" },
  { value: "camera",      label: "Câmera IP",   icon: "📷" },
  { value: "router",      label: "Roteador",    icon: "🌐" },
  { value: "switch",      label: "Switch",      icon: "🔀" },
  { value: "routerboard", label: "RouterBoard", icon: "📡" },
  { value: "unifi",       label: "UniFi",       icon: "📶" },
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
  { value: "pro",        label: "Pro",        color: "#38bdf8" },
  { value: "enterprise", label: "Enterprise", color: "#a78bfa" },
];

const deviceIcon  = (t) => DEVICE_TYPES.find((d) => d.value === t)?.icon || "📦";
const deviceLabel = (t) => DEVICE_TYPES.find((d) => d.value === t)?.label || "Outro";
const planColor   = (p) => PLANS.find((x) => x.value === p)?.color || "#64748b";

// ── Styles ────────────────────────────────────────────────────
const S = {
  app: { 
    minHeight: "100vh", 
    background: "transparent", 
    color: "#e2e8f0", 
    fontFamily: "'Rajdhani', sans-serif", 
    display: "flex",
    position: "relative"
  },
  sidebar: { 
    width: 240, 
    background: "rgba(5, 5, 10, 0.8)", 
    backdropFilter: "blur(12px)",
    borderRight: "1px solid rgba(56, 189, 248, 0.2)", 
    display: "flex", 
    flexDirection: "column", 
    padding: "20px 0", 
    flexShrink: 0,
    boxShadow: "10px 0 30px rgba(0,0,0,0.5)"
  },
  logo: { padding: "0 24px 24px", borderBottom: "1px solid rgba(56, 189, 248, 0.1)", marginBottom: 12 },
  logoTitle: { 
    fontSize: 22, 
    fontWeight: 700, 
    color: "#38bdf8", 
    letterSpacing: 2,
    textTransform: "uppercase",
    textShadow: "0 0 10px rgba(56, 189, 248, 0.5)"
  },
  logoSub: { fontSize: 10, color: "#3a5070", marginTop: 2, letterSpacing: 1 },
  navSection: { fontSize: 10, color: "#4a6080", padding: "16px 24px 8px", textTransform: "uppercase", letterSpacing: 2, fontWeight: 600 },
  navItem: (a) => ({ 
    display: "flex", 
    alignItems: "center", 
    gap: 12, 
    padding: "12px 24px", 
    cursor: "pointer", 
    color: a ? "#fff" : "#4a6080", 
    background: a ? "linear-gradient(90deg, rgba(56,189,248,0.15) 0%, transparent 100%)" : "transparent", 
    borderLeft: a ? "3px solid #38bdf8" : "3px solid transparent", 
    fontSize: 14, 
    fontWeight: a ? 600 : 500, 
    transition: "all 0.3s ease", 
    userSelect: "none",
    textShadow: a ? "0 0 8px rgba(56, 189, 248, 0.5)" : "none"
  }),
  main: { flex: 1, overflow: "auto", padding: "30px 40px", background: "rgba(0,0,0,0.2)" },
  pageTitle: { 
    fontSize: 28, 
    fontWeight: 700, 
    color: "#fff", 
    marginBottom: 6, 
    letterSpacing: 1,
    textTransform: "uppercase",
    textShadow: "0 0 15px rgba(255,255,255,0.2)"
  },
  pageSub: { fontSize: 12, color: "#64748b", marginBottom: 30, letterSpacing: 0.5 },
  grid: (cols) => ({ 
    display: "grid", 
    gridTemplateColumns: window.innerWidth < 768 ? "1fr" : `repeat(${cols}, 1fr)`, 
    gap: 20, 
    marginBottom: 20 
  }),
  card: { 
    background: "rgba(10, 15, 26, 0.6)", 
    backdropFilter: "blur(12px)",
    border: "1px solid rgba(56, 189, 248, 0.15)", 
    borderRadius: 16, 
    padding: 24,
    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
    position: "relative",
    overflow: "hidden",
    transition: "transform 0.2s ease, box-shadow 0.2s ease"
  },
  statCard: (c) => ({ 
    background: "rgba(10, 15, 26, 0.6)", 
    backdropFilter: "blur(12px)",
    border: `1px solid ${c}40`, 
    borderRadius: 16, 
    padding: 24,
    boxShadow: `0 0 20px ${c}10`,
    transition: "transform 0.2s ease"
  }),
  statVal: (c) => ({ 
    fontSize: 36, 
    fontWeight: 800, 
    color: c, 
    lineHeight: 1,
    textShadow: `0 0 15px ${c}60`
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
    boxShadow: `0 0 10px ${c}20`
  }),
  btn: (v = "primary") => ({ 
    padding: "10px 20px", 
    borderRadius: 8, 
    border: v === "ghost" ? "1px solid rgba(56, 189, 248, 0.1)" : "1px solid transparent", 
    cursor: "pointer", 
    fontSize: 12, 
    fontWeight: 700, 
    fontFamily: "inherit", 
    background: v === "primary" ? "#38bdf8" : v === "danger" ? "#ef4444" : v === "purple" ? "#a78bfa" : "rgba(15, 23, 42, 0.6)", 
    color: v === "ghost" ? "#94a3b8" : "#050508", 
    transition: "all 0.2s ease",
    textTransform: "uppercase",
    letterSpacing: 1,
    boxShadow: v !== "ghost" ? `0 4px 15px ${v === "primary" ? "#38bdf866" : v === "danger" ? "#ef444466" : "#00000044"}` : "none"
  }),
  btnSm: (v = "ghost") => ({ 
    padding: "6px 14px", 
    borderRadius: 6, 
    border: "1px solid rgba(56, 189, 248, 0.15)", 
    cursor: "pointer", 
    fontSize: 10, 
    fontWeight: 600, 
    fontFamily: "inherit", 
    background: v === "danger" ? "rgba(239, 68, 68, 0.15)" : "rgba(15, 23, 42, 0.6)", 
    color: v === "danger" ? "#ef4444" : "#38bdf8",
    transition: "all 0.2s ease",
    textTransform: "uppercase",
    letterSpacing: 0.5
  }),
  input: { 
    width: "100%", 
    background: "rgba(5, 5, 10, 0.6)", 
    border: "1px solid rgba(56, 189, 248, 0.2)", 
    borderRadius: 8, 
    padding: "12px 16px", 
    color: "#fff", 
    fontSize: 13, 
    fontFamily: "inherit", 
    boxSizing: "border-box", 
    outline: "none",
    transition: "all 0.2s ease",
    boxShadow: "inset 0 2px 4px rgba(0,0,0,0.5)",
    "&:focus": { borderColor: "#38bdf8", boxShadow: "0 0 10px rgba(56, 189, 248, 0.2), inset 0 2px 4px rgba(0,0,0,0.5)" }
  },
  select: { 
    width: "100%", 
    background: "rgba(5, 5, 10, 0.6)", 
    border: "1px solid rgba(56, 189, 248, 0.2)", 
    borderRadius: 8, 
    padding: "12px 16px", 
    color: "#fff", 
    fontSize: 13, 
    fontFamily: "inherit", 
    boxSizing: "border-box", 
    outline: "none",
    transition: "all 0.2s ease",
    boxShadow: "inset 0 2px 4px rgba(0,0,0,0.5)"
  },
  label: { fontSize: 11, color: "#64748b", marginBottom: 6, display: "block", textTransform: "uppercase", letterSpacing: 1, fontWeight: 700 },
  fg: { marginBottom: 20 },
  table: { width: "100%", borderCollapse: "separate", borderSpacing: "0 8px", fontSize: 13 },
  th: { padding: "12px 16px", textAlign: "left", color: "#4a6080", fontSize: 10, textTransform: "uppercase", letterSpacing: 1.5, fontWeight: 700, borderBottom: "1px solid rgba(56, 189, 248, 0.1)" },
  td: { padding: "16px", background: "rgba(15, 23, 42, 0.4)", borderTop: "1px solid rgba(56, 189, 248, 0.05)", borderBottom: "1px solid rgba(56, 189, 248, 0.05)", color: "#cbd5e1" },
  modal: { position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", backdropFilter: "blur(8px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 },
  modalBox: { 
    background: "rgba(10, 15, 26, 0.95)", 
    border: "1px solid rgba(56, 189, 248, 0.4)", 
    borderRadius: 20, 
    padding: window.innerWidth < 768 ? 20 : 32, 
    width: "95%",
    maxWidth: 600, 
    maxHeight: "90vh", 
    overflowY: "auto",
    boxShadow: "0 20px 60px rgba(0,0,0,0.8), 0 0 30px rgba(56, 189, 248, 0.15)"
  },
  modalTitle: { fontSize: 20, fontWeight: 800, color: "#fff", marginBottom: 24, textTransform: "uppercase", letterSpacing: 1, textShadow: "0 0 15px rgba(56, 189, 248, 0.5)", display: "flex", alignItems: "center", gap: 10 },
  sectionTitle: { fontSize: 11, fontWeight: 800, color: "#38bdf8", marginBottom: 16, textTransform: "uppercase", letterSpacing: 2, background: "rgba(56, 189, 248, 0.05)", padding: "6px 12px", borderRadius: 6, display: "inline-block" },
  divider: { borderTop: "1px solid rgba(56, 189, 248, 0.1)", margin: "24px 0" },
  tag: { display: "inline-flex", alignItems: "center", gap: 4, background: "rgba(56, 189, 248, 0.1)", color: "#38bdf8", border: "1px solid rgba(56, 189, 248, 0.3)", borderRadius: 6, padding: "3px 10px", fontSize: 10, fontWeight: 700, marginRight: 6, marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5, boxShadow: "0 0 10px rgba(56, 189, 248, 0.1)" },
  eventCard: (severity) => ({
    padding: "16px 20px",
    borderRadius: 14,
    background: severity === "critical" ? "rgba(239, 68, 68, 0.08)" : "rgba(15, 23, 42, 0.5)",
    border: `1px solid ${severity === "critical" ? "rgba(239, 68, 68, 0.3)" : "rgba(56, 189, 248, 0.15)"}`,
    marginBottom: 12,
    display: "flex",
    gap: 16,
    alignItems: "center",
    transition: "transform 0.2s ease, box-shadow 0.2s ease",
    boxShadow: severity === "critical" ? "0 0 15px rgba(239, 68, 68, 0.15)" : "none",
    cursor: "default"
  }),
};

// ── Components ────────────────────────────────────────────────
function Bar({ value, color = "#38bdf8" }) {
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
      localStorage.setItem("NEXUS_API_URL", tempApi);
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
        const timeoutId = setTimeout(() => controller.abort(), 8000);

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
        setErr(`❌ Erro de Conexão: ${e.message}. Verifique se o link ${finalApi} está correto.`);
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
      setToken(d.token); onLogin(d.role, d.client_id);
    } catch (e) { setErr(e.error || "Erro"); }
    finally { setLoading(false); }
  };

  if (!step && !err) return <div style={{ ...S.app, alignItems: "center", justifyContent: "center", color: "#38bdf8", fontFamily: 'Rajdhani', fontSize: 20 }}>Carregando...</div>;

  return (
    <div style={{ ...S.app, alignItems: "center", justifyContent: "center" }}>
      <div style={{ 
        ...S.card, 
        width: "90%",
        maxWidth: 380, 
        textAlign: "center", 
        padding: window.innerWidth < 768 ? "30px 20px" : 40,
        border: "1px solid rgba(56, 189, 248, 0.3)",
        boxShadow: "0 0 50px rgba(0, 0, 0, 0.5), 0 0 20px rgba(56, 189, 248, 0.1)"
      }}>
        <div style={{ fontSize: 42, marginBottom: 16, display: 'flex', justifyContent: 'center' }}>
          <FuturisticLogo />
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
        
        {err && <div style={{ color: "#ff0055", fontSize: 12, marginBottom: 16, fontWeight: 600, background: 'rgba(255,0,85,0.1)', padding: 10, borderRadius: 8 }}>⚠️ {err}</div>}
        
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

function ClientModal({ client, onSave, onClose }) {
  const [form, setForm] = useState(client ? { ...EMPTY_CLIENT, ...client } : { ...EMPTY_CLIENT });
  const [tab, setTab] = useState("info");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    if (!form.name) return setErr("Nome obrigatório");
    setLoading(true); setErr("");
    try {
      if (client?.id) await api(`/clients/${client.id}`, { method: "PUT", body: JSON.stringify(form) });
      else await api("/clients", { method: "POST", body: JSON.stringify(form) });
      onSave();
    } catch (e) { 
      console.error("Save Client Error:", e);
      setErr(e.error || e.message || "Erro ao salvar cliente no banco de dados"); 
    }
    finally { setLoading(false); }
  };

  const tabs = ["info", "contato", "alertas", "notas"];
  const tabLabel = { info: "📋 Info", contato: "📞 Contato", alertas: "🔔 Alertas", notas: "📝 Notas" };

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
  const [newUser, setNewUser] = useState({ username: "", password: "" });
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
    await api(`/clients/${userModal}/users`, { method: "POST", body: JSON.stringify(newUser) });
    setUserModal(null); setNewUser({ username: "", password: "" });
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
        <button style={{ ...S.btn("primary"), boxShadow: "0 0 15px rgba(56,189,248,0.4)" }} onClick={() => setModal("new")}>+ Novo Cliente</button>
      </div>

      <div style={{ ...S.card, marginBottom: 24, display: "flex", gap: 10, background: "rgba(10, 15, 26, 0.4)", border: "1px solid rgba(56,189,248,0.1)" }}>
        <input style={{ ...S.input, maxWidth: 300 }} placeholder="🔍 Buscar cliente..." value={search} onChange={(e) => setSearch(e.target.value)} />
        <span style={{ fontSize: 12, color: "#38bdf8", alignSelf: "center", fontWeight: 600 }}>{filtered.length} resultado(s)</span>
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
                    ? "rgba(56,189,248,0.06)"
                    : i % 2 === 0
                      ? "transparent"
                      : "rgba(15,23,42,0.20)",
                  transition: "background 0.2s, box-shadow 0.2s",
                  boxShadow: hoverId === c.id ? "inset 0 0 0 1px rgba(56,189,248,0.18)" : "none",
                }}
              >
                <td style={{ ...S.td, border: "none", padding: "16px 20px" }}>
                  <div style={{ fontWeight: 800, color: "#f1f5f9", fontSize: 14 }}>{c.name}</div>
                  <div style={{ fontSize: 11, color: "#64748b", fontFamily: "monospace", marginTop: 2 }}>{c.document || "—"}</div>
                </td>
                <td style={{ ...S.td, border: "none" }}><span style={S.badge(planColor(c.plan))}>{c.plan}</span></td>
                <td style={{ ...S.td, border: "none" }}><span style={S.badge(statusColor[c.status] || "#64748b")}>{statusLabel[c.status] || c.status}</span></td>
                <td style={{ ...S.td, border: "none", color: "#38bdf8", fontWeight: 800, fontSize: 16 }}>{c.device_count || 0}</td>
                <td style={{ ...S.td, border: "none", color: "#22c55e", fontWeight: 800, fontSize: 16 }}>{c.online_count || 0}</td>
                <td style={{ ...S.td, border: "none", color: c.offline_count > 0 ? "#ef4444" : "#3a5070", fontWeight: 800, fontSize: 16 }}>{c.offline_count || 0}</td>
                <td style={{ ...S.td, border: "none", color: "#94a3b8", fontSize: 12 }}>{c.city || "—"}</td>
                <td style={{ ...S.td, border: "none" }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button style={S.btnSm()} onClick={() => setModal(c)} title="Editar">✏️</button>
                    <button style={S.btnSm()} onClick={() => setUserModal(c.id)} title="Criar usuário">👤</button>
                    <button style={S.btnSm("danger")} onClick={() => del(c.id)}>🗑️</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(modal === "new" || (modal && modal.id)) && (
        <ClientModal client={modal === "new" ? null : modal} onSave={() => { load(); setModal(null); }} onClose={() => setModal(null)} />
      )}

      {userModal && (
        <div style={S.modal} onClick={() => setUserModal(null)}>
          <div style={{ ...S.modalBox, width: 360 }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalTitle}>👤 Criar Acesso do Cliente</div>
            <div style={S.fg}><label style={S.label}>Usuário</label><input style={S.input} value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} placeholder="cliente_abc" /></div>
            <div style={S.fg}><label style={S.label}>Senha</label><input style={S.input} type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} placeholder="••••••••" /></div>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button style={S.btn("ghost")} onClick={() => setUserModal(null)}>Cancelar</button>
              <button style={S.btn("primary")} onClick={createUser}>Criar Acesso</button>
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
  mac_address: "", serial_number: "",
};

function DeviceModal({ device, clients, userRole, userClientId, onSave, onClose }) {
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
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setOnvifField = (k, v) => setOnvif((o) => ({ ...o, [k]: v }));
  const setRtspField = (k, v) => setRtsp((o) => ({ ...o, [k]: v }));

  useEffect(() => {
    let alive = true;
    if (!device?.id) return;
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
    if (!device?.id) return;
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
    } catch (e) { setErr(e.error || "Erro ao salvar dados"); }
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
            <select style={S.select} value={form.device_type} onChange={(e) => set("device_type", e.target.value)}>
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
          <div style={{...S.fg, border: "1px solid #38bdf833", padding: "10px", borderRadius: "8px", background: "rgba(56, 189, 248, 0.05)"}}>
            <label style={{...S.label, color: "#38bdf8"}}>🆔 MAC Address</label>
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
          <textarea
            style={{ ...S.input, minHeight: 110, resize: "vertical", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace" }}
            value={rtsp.streams_text}
            onChange={(e) => setRtspField("streams_text", e.target.value)}
            placeholder='[{"channel":1,"name":"Canal 1","url":"rtsp://192.168.1.100:554/...","timeout_seconds":8,"interval_seconds":30,"transport":"tcp"}]'
          />
        </div>

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
function DevicesPage({ userRole, userClientId }) {
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

      <div style={{ ...S.card, marginBottom: 24, display: "flex", gap: 12, flexWrap: "wrap", background: "rgba(10, 15, 26, 0.4)", border: "1px solid rgba(56,189,248,0.1)" }}>
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
            boxShadow: d.status === "online" ? "0 10px 30px rgba(34, 197, 94, 0.05)" : "0 10px 30px rgba(239, 68, 68, 0.1)"
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

            <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: 12, padding: 16, marginBottom: 20, border: "1px solid rgba(255,255,255,0.03)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontSize: 10, color: "#64748b", fontWeight: 700 }}>{d.ddns_address ? "DDNS" : "IP / VPN"}</span>
                <span style={{ fontSize: 11, color: d.ddns_address ? "#38bdf8" : "#a78bfa", fontFamily: "monospace", fontWeight: 700 }}>{d.ddns_address || d.ip_address || "—"}</span>
              </div>
              
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px", marginTop: "10px", marginBottom: "10px" }}>
                <div style={{ background: "rgba(56, 189, 248, 0.08)", padding: "8px", borderRadius: "8px", border: "1px solid rgba(56, 189, 248, 0.15)" }}>
                  <span style={{ fontSize: "9px", color: "#38bdf8", display: "block", textTransform: "uppercase", fontWeight: 800, marginBottom: 2 }}>MAC Address</span>
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
                    <span style={{ fontSize: 14, color: "#fff", fontWeight: 800, textShadow: "0 0 10px rgba(234,179,8,0.5)" }}>{d.battery_percent}%</span>
                  </div>
                  <div style={{ height: 6, background: "rgba(255,255,255,0.1)", borderRadius: 3, overflow: "hidden", marginBottom: 10 }}>
                    <div style={{ height: "100%", width: `${d.battery_percent}%`, background: d.battery_percent > 20 ? "#22c55e" : "#ef4444", transition: "width 0.5s ease", boxShadow: "0 0 10px rgba(34,197,94,0.5)" }} />
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
                  <span style={{ fontSize: 11, color: "#38bdf8", fontWeight: 800 }}>{d.monitor_port}</span>
                </div>
              )}
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: d.monitor_port > 0 ? 0 : 10 }}>
                <span style={{ fontSize: 10, color: "#64748b", fontWeight: 700 }}>LATÊNCIA</span>
                <span style={{ fontSize: 11, color: "#22c55e", fontWeight: 800, textShadow: "0 0 10px rgba(34,197,94,0.4)" }}>{d.last_latency ? `${Math.round(d.last_latency)}ms` : "—"}</span>
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
                  background: "rgba(15,23,42,0.95)", backdropFilter: "blur(10px)", border: "1px solid rgba(56,189,248,0.3)", 
                  borderRadius: 12, padding: 8, zIndex: 10, boxShadow: "0 10px 30px rgba(0,0,0,0.8)", marginBottom: 8
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
        <DeviceModal device={modal === "new" ? null : modal} clients={clients} userRole={userRole} userClientId={userClientId}
          onSave={() => { load(); setModal(null); }} onClose={() => setModal(null)} />
      )}
      {tokenModal && (
        <div style={S.modal} onClick={() => setTokenModal(null)}>
          <div style={{ ...S.modalBox, width: 380 }} onClick={(e) => e.stopPropagation()}>
            <div style={S.modalTitle}>🔑 Token do Device</div>
            <div style={{ ...S.input, wordBreak: "break-all", padding: 10, fontSize: 10, color: "#38bdf8", marginBottom: 14 }}>{tokenModal}</div>
            <button style={{ ...S.btn("primary"), width: "100%" }} onClick={() => { navigator.clipboard.writeText(tokenModal); setTokenModal(null); }}>📋 Copiar e Fechar</button>
          </div>
        </div>
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

  const load = useCallback(() => {
    api("/stats").then(setStats).catch(() => {});
    api("/devices").then((data) => setDevices(Array.isArray(data) ? data : [])).catch(() => {});
    api("/alerts").then((data) => setAlerts(Array.isArray(data) ? data : [])).catch(() => {});
    if (userRole === "superadmin") api("/clients").then((data) => setClients(Array.isArray(data) ? data : [])).catch(() => {});
  }, [userRole]);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000); // REFRESH CADA 2 SEGUNDOS (MODO REAL-TIME)
    return () => clearInterval(t);
  }, [load]);

  const byType = DEVICE_TYPES.map((t) => ({ ...t, count: devices.filter((d) => d.device_type === t.value).length })).filter((t) => t.count > 0);

  const statTiles = [
    ...(userRole === "superadmin" ? [{ icon: "🏢", label: "Clientes", value: stats.clients, color: "#a78bfa" }] : []),
    { icon: "🧩", label: "Total Devices", value: stats.devices, color: "#38bdf8" },
    { icon: "🟢", label: "Online", value: stats.online, color: "#22c55e" },
    { icon: "🔴", label: "Offline", value: stats.offline, color: "#ef4444" },
    { icon: "🚨", label: "Alertas 24h", value: alerts.length, color: "#f59e0b" },
  ];

  return (
    <div style={{ padding: isMobile ? "0 5px" : 0 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
        <div>
          <div style={S.pageTitle}>📊 Dashboard</div>
          <div style={S.pageSub}>Visão geral — ETI SENTINEL</div>
        </div>
        <button onClick={load} style={{ ...S.btn("ghost"), padding: "10px 16px", borderRadius: 12 }}>
          ↻ Atualizar
        </button>
      </div>

      <div style={{ 
        display: "grid", 
        gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : `repeat(${userRole === "superadmin" ? 5 : 4}, 1fr)`, 
        gap: isMobile ? 10 : 20, 
        marginBottom: 20 
      }}>
        {statTiles.map((s) => (
          <div
            key={s.label}
            style={{
              ...S.statCard(s.color),
              padding: isMobile ? 12 : 20,
              background: `radial-gradient(120% 120% at 10% 10%, ${s.color}12 0%, rgba(10, 15, 26, 0.62) 55%, rgba(10, 15, 26, 0.62) 100%)`,
              border: `1px solid ${s.color}30`,
              boxShadow: `0 0 22px ${s.color}12, 0 8px 30px rgba(0,0,0,0.35)`,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                <div style={{ width: 36, height: 36, borderRadius: 12, background: `${s.color}18`, border: `1px solid ${s.color}33`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, boxShadow: `0 0 14px ${s.color}22` }}>
                  {s.icon}
                </div>
                <div style={{ ...S.statLabel, fontSize: isMobile ? 9 : 11, marginTop: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {s.label}
                </div>
              </div>
              <div style={{ ...S.statVal(s.color), fontSize: isMobile ? 24 : 34 }}>{s.value}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ 
        display: "grid", 
        gridTemplateColumns: isMobile ? "1fr" : `repeat(${userRole === "superadmin" ? 3 : 2}, 1fr)`, 
        gap: 20, 
        marginBottom: 20 
      }}>
        <div style={S.card}>
          <div style={S.sectionTitle}>Devices por Tipo</div>
          {byType.length === 0 && <div style={{ color: "#3a5070", fontSize: 11 }}>Nenhum device</div>}
          {byType.map((t) => (
            <div key={t.value} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: 12 }}>{t.icon} {t.label}</span>
              <span style={S.badge("#38bdf8")}>{t.count}</span>
            </div>
          ))}
        </div>

        {userRole === "superadmin" && (
          <div style={S.card}>
            <div style={S.sectionTitle}>Top Clientes</div>
            {clients.slice(0, 6).map((c) => (
              <div key={c.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 11, color: "#f1f5f9", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</div>
                  <div style={{ fontSize: 9, color: "#3a5070" }}>{c.city||"—"}</div>
                </div>
                <div style={{ display: "flex", gap: 5, alignItems: "center", marginLeft: 10 }}>
                  <span style={S.badge("#22c55e")}>{c.online_count||0} on</span>
                  {(c.offline_count||0) > 0 && <span style={S.badge("#ef4444")}>{c.offline_count} off</span>}
                </div>
              </div>
            ))}
          </div>
        )}

      <div style={S.card}>
        <div style={S.sectionTitle}>Alertas Recentes (24h)</div>
        {alerts.slice(0, 8).length === 0 && <div style={{ color: "#3a5070", fontSize: 11 }}>Nenhum alerta</div>}
        {alerts.slice(0, 8).map((a) => (
          <div key={a.id} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#fff", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.trigger_name || (a.expression || "").toUpperCase()}</span>
              <span style={S.badge(a.alert_type==="offline"?"#ef4444":"#f59e0b")}>{a.alert_type==="offline"?"🔴 OFFLINE":"⚠️ AVISO"}</span>
            </div>
            <div style={{ fontSize: 10, color: "#38bdf8", marginTop: 4 }}>{a.device_name||a.host}</div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
              <span style={{ fontSize: 9, color: "#475569" }}>🕒 {new Date(a.fired_at).toLocaleString("pt-BR")}</span>
              <span style={{ fontSize: 9, color: "#22c55e", fontWeight: 700 }}>{a.value != null ? `${a.value.toFixed(1)}ms` : ""}</span>
            </div>
          </div>
        ))}
      </div>
      </div>

      <div style={S.card}>
        <div style={S.sectionTitle}>Dispositivos em Tempo Real</div>
        <div style={{ 
          display: "grid", 
          gridTemplateColumns: isMobile ? "1fr" : "repeat(auto-fill, minmax(240px, 1fr))", 
          gap: 15 
        }}>
          {devices.filter((d) => d.status==="online").slice(0,12).map((d) => (
            <div key={d.id} style={{ 
              background: "rgba(10, 15, 26, 0.4)", 
              border: "1px solid rgba(56, 189, 248, 0.15)", 
              borderRadius: 14, 
              padding: 14,
              position: "relative",
              boxShadow: "0 4px 15px rgba(0,0,0,0.2)"
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <div style={{ 
                  width: 36, height: 36, borderRadius: 10, 
                  background: "rgba(56, 189, 248, 0.1)", 
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 18,
                  border: "1px solid rgba(56, 189, 248, 0.2)"
                }}>
                  {deviceIcon(d.device_type)}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#fff", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.name}</div>
                  <div style={{ fontSize: 9, color: "#38bdf8", fontWeight: 600 }}>{d.client_name||"—"}</div>
                </div>
              </div>
              
              <div style={{ display: "flex", gap: 10, marginBottom: 10 }}>
                {d.last_cpu != null ? (
                  <>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#64748b", marginBottom: 4 }}>
                        <span>CPU</span><span style={{ color: "#38bdf8", fontWeight: 700 }}>{(d.last_cpu||0).toFixed(0)}%</span>
                      </div>
                      <Bar value={d.last_cpu} color="#38bdf8" />
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#64748b", marginBottom: 4 }}>
                        <span>RAM</span><span style={{ color: "#a78bfa", fontWeight: 700 }}>{(d.last_memory||0).toFixed(0)}%</span>
                      </div>
                      <Bar value={d.last_memory} color="#a78bfa" />
                    </div>
                  </>
                ) : (
                  <div style={{ flex: 1, textAlign: "center", padding: "8px 0", background: "rgba(56, 189, 248, 0.05)", borderRadius: 8, border: "1px solid rgba(56, 189, 248, 0.1)" }}>
                    <div style={{ fontSize: 10, color: "#38bdf8", fontWeight: 800 }}>MODO PUSH / AUTO</div>
                    <div style={{ fontSize: 8, color: "#4a6080" }}>{d.mac_address || d.serial_number || "SINAL OK"}</div>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.03)" }}>
                <div style={{ fontSize: 10, color: "#22c55e", fontWeight: 800, textShadow: "0 0 10px rgba(34, 197, 94, 0.4)" }}>● ONLINE</div>
                <div style={{ textAlign: "right" }}>
                   <div style={{ fontSize: 11, color: "#fff", fontWeight: 700 }}>{Math.round(d.last_latency||0)}<span style={{fontSize:8, marginLeft:2, color:"#4a6080"}}>ms</span></div>
                   <div style={{ fontSize: 7, color: "#475569" }}>{new Date(d.last_seen).toLocaleTimeString("pt-BR")}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
        {devices.filter((d) => d.status==="online").length === 0 && (
          <div style={{ textAlign: "center", padding: "40px 0", color: "#3a5070", fontSize: 12 }}>
            Aguardando dispositivos ficarem online...
          </div>
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
                  <span style={{ color: "#38bdf8", fontWeight: 600 }}>{e.device_name}</span>
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
    offline:   { bg:"rgba(255, 0, 85, 0.06)", border:"rgba(255, 0, 85, 0.28)", icon:"🔴", label:"Offline",   color:"#ff0055", shadow:"0 0 14px rgba(255,0,85,0.18)" },
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
          ["all", "TODOS", "#38bdf8", counts.all],
          ["offline", "OFFLINE", "#ff0055", counts.offline],
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
              boxShadow: filter === k ? `0 0 14px ${c}33` : "none",
              backdropFilter: "blur(10px)",
              letterSpacing: "0.8px",
              textTransform: "uppercase",
            }}
          >
            <span style={{ width: 10, height: 10, borderRadius: 999, background: c, boxShadow: `0 0 10px ${c}99` }} />
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
        <div style={{ textAlign: "center", padding: "70px 24px", background: "rgba(15,15,25,0.35)", borderRadius: 24, border: "1px solid rgba(255,255,255,0.06)" }}>
          <div style={{ fontSize: 56, marginBottom: 14, filter: "drop-shadow(0 0 14px rgba(56,189,248,0.35))" }}>✅</div>
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
                backdropFilter: "blur(12px)",
              }}
            >
              <div style={{ fontSize: 28, flexShrink: 0, filter: `drop-shadow(0 0 8px ${t.color})` }}>{t.icon}</div>

              <div style={{ flex: 1, minWidth: 260 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 16, fontWeight: 900, color: t.color, letterSpacing: "0.6px", textShadow: `0 0 8px ${t.color}66` }}>
                    {a.trigger_name || (a.alert_type === "offline" ? "DEVICE OFFLINE" : "ALERT TRIGGERED")}
                  </span>
                  <span style={{ fontSize: 11, fontWeight: 900, background: `${t.color}20`, color: t.color, borderRadius: 999, padding: "4px 10px", border: `1px solid ${t.color}40`, textTransform: "uppercase" }}>
                    {t.label}
                  </span>
                  {userRole === "superadmin" && (
                    <span style={{ fontSize: 11, fontWeight: 800, background: "rgba(56,189,248,0.12)", color: "#38bdf8", borderRadius: 999, padding: "4px 10px", border: "1px solid rgba(56,189,248,0.28)" }}>
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
              <tr key={t.id} style={{ background: i % 2 === 0 ? "transparent" : "rgba(15,23,42,0.2)", transition: "background 0.2s", ":hover": { background: "rgba(56,189,248,0.05)" } }}>
                <td style={{ ...S.td, border: "none", padding: "16px 20px" }}><span style={S.badge(t.enabled?"#22c55e":"#4a6080")}>{t.enabled?"● ativo":"○ inativo"}</span></td>
                <td style={{ ...S.td, border: "none", fontWeight: 700, color: "#f1f5f9", fontSize: 14 }}>{t.name}</td>
                <td style={{ ...S.td, border: "none", color: "#cbd5e1" }}>{EXPRESSIONS.find((e) => e.value===t.expression)?.label||t.expression}</td>
                <td style={{ ...S.td, border: "none", color: "#f59e0b", fontWeight: 800, fontSize: 15 }}>{t.threshold}</td>
                {userRole === "superadmin" && <td style={{ ...S.td, border: "none" }}><span style={{ fontSize: 11, color: "#38bdf8", fontWeight: 600 }}>{clients.find((c) => c.id===t.client_id)?.name||"Todos"}</span></td>}
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
            <div style={S.fg}><label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#cbd5e1", cursor: "pointer", fontWeight: 600 }}><input type="checkbox" style={{ accentColor: "#38bdf8", transform: "scale(1.2)" }} checked={form.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Trigger ativo</label></div>
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
          { label: "Potência Atual", value: (summary.total_power_w/1000).toFixed(2), color: "#38bdf8", suffix: " kW" },
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
                <div style={{ fontSize: 10, color: "#38bdf8", marginBottom: 10 }}>🏢 {inv.client_name}</div>
              )}

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 12 }}>
                {[
                  { label: "Potência", value: `${power.toFixed(2)} kW`, color: "#38bdf8", icon: "⚡" },
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
  const [page, setPage] = useState("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (authed) {
      api("/auth/me").then((u) => { setUserRole(u.role); setUserClientId(u.client_id); }).catch(() => {});
    }
  }, [authed]);

  useEffect(() => {
    if (isMobile) setSidebarOpen(false);
  }, [page, isMobile]);

  if (!authed) return <AuthPage onLogin={(role, cid) => { setUserRole(role); setUserClientId(cid); setAuthed(true); }} />;

  const isSuperAdmin = userRole === "superadmin";

  const NAV_SUPERADMIN = [
    { section: "GERAL" },
    { id: "dashboard", label: "Dashboard",  icon: "📊" },
    { section: "GERENCIAR" },
    { id: "clients",   label: "Clientes",   icon: "🏢" },
    { id: "devices",   label: "Devices",    icon: "🖥️" },
    { id: "triggers",  label: "Triggers",   icon: "⚡" },
    { id: "alerts",    label: "Alertas",    icon: "🚨" },
    { id: "events",    label: "Eventos",    icon: "🎬" },
    { id: "solar", label: "Solar", icon: "☀️" },
  ];

  const NAV_CLIENT = [
    { section: "MENU" },
    { id: "dashboard", label: "Dashboard", icon: "📊" },
    { id: "devices",   label: "Devices",   icon: "🖥️" },
    { id: "alerts",    label: "Alertas",   icon: "🚨" },
    { id: "events",    label: "Eventos",   icon: "🎬" },
  ];

  const NAV = isSuperAdmin ? NAV_SUPERADMIN : NAV_CLIENT;

  const PAGES = {
    dashboard: <Dashboard userRole={userRole} />,
    clients:   <ClientsPage />,
    devices:   <DevicesPage userRole={userRole} userClientId={userClientId} />,
    triggers:  <TriggersPage userRole={userRole} />,
    alerts:    <AlertsPage userRole={userRole} />,
    events:    <EventsPage userRole={userRole} />,
    solar: <SolarPage userRole={userRole} />,
  };

  const sidebarStyle = {
    ...S.sidebar,
    position: isMobile ? "fixed" : "relative",
    zIndex: 1001,
    height: "100vh",
    transform: isMobile ? (sidebarOpen ? "translateX(0)" : "translateX(-100%)") : "none",
    transition: "transform 0.3s ease-in-out",
    width: 240,
  };

  return (
    <div style={{...S.app, flexDirection: "row", overflow: "hidden"}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;500;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: rgba(0,0,0,0.1); }
        ::-webkit-scrollbar-thumb { background: rgba(56, 189, 248, 0.2); border-radius: 10px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(56, 189, 248, 0.4); }
        input[type=checkbox] { accent-color: #38bdf8; }
        
        @media (max-width: 768px) {
          body { overflow: auto !important; }
          .main-content { padding: 15px !important; }
          .grid-responsive { grid-template-columns: 1fr !important; }
        }

        .glass {
          background: rgba(255, 255, 255, 0.03);
          backdrop-filter: blur(10px);
          border: 1px solid rgba(255, 255, 255, 0.05);
        }

        @keyframes pulse {
          0% { opacity: 0.6; }
          50% { opacity: 1; }
          100% { opacity: 0.6; }
        }
      `}</style>

      {isMobile && sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.5)",
            backdropFilter: "blur(2px)",
            zIndex: 1000
          }}
        />
      )}

      <div style={sidebarStyle}>
        <div style={S.logo}>
          <div style={{ display: "flex", alignItems: "center", marginBottom: 8 }}>
            <FuturisticLogo />
            <div style={S.logoTitle}>ETI SENTINEL</div>
          </div>
          <div style={{...S.logoSub, color: "#38bdf8", fontWeight: "bold"}}>🚀 v1.0.3 (CACHE FIXED)</div>
          <div style={S.logoSub}>{isSuperAdmin ? "⚡ Superadmin" : "👤 Cliente"}</div>
        </div>

        <div style={{ flex: 1, overflowY: "auto" }}>
          {NAV.map((n, i) =>
            n.section
              ? <div key={i} style={S.navSection}>{n.section}</div>
              : <div key={n.id} style={S.navItem(page===n.id)} onClick={() => setPage(n.id)}>
                  <span>{n.icon}</span><span>{n.label}</span>
                </div>
          )}
        </div>

        <div style={{ marginTop: "auto", padding: "16px" }}>
          <button style={{ ...S.btn("ghost"), width: "100%", fontSize: 10 }} onClick={() => { removeToken(); setAuthed(false); }}>
            ⏻ Sair
          </button>
        </div>
      </div>

      <div style={{ ...S.main, padding: isMobile ? "70px 15px 20px" : "30px 40px" }} className="main-content">
        {isMobile && (
          <button
            onClick={() => setSidebarOpen(true)}
            style={{
              position: "fixed",
              top: 15,
              left: 15,
              zIndex: 999,
              background: "rgba(10, 15, 26, 0.8)",
              border: "1px solid rgba(56, 189, 248, 0.3)",
              color: "#38bdf8",
              padding: "8px 12px",
              borderRadius: 8,
              fontSize: 18,
              backdropFilter: "blur(8px)",
              boxShadow: "0 0 15px rgba(56, 189, 248, 0.2)"
            }}
          >
            ☰
          </button>
        )}
        {PAGES[page] || PAGES.dashboard}
      </div>
    </div>
  );
}
