import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Gauge, Network, RefreshCw, Stethoscope, Wifi } from "lucide-react";
import { etiTheme, clamp, timeAgoPtBR } from "../eti/theme";
import { Button, Card, Pill, Segmented } from "../components/eti/EtiUI";
import { genSeries, InternetActivityCard, MiniList } from "./dashboard/dashboardParts";

export default function DashboardEti({ api, onToast, onGoTopology }) {
  const [tab, setTab] = useState("internet");
  const [wan, setWan] = useState("all");
  const [location, setLocation] = useState("");
  const [locations, setLocations] = useState([]);
  const [showInternet, setShowInternet] = useState(true);
  const [showLatency, setShowLatency] = useState(true);
  const [showLoss, setShowLoss] = useState(false);
  const [series, setSeries] = useState(() => genSeries(24));
  const [lastUpdatedAt, setLastUpdatedAt] = useState(Date.now());

  const [stats, setStats] = useState(null);
  const [devices, setDevices] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [events, setEvents] = useState([]);

  const refresh = useCallback(() => {
    setLastUpdatedAt(Date.now());
    setSeries(genSeries(24));
    
    const locParam = location ? `?location=${encodeURIComponent(location)}` : "";
    const reqs = [
      api?.(`/stats${locParam}`).then((d) => setStats(d)).catch(() => {}),
      api?.(`/devices${locParam}`).then((d) => setDevices(Array.isArray(d) ? d : [])).catch(() => {}),
      api?.(`/alerts${locParam}`).then((d) => setAlerts(Array.isArray(d) ? d : [])).catch(() => {}),
      api?.(`/events${locParam}`).then((d) => setEvents(Array.isArray(d) ? d : [])).catch(() => {}),
      api?.("/locations").then((d) => setLocations(Array.isArray(d) ? d : [])).catch(() => {}),
    ];
    Promise.allSettled(reqs).then(() => {});
  }, [api, location]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const siteName = location || "ETI Sentinel";
  const gatewayIp = stats?.gateway_ip || "192.168.0.1";

  const kpi = useMemo(() => {
    const ds = stats && typeof stats === "object" ? stats : {};
    const total = Number(ds.devices || devices.length || 0);
    const online = Number(ds.online || 0);
    const offline = Number(ds.offline || 0);
    const openAlerts = Array.isArray(alerts) ? alerts.filter((a) => (a.status || "").toLowerCase() !== "ack").length : 0;
    const down = clamp((series[series.length - 1]?.down_mbps || 0) * 1000 * 1000, 0, 1e12);
    const up = clamp((series[series.length - 1]?.up_mbps || 0) * 1000 * 1000, 0, 1e12);
    const lat = clamp(series[series.length - 1]?.latency_ms || 0, 0, 9999);
    return {
      total,
      online,
      offline,
      openAlerts,
      downBps: down,
      upBps: up,
      latencyMs: lat,
    };
  }, [alerts, devices.length, series, stats]);

  const criticalItems = useMemo(() => {
    const ds = Array.isArray(devices) ? devices : [];
    const pick = ds
      .map((d) => {
        const status = String(d.status || d.estado || "").toLowerCase();
        const offline = status === "offline";
        const warn = status === "warning" || status === "alert";
        const sev = offline ? "critical" : warn ? "warn" : "success";
        return {
          id: d.id || `${d.name || d.nome}-${d.ip || ""}`,
          title: d.name || d.nome || "Device",
          subtitle: `${d.type || d.tipo || "device"} • ${d.ip || "—"} • visto ${timeAgoPtBR(d.last_seen_at || d.last_seen || Date.now())}`,
          pill: offline ? "Offline" : warn ? "Atenção" : "Online",
          pillColor: offline ? "critical" : warn ? "warn" : "success",
          raw: d,
          sev,
        };
      })
      .filter((x) => x.sev !== "success")
      .slice(0, 6);
    if (pick.length > 0) return pick;
    return [
      {
        id: "ok-1",
        title: "Nenhum ativo crítico agora",
        subtitle: "Tudo saudável — monitoração em andamento",
        pill: "OK",
        pillColor: "success",
        raw: null,
      },
    ];
  }, [devices]);

  const recentEvents = useMemo(() => {
    const ev = Array.isArray(events) ? events : [];
    const norm = ev
      .slice(0, 8)
      .map((e, idx) => ({
        id: e.id || `${idx}-${e.created_at || ""}`,
        title: e.device_name || e.source_name || e.host || "Evento",
        subtitle: `${e.event_type || e.message || "Ocorrência"} • ${timeAgoPtBR(e.created_at || Date.now())}`,
        pill: (e.severity || "info").toUpperCase(),
        pillColor: String(e.severity || "info").toLowerCase() === "critical" ? "critical" : String(e.severity || "").toLowerCase() === "warning" ? "warn" : "neutral",
        raw: e,
      }));
    if (norm.length > 0) return norm;
    return [
      { id: "ev-0", title: "Sem eventos recentes", subtitle: "Aguardando novas ocorrências", pill: "INFO", pillColor: "neutral", raw: null },
    ];
  }, [events]);

  const topApps = [
    { name: "Netflix" },
    { name: "Instagram" },
    { name: "YouTube" },
    { name: "SSL/TLS" },
    { name: "WhatsApp" },
    { name: "QUIC" },
    { name: "Google" },
    { name: "TikTok" },
  ];

  return (
    <div style={{ color: etiTheme.colors.text }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 14,
              background: "rgba(33, 212, 253, 0.10)",
              border: `1px solid rgba(33, 212, 253, 0.24)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Network size={18} color={etiTheme.colors.cyan} />
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 950, letterSpacing: "0.05em" }}>Network</div>
            <div style={{ fontSize: 12, color: etiTheme.colors.text3 }}>Dashboard ETI • ETI SENTINEL • última atualização {timeAgoPtBR(lastUpdatedAt)}</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <select
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            style={{
              height: 40,
              borderRadius: 12,
              padding: "0 12px",
              background: "rgba(59, 158, 255, 0.12)",
              border: `1px solid ${etiTheme.colors.cyan}44`,
              color: etiTheme.colors.text,
              fontWeight: 800,
              letterSpacing: "0.06em",
              marginRight: 10
            }}
          >
            <option value="">🌎 Todos os Pontos</option>
            {locations.map(loc => (
              <option key={loc} value={loc}>📍 {loc}</option>
            ))}
          </select>
          <Segmented
            value={tab}
            options={[
              { value: "internet", label: "Internet" },
              { value: "wifi", label: "WiFi" },
              { value: "flows", label: "Flows" },
            ]}
            onChange={(v) => {
              setTab(v);
              onToast?.("Aba", `Mudou para ${v.toUpperCase()}`, "info");
            }}
          />
          <select
            value={wan}
            onChange={(e) => setWan(e.target.value)}
            style={{
              height: 40,
              borderRadius: 12,
              padding: "0 12px",
              background: "rgba(0,0,0,0.18)",
              border: `1px solid ${etiTheme.colors.borderSoft}`,
              color: etiTheme.colors.text,
              fontWeight: 800,
              letterSpacing: "0.06em",
            }}
          >
            <option value="all">All WANs</option>
            <option value="wan1">WAN 1</option>
            <option value="wan2">WAN 2</option>
          </select>
          <Button variant="secondary" leftIcon={<RefreshCw size={16} />} onClick={refresh}>
            Atualizar
          </Button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 16, alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Card
            title={siteName}
            right={<Pill label="Online" color="success" />}
            style={{
              background: `radial-gradient(1200px 380px at 20% 0%, rgba(47, 122, 248, 0.20), transparent 55%), linear-gradient(180deg, ${etiTheme.colors.card}, rgba(18, 35, 58, 0.65))`,
            }}
          >
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 10 }}>
              <div style={{ color: etiTheme.colors.text3, fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", textTransform: "uppercase" }}>Gateway IP</div>
              <div style={{ fontWeight: 900 }}>{gatewayIp}</div>

              <div style={{ color: etiTheme.colors.text3, fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", textTransform: "uppercase" }}>Devices</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Pill label={`${kpi.online} online`} color="success" />
                <Pill label={`${kpi.offline} offline`} color={kpi.offline > 0 ? "critical" : "neutral"} />
              </div>

              <div style={{ color: etiTheme.colors.text3, fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", textTransform: "uppercase" }}>Monthly Data</div>
              <div style={{ fontWeight: 900 }}>{stats?.monthly_gb ? `${stats.monthly_gb} GB` : "—"}</div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderRadius: 16, border: `1px solid ${etiTheme.colors.borderSoft}`, background: "rgba(0,0,0,0.18)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, color: etiTheme.colors.text2, fontWeight: 900, letterSpacing: "0.06em", textTransform: "uppercase", fontSize: 11 }}>
                    <Wifi size={14} /> Download
                  </div>
                  <div style={{ fontWeight: 950 }}>{(kpi.downBps / 1e6).toFixed(2)} Mbps</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderRadius: 16, border: `1px solid ${etiTheme.colors.borderSoft}`, background: "rgba(0,0,0,0.18)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, color: etiTheme.colors.text2, fontWeight: 900, letterSpacing: "0.06em", textTransform: "uppercase", fontSize: 11 }}>
                    <Gauge size={14} /> Upload
                  </div>
                  <div style={{ fontWeight: 950 }}>{(kpi.upBps / 1e6).toFixed(2)} Mbps</div>
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderRadius: 16, border: `1px solid ${etiTheme.colors.borderSoft}`, background: "rgba(0,0,0,0.18)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, color: etiTheme.colors.text2, fontWeight: 900, letterSpacing: "0.06em", textTransform: "uppercase", fontSize: 11 }}>
                    <Activity size={14} /> Latência
                  </div>
                  <div style={{ fontWeight: 950 }}>{Math.round(kpi.latencyMs)}ms</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", borderRadius: 16, border: `1px solid ${etiTheme.colors.borderSoft}`, background: "rgba(0,0,0,0.18)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, color: etiTheme.colors.text2, fontWeight: 900, letterSpacing: "0.06em", textTransform: "uppercase", fontSize: 11 }}>
                    Alertas
                  </div>
                  <div style={{ fontWeight: 950, color: kpi.openAlerts > 0 ? etiTheme.colors.critical : etiTheme.colors.success }}>{kpi.openAlerts}</div>
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 14 }}>
              <Button
                variant="secondary"
                leftIcon={<Gauge size={16} />}
                onClick={() => onToast?.("Speed Test", "Executar teste ISP (demo)", "info")}
              >
                Teste ISP
              </Button>
              <Button
                variant="secondary"
                leftIcon={<Stethoscope size={16} />}
                onClick={() => onToast?.("WiFi Doctor", "Abrir diagnóstico WiFi (demo)", "info")}
              >
                WiFi Doctor
              </Button>
            </div>
          </Card>

          <Card title="Default WiFi Speeds" right={<Pill label="Conservative" color="neutral" />}>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ color: etiTheme.colors.text3, fontSize: 11, fontWeight: 900, letterSpacing: "0.12em", textTransform: "uppercase" }}>
                Channel Widths (MHz)
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "56px 1fr", gap: 10, alignItems: "center" }}>
                <div style={{ color: etiTheme.colors.text2, fontWeight: 900 }}>5 GHz</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {[20, 40, 80, 160].map((w) => (
                    <Button
                      key={w}
                      size="sm"
                      variant={w === 40 ? "primary" : "ghost"}
                      onClick={() => onToast?.("WiFi", `Largura 5GHz: ${w}MHz (demo)`, "info")}
                    >
                      {w}
                    </Button>
                  ))}
                </div>
                <div style={{ color: etiTheme.colors.text2, fontWeight: 900 }}>6 GHz</div>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {[20, 40, 80, 160, 320].map((w) => (
                    <Button
                      key={w}
                      size="sm"
                      variant={w === 160 || w === 320 ? "primary" : "ghost"}
                      onClick={() => onToast?.("WiFi", `Largura 6GHz: ${w}MHz (demo)`, "info")}
                    >
                      {w}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
          </Card>

          <Card
            title="CyberSecure Enhanced"
            right={
              <Button
                size="sm"
                variant="primary"
                onClick={() => onToast?.("CyberSecure", "Ativar módulo de segurança (demo)", "info")}
              >
                Ativar
              </Button>
            }
          >
            <div style={{ color: etiTheme.colors.text2, fontSize: 12, lineHeight: 1.45 }}>
              Até 70K assinaturas • filtros de conteúdo • integração ETI Sentinel.
            </div>
            <div style={{ marginTop: 10 }}>
              <button
                type="button"
                onClick={() => onToast?.("Widgets", "Configurar widgets (demo)", "info")}
                style={{
                  background: "transparent",
                  border: "none",
                  color: etiTheme.colors.cyan,
                  fontWeight: 900,
                  cursor: "pointer",
                  padding: 0,
                  letterSpacing: "0.06em",
                }}
              >
                Dashboard Widgets
              </button>
            </div>
          </Card>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <InternetActivityCard
            series={series}
            showInternet={showInternet}
            showLatency={showLatency}
            showLoss={showLoss}
            onToggleInternet={setShowInternet}
            onToggleLatency={setShowLatency}
            onToggleLoss={setShowLoss}
          />

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <MiniList
              title="Ativos críticos"
              items={criticalItems}
              onPrimary={(it) => {
                if (it?.raw) onGoTopology?.(it.raw);
                else onToast?.("Topologia", "Sem itens críticos para focar", "info");
              }}
            />
            <MiniList
              title="Eventos recentes"
              items={recentEvents}
              onPrimary={() => onToast?.("Eventos", "Abrir detalhes do evento (demo)", "info")}
            />
          </div>

          <Card title="Top Apps">
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {topApps.map((a) => (
                <button
                  key={a.name}
                  type="button"
                  onClick={() => onToast?.("App", `${a.name} (demo)`, "info")}
                  style={{
                    width: 84,
                    height: 70,
                    borderRadius: 16,
                    background: "rgba(0,0,0,0.18)",
                    border: `1px solid ${etiTheme.colors.borderSoft}`,
                    color: etiTheme.colors.text2,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 900,
                    fontSize: 12,
                  }}
                >
                  {a.name}
                </button>
              ))}
            </div>
          </Card>

          <Card
            title="Acesso rápido"
            right={
              <Button variant="primary" leftIcon={<Wifi size={16} />} onClick={() => onToast?.("CFTV", "Abrir visão de câmeras (menu Câmeras)", "info")}>
                CFTV
              </Button>
            }
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div style={{ color: etiTheme.colors.text2, fontSize: 12 }}>
                Use a topologia para diagnosticar falhas e entender a cadeia de conexão.
              </div>
              <Button variant="secondary" leftIcon={<Network size={16} />} onClick={() => onGoTopology?.(null)}>
                Abrir Topologia
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
