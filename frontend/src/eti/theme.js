export const etiTheme = {
  colors: {
    bg: "#0B1220",
    surface: "#0F1B2D",
    card: "#12233A",
    border: "rgba(47, 122, 248, 0.18)",
    borderSoft: "rgba(255, 255, 255, 0.06)",
    text: "#E6EDF7",
    text2: "#9FB0C7",
    text3: "rgba(159, 176, 199, 0.65)",
    blue: "#2F7AF8",
    cyan: "#21D4FD",
    success: "#2FD07A",
    warn: "#F6C343",
    critical: "#FF4D4F",
  },
  radius: {
    sm: 10,
    md: 14,
    lg: 18,
    xl: 22,
  },
  shadow: {
    card: "0 18px 50px rgba(0,0,0,0.35)",
    glow: "0 0 18px rgba(47, 122, 248, 0.18)",
  },
};

export function clamp(n, min, max) {
  const v = Number(n);
  if (!Number.isFinite(v)) return min;
  return Math.max(min, Math.min(max, v));
}

export function formatBps(bps) {
  const v = Number(bps);
  if (!Number.isFinite(v) || v < 0) return "—";
  const kbps = v / 1000;
  const mbps = kbps / 1000;
  if (mbps >= 1) return `${mbps.toFixed(2)} Mbps`;
  if (kbps >= 1) return `${kbps.toFixed(0)} Kbps`;
  return `${v.toFixed(0)} bps`;
}

export function formatMs(ms) {
  const v = Number(ms);
  if (!Number.isFinite(v) || v < 0) return "—";
  return `${Math.round(v)}ms`;
}

export function timeAgoPtBR(date) {
  const d = date instanceof Date ? date : new Date(date);
  const diff = Date.now() - d.getTime();
  if (!Number.isFinite(diff)) return "—";
  const s = Math.max(0, Math.floor(diff / 1000));
  if (s < 60) return `${s}s atrás`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min atrás`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h atrás`;
  const days = Math.floor(h / 24);
  return `${days}d atrás`;
}

