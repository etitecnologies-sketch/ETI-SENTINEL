import { etiTheme } from "../../eti/theme";

export function statusToColor(status) {
  const s = String(status || "").toLowerCase();
  if (s === "offline" || s === "critical") return etiTheme.colors.critical;
  if (s === "warning" || s === "alert") return etiTheme.colors.warn;
  if (s === "online" || s === "ok") return etiTheme.colors.success;
  return "rgba(159,176,199,0.55)";
}

export function buildDemoGraph(devices) {
  const ds = Array.isArray(devices) ? devices : [];
  const mkId = (p, i) => `${p}-${i}`;

  const nodes = [];
  const links = [];
  const addNode = (n) => {
    nodes.push(n);
    if (n.parentId) links.push({ from: n.parentId, to: n.id });
  };

  addNode({ id: "root", label: "ETI", type: "cloud", status: "online" });
  addNode({ id: "wan", label: "Internet", type: "wan", status: "online", parentId: "root" });
  addNode({ id: "gw", label: "Gateway", type: "gateway", status: "online", ip: "192.168.0.1", parentId: "wan" });

  const switches = ds.filter((d) => String(d.type || d.tipo || "").toLowerCase().includes("switch")).slice(0, 2);
  const aps = ds.filter((d) => String(d.type || d.tipo || "").toLowerCase().includes("ap") || String(d.type || "").toLowerCase().includes("access")).slice(0, 3);
  const cams = ds.filter((d) => String(d.type || d.tipo || "").toLowerCase().includes("camera") || String(d.type || d.tipo || "").toLowerCase().includes("cftv")).slice(0, 4);
  const clients = ds.filter((d) => String(d.type || d.tipo || "").toLowerCase().includes("client") || String(d.type || d.tipo || "").toLowerCase().includes("host")).slice(0, 6);

  const swList = switches.length > 0 ? switches : [{ name: "Switch 24", status: "online", ip: "192.168.0.2" }];
  const apList = aps.length > 0 ? aps : [{ name: "Access Point", status: "online", ip: "192.168.0.3" }];
  const camList = cams.length > 0 ? cams : [{ name: "Câmera Entrada", status: "online", ip: "192.168.0.50" }];
  const clList = clients.length > 0 ? clients : [{ name: "iPhone", status: "online", ip: "192.168.0.101" }, { name: "TV", status: "online", ip: "192.168.0.110" }];

  swList.forEach((d, i) => {
    addNode({
      id: d.id || mkId("sw", i),
      label: d.name || d.nome || d.label || "Switch",
      type: "switch",
      status: d.status || "online",
      ip: d.ip,
      mac: d.mac,
      last_seen_at: d.last_seen_at,
      parentId: "gw",
      raw: d,
    });
  });

  const parentForAp = swList[0]?.id || "gw";
  apList.forEach((d, i) => {
    addNode({
      id: d.id || mkId("ap", i),
      label: d.name || d.nome || d.label || "AP",
      type: "ap",
      status: d.status || "online",
      ip: d.ip,
      mac: d.mac,
      last_seen_at: d.last_seen_at,
      parentId: parentForAp,
      raw: d,
    });
  });

  const parentForClients = apList[0]?.id || parentForAp;
  clList.forEach((d, i) => {
    addNode({
      id: d.id || mkId("cl", i),
      label: d.name || d.nome || d.label || "Cliente",
      type: "client",
      status: d.status || "online",
      ip: d.ip,
      mac: d.mac,
      last_seen_at: d.last_seen_at,
      parentId: parentForClients,
      raw: d,
    });
  });

  const parentForCams = swList[1]?.id || swList[0]?.id || "gw";
  camList.forEach((d, i) => {
    addNode({
      id: d.id || mkId("cam", i),
      label: d.name || d.nome || d.label || "Câmera",
      type: "camera",
      status: d.status || "online",
      ip: d.ip,
      mac: d.mac,
      last_seen_at: d.last_seen_at,
      parentId: parentForCams,
      raw: d,
    });
  });

  return { nodes, links };
}

export function layoutTree(nodes, width) {
  const byParent = new Map();
  nodes.forEach((n) => {
    const p = n.parentId || "__root";
    if (!byParent.has(p)) byParent.set(p, []);
    byParent.get(p).push(n);
  });

  const levels = [];
  const root = nodes.find((n) => n.id === "root") || nodes[0];
  const q = [{ n: root, depth: 0 }];
  const seen = new Set();

  while (q.length) {
    const { n, depth } = q.shift();
    if (!n || seen.has(n.id)) continue;
    seen.add(n.id);
    while (levels.length <= depth) levels.push([]);
    levels[depth].push(n);
    const kids = byParent.get(n.id) || [];
    kids.forEach((k) => q.push({ n: k, depth: depth + 1 }));
  }

  const marginX = 50;
  const startY = 80;
  const gapY = 110;
  const pos = new Map();
  levels.forEach((lv, depth) => {
    const count = lv.length;
    const usable = Math.max(200, width - marginX * 2);
    const step = usable / Math.max(1, count);
    lv.forEach((n, i) => {
      const x = marginX + step * (i + 0.5);
      const y = startY + depth * gapY;
      pos.set(n.id, { x, y });
    });
  });
  return pos;
}

