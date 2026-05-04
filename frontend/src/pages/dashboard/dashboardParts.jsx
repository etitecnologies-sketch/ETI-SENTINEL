import React from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { etiTheme, clamp, formatBps, formatMs, timeAgoPtBR } from "../../eti/theme";
import { Button, Card, CheckboxPill, Pill } from "../../components/eti/EtiUI";

export function genSeries(hours = 24) {
  const out = [];
  const now = Date.now();
  for (let i = hours; i >= 0; i -= 1) {
    const t = now - i * 60 * 60 * 1000;
    const p = (Math.sin(i / 2.8) + 1) / 2;
    const spike = Math.random() < 0.08 ? Math.random() * 10 : 0;
    const downMbps = clamp(2 + p * 12 + spike, 0, 30);
    const upMbps = clamp(0.8 + p * 5 + spike * 0.35, 0, 18);
    const latency = clamp(18 + (1 - p) * 55 + (Math.random() * 8 - 4), 8, 130);
    const loss = Math.random() < 0.06 ? clamp(Math.random() * 4, 0, 8) : 0;
    out.push({
      ts: t,
      time: new Date(t).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
      down_mbps: downMbps,
      up_mbps: upMbps,
      latency_ms: latency,
      loss_pct: loss,
    });
  }
  return out;
}

export function MetricTile({ icon: Icon, label, value, color }) {
  return (
    <div
      style={{
        background: "rgba(0,0,0,0.22)",
        border: `1px solid ${etiTheme.colors.borderSoft}`,
        borderRadius: etiTheme.radius.lg,
        padding: "12px 12px",
        display: "flex",
        alignItems: "center",
        gap: 10,
      }}
    >
      <div
        style={{
          width: 38,
          height: 38,
          borderRadius: 14,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: `rgba(47, 122, 248, 0.12)`,
          border: `1px solid ${etiTheme.colors.border}`,
        }}
      >
        <Icon size={18} color={color || etiTheme.colors.blue} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: etiTheme.colors.text3, fontSize: 10, fontWeight: 900, letterSpacing: "0.12em", textTransform: "uppercase" }}>{label}</div>
        <div style={{ color: etiTheme.colors.text, fontSize: 16, fontWeight: 900, letterSpacing: "0.04em" }}>{value}</div>
      </div>
    </div>
  );
}

export function MiniList({ title, items, onPrimary }) {
  return (
    <Card title={title} style={{ minHeight: 210 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {items.map((it) => (
          <button
            key={it.id}
            type="button"
            onClick={() => onPrimary(it)}
            style={{
              textAlign: "left",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              background: "rgba(0,0,0,0.18)",
              border: `1px solid ${etiTheme.colors.borderSoft}`,
              borderRadius: etiTheme.radius.lg,
              padding: "12px 12px",
              cursor: "pointer",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ color: etiTheme.colors.text, fontWeight: 900, fontSize: 13, letterSpacing: "0.03em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {it.title}
              </div>
              <div style={{ color: etiTheme.colors.text3, fontSize: 11, marginTop: 3 }}>{it.subtitle}</div>
            </div>
            <Pill label={it.pill} color={it.pillColor} />
          </button>
        ))}
      </div>
    </Card>
  );
}

export function InternetActivityCard({ series, showInternet, showLatency, showLoss, onToggleInternet, onToggleLatency, onToggleLoss }) {
  return (
    <Card
      title="Internet Activity"
      right={
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
          <CheckboxPill checked={showInternet} label="Internet" onChange={onToggleInternet} />
          <CheckboxPill checked={showLatency} label="Avg. Latency" onChange={onToggleLatency} />
          <CheckboxPill checked={showLoss} label="Packet Loss" onChange={onToggleLoss} />
        </div>
      }
      style={{ minHeight: 360 }}
    >
      <div style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="time" tick={{ fill: "rgba(159,176,199,0.7)", fontSize: 11 }} axisLine={{ stroke: "rgba(255,255,255,0.06)" }} tickLine={false} />
            <YAxis yAxisId="mbps" tick={{ fill: "rgba(159,176,199,0.7)", fontSize: 11 }} axisLine={{ stroke: "rgba(255,255,255,0.06)" }} tickLine={false} unit=" Mbps" domain={[0, 30]} />
            <YAxis yAxisId="ms" orientation="right" tick={{ fill: "rgba(159,176,199,0.7)", fontSize: 11 }} axisLine={{ stroke: "rgba(255,255,255,0.06)" }} tickLine={false} unit=" ms" domain={[0, 130]} />
            <Tooltip
              contentStyle={{ background: "rgba(7, 13, 24, 0.94)", border: `1px solid ${etiTheme.colors.borderSoft}`, borderRadius: 12, color: etiTheme.colors.text }}
              labelStyle={{ color: etiTheme.colors.text2, fontWeight: 900 }}
              formatter={(value, name) => {
                if (name === "latency_ms") return [formatMs(value), "Latência"];
                if (name === "loss_pct") return [`${Number(value).toFixed(1)}%`, "Perda"];
                if (name === "down_mbps") return [`${Number(value).toFixed(2)} Mbps`, "Download"];
                if (name === "up_mbps") return [`${Number(value).toFixed(2)} Mbps`, "Upload"];
                return [value, name];
              }}
            />
            {showInternet && <Line yAxisId="mbps" type="monotone" dataKey="down_mbps" stroke={etiTheme.colors.cyan} strokeWidth={2} dot={false} />}
            {showInternet && <Line yAxisId="mbps" type="monotone" dataKey="up_mbps" stroke={etiTheme.colors.blue} strokeWidth={2} dot={false} />}
            {showLatency && <Line yAxisId="ms" type="monotone" dataKey="latency_ms" stroke={etiTheme.colors.warn} strokeWidth={2} dot={false} strokeDasharray="4 4" />}
            {showLoss && <Line yAxisId="ms" type="monotone" dataKey="loss_pct" stroke={etiTheme.colors.critical} strokeWidth={2} dot={false} />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12 }}>
        <div style={{ height: 10, borderRadius: 999, background: "rgba(47, 208, 122, 0.26)", border: "1px solid rgba(47, 208, 122, 0.28)" }} />
        <div style={{ height: 10, borderRadius: 999, background: "rgba(47, 208, 122, 0.26)", border: "1px solid rgba(47, 208, 122, 0.28)" }} />
      </div>
    </Card>
  );
}

export function SiteStatusCard({
  siteName,
  gatewayIp,
  online,
  offline,
  monthlyGb,
  downBps,
  upBps,
  latencyMs,
  openAlerts,
  onSpeedTest,
  onWifiDoctor,
  leftTiles,
}) {
  return (
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
          <Pill label={`${online} online`} color="success" />
          <Pill label={`${offline} offline`} color={offline > 0 ? "critical" : "neutral"} />
        </div>

        <div style={{ color: etiTheme.colors.text3, fontSize: 11, fontWeight: 900, letterSpacing: "0.14em", textTransform: "uppercase" }}>Monthly Data</div>
        <div style={{ fontWeight: 900 }}>{monthlyGb ? `${monthlyGb} GB` : "—"}</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 14 }}>{leftTiles}</div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 14 }}>
        <MetricTile icon={() => null} label="Download" value={formatBps(downBps)} color={etiTheme.colors.cyan} />
        <MetricTile icon={() => null} label="Upload" value={formatBps(upBps)} color={etiTheme.colors.blue} />
        <MetricTile icon={() => null} label="Latência" value={formatMs(latencyMs)} color={etiTheme.colors.warn} />
        <MetricTile icon={() => null} label="Alertas" value={`${openAlerts}`} color={openAlerts > 0 ? etiTheme.colors.critical : etiTheme.colors.success} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 14 }}>
        <Button variant="secondary" onClick={onSpeedTest}>
          Teste ISP
        </Button>
        <Button variant="secondary" onClick={onWifiDoctor}>
          WiFi Doctor
        </Button>
      </div>
    </Card>
  );
}

