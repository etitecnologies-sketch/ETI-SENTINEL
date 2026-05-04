import React from "react";
import { ChevronDown } from "lucide-react";
import { etiTheme } from "../../eti/theme";
import { Button, Card, Pill } from "../../components/eti/EtiUI";

export default function TopologyFilters({ mode, filters, setFilters, onlineCount }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Card
        title={mode === "topology" ? "Topology" : "Infrastructure"}
        right={
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              setFilters({
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
              })
            }
          >
            Clear Filters
          </Button>
        }
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
            <span style={{ fontWeight: 900, color: etiTheme.colors.text2 }}>Show Internet Traffic</span>
            <input type="checkbox" checked={filters.showInternetTraffic} onChange={(e) => setFilters((p) => ({ ...p, showInternetTraffic: e.target.checked }))} />
          </label>

          <div style={{ borderTop: `1px solid ${etiTheme.colors.borderSoft}`, paddingTop: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontWeight: 950 }}>Device Status</div>
              <ChevronDown size={16} color={etiTheme.colors.text2} />
            </div>
            <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked readOnly />
              <span style={{ fontWeight: 900 }}>Online ({onlineCount})</span>
            </div>
          </div>

          <div style={{ borderTop: `1px solid ${etiTheme.colors.borderSoft}`, paddingTop: 10 }}>
            <div style={{ fontWeight: 950 }}>Client Devices</div>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { k: "clientWired", label: "Wired" },
                { k: "client24", label: "2.4 GHz WiFi" },
                { k: "client5", label: "5 GHz WiFi" },
              ].map((x) => (
                <label key={x.k} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                  <span style={{ color: etiTheme.colors.text2, fontWeight: 900 }}>{x.label}</span>
                  <input type="checkbox" checked={filters[x.k]} onChange={(e) => setFilters((p) => ({ ...p, [x.k]: e.target.checked }))} />
                </label>
              ))}
            </div>
          </div>

          <div style={{ borderTop: `1px solid ${etiTheme.colors.borderSoft}`, paddingTop: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontWeight: 950 }}>VLANs</div>
              <ChevronDown size={16} color={etiTheme.colors.text2} />
            </div>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
              <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontWeight: 900, color: etiTheme.colors.text2 }}>Default</span>
                <input type="checkbox" checked={filters.vlanDefault} onChange={(e) => setFilters((p) => ({ ...p, vlanDefault: e.target.checked }))} />
              </label>
              <label style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontWeight: 900, color: etiTheme.colors.text2 }}>Rede Casa</span>
                <input type="checkbox" checked={filters.vlanCasa} onChange={(e) => setFilters((p) => ({ ...p, vlanCasa: e.target.checked }))} />
              </label>
            </div>
          </div>

          <div style={{ borderTop: `1px solid ${etiTheme.colors.borderSoft}`, paddingTop: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontWeight: 950 }}>WiFi Broadcasts</div>
              <ChevronDown size={16} color={etiTheme.colors.text2} />
            </div>
            <label style={{ marginTop: 10, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontWeight: 900, color: etiTheme.colors.text2 }}>JKS</span>
              <input type="checkbox" checked={filters.wifiJks} onChange={(e) => setFilters((p) => ({ ...p, wifiJks: e.target.checked }))} />
            </label>
          </div>

          <div style={{ borderTop: `1px solid ${etiTheme.colors.borderSoft}`, paddingTop: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontWeight: 950 }}>Vendors</div>
              <ChevronDown size={16} color={etiTheme.colors.text2} />
            </div>
            <label style={{ marginTop: 10, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontWeight: 900, color: etiTheme.colors.text2 }}>Apple, Inc</span>
              <input type="checkbox" checked={filters.vendorApple} onChange={(e) => setFilters((p) => ({ ...p, vendorApple: e.target.checked }))} />
            </label>
          </div>

          <div style={{ borderTop: `1px solid ${etiTheme.colors.borderSoft}`, paddingTop: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontWeight: 950 }}>Navigation Mode</div>
              <input type="checkbox" checked={filters.navMode} onChange={(e) => setFilters((p) => ({ ...p, navMode: e.target.checked }))} />
            </div>
          </div>
        </div>
      </Card>

      <Card title="Somente problema" right={<Pill label={filters.onlyProblems ? "ON" : "OFF"} color={filters.onlyProblems ? "warn" : "neutral"} />}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <div style={{ color: etiTheme.colors.text2, fontSize: 12 }}>Filtra nós offline/alerta</div>
          <Button size="sm" variant={filters.onlyProblems ? "primary" : "ghost"} onClick={() => setFilters((p) => ({ ...p, onlyProblems: !p.onlyProblems }))}>
            Alternar
          </Button>
        </div>
      </Card>
    </div>
  );
}

