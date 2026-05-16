import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, Camera, Gauge, Network, RefreshCw, Scan, Video, Zap } from "lucide-react";
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

  const runSpeedTest = async () => {
    onToast?.("Speed Test", "Iniciando teste real no agente...", "info");
    try {
      // Notifica o agente via API (supondo que o agente tenha um endpoint exposto ou via WebSocket)
      // Como o agente é quem deve iniciar, vamos enviar um comando para a Ingest API encaminhar
      await api?.("/speedtest/run", { method: "POST" });
      onToast?.("Speed Test", "Teste solicitado ao Agente de Borda. Aguarde os resultados.", "success");
    } catch (e) {
      onToast?.("Speed Test", "Erro ao solicitar teste: " + e.message, "error");
    }
  };

  // Detecções de IA dos eventos reais
  const aiEvents = useMemo(() => {
    return events
      .filter((e) => (e.event_type || "").startsWith("ai_"))
      .slice(0, 6);
  }, [events]);

  // Câmeras e DVRs dos dispositivos reais
  const cameraDevices = useMemo(() => {
    return devices.filter((d) => {
      const t = String(d.type || d.tipo || "").toLowerCase();
      return t.includes("camera") || t.includes("câmera") || t.includes("cam") ||
             t.includes("dvr") || t.includes("nvr") || t.includes("speed") || t.includes("dome");
    });
  }, [devices]);

  const _AI_LABELS = {
    ai_person_detected:   "👤 Pessoa detectada",
    ai_car_detected:      "🚗 Carro detectado",
    ai_motorcycle_detected: "🏍 Moto detectada",
    ai_truck_detected:    "🚛 Caminhão detectado",
    ai_bus_detected:      "🚌 Ônibus detectado",
    ai_zone_intrusion:    "🔴 Intrusão em zona",
    ai_line_crossing:     "⚠️ Cruzou linha virtual",
    ai_crowd_alert:       "👥 Alerta de lotação",
    ai_people_count:      "📊 Contagem de pessoas",
  };

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
                onClick={runSpeedTest}
              >
                Teste ISP
              </Button>
              <Button
                variant="secondary"
                leftIcon={<Scan size={16} />}
                onClick={() => onToast?.("Scanner", "Use o menu Descoberta para varrer câmeras na rede", "info")}
              >
                Varredura
              </Button>
            </div>
          </Card>

          <Card title="Câmeras Monitoradas" right={<Pill label={`${cameraDevices.length} câmera${cameraDevices.length !== 1 ? "s" : ""}`} color="neutral" />}>
            {cameraDevices.length === 0 ? (
              <div style={{ color: etiTheme.colors.text3, fontSize: 13, padding: "8px 0" }}>
                Nenhuma câmera ou DVR cadastrado.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {cameraDevices.slice(0, 5).map((cam) => {
                  const st = String(cam.status || cam.estado || "").toLowerCase();
                  const isOnline = st === "online" || st === "ok" || st === "ativo";
                  return (
                    <div
                      key={cam.id || cam.name}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "8px 10px", borderRadius: 10,
                        background: "rgba(0,0,0,0.18)",
                        border: `1px solid ${etiTheme.colors.borderSoft}`,
                      }}
                    >
                      <Camera size={14} color={isOnline ? etiTheme.colors.success : etiTheme.colors.critical} />
                      <div style={{ flex: 1, fontSize: 13, fontWeight: 700, color: etiTheme.colors.text }}>
                        {cam.name || cam.nome || "Câmera"}
                      </div>
                      <div style={{ fontSize: 11, color: etiTheme.colors.text3 }}>{cam.ip || ""}</div>
                      <Pill label={isOnline ? "Online" : "Offline"} color={isOnline ? "success" : "critical"} />
                    </div>
                  );
                })}
                {cameraDevices.length > 5 && (
                  <div style={{ fontSize: 12, color: etiTheme.colors.text3, textAlign: "center" }}>
                    +{cameraDevices.length - 5} câmera{cameraDevices.length - 5 !== 1 ? "s" : ""} no inventário
                  </div>
                )}
              </div>
            )}
          </Card>

          <Card title="Ações Rápidas" right={<Zap size={16} color={etiTheme.colors.cyan} />}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <Button variant="secondary" leftIcon={<Network size={14} />} onClick={() => onGoTopology?.(null)}>
                Topologia
              </Button>
              <Button variant="secondary" leftIcon={<Camera size={14} />} onClick={() => onToast?.("Câmeras", "Acesse o menu Dispositivos para gerenciar câmeras", "info")}>
                Câmeras
              </Button>
              <Button variant="secondary" leftIcon={<Video size={14} />} onClick={() => onToast?.("Ao Vivo", "Acesse http://localhost:8808 para ver o stream local", "info")}>
                Ao Vivo
              </Button>
              <Button variant="secondary" leftIcon={<Scan size={14} />} onClick={() => onToast?.("Varredura", "Acesse o menu Descoberta para escanear câmeras ONVIF", "info")}>
                Descoberta
              </Button>
            </div>
            <div style={{ marginTop: 10, fontSize: 12, color: etiTheme.colors.text3, lineHeight: 1.5 }}>
              Painel local do técnico:{" "}
              <a href="http://localhost:8808" target="_blank" rel="noreferrer" style={{ color: etiTheme.colors.cyan, fontWeight: 700 }}>
                localhost:8808
              </a>
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

          <Card
            title="Detecções de IA"
            right={
              aiEvents.length > 0
                ? <Pill label={`${aiEvents.length} hoje`} color="warn" />
                : <Pill label="IA ativa" color="success" />
            }
          >
            {aiEvents.length === 0 ? (
              <div style={{ color: etiTheme.colors.text3, fontSize: 13, padding: "12px 0", textAlign: "center" }}>
                <Camera size={28} color={etiTheme.colors.text3} style={{ display: "block", margin: "0 auto 8px" }} />
                Nenhuma detecção ainda. Passe em frente a uma câmera para testar.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {aiEvents.map((ev, i) => {
                  const label = _AI_LABELS[ev.event_type] || (ev.event_type || "Detecção").replace("ai_", "").replace(/_/g, " ");
                  const cam = ev.device_name || ev.source_name || "Câmera";
                  const ts = timeAgoPtBR(ev.created_at || ev.timestamp || Date.now());
                  const sev = String(ev.severity || "info").toLowerCase();
                  return (
                    <div
                      key={ev.id || i}
                      style={{
                        display: "flex", alignItems: "center", gap: 10,
                        padding: "8px 10px", borderRadius: 10,
                        background: "rgba(0,0,0,0.18)",
                        border: `1px solid ${sev === "warn" ? "rgba(245,158,11,0.3)" : etiTheme.colors.borderSoft}`,
                      }}
                    >
                      <div style={{ fontSize: 20, flexShrink: 0 }}>
                        {label.split(" ")[0]}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: etiTheme.colors.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {label.replace(/^[^\s]+\s/, "")}
                        </div>
                        <div style={{ fontSize: 11, color: etiTheme.colors.text3 }}>{cam}</div>
                      </div>
                      <div style={{ fontSize: 11, color: etiTheme.colors.text3, flexShrink: 0 }}>{ts}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          <Card
            title="Acesso rápido"
            right={
              <Button variant="primary" leftIcon={<Video size={16} />}
                onClick={() => window.open("http://localhost:8808", "_blank")}>
                Painel Técnico
              </Button>
            }
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div style={{ color: etiTheme.colors.text2, fontSize: 12 }}>
                A topologia mostra a cadeia de conexão da rede. O painel técnico exibe câmeras e eventos de IA.
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
