import React, { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCw, Waypoints } from "lucide-react";
import { etiTheme } from "../eti/theme";
import { Button, Segmented } from "../components/eti/EtiUI";
import { buildDemoGraph } from "./topology/topologyModel";
import TopologyCanvas from "./topology/TopologyCanvas";
import TopologyDrawer from "./topology/TopologyDrawer";
import TopologyFilters from "./topology/TopologyFilters";

export default function TopologyUniFi({ api, onToast, canAdmin }) {
  const [mode, setMode] = useState("topology");
  const [devices, setDevices] = useState([]);
  const [filters, setFilters] = useState({
    showInternetTraffic: false,
    onlyProblems: false,
    clientWired: true,
    client24: true,
    client5: true,
    vlanDefault: true,
    vlanCasa: true,
    wifiJks: true,
    vendorApple: false,
    navMode: true,
  });
  const [selectedId, setSelectedId] = useState(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);

  const refresh = useCallback(() => {
    api?.("/devices")
      .then((d) => setDevices(Array.isArray(d) ? d : []))
      .catch(() => setDevices([]));
  }, [api]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const graph = useMemo(() => buildDemoGraph(devices), [devices]);
  const filteredNodes = useMemo(() => {
    const onlyProblems = filters.onlyProblems;
    return graph.nodes.filter((n) => {
      if (!onlyProblems) return true;
      const s = String(n.status || "").toLowerCase();
      return s === "offline" || s === "warning" || s === "alert" || s === "critical";
    });
  }, [filters.onlyProblems, graph.nodes]);

  const nodeById = useMemo(() => {
    const m = new Map();
    graph.nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [graph.nodes]);

  const selected = selectedId ? nodeById.get(selectedId) : null;

  const links = useMemo(() => {
    const visible = new Set(filteredNodes.map((n) => n.id));
    return graph.links.filter((l) => visible.has(l.from) && visible.has(l.to));
  }, [filteredNodes, graph.links]);

  const center = useCallback(() => {
    setPan({ x: 0, y: 0 });
    setZoom(1);
    onToast?.("Topologia", "Centralizado", "info");
  }, [onToast]);

  return (
    <div style={{ color: etiTheme.colors.text }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, flexWrap: "wrap", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 38, height: 38, borderRadius: 14, background: "rgba(47,122,248,0.12)", border: `1px solid ${etiTheme.colors.border}`, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Waypoints size={18} color={etiTheme.colors.blue} />
          </div>
          <div>
            <div style={{ fontSize: 20, fontWeight: 950, letterSpacing: "0.05em" }}>Topologia</div>
            <div style={{ fontSize: 12, color: etiTheme.colors.text3 }}>Mapa de devices e CFTV • inspirado no UniFi • ETI Sentinel</div>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <Segmented value={mode} options={[{ value: "topology", label: "Topology" }, { value: "infra", label: "Infrastructure" }]} onChange={setMode} />
          <Button variant="secondary" leftIcon={<RefreshCw size={16} />} onClick={refresh}>
            Atualizar
          </Button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 16, alignItems: "start" }}>
        <TopologyFilters mode={mode} filters={filters} setFilters={setFilters} onlineCount={filteredNodes.length} />
        <TopologyCanvas
          mode={mode}
          nodes={filteredNodes}
          links={links}
          selectedId={selectedId}
          onSelect={setSelectedId}
          navMode={filters.navMode}
          pan={pan}
          setPan={setPan}
          zoom={zoom}
          setZoom={setZoom}
          onToast={onToast}
          onCenter={center}
          onAddVlan={() => onToast?.("VLAN", "Adicionar VLAN (demo)", "info")}
        />
      </div>

      <TopologyDrawer open={!!selected} node={selected} onClose={() => setSelectedId(null)} onToast={onToast} canAdmin={!!canAdmin} />
    </div>
  );
}

