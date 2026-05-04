import React from "react";
import { Crosshair, CircleDot, Copy, LocateFixed, RefreshCw, Router, SwitchCamera, Waypoints, Wifi } from "lucide-react";
import { etiTheme, timeAgoPtBR } from "../../eti/theme";
import { Button, Card, Pill } from "../../components/eti/EtiUI";
import { statusToColor } from "./topologyModel";

function NodeIcon({ type, color }) {
  const t = String(type || "").toLowerCase();
  const common = { size: 16, color };
  if (t === "gateway") return <Router {...common} />;
  if (t === "switch") return <Waypoints {...common} />;
  if (t === "ap") return <Wifi {...common} />;
  if (t === "camera") return <SwitchCamera {...common} />;
  return <CircleDot {...common} />;
}

export default function TopologyDrawer({ open, node, onClose, onToast, canAdmin }) {
  if (!open || !node) return null;
  const color = statusToColor(node.status);
  const pillColor = String(node.status || "").toLowerCase() === "offline" ? "critical" : String(node.status || "").toLowerCase() === "warning" ? "warn" : "success";
  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        width: 380,
        height: "100vh",
        background: `linear-gradient(180deg, ${etiTheme.colors.surface}, rgba(11, 18, 32, 0.98))`,
        borderLeft: `1px solid ${etiTheme.colors.borderSoft}`,
        zIndex: 3000,
        boxShadow: "-20px 0 60px rgba(0,0,0,0.5)",
        overflow: "auto",
      }}
    >
      <div style={{ padding: 16, borderBottom: `1px solid ${etiTheme.colors.borderSoft}`, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 30, height: 30, borderRadius: 12, background: "rgba(0,0,0,0.25)", border: `1px solid ${etiTheme.colors.borderSoft}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <NodeIcon type={node.type} color={color} />
            </div>
            <div style={{ fontWeight: 950, letterSpacing: "0.03em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{node.label}</div>
          </div>
          <div style={{ marginTop: 6 }}>
            <Pill label={String(node.status || "unknown").toUpperCase()} color={pillColor} />
          </div>
        </div>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Fechar
        </Button>
      </div>

      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <Card title="Visão geral">
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 10, fontSize: 12 }}>
            <div style={{ color: etiTheme.colors.text3, fontWeight: 900, letterSpacing: "0.12em", textTransform: "uppercase" }}>Tipo</div>
            <div style={{ fontWeight: 900 }}>{node.type}</div>
            <div style={{ color: etiTheme.colors.text3, fontWeight: 900, letterSpacing: "0.12em", textTransform: "uppercase" }}>IP</div>
            <div style={{ fontWeight: 900 }}>{node.ip || "—"}</div>
            <div style={{ color: etiTheme.colors.text3, fontWeight: 900, letterSpacing: "0.12em", textTransform: "uppercase" }}>MAC</div>
            <div style={{ fontWeight: 900 }}>{node.mac || "—"}</div>
            <div style={{ color: etiTheme.colors.text3, fontWeight: 900, letterSpacing: "0.12em", textTransform: "uppercase" }}>Último visto</div>
            <div style={{ fontWeight: 900 }}>{node.last_seen_at ? timeAgoPtBR(node.last_seen_at) : "—"}</div>
          </div>
        </Card>

        <Card title="Ações">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <Button
              variant="secondary"
              leftIcon={<Copy size={16} />}
              onClick={async () => {
                const text = node.ip || node.mac || node.label;
                try {
                  await navigator.clipboard.writeText(String(text || ""));
                  onToast?.("Copiado", String(text || ""), "info");
                } catch {
                  onToast?.("Copiar", "Falha ao copiar no clipboard", "danger");
                }
              }}
            >
              Copiar
            </Button>
            <Button variant="secondary" leftIcon={<LocateFixed size={16} />} onClick={() => onToast?.("Localizar", "Comando de LED/Beep enviado (demo)", "info")}>
              Localizar
            </Button>
            <Button variant={canAdmin ? "danger" : "ghost"} disabled={!canAdmin} leftIcon={<RefreshCw size={16} />} onClick={() => onToast?.("Reiniciar", "Reinício solicitado (demo)", "info")}>
              Reiniciar
            </Button>
            {String(node.type || "") === "camera" ? (
              <Button variant="primary" leftIcon={<SwitchCamera size={16} />} onClick={() => onToast?.("Câmera", "Abrir ao vivo (demo)", "info")}>
                Ao vivo
              </Button>
            ) : (
              <Button variant="ghost" leftIcon={<Crosshair size={16} />} onClick={() => onToast?.("Foco", "Centralizar na topologia", "info")}>
                Focar
              </Button>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
