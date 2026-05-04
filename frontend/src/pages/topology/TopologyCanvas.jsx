import React, { useCallback, useMemo, useRef } from "react";
import { Crosshair, CircleDot, Minus, Plus, Router, ShieldAlert, ShieldCheck, Sparkles, SwitchCamera, Waypoints, Wifi } from "lucide-react";
import { etiTheme } from "../../eti/theme";
import { Button, Card } from "../../components/eti/EtiUI";
import { layoutTree, statusToColor } from "./topologyModel";

function NodeIcon({ type, color }) {
  const t = String(type || "").toLowerCase();
  const common = { size: 16, color };
  if (t === "gateway") return <Router {...common} />;
  if (t === "switch") return <Waypoints {...common} />;
  if (t === "ap") return <Wifi {...common} />;
  if (t === "camera") return <SwitchCamera {...common} />;
  if (t === "wan") return <Sparkles {...common} />;
  return <CircleDot {...common} />;
}

export default function TopologyCanvas({ mode, nodes, links, selectedId, onSelect, navMode, pan, setPan, zoom, setZoom, onToast, onCenter, onAddVlan }) {
  const dragRef = useRef(null);
  const wrapRef = useRef(null);

  const pos = useMemo(() => {
    const w = wrapRef.current?.clientWidth || 900;
    return layoutTree(nodes, w);
  }, [nodes, wrapRef.current?.clientWidth]);

  const handleWheel = useCallback(
    (e) => {
      e.preventDefault();
      const delta = e.deltaY || 0;
      const next = Math.max(0.55, Math.min(1.8, zoom + (delta > 0 ? -0.08 : 0.08)));
      setZoom(next);
    },
    [setZoom, zoom]
  );

  const onMouseDown = useCallback(
    (e) => {
      if (!navMode) return;
      dragRef.current = { x: e.clientX, y: e.clientY, panX: pan.x, panY: pan.y };
    },
    [navMode, pan.x, pan.y]
  );

  const onMouseMove = useCallback(
    (e) => {
      const d = dragRef.current;
      if (!d) return;
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      setPan({ x: d.panX + dx, y: d.panY + dy });
    },
    [setPan]
  );

  const onMouseUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  return (
    <Card
      title={mode === "topology" ? "Mapa" : "Digital Twin"}
      right={
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Button size="sm" variant="ghost" leftIcon={<Minus size={16} />} onClick={() => setZoom((z) => Math.max(0.55, z - 0.1))}>
            
          </Button>
          <Button size="sm" variant="ghost" leftIcon={<Plus size={16} />} onClick={() => setZoom((z) => Math.min(1.8, z + 0.1))}>
            
          </Button>
          <Button size="sm" variant="ghost" leftIcon={<Crosshair size={16} />} onClick={onCenter}>
            
          </Button>
        </div>
      }
      style={{ minHeight: 680 }}
    >
      <div
        ref={wrapRef}
        style={{
          height: 600,
          background: "radial-gradient(1200px 520px at 50% 0%, rgba(47, 122, 248, 0.12), transparent 60%)",
          borderRadius: etiTheme.radius.xl,
          border: `1px solid ${etiTheme.colors.borderSoft}`,
          overflow: "hidden",
          position: "relative",
        }}
        onWheel={handleWheel}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      >
        <svg width="100%" height="100%" style={{ display: "block" }}>
          <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
            {links.map((l) => {
              const a = pos.get(l.from);
              const b = pos.get(l.to);
              if (!a || !b) return null;
              return (
                <path
                  key={`${l.from}-${l.to}`}
                  d={`M ${a.x} ${a.y + 22} C ${a.x} ${a.y + 70}, ${b.x} ${b.y - 70}, ${b.x} ${b.y - 22}`}
                  stroke="rgba(47, 122, 248, 0.30)"
                  strokeWidth={2}
                  fill="none"
                />
              );
            })}

            {nodes.map((n) => {
              const p0 = pos.get(n.id);
              if (!p0) return null;
              const active = selectedId === n.id;
              const color = statusToColor(n.status);
              return (
                <g key={n.id} transform={`translate(${p0.x},${p0.y})`}>
                  <rect
                    x={-90}
                    y={-22}
                    width={180}
                    height={44}
                    rx={14}
                    ry={14}
                    fill={active ? "rgba(47, 122, 248, 0.14)" : "rgba(0,0,0,0.22)"}
                    stroke={active ? etiTheme.colors.blue : "rgba(255,255,255,0.08)"}
                    strokeWidth={1}
                    onClick={() => onSelect(n.id)}
                    style={{ cursor: "pointer" }}
                  />
                  <circle cx={-68} cy={0} r={12} fill="rgba(0,0,0,0.28)" stroke="rgba(255,255,255,0.10)" />
                  <foreignObject x={-76} y={-8} width={16} height={16} pointerEvents="none">
                    <div style={{ width: 16, height: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <NodeIcon type={n.type} color={color} />
                    </div>
                  </foreignObject>
                  <circle cx={80} cy={0} r={5} fill={color} />
                  <text x={-48} y={-2} fill={etiTheme.colors.text} fontSize={12} fontWeight={900} style={{ userSelect: "none" }}>
                    {String(n.label).slice(0, 18)}
                  </text>
                  <text x={-48} y={14} fill={etiTheme.colors.text3} fontSize={10} fontWeight={800} style={{ userSelect: "none" }}>
                    {n.ip ? String(n.ip) : String(n.type).toUpperCase()}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>

        <div style={{ position: "absolute", left: 14, bottom: 14, display: "flex", flexDirection: "column", gap: 8 }}>
          <Button size="sm" variant="secondary" leftIcon={<ShieldCheck size={16} />} onClick={() => onToast?.("Infra", "Modo de saúde (demo)", "info")}>
            
          </Button>
          <Button size="sm" variant="secondary" leftIcon={<ShieldAlert size={16} />} onClick={() => onToast?.("Alertas", "Filtro de alertas (demo)", "info")}>
            
          </Button>
        </div>

        <div style={{ position: "absolute", right: 14, bottom: 14 }}>
          <Button size="sm" variant="secondary" leftIcon={<Plus size={16} />} onClick={onAddVlan}>
            Rede Casa
          </Button>
        </div>
      </div>
    </Card>
  );
}
