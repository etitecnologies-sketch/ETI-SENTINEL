const express = require("express");
const { Pool } = require("pg");
const bcrypt = require("bcryptjs");
const jwt = require("jsonwebtoken");
const cors = require("cors");
const crypto = require("crypto");
const rateLimit = require("express-rate-limit");
require("dotenv").config();
const net = require("net");
const dns = require("dns").promises;
const xmlparser = require("express-xml-bodyparser");
const path = require("path");
const fs = require("fs");

const app = express();
app.set("trust proxy", 1);

function sanitizeCorsValue(v) {
  const s = v ? String(v).trim() : "";
  return s.replace(/["'`\s]/g, "");
}

const corsOriginRawEarly = process.env.CORS_ORIGIN || "*";
const corsOriginEarly = corsOriginRawEarly
  .split(",")
  .map((s) => sanitizeCorsValue(s))
  .filter(Boolean);

const corsOptionsEarly = {
  origin: corsOriginEarly.length === 0 ? "*" : corsOriginEarly,
  credentials: corsOriginEarly.length > 0 && !(corsOriginEarly.length === 1 && corsOriginEarly[0] === "*"),
  methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization", "x-device-token", "x-collector-key", "x-event-source"],
  optionsSuccessStatus: 204,
};

app.use(cors(corsOptionsEarly));
app.options("*", cors(corsOptionsEarly));

const frontendDistDir = path.join(__dirname, "..", "frontend", "dist");
const frontendIndex = path.join(frontendDistDir, "index.html");
const hasFrontend = fs.existsSync(frontendIndex);

const escapeHtml = (text) => {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
};

function ensureDirSync(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function normalizeMac(input) {
  return String(input || "").replace(/[:-]/g, "").toUpperCase();
}

function detectImageExt(buf, contentType = "") {
  const ct = String(contentType || "").toLowerCase();
  if (ct.includes("image/jpeg") || ct.includes("image/jpg")) return { ext: "jpg", mime: "image/jpeg" };
  if (ct.includes("image/png")) return { ext: "png", mime: "image/png" };
  if (ct.includes("image/webp")) return { ext: "webp", mime: "image/webp" };
  if (Buffer.isBuffer(buf) && buf.length >= 12) {
    if (buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return { ext: "jpg", mime: "image/jpeg" };
    if (buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47) return { ext: "png", mime: "image/png" };
    if (buf[0] === 0x52 && buf[1] === 0x49 && buf[2] === 0x46 && buf[3] === 0x46 && buf[8] === 0x57 && buf[9] === 0x45 && buf[10] === 0x42 && buf[11] === 0x50) return { ext: "webp", mime: "image/webp" };
  }
  return { ext: "bin", mime: ct.split(";")[0] || "application/octet-stream" };
}

function parseMultipartFirstFile(bodyBuf, boundary) {
  const b = Buffer.from(`--${boundary}`);
  const headerSep = Buffer.from("\r\n\r\n");
  let i = bodyBuf.indexOf(b);
  while (i !== -1) {
    const partStart = i + b.length;
    if (bodyBuf.slice(partStart, partStart + 2).toString() === "--") break;
    let hStart = partStart;
    if (bodyBuf.slice(hStart, hStart + 2).toString() === "\r\n") hStart += 2;
    const hEnd = bodyBuf.indexOf(headerSep, hStart);
    if (hEnd === -1) break;
    const headersText = bodyBuf.slice(hStart, hEnd).toString("utf8");
    const dataStart = hEnd + headerSep.length;
    let next = bodyBuf.indexOf(b, dataStart);
    if (next === -1) break;
    let dataEnd = next - 2;
    if (dataEnd < dataStart) dataEnd = dataStart;
    const disp = headersText.split("\r\n").find((l) => l.toLowerCase().startsWith("content-disposition:")) || "";
    const ctype = headersText.split("\r\n").find((l) => l.toLowerCase().startsWith("content-type:")) || "";
    const mFilename = disp.match(/filename="([^"]*)"/i);
    const filename = mFilename ? mFilename[1] : "";
    const mPartName = disp.match(/name="([^"]*)"/i);
    const partName = mPartName ? mPartName[1] : "";
    const contentType = ctype.split(":").slice(1).join(":").trim();
    if (filename || partName.toLowerCase().includes("file") || contentType.toLowerCase().startsWith("image/")) {
      return {
        filename,
        contentType,
        data: bodyBuf.slice(dataStart, dataEnd),
      };
    }
    i = bodyBuf.indexOf(b, next);
  }
  return null;
}

function maskTokenLike(v) {
  const s = v ? String(v) : "";
  if (s.length <= 8) return "***";
  return s.slice(0, 2) + "***" + s.slice(-2);
}

function sanitizeUrlForLog(originalUrl) {
  try {
    const u = new URL(String(originalUrl || ""), "http://localhost");
    const sensitiveKeys = new Set(["token", "sn", "serial", "serial_number", "mac", "mac_address", "x-device-token"]);
    for (const [k] of u.searchParams) {
      const lk = String(k || "").toLowerCase();
      if (sensitiveKeys.has(lk) || lk.includes("token") || lk.includes("pass")) {
        u.searchParams.set(k, "***");
      }
    }
    const p = u.pathname || "";
    if (p.startsWith("/picture-upload/")) {
      return "/picture-upload/***" + (u.search ? u.search : "");
    }
    return (u.pathname || "") + (u.search || "");
  } catch {
    return String(originalUrl || "").replace(/([?&](token|sn|serial|mac)=[^&]+)/gi, "$1***");
  }
}

app.use((req, res, next) => {
  const safeUrl = sanitizeUrlForLog(req.url);
  console.log(`[${new Date().toISOString()}] ${req.method} ${safeUrl}`);
  if ((req.url === "/" || req.url === "") && req.method === "POST") {
    req.url = "/push";
  }
  next();
});

app.get("/", (req, res) => {
  if (hasFrontend) return res.sendFile(frontendIndex);
  return res.json({ status: "online", service: "ETI SENTINEL API", version: "1.0.5" });
});
app.get("/health", async (req, res) => {
  try {
    await pool.query("SELECT 1");
    res.json({ status: "ok", db: "connected" });
  } catch (e) {
    res.status(500).json({ status: "error", error: e.message });
  }
});
app.get("/ready", (req, res) => res.json({ status: "ready" }));
app.get("/push", (req, res) => res.json({ message: "Endpoint pronto para receber POST das câmeras." }));

app.post(
  "/picture-upload/:token?",
  rateLimit({
    windowMs: 60 * 1000,
    max: 60,
    standardHeaders: true,
    legacyHeaders: false,
    keyGenerator: (req) => {
      const t =
        req.params.token ||
        req.query.token ||
        req.headers["x-device-token"] ||
        req.query.sn ||
        req.query.serial ||
        req.query.mac ||
        req.ip;
      return String(t || req.ip || "");
    },
    handler: (req, res) => res.status(429).json({ error: "Too Many Requests" }),
  }),
  express.raw({ type: () => true, limit: "15mb" }),
  async (req, res) => {
    const ct = String(req.headers["content-type"] || "");
    const bodyBuf = Buffer.isBuffer(req.body) ? req.body : Buffer.from([]);
    let fileBuf = bodyBuf;
    let fileContentType = ct;
    let fileName = "";

    if (ct.toLowerCase().includes("multipart/form-data")) {
      const m = ct.match(/boundary=([^\s;]+)/i);
      const boundary = m ? m[1] : "";
      if (boundary) {
        const part = parseMultipartFirstFile(bodyBuf, boundary);
        if (part) {
          fileBuf = part.data;
          fileContentType = part.contentType || ct;
          fileName = part.filename || "";
        }
      }
    }

    if (!Buffer.isBuffer(fileBuf) || fileBuf.length === 0) {
      return res.status(400).json({ error: "No file received" });
    }

    const tokenCandidate =
      req.params.token ||
      req.query.token ||
      req.headers["x-device-token"] ||
      req.query.sn ||
      req.query.serial ||
      req.query.mac;

    let cleanMac = normalizeMac(req.query.mac || "");
    if (!cleanMac && tokenCandidate) {
      const s = String(tokenCandidate);
      if (s.includes(":") || s.includes("-") || s.length === 12) cleanMac = normalizeMac(s);
    }

    if (!tokenCandidate && !cleanMac) {
      return res.status(401).json({ error: "Identification (Token/SN/MAC) required" });
    }

    const dr = await pool.query(
      `
      SELECT id, client_id, name
      FROM devices
      WHERE token=$1
         OR serial_number=$1
         OR UPPER(REPLACE(REPLACE(mac_address, ':', ''), '-', '')) = $2
      LIMIT 1
      `,
      [tokenCandidate || "", cleanMac]
    );
    if (dr.rows.length === 0) return res.status(401).json({ error: "Invalid identification" });
    const dev = dr.rows[0];

    await pool.query("UPDATE devices SET last_seen=NOW(), status='online' WHERE id=$1", [dev.id]);

    const img = detectImageExt(fileBuf, fileContentType);
    const baseDir = path.join(__dirname, "uploads", "snapshots", String(dev.id));
    ensureDirSync(baseDir);

    const safeBase = path.join(__dirname, "uploads", "snapshots");
    const filename = `${Date.now()}-${crypto.randomBytes(6).toString("hex")}.${img.ext}`;
    const absPath = path.join(baseDir, filename);
    fs.writeFileSync(absPath, fileBuf);

    try {
      const maxFiles = 300;
      const files = fs.readdirSync(baseDir)
        .map((n) => ({
          name: n,
          p: path.join(baseDir, n),
        }))
        .filter((x) => x.p.startsWith(baseDir))
        .map((x) => {
          try {
            const st = fs.statSync(x.p);
            return { ...x, mtime: st.mtimeMs, isFile: st.isFile() };
          } catch {
            return { ...x, mtime: 0, isFile: false };
          }
        })
        .filter((x) => x.isFile)
        .sort((a, b) => a.mtime - b.mtime);
      if (files.length > maxFiles) {
        for (const f of files.slice(0, files.length - maxFiles)) {
          try { fs.unlinkSync(f.p); } catch {}
        }
      }
    } catch {}

    const snapshot = {
      path: absPath,
      mime: img.mime,
      size: fileBuf.length,
      name: fileName || "",
      query: req.query || {},
      received_at: new Date().toISOString(),
    };

    const er = await pool.query(
      `
      WITH latest AS (
        SELECT id
        FROM events
        WHERE device_id=$1
          AND time > NOW() - interval '2 minutes'
        ORDER BY time DESC
        LIMIT 1
      )
      UPDATE events e
      SET payload = jsonb_set(COALESCE(e.payload, '{}'::jsonb), '{snapshot}', $2::jsonb, true)
      WHERE e.id = (SELECT id FROM latest)
      RETURNING e.id
      `,
      [dev.id, JSON.stringify(snapshot)]
    );

    if (!absPath.startsWith(safeBase)) return res.status(500).json({ error: "Unsafe snapshot path" });

    res.json({ ok: true, device_id: dev.id, attached_event_id: er.rows[0]?.id || null });
  }
);

// ── Security & Middleware ────────────────────────────────────
app.use(express.json({ limit: "100kb" }));
app.use(express.urlencoded({ extended: true, limit: "100kb" }));
app.use(xmlparser({ explicitArray: false, normalize: true })); // Suporte para XML (Intelbras/Hikvision)

if (hasFrontend) {
  app.use(express.static(frontendDistDir, { index: false }));
}

const loginLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 10,
  message: "Muitas tentativas de login. Tente novamente em 15 minutos."
});

const metricsLimiter = rateLimit({
  windowMs: 1 * 60 * 1000,
  max: 1000,
  skip: (req) => req.headers["x-device-token"],
});

const pool = new Pool({ 
  connectionString: process.env.DATABASE_URL,
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});

// ── Database Initialization ──────────────────────────────────
async function initDB() {
  try {
    await pool.query(`
      CREATE TABLE IF NOT EXISTS clients (
          id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, document TEXT DEFAULT '',
          email TEXT DEFAULT '', phone TEXT DEFAULT '', address TEXT DEFAULT '',
          city TEXT DEFAULT '', state TEXT DEFAULT '', plan TEXT DEFAULT 'basic',
          status TEXT DEFAULT 'active', telegram_token TEXT DEFAULT '',
          telegram_chat_id TEXT DEFAULT '', alert_email TEXT DEFAULT '',
          wa_instance TEXT DEFAULT '', wa_token TEXT DEFAULT '', wa_number TEXT DEFAULT '',
          notes TEXT DEFAULT '',
          collector_key_hash TEXT DEFAULT '',
          collector_key_rotated_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS users (
          id SERIAL PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'client',
          access_level SMALLINT NOT NULL DEFAULT 1,
          permissions JSONB DEFAULT '{}'::jsonb,
          client_id INT REFERENCES clients(id) ON DELETE CASCADE,
          created_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS hosts (
          id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS devices (
          id SERIAL PRIMARY KEY, name TEXT NOT NULL, hostname TEXT UNIQUE,
          token TEXT NOT NULL UNIQUE, client_id INT REFERENCES clients(id) ON DELETE CASCADE,
          ip_address TEXT DEFAULT '', device_type TEXT DEFAULT 'server', tags TEXT[] DEFAULT '{}',
          description TEXT DEFAULT '', location TEXT DEFAULT '', status TEXT DEFAULT 'pending',
          last_seen TIMESTAMPTZ, created_at TIMESTAMPTZ DEFAULT NOW(),
          snmp_community TEXT DEFAULT 'public', snmp_version TEXT DEFAULT '2c',
          ssh_user TEXT, ssh_port INT DEFAULT 22, monitor_ping BOOLEAN DEFAULT TRUE,
          monitor_snmp BOOLEAN DEFAULT FALSE, monitor_agent BOOLEAN DEFAULT TRUE,
          ddns_address TEXT DEFAULT '', monitor_port INT DEFAULT 0, notes TEXT DEFAULT '',
          mac_address TEXT DEFAULT '', serial_number TEXT DEFAULT ''
      );
      CREATE TABLE IF NOT EXISTS metrics (
          id BIGSERIAL PRIMARY KEY, time TIMESTAMPTZ NOT NULL, host_id INT REFERENCES hosts(id) ON DELETE CASCADE,
          host TEXT NOT NULL, device_id INT REFERENCES devices(id) ON DELETE SET NULL,
          cpu FLOAT DEFAULT 0, memory FLOAT DEFAULT 0, disk_percent FLOAT DEFAULT 0,
          latency_ms FLOAT DEFAULT 0, status TEXT DEFAULT 'online',
          solar_voltage FLOAT DEFAULT 0, battery_voltage FLOAT DEFAULT 0,
          battery_percent FLOAT DEFAULT 0, charge_current FLOAT DEFAULT 0,
          load_current FLOAT DEFAULT 0, uptime_seconds BIGINT DEFAULT 0,
          load_avg FLOAT DEFAULT 0, processes INT DEFAULT 0, temperature FLOAT DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS triggers (
          id SERIAL PRIMARY KEY, name TEXT NOT NULL, expression TEXT NOT NULL,
          threshold FLOAT NOT NULL, enabled BOOLEAN DEFAULT TRUE,
          client_id INT REFERENCES clients(id) ON DELETE CASCADE,
          created_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS automation_rules (
          id SERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          enabled BOOLEAN DEFAULT TRUE,
          client_id INT REFERENCES clients(id) ON DELETE CASCADE,
          rule JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS alerts (
          id BIGSERIAL PRIMARY KEY, trigger_id INT REFERENCES triggers(id) ON DELETE CASCADE,
          device_id INT REFERENCES devices(id) ON DELETE SET NULL,
          host TEXT NOT NULL, expression TEXT NOT NULL, value FLOAT NOT NULL,
          threshold FLOAT NOT NULL, alert_type TEXT NOT NULL DEFAULT 'threshold',
          fired_at TIMESTAMPTZ DEFAULT NOW(), resolved_at TIMESTAMPTZ,
          client_id INT REFERENCES clients(id) ON DELETE CASCADE
      );
      CREATE TABLE IF NOT EXISTS events (
          id BIGSERIAL PRIMARY KEY, time TIMESTAMPTZ DEFAULT NOW(),
          device_id INT REFERENCES devices(id) ON DELETE CASCADE,
          event_type TEXT NOT NULL, channel INT DEFAULT 0,
          description TEXT, severity TEXT DEFAULT 'info',
          source TEXT DEFAULT 'push',
          raw_event_type TEXT DEFAULT '',
          payload JSONB DEFAULT '{}'::jsonb,
          is_read BOOLEAN DEFAULT FALSE
      );
      CREATE TABLE IF NOT EXISTS onvif_configs (
          device_id INT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
          enabled BOOLEAN DEFAULT FALSE,
          host TEXT NOT NULL DEFAULT '',
          port INT DEFAULT 80,
          username TEXT DEFAULT '',
          password_enc TEXT DEFAULT '',
          channel_map JSONB DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS rtsp_configs (
          device_id INT PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
          enabled BOOLEAN DEFAULT FALSE,
          username TEXT DEFAULT '',
          password_enc TEXT DEFAULT '',
          streams JSONB DEFAULT '[]'::jsonb,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS discovered_devices (
          id BIGSERIAL PRIMARY KEY,
          agent_id TEXT NOT NULL DEFAULT '',
          client_id INT REFERENCES clients(id) ON DELETE SET NULL,
          ip_address TEXT NOT NULL DEFAULT '',
          mac_address TEXT DEFAULT '',
          hostname TEXT DEFAULT '',
          vendor TEXT DEFAULT '',
          guess_type TEXT DEFAULT '',
          open_ports INT[] DEFAULT '{}',
          onvif_xaddrs TEXT DEFAULT '',
          device_id INT REFERENCES devices(id) ON DELETE SET NULL,
          raw JSONB DEFAULT '{}'::jsonb,
          first_seen TIMESTAMPTZ DEFAULT NOW(),
          last_seen TIMESTAMPTZ DEFAULT NOW()
      );
    `);

    await pool.query(`
      CREATE UNIQUE INDEX IF NOT EXISTS idx_discovered_devices_agent_ip ON discovered_devices (agent_id, ip_address);
      CREATE INDEX IF NOT EXISTS idx_discovered_devices_client ON discovered_devices (client_id);
      CREATE INDEX IF NOT EXISTS idx_discovered_devices_last_seen ON discovered_devices (last_seen DESC);
      CREATE INDEX IF NOT EXISTS idx_automation_rules_client ON automation_rules (client_id);
      CREATE INDEX IF NOT EXISTS idx_automation_rules_enabled ON automation_rules (enabled);
    `);
    
    // Default triggers if none exist
    const triggerCount = await pool.query("SELECT COUNT(*) FROM triggers");
    if (parseInt(triggerCount.rows[0].count) === 0) {
      await pool.query(`
        INSERT INTO triggers (name, expression, threshold) VALUES
        ('High CPU', 'cpu', 80),
        ('High Memory', 'memory', 85),
        ('High Disk', 'disk_percent', 90),
        ('High Latency', 'latency_ms', 500),
        ('High Load', 'load_avg', 5)
      `);
    }

    const migrations = [
      "ALTER TABLE users ADD COLUMN IF NOT EXISTS access_level SMALLINT NOT NULL DEFAULT 1",
      "ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB DEFAULT '{}'::jsonb",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS ddns_address TEXT DEFAULT ''",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS monitor_port INT DEFAULT 0",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT ''",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}'",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS monitor_agent BOOLEAN DEFAULT TRUE",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS monitor_ping BOOLEAN DEFAULT TRUE",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS monitor_snmp BOOLEAN DEFAULT FALSE",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT FALSE",
      "ALTER TABLE metrics ADD COLUMN IF NOT EXISTS disk_percent FLOAT DEFAULT 0",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS mac_address TEXT DEFAULT ''",
      "ALTER TABLE devices ADD COLUMN IF NOT EXISTS serial_number TEXT DEFAULT ''",
      "ALTER TABLE metrics ADD COLUMN IF NOT EXISTS uptime_seconds BIGINT DEFAULT 0",
      "ALTER TABLE metrics ADD COLUMN IF NOT EXISTS load_avg FLOAT DEFAULT 0",
      "ALTER TABLE metrics ADD COLUMN IF NOT EXISTS processes INT DEFAULT 0",
      "ALTER TABLE metrics ADD COLUMN IF NOT EXISTS temperature FLOAT DEFAULT 0",
      "ALTER TABLE triggers ADD COLUMN IF NOT EXISTS client_id INT REFERENCES clients(id) ON DELETE CASCADE",
      "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS client_id INT REFERENCES clients(id) ON DELETE CASCADE",
      "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_type TEXT NOT NULL DEFAULT 'threshold'",
      "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS fired_at TIMESTAMPTZ DEFAULT NOW()",
      "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS document TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS email TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS phone TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS address TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS city TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS state TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'basic'",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS telegram_token TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS alert_email TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS wa_instance TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS wa_token TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS wa_number TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS collector_key_hash TEXT DEFAULT ''",
      "ALTER TABLE clients ADD COLUMN IF NOT EXISTS collector_key_rotated_at TIMESTAMPTZ",
      "ALTER TABLE solar_inverters ADD COLUMN IF NOT EXISTS saj_user TEXT DEFAULT ''",
      "ALTER TABLE solar_inverters ADD COLUMN IF NOT EXISTS saj_pass TEXT DEFAULT ''",
      "ALTER TABLE solar_inverters ADD COLUMN IF NOT EXISTS saj_plant_id TEXT DEFAULT ''",
      "ALTER TABLE events ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'push'",
      "ALTER TABLE events ADD COLUMN IF NOT EXISTS raw_event_type TEXT DEFAULT ''",
      "ALTER TABLE events ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'::jsonb"
    ];
    for (let m of migrations) { await pool.query(m).catch(() => {}); }

    await pool.query("UPDATE users SET access_level=3 WHERE role='superadmin' AND (access_level IS NULL OR access_level < 3)").catch(() => {});
    
    // Inicia tabelas solares se não existirem
    await pool.query(`
      CREATE TABLE IF NOT EXISTS solar_inverters (
          id              SERIAL PRIMARY KEY,
          client_id       INTEGER REFERENCES clients(id) ON DELETE CASCADE,
          name            TEXT NOT NULL,
          brand           TEXT NOT NULL,
          model           TEXT DEFAULT '',
          location        TEXT DEFAULT '',
          capacity_kwp    FLOAT DEFAULT 0,
          tariff_kwh      FLOAT DEFAULT 0.85,
          status          TEXT DEFAULT 'active',
          growatt_user    TEXT DEFAULT '',
          growatt_pass    TEXT DEFAULT '',
          growatt_plant_id TEXT DEFAULT '',
          fronius_ip      TEXT DEFAULT '',
          fronius_device_id INTEGER DEFAULT 1,
          solarman_token  TEXT DEFAULT '',
          solarman_app_id TEXT DEFAULT '',
          solarman_logger_sn TEXT DEFAULT '',
          sma_user        TEXT DEFAULT '',
          sma_pass        TEXT DEFAULT '',
          sma_plant_id    TEXT DEFAULT '',
          goodwe_user     TEXT DEFAULT '',
          goodwe_pass     TEXT DEFAULT '',
          goodwe_station_id TEXT DEFAULT '',
          huawei_user     TEXT DEFAULT '',
          huawei_pass     TEXT DEFAULT '',
          huawei_station_id TEXT DEFAULT '',
          saj_user        TEXT DEFAULT '',
          saj_pass        TEXT DEFAULT '',
          saj_plant_id    TEXT DEFAULT '',
          api_url         TEXT DEFAULT '',
          api_key         TEXT DEFAULT '',
          api_type        TEXT DEFAULT '',
          notes           TEXT DEFAULT '',
          created_at      TIMESTAMPTZ DEFAULT NOW()
      );
      CREATE TABLE IF NOT EXISTS solar_metrics (
          time            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          inverter_id     INTEGER REFERENCES solar_inverters(id) ON DELETE CASCADE,
          client_id       INTEGER REFERENCES clients(id),
          power_w         FLOAT DEFAULT 0,
          energy_today_kwh FLOAT DEFAULT 0,
          energy_month_kwh FLOAT DEFAULT 0,
          energy_total_kwh FLOAT DEFAULT 0,
          voltage_pv      FLOAT DEFAULT 0,
          voltage_ac      FLOAT DEFAULT 0,
          current_ac      FLOAT DEFAULT 0,
          frequency_hz    FLOAT DEFAULT 50,
          temperature_c   FLOAT DEFAULT 0,
          revenue_today   FLOAT DEFAULT 0,
          revenue_month   FLOAT DEFAULT 0,
          revenue_total   FLOAT DEFAULT 0,
          inverter_status TEXT DEFAULT 'unknown',
          fault_code      TEXT DEFAULT '',
          last_update     TIMESTAMPTZ DEFAULT NOW()
      );
    `).catch(e => console.log("Solar Tables Error:", e.message));

    console.log("Database Professional Restore: OK");
  } catch (e) { console.error("DB Restore Error:", e.message); }
}
initDB();

const isDev = (process.env.NODE_ENV || "").toLowerCase() === "development";
const JWT_SECRET = process.env.JWT_SECRET || (isDev ? "dev-insecure-jwt" : "");
if (!JWT_SECRET || JWT_SECRET === "changeme-secret-jwt" || JWT_SECRET === "dev-insecure-jwt") {
  if (!isDev) {
    throw new Error("JWT_SECRET obrigatório em produção.");
  }
}
function sanitize(v) {
  return v ? String(v).replace(/["'`\s]/g, "").trim() : "";
}

function _collectorRawKey() {
  const raw = crypto.randomBytes(32).toString("base64");
  return raw.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function _collectorHash(rawKey) {
  return crypto.createHash("sha256").update(String(rawKey || "")).digest("hex");
}

function _collectorMatches(rawKey, storedHashHex) {
  try {
    const a = Buffer.from(_collectorHash(rawKey), "hex");
    const b = Buffer.from(String(storedHashHex || ""), "hex");
    if (!a.length || a.length !== b.length) return false;
    return crypto.timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

async function authorizeCollector(req) {
  const key = sanitize(req.headers["x-collector-key"] || "");
  const cid =
    (req.query?.client_id ? parseInt(req.query.client_id) : null) ||
    (req.body?.client_id ? parseInt(req.body.client_id) : null);

  if (!cid || !Number.isFinite(cid) || cid <= 0) {
    return { ok: false, status: 400, error: "client_id required" };
  }

  if (COLLECTOR_KEY && key && key === COLLECTOR_KEY) {
    return { ok: true, client_id: cid, mode: "legacy" };
  }

  const r = await pool.query("SELECT collector_key_hash FROM clients WHERE id=$1 LIMIT 1", [cid]);
  if (r.rows.length === 0) return { ok: false, status: 404, error: "client not found" };
  const hash = String(r.rows[0].collector_key_hash || "");
  if (!hash) return { ok: false, status: 403, error: "collector_key not provisioned" };
  if (!key || !_collectorMatches(key, hash)) return { ok: false, status: 401, error: "Unauthorized" };
  return { ok: true, client_id: cid, mode: "client" };
}
const WEBSOCKET_URL = sanitize(process.env.WEBSOCKET_URL || "");
const TG_TOKEN_GLOBAL = sanitize(process.env.TELEGRAM_TOKEN || "");
const TG_CHAT_ID_GLOBAL = sanitize(process.env.TELEGRAM_CHAT_ID || "");
const WA_API_URL_GLOBAL = sanitize(process.env.WA_API_URL || "");
const WA_INSTANCE_GLOBAL = sanitize(process.env.WA_INSTANCE || "");
const WA_TOKEN_GLOBAL = sanitize(process.env.WA_TOKEN || "");
const WA_NUMBER_GLOBAL = sanitize(process.env.WA_NUMBER || "");
const TWILIO_ACCOUNT_SID_GLOBAL = sanitize(process.env.TWILIO_ACCOUNT_SID || "") || WA_INSTANCE_GLOBAL;
const TWILIO_AUTH_TOKEN_GLOBAL = sanitize(process.env.TWILIO_AUTH_TOKEN || "") || WA_TOKEN_GLOBAL;
const TWILIO_WHATSAPP_NUMBER_GLOBAL = sanitize(process.env.TWILIO_WHATSAPP_NUMBER || "");
const TWILIO_CONTENT_SID_GLOBAL = sanitize(process.env.TWILIO_CONTENT_SID || "");
const INSTANT_ANALYTICS_ALERTS = sanitize(process.env.INSTANT_ANALYTICS_ALERTS || "0") === "1";
const INSTANT_ANALYTICS_LOG = sanitize(process.env.INSTANT_ANALYTICS_LOG || "0") === "1";
const COLLECTOR_KEY = sanitize(process.env.COLLECTOR_KEY || "");
const AUTO_ADOPT_DISCOVERY = sanitize(process.env.AUTO_ADOPT_DISCOVERY || "0") === "1";
const DEFAULT_DISCOVERY_CLIENT_ID = (() => {
  const v = sanitize(process.env.DEFAULT_DISCOVERY_CLIENT_ID || "");
  const n = parseInt(v);
  return Number.isFinite(n) && n > 0 ? n : null;
})();
const ONVIF_CRED_SECRET = process.env.ONVIF_CRED_SECRET || JWT_SECRET;
const ONVIF_CRED_KEY = crypto.createHash("sha256").update(String(ONVIF_CRED_SECRET)).digest();

function encOnvif(text) {
  if (!text) return "";
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", ONVIF_CRED_KEY, iv);
  const ciphertext = Buffer.concat([cipher.update(String(text), "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `${iv.toString("base64")}.${tag.toString("base64")}.${ciphertext.toString("base64")}`;
}

function decOnvif(payload) {
  if (!payload) return "";
  const parts = String(payload).split(".");
  if (parts.length !== 3) return "";
  try {
    const iv = Buffer.from(parts[0], "base64");
    const tag = Buffer.from(parts[1], "base64");
    const ciphertext = Buffer.from(parts[2], "base64");
    const decipher = crypto.createDecipheriv("aes-256-gcm", ONVIF_CRED_KEY, iv);
    decipher.setAuthTag(tag);
    const plain = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
    return plain.toString("utf8");
  } catch {
    return "";
  }
}

function _uniqueTargets(targets) {
  const seen = new Set();
  const out = [];
  for (const t of targets) {
    const key = `${t?.token || ""}|${t?.chat_id || ""}|${t?.number || ""}|${t?.account_sid || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(t);
  }
  return out;
}

const _instantDedup = new Map();
function _instantShouldSend(key, ttlMs) {
  const now = Date.now();
  const prev = _instantDedup.get(key);
  if (prev && now - prev < ttlMs) return false;
  _instantDedup.set(key, now);
  return true;
}

async function _sendTelegramInstant(message, token, chatId) {
  const tok = sanitize(token || "");
  const cid = sanitize(chatId || "");
  if (!tok || !cid) return;
  const cleanTok = tok.toLowerCase().startsWith("bot") ? tok.slice(3) : tok;
  const url = `https://api.telegram.org/bot${cleanTok}/sendMessage`;
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: cid, text: String(message || "") }),
    });
    if (INSTANT_ANALYTICS_LOG && !r.ok) {
      const shortCid = cid.length > 6 ? `${cid.slice(0, 2)}***${cid.slice(-2)}` : cid;
      console.log(`[Instant Alerts] Telegram failed status=${r.status} chat=${shortCid}`);
    }
  } catch (e) {
    if (INSTANT_ANALYTICS_LOG) console.log(`[Instant Alerts] Telegram exception: ${String(e?.message || e)}`);
  }
}

async function _sendWhatsAppTwilioInstant(message, accountSid, authToken, toNumber) {
  const sid = sanitize(accountSid || "");
  const tok = sanitize(authToken || "");
  const numRaw = sanitize(toNumber || "");
  if (!sid || !tok || !numRaw) return;
  const to = numRaw.startsWith("+") ? numRaw : `+${numRaw}`;
  const toFinal = to.startsWith("whatsapp:") ? to : `whatsapp:${to}`;

  const fromFinal = TWILIO_WHATSAPP_NUMBER_GLOBAL || "whatsapp:+14155238886";
  const url = `https://api.twilio.com/2010-04-01/Accounts/${sid}/Messages.json`;
  const auth = Buffer.from(`${sid}:${tok}`).toString("base64");
  const params = new URLSearchParams();
  params.set("To", toFinal);
  params.set("From", fromFinal);
  if (TWILIO_CONTENT_SID_GLOBAL) {
    params.set("ContentSid", TWILIO_CONTENT_SID_GLOBAL);
    params.set("ContentVariables", JSON.stringify({ 1: String(message || "").slice(0, 1500) }));
  } else {
    params.set("Body", String(message || ""));
  }
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Basic ${auth}`, "Content-Type": "application/x-www-form-urlencoded" },
      body: params,
    });
    if (INSTANT_ANALYTICS_LOG && !(r.status === 200 || r.status === 201)) {
      const maskedTo = toFinal.replace(/(\d)(?=\d{2})/g, "*");
      console.log(`[Instant Alerts] WhatsApp(Twilio) failed status=${r.status} to=${maskedTo}`);
    }
  } catch (e) {
    if (INSTANT_ANALYTICS_LOG) console.log(`[Instant Alerts] WhatsApp(Twilio) exception: ${String(e?.message || e)}`);
  }
}

async function _sendInstantAnalyticsAlerts(devRow, eventType, channel, description) {
  if (!INSTANT_ANALYTICS_ALERTS) return;
  if (!devRow || !eventType) return;
  const devName = String(devRow.name || "device");
  const ch = Number(channel || 0) || 0;
  const et = String(eventType || "");
  const desc = String(description || "");

  const dedupKey = `analytics|${devRow.id || devRow.device_id || ""}|${et}|${ch}|${desc}`;
  if (!_instantShouldSend(dedupKey, 2500)) return;

  const msgLines = [
    "🎬 ALERTA ANALÍTICO",
    `📷 ${devName}`,
    `Evento: ${et}`,
    `Canal: ${ch || "-"}`,
    desc ? `Detalhes: ${desc}` : "",
    `🕐 ${new Date().toISOString()}`,
  ].filter(Boolean);
  const msg = msgLines.join("\n");

  const tgTargets = _uniqueTargets([
    { token: devRow.telegram_token, chat_id: devRow.telegram_chat_id },
    { token: TG_TOKEN_GLOBAL, chat_id: TG_CHAT_ID_GLOBAL },
  ]);

  const waTargets = _uniqueTargets([
    { account_sid: devRow.wa_instance, auth_token: devRow.wa_token, number: devRow.wa_number },
    { account_sid: TWILIO_ACCOUNT_SID_GLOBAL, auth_token: TWILIO_AUTH_TOKEN_GLOBAL, number: WA_NUMBER_GLOBAL },
  ]);

  if (INSTANT_ANALYTICS_LOG) {
    console.log(
      `[Instant Alerts] analytics dev=${String(devRow.id || "")} tg_targets=${tgTargets.length} wa_targets=${waTargets.length} type=${et}`
    );
  }

  await Promise.all([
    ...tgTargets.map((t) => _sendTelegramInstant(msg, t.token, t.chat_id)),
    ...waTargets.map((t) => _sendWhatsAppTwilioInstant(msg, t.account_sid, t.auth_token, t.number)),
  ]);
}

async function assertDeviceAccess(req, deviceId) {
  const r = await pool.query("SELECT id, client_id FROM devices WHERE id=$1", [deviceId]);
  if (r.rows.length === 0) return { ok: false, status: 404, error: "Device not found" };
  const dev = r.rows[0];
  if (req.user.role !== "superadmin" && dev.client_id !== req.user.client_id) {
    return { ok: false, status: 403, error: "Forbidden" };
  }
  return { ok: true, device: dev };
}

// ── Middlewares ──────────────────────────────────────────────
function auth(req, res, next) {
  const token = req.headers.authorization?.split(" ")[1];
  if (!token) return res.status(401).json({ error: "Token required" });
  try { req.user = jwt.verify(token, JWT_SECRET); next(); }
  catch (e) { res.status(401).json({ error: "Invalid token" }); }
}

function superadmin(req, res, next) {
  if (req.user.role !== "superadmin") return res.status(403).json({ error: "Superadmin only" });
  next();
}

function requireAccessLevel(minLevel) {
  return (req, res, next) => {
    const lvl = Number(req.user?.access_level ?? 1);
    if (Number.isNaN(lvl) || lvl < minLevel) {
      return res.status(403).json({ error: `Access level ${minLevel}+ required` });
    }
    next();
  };
}

function clientFilter(req) {
  return req.user.role === "superadmin" ? (req.query.client_id ? parseInt(req.query.client_id) : null) : req.user.client_id;
}

// ── Auth ─────────────────────────────────────────────────────
app.get("/auth/status", async (req, res) => {
  try {
    const r = await pool.query("SELECT id FROM users LIMIT 1");
    res.json({ setupDone: r.rows.length > 0 });
  } catch (e) {
    res.status(503).json({ setupDone: false, error: "Database unavailable" });
  }
});

app.post("/auth/setup", async (req, res) => {
  try {
    const { username, password } = req.body;
    const exists = await pool.query("SELECT id FROM users LIMIT 1");
    if (exists.rows.length > 0) return res.status(409).json({ error: "Setup already done" });
    const hash = await bcrypt.hash(password, 10);
    await pool.query("INSERT INTO users (username, password_hash, role, access_level) VALUES ($1,$2,'superadmin',3)", [username, hash]);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: "Setup failed" });
  }
});

app.post("/auth/login", loginLimiter, async (req, res) => {
  try {
    const { username, password } = req.body;
    const r = await pool.query("SELECT * FROM users WHERE username=$1", [username]);
    const user = r.rows[0];
    if (!user || !(await bcrypt.compare(password, user.password_hash))) {
      return res.status(401).json({ error: "Invalid credentials" });
    }
    const access_level = Number(user.access_level || (user.role === "superadmin" ? 3 : 1));
    const permissions = user.permissions || {};
    const token = jwt.sign(
      { id: user.id, username, role: user.role, client_id: user.client_id, access_level, permissions },
      JWT_SECRET,
      { expiresIn: "7d" }
    );
    res.json({ token, role: user.role, client_id: user.client_id, access_level, permissions });
  } catch (e) {
    res.status(500).json({ error: "Login failed" });
  }
});

app.get("/auth/me", auth, (req, res) => res.json(req.user));

// ── Devices ──────────────────────────────────────────────────
app.get("/devices", auth, async (req, res) => {
  try {
    const cid = clientFilter(req);
    const loc = sanitize(req.query.location || "");
    
    let where = "1=1";
    const params = [];
    
    if (cid) {
      params.push(cid);
      where += ` AND d.client_id=$${params.length}`;
    }
    
    if (loc) {
      params.push(loc);
      where += ` AND d.location=$${params.length}`;
    }

    let query = `
      SELECT d.*, c.name as client_name,
        (SELECT latency_ms FROM metrics WHERE device_id=d.id ORDER BY time DESC LIMIT 1) as last_latency,
        (SELECT cpu FROM metrics WHERE device_id=d.id ORDER BY time DESC LIMIT 1) as last_cpu,
        (SELECT memory FROM metrics WHERE device_id=d.id ORDER BY time DESC LIMIT 1) as last_memory,
        d.status as last_status
      FROM devices d
      LEFT JOIN clients c ON c.id = d.client_id
      WHERE ${where}
    `;
    query += " ORDER BY d.created_at DESC";
    const r = await pool.query(query, params);
    res.json(r.rows);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.post("/devices", auth, async (req, res) => {
  const { 
    name, description, location, device_type, ip_address, tags, 
    ddns_address, monitor_port, monitor_ping, monitor_agent, notes, client_id,
    snmp_community, snmp_version, ssh_user, ssh_port,
    mac_address, serial_number,
    ai_enabled
  } = req.body;
  if (!name) return res.status(400).json({ error: "Name required" });
  const cid = req.user.role === "superadmin" ? (client_id || null) : req.user.client_id;
  const token = crypto.randomBytes(32).toString("hex");
  try {
    const r = await pool.query(`
      INSERT INTO devices (
        name, description, location, token, device_type, ip_address, tags, 
        ddns_address, monitor_port, monitor_ping, monitor_agent, ai_enabled, notes, client_id,
        snmp_community, snmp_version, ssh_user, ssh_port,
        mac_address, serial_number
      )
      VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20) RETURNING *
    `, [
      name, description||"", location||"", token, device_type||"other", ip_address||"", tags||[], 
      ddns_address||"", parseInt(monitor_port)||0, monitor_ping!==false, monitor_agent!==false, ai_enabled===true, notes||"", cid,
      snmp_community||"public", snmp_version||"2c", ssh_user||"", parseInt(ssh_port)||22,
      mac_address||"", serial_number||""
    ]);
    res.status(201).json(r.rows[0]);
    if (ddns_address && monitor_port) setImmediate(() => cloudMonitor(r.rows[0].id));
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.put("/devices/:id", auth, async (req, res) => {
  const { 
    name, description, location, device_type, ip_address, tags, 
    ddns_address, monitor_port, monitor_ping, monitor_agent, notes,
    snmp_community, snmp_version, ssh_user, ssh_port,
    mac_address, serial_number, client_id,
    ai_enabled
  } = req.body;
  const cid = req.user.role === "superadmin" ? (client_id || null) : req.user.client_id;
  try {
    const r = await pool.query(`
      UPDATE devices SET 
        name=$1, description=$2, location=$3, device_type=$4, ip_address=$5, tags=$6, 
        ddns_address=$7, monitor_port=$8, monitor_ping=$9, monitor_agent=$10, ai_enabled=$11, notes=$12,
        snmp_community=$13, snmp_version=$14, ssh_user=$15, ssh_port=$16,
        mac_address=$17, serial_number=$18, client_id=$19
      WHERE id=$20 RETURNING *
    `, [
      name, description||"", location||"", device_type||"other", ip_address||"", tags||[], 
      ddns_address||"", parseInt(monitor_port)||0, monitor_ping!==false, monitor_agent!==false, ai_enabled===true, notes||"",
      snmp_community||"public", snmp_version||"2c", ssh_user||"", parseInt(ssh_port)||22,
      mac_address||"", serial_number||"", cid,
      req.params.id
    ]);
    res.json(r.rows[0]);
    if (ddns_address && monitor_port) setImmediate(() => cloudMonitor(req.params.id));
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.delete("/devices/:id", auth, async (req, res) => {
  await pool.query("DELETE FROM devices WHERE id=$1", [req.params.id]);
  res.json({ ok: true });
});

app.get("/devices/:id/onvif", auth, requireAccessLevel(2), async (req, res) => {
  const deviceId = parseInt(req.params.id);
  const access = await assertDeviceAccess(req, deviceId);
  if (!access.ok) return res.status(access.status).json({ error: access.error });
  const r = await pool.query("SELECT enabled, host, port, username, channel_map, (password_enc <> '') as password_set FROM onvif_configs WHERE device_id=$1", [deviceId]);
  if (r.rows.length === 0) {
    return res.json({ enabled: false, host: "", port: 80, username: "", channel_map: {}, password_set: false });
  }
  res.json(r.rows[0]);
});

app.put("/devices/:id/onvif", auth, requireAccessLevel(2), async (req, res) => {
  try {
    const deviceId = parseInt(req.params.id);
    const access = await assertDeviceAccess(req, deviceId);
    if (!access.ok) return res.status(access.status).json({ error: access.error });

    const enabled = req.body.enabled === true;
    const host = String(req.body.host || "").trim();
    const port = parseInt(req.body.port) || 80;
    const username = String(req.body.username || "");
    const password = req.body.password;
    let channel_map = req.body.channel_map;

    if (enabled && !host) return res.status(400).json({ error: "Host required" });
    if (port < 1 || port > 65535) return res.status(400).json({ error: "Invalid port" });

    if (typeof channel_map === "string") {
      try { channel_map = JSON.parse(channel_map || "{}"); } catch { return res.status(400).json({ error: "Invalid channel_map JSON" }); }
    }
    if (!channel_map || typeof channel_map !== "object") channel_map = {};

    const existing = await pool.query("SELECT password_enc FROM onvif_configs WHERE device_id=$1", [deviceId]);
    let password_enc = existing.rows[0]?.password_enc || "";
    if (password === "") password_enc = "";
    else if (typeof password === "string" && password.length > 0) password_enc = encOnvif(password);

    const channelMapJson = JSON.stringify(channel_map || {});

    await pool.query(
      `
      INSERT INTO onvif_configs (device_id, enabled, host, port, username, password_enc, channel_map, updated_at)
      VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,NOW())
      ON CONFLICT (device_id) DO UPDATE SET
        enabled=EXCLUDED.enabled,
        host=EXCLUDED.host,
        port=EXCLUDED.port,
        username=EXCLUDED.username,
        password_enc=EXCLUDED.password_enc,
        channel_map=EXCLUDED.channel_map,
        updated_at=NOW()
      `,
      [deviceId, enabled, host, port, username, password_enc, channelMapJson]
    );

    res.json({ ok: true });
  } catch (e) {
    console.error("/devices/:id/onvif error:", e.message);
    res.status(500).json({ error: "Failed to save ONVIF config", detail: e.message });
  }
});

app.get("/devices/:id/rtsp", auth, requireAccessLevel(2), async (req, res) => {
  const deviceId = parseInt(req.params.id);
  const access = await assertDeviceAccess(req, deviceId);
  if (!access.ok) return res.status(access.status).json({ error: access.error });
  const r = await pool.query("SELECT enabled, username, streams, (password_enc <> '') as password_set FROM rtsp_configs WHERE device_id=$1", [deviceId]);
  if (r.rows.length === 0) {
    return res.json({ enabled: false, username: "", streams: [], password_set: false });
  }
  res.json(r.rows[0]);
});

app.put("/devices/:id/rtsp", auth, requireAccessLevel(2), async (req, res) => {
  try {
    const deviceId = parseInt(req.params.id);
    const access = await assertDeviceAccess(req, deviceId);
    if (!access.ok) return res.status(access.status).json({ error: access.error });

    const enabled = req.body.enabled === true;
    const username = String(req.body.username || "");
    const password = req.body.password;
    let streams = req.body.streams;

    if (typeof streams === "string") {
      try { streams = JSON.parse(streams || "[]"); } catch { return res.status(400).json({ error: "Invalid streams JSON" }); }
    }
    if (streams && typeof streams === "object" && !Array.isArray(streams)) streams = [streams];
    if (!Array.isArray(streams)) streams = [];
    streams = streams
      .filter((s) => s && typeof s === "object")
      .map((s) => ({
        channel: parseInt(s.channel) || 0,
        name: String(s.name || ""),
        url: String(s.url || "").trim(),
        enabled: s.enabled !== false,
        timeout_seconds: parseInt(s.timeout_seconds) || 8,
        interval_seconds: parseInt(s.interval_seconds) || 30,
        transport: String(s.transport || "tcp"),
      }))
      .filter((s) => s.url);

    const existing = await pool.query("SELECT password_enc FROM rtsp_configs WHERE device_id=$1", [deviceId]);
    let password_enc = existing.rows[0]?.password_enc || "";
    if (password === "") password_enc = "";
    else if (typeof password === "string" && password.length > 0) password_enc = encOnvif(password);

    if (enabled && streams.length === 0) {
      const dev = await pool.query("SELECT name, ip_address FROM devices WHERE id=$1", [deviceId]);
      const ip = String(dev.rows[0]?.ip_address || "").trim();
      const devName = String(dev.rows[0]?.name || "").trim();
      if (!ip) return res.status(400).json({ error: "Device IP is required for auto RTSP" });
      const streamName = devName || "Principal";
      streams = [
        {
          channel: 1,
          name: streamName,
          url: `rtsp://{username}:{password}@${ip}:554/cam/realmonitor?channel=1&subtype=0`,
          enabled: true,
          timeout_seconds: 8,
          interval_seconds: 30,
          transport: "tcp",
        },
      ];
    }

    const streamsJson = JSON.stringify(streams || []);

    await pool.query(
      `
      INSERT INTO rtsp_configs (device_id, enabled, username, password_enc, streams, updated_at)
      VALUES ($1,$2,$3,$4,$5::jsonb,NOW())
      ON CONFLICT (device_id) DO UPDATE SET
        enabled=EXCLUDED.enabled,
        username=EXCLUDED.username,
        password_enc=EXCLUDED.password_enc,
        streams=EXCLUDED.streams,
        updated_at=NOW()
      `,
      [deviceId, enabled, username, password_enc, streamsJson]
    );

    res.json({ ok: true });
  } catch (e) {
    console.error("/devices/:id/rtsp error:", e.message);
    res.status(500).json({ error: "Failed to save RTSP config", detail: e.message });
  }
});

app.get("/collector/onvif-config", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    const cid = req.query.client_id ? parseInt(req.query.client_id) : null;
    const params = [];
    let where = "oc.enabled=TRUE AND oc.host <> ''";
    if (cid) {
      params.push(cid);
      where += ` AND d.client_id=$${params.length}`;
    }

    const r = await pool.query(
      `
      SELECT d.id as device_id, d.name, d.client_id, d.token,
             oc.host, oc.port, oc.username, oc.password_enc, oc.channel_map
      FROM onvif_configs oc
      JOIN devices d ON d.id = oc.device_id
      WHERE ${where}
      ORDER BY d.id ASC
      `,
      params
    );

    res.json(
      r.rows.map((row) => ({
        device_id: row.device_id,
        name: row.name,
        client_id: row.client_id,
        token: row.token,
        host: row.host,
        port: row.port,
        username: row.username,
        password: decOnvif(row.password_enc),
        channel_map: row.channel_map || {},
      }))
    );
  } catch (e) {
    console.error("/collector/onvif-config error:", e.message);
    res.status(500).json({ error: "Failed to fetch onvif config", detail: e.message });
  }
});

app.get("/collector/rtsp-config", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    const cid = req.query.client_id ? parseInt(req.query.client_id) : null;
    const params = [];
    let where = "rc.enabled=TRUE";
    if (cid) {
      params.push(cid);
      where += ` AND d.client_id=$${params.length}`;
    }

    const r = await pool.query(
      `
      WITH cfg AS (
        SELECT
          d.id as device_id,
          d.name,
          d.client_id,
          d.token,
          d.device_type,
          d.ai_enabled,
          d.tags,
          rc.username,
          rc.password_enc,
          CASE
            WHEN jsonb_typeof(rc.streams) = 'array' THEN rc.streams
            ELSE '[]'::jsonb
          END AS streams
        FROM rtsp_configs rc
        JOIN devices d ON d.id = rc.device_id
        WHERE ${where}
      )
      SELECT d.device_id, d.name, d.client_id, d.token,
             d.device_type, d.ai_enabled, d.tags,
             d.username, d.password_enc, d.streams
      FROM cfg d
      WHERE jsonb_array_length(d.streams) > 0
      ORDER BY d.device_id ASC
      `,
      params
    );

    res.json(
      r.rows.map((row) => ({
        device_id: row.device_id,
        name: row.name,
        client_id: row.client_id,
        token: row.token,
        device_type: row.device_type || "",
        ai_enabled: row.ai_enabled === true,
        tags: Array.isArray(row.tags) ? row.tags : [],
        username: row.username,
        password: decOnvif(row.password_enc),
        streams: row.streams || [],
      }))
    );
  } catch (e) {
    console.error("/collector/rtsp-config error:", e.message);
    res.status(500).json({ error: "Failed to fetch rtsp config", detail: e.message });
  }
});

app.get("/collector/devices", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    const cid = req.query.client_id ? parseInt(req.query.client_id) : null;
    const params = [];
    let where = "1=1";
    if (cid) {
      params.push(cid);
      where += ` AND client_id=$${params.length}`;
    }

    const r = await pool.query(
      `
      SELECT
        id as device_id,
        name,
        client_id,
        token,
        ip_address,
        ddns_address,
        monitor_ping,
        monitor_port,
        device_type,
        ai_enabled,
        mac_address,
        serial_number,
        hostname,
        tags
      FROM devices
      WHERE ${where}
      ORDER BY id ASC
      `,
      params
    );

    res.json(
      r.rows.map((row) => ({
        device_id: row.device_id,
        name: row.name,
        client_id: row.client_id,
        token: row.token,
        ip_address: row.ip_address || "",
        ddns_address: row.ddns_address || "",
        monitor_ping: row.monitor_ping === true,
        monitor_port: parseInt(row.monitor_port) || 0,
        device_type: row.device_type || "",
        ai_enabled: row.ai_enabled === true,
        mac_address: row.mac_address || "",
        serial_number: row.serial_number || "",
        hostname: row.hostname || "",
        tags: Array.isArray(row.tags) ? row.tags : [],
      }))
    );
  } catch (e) {
    console.error("/collector/devices error:", e.message);
    res.status(500).json({ error: "Failed to fetch devices", detail: e.message });
  }
});

app.post("/collector/heartbeat", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    const cid = authz.client_id;
    // O agente envia métricas de saúde dele mesmo aqui
    // Podemos usar isso para saber que o Agente de Borda está online
    // e atualizar todos os devices 'monitor_agent' desse cliente que estão 'online' no banco
    await pool.query(
      "UPDATE clients SET collector_key_rotated_at=NOW() WHERE id=$1",
      [cid]
    );
    res.json({ ok: true });
  } catch (e) {
    console.error("/collector/heartbeat error:", e.message);
    res.status(500).json({ error: "Failed to process heartbeat" });
  }
});

app.get("/collector/notify-config", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    const cid = req.query.client_id ? parseInt(req.query.client_id) : null;
    const params = [];
    let where = "1=1";
    if (cid) {
      params.push(cid);
      where += ` AND id=$${params.length}`;
    }
    const r = await pool.query(
      `
      SELECT
        id,
        name,
        telegram_token,
        telegram_chat_id,
        wa_instance,
        wa_token,
        wa_number
      FROM clients
      WHERE ${where}
      ORDER BY id ASC
      `,
      params
    );
    res.json(
      r.rows.map((row) => ({
        client_id: row.id,
        name: row.name,
        telegram_configured: !!(row.telegram_token && row.telegram_chat_id),
        whatsapp_configured: !!(row.wa_instance && row.wa_token && row.wa_number),
      }))
    );
  } catch (e) {
    console.error("/collector/notify-config error:", e.message);
    res.status(500).json({ error: "Failed to fetch notify config", detail: e.message });
  }
});

app.get("/collector/client-notify", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    const cid = req.query.client_id ? parseInt(req.query.client_id) : null;
    if (!cid) return res.status(400).json({ error: "client_id required" });

    const r = await pool.query(
      `
      SELECT
        id,
        name,
        telegram_token,
        telegram_chat_id,
        wa_instance,
        wa_token,
        wa_number
      FROM clients
      WHERE id=$1
      LIMIT 1
      `,
      [cid]
    );
    if (r.rows.length === 0) return res.status(404).json({ error: "not_found" });
    const row = r.rows[0];
    res.json({
      client_id: row.id,
      name: row.name,
      telegram_token: row.telegram_token || "",
      telegram_chat_id: row.telegram_chat_id || "",
      wa_instance: row.wa_instance || "",
      wa_token: row.wa_token || "",
      wa_number: row.wa_number || "",
    });
  } catch (e) {
    console.error("/collector/client-notify error:", e.message);
    res.status(500).json({ error: "Failed to fetch client notify", detail: e.message });
  }
});

app.get("/collector/global-notify", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    res.json({
      telegram_token: sanitize(process.env.TELEGRAM_TOKEN || ""),
      telegram_chat_id: sanitize(process.env.TELEGRAM_CHAT_ID || ""),
      wa_instance: sanitize(process.env.TWILIO_ACCOUNT_SID || process.env.WA_INSTANCE || ""),
      wa_token: sanitize(process.env.TWILIO_AUTH_TOKEN || process.env.WA_TOKEN || ""),
      wa_number: sanitize(process.env.WA_NUMBER || ""),
      twilio_whatsapp_number: sanitize(process.env.TWILIO_WHATSAPP_NUMBER || ""),
      twilio_content_sid: sanitize(process.env.TWILIO_CONTENT_SID || ""),
    });
  } catch (e) {
    console.error("/collector/global-notify error:", e.message);
    res.status(500).json({ error: "Failed to fetch global notify", detail: e.message });
  }
});

app.get("/collector/automation-rules", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    const cid = req.query.client_id ? parseInt(req.query.client_id) : null;
    if (!cid) return res.status(400).json({ error: "client_id required" });
    const r = await pool.query(
      `
      SELECT id, name, enabled, rule, updated_at
      FROM automation_rules
      WHERE client_id=$1 AND enabled=TRUE
      ORDER BY id ASC
      `,
      [cid]
    );
    res.json(
      r.rows.map((row) => ({
        id: row.id,
        name: row.name,
        enabled: row.enabled === true,
        rule: row.rule || {},
        updated_at: row.updated_at,
      }))
    );
  } catch (e) {
    console.error("/collector/automation-rules error:", e.message);
    res.status(500).json({ error: "Failed to fetch rules", detail: e.message });
  }
});

app.post("/collector/automation-rules", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    function sanitizeLabel(v) {
      return v ? String(v).replace(/["'`]/g, "").trim() : "";
    }

    const cid =
      (req.body?.client_id ? parseInt(req.body.client_id) : null) ||
      (req.query.client_id ? parseInt(req.query.client_id) : null);
    if (!cid) return res.status(400).json({ error: "client_id required" });

    const enabled = typeof req.body?.enabled === "boolean" ? req.body.enabled === true : true;

    const rawRule = req.body?.rule;
    if (!rawRule || typeof rawRule !== "object" || Array.isArray(rawRule)) {
      return res.status(400).json({ error: "rule must be an object" });
    }

    const withinSeconds = Number.isFinite(Number(rawRule.within_seconds)) ? Number(rawRule.within_seconds) : 10;
    if (!Number.isFinite(withinSeconds) || withinSeconds < 1 || withinSeconds > 86400) {
      return res.status(400).json({ error: "rule.within_seconds invalid" });
    }

    const cooldownSecondsRaw =
      rawRule.cooldown_seconds === undefined || rawRule.cooldown_seconds === null ? null : Number(rawRule.cooldown_seconds);
    if (cooldownSecondsRaw !== null) {
      if (!Number.isFinite(cooldownSecondsRaw) || cooldownSecondsRaw < 1 || cooldownSecondsRaw > 86400) {
        return res.status(400).json({ error: "rule.cooldown_seconds invalid" });
      }
    }

    const ifAll = Array.isArray(rawRule.if_all) ? rawRule.if_all : [];
    if (ifAll.length === 0) return res.status(400).json({ error: "rule.if_all required" });
    const ifAllNorm = [];
    for (const c of ifAll) {
      if (!c || typeof c !== "object" || Array.isArray(c)) return res.status(400).json({ error: "rule.if_all invalid" });
      const cond = {};
      if (c.event_type !== undefined) cond.event_type = sanitize(c.event_type || "");
      if (c.device_id !== undefined) cond.device_id = parseInt(c.device_id);
      if (c.channel !== undefined) cond.channel = parseInt(c.channel);
      if (c.severity !== undefined) cond.severity = sanitize(c.severity || "");
      if (c.source !== undefined) cond.source = sanitize(c.source || "");
      if (cond.event_type !== undefined && !cond.event_type) return res.status(400).json({ error: "rule.if_all.event_type invalid" });
      if (cond.device_id !== undefined && !(Number.isFinite(cond.device_id) && cond.device_id > 0)) {
        return res.status(400).json({ error: "rule.if_all.device_id invalid" });
      }
      if (cond.channel !== undefined && !(Number.isFinite(cond.channel) && cond.channel >= 0)) {
        return res.status(400).json({ error: "rule.if_all.channel invalid" });
      }
      if (cond.severity !== undefined && !cond.severity) return res.status(400).json({ error: "rule.if_all.severity invalid" });
      if (cond.source !== undefined && !cond.source) return res.status(400).json({ error: "rule.if_all.source invalid" });
      ifAllNorm.push(cond);
    }

    const ifNot = Array.isArray(rawRule.if_not) ? rawRule.if_not : [];
    const ifNotNorm = [];
    for (const c of ifNot) {
      if (!c || typeof c !== "object" || Array.isArray(c)) return res.status(400).json({ error: "rule.if_not invalid" });
      const cond = {};
      if (c.event_type !== undefined) cond.event_type = sanitize(c.event_type || "");
      if (c.device_id !== undefined) cond.device_id = parseInt(c.device_id);
      if (c.channel !== undefined) cond.channel = parseInt(c.channel);
      if (c.severity !== undefined) cond.severity = sanitize(c.severity || "");
      if (c.source !== undefined) cond.source = sanitize(c.source || "");
      if (cond.event_type !== undefined && !cond.event_type) return res.status(400).json({ error: "rule.if_not.event_type invalid" });
      if (cond.device_id !== undefined && !(Number.isFinite(cond.device_id) && cond.device_id > 0)) {
        return res.status(400).json({ error: "rule.if_not.device_id invalid" });
      }
      if (cond.channel !== undefined && !(Number.isFinite(cond.channel) && cond.channel >= 0)) {
        return res.status(400).json({ error: "rule.if_not.channel invalid" });
      }
      if (cond.severity !== undefined && !cond.severity) return res.status(400).json({ error: "rule.if_not.severity invalid" });
      if (cond.source !== undefined && !cond.source) return res.status(400).json({ error: "rule.if_not.source invalid" });
      ifNotNorm.push(cond);
    }

    const actions = Array.isArray(rawRule.actions) ? rawRule.actions : [];
    if (actions.length === 0) return res.status(400).json({ error: "rule.actions required" });
    const actionsNorm = [];
    for (const a of actions) {
      if (!a || typeof a !== "object" || Array.isArray(a)) return res.status(400).json({ error: "rule.actions invalid" });
      const type = sanitize(a.type || "");
      if (type !== "notify") return res.status(400).json({ error: "rule.actions.type unsupported" });
      let channels = Array.isArray(a.channels) ? a.channels : a.channels ? [a.channels] : ["telegram", "whatsapp"];
      channels = channels.map((x) => sanitize(x)).filter((x) => x);
      if (channels.length === 0) channels = ["telegram"];
      actionsNorm.push({ type: "notify", channels });
    }

    const message = rawRule.message !== undefined && rawRule.message !== null ? String(rawRule.message) : "";
    if (message && message.length > 400) return res.status(400).json({ error: "rule.message too long" });

    const rule = {
      within_seconds: withinSeconds,
      if_all: ifAllNorm,
      actions: actionsNorm,
    };
    if (ifNotNorm.length > 0) rule.if_not = ifNotNorm;
    if (cooldownSecondsRaw !== null) rule.cooldown_seconds = cooldownSecondsRaw;
    if (message) rule.message = message;

    const ridBody = req.body?.id ? parseInt(req.body.id) : null;
    if (ridBody && Number.isFinite(ridBody) && ridBody > 0) {
      const existingById = await pool.query("SELECT id, name FROM automation_rules WHERE id=$1 AND client_id=$2 LIMIT 1", [
        ridBody,
        cid,
      ]);
      if (existingById.rows.length === 0) return res.status(404).json({ error: "not_found" });
      const nameExisting = existingById.rows[0].name || "";
      const nameNew = sanitizeLabel(req.body?.name || "") || nameExisting;
      if (!nameNew) return res.status(400).json({ error: "name required" });
      await pool.query("UPDATE automation_rules SET name=$1, enabled=$2, rule=$3::jsonb, updated_at=NOW() WHERE id=$4", [
        nameNew,
        enabled,
        JSON.stringify(rule),
        ridBody,
      ]);
      return res.json({ ok: true, id: ridBody, updated: true });
    }

    const name = sanitizeLabel(req.body?.name || "");
    if (!name) return res.status(400).json({ error: "name required" });

    const existing = await pool.query("SELECT id FROM automation_rules WHERE client_id=$1 AND name=$2 ORDER BY id ASC LIMIT 1", [
      cid,
      name,
    ]);
    if (existing.rows.length > 0) {
      const id = existing.rows[0].id;
      await pool.query("UPDATE automation_rules SET enabled=$1, rule=$2::jsonb, updated_at=NOW() WHERE id=$3", [
        enabled,
        JSON.stringify(rule),
        id,
      ]);
      return res.json({ ok: true, id, updated: true });
    }

    const ins = await pool.query(
      `
      INSERT INTO automation_rules (name, enabled, client_id, rule, created_at, updated_at)
      VALUES ($1,$2,$3,$4::jsonb,NOW(),NOW())
      RETURNING id
      `,
      [name, enabled, cid, JSON.stringify(rule)]
    );
    res.json({ ok: true, id: ins.rows[0].id, created: true });
  } catch (e) {
    console.error("/collector/automation-rules POST error:", e.message);
    res.status(500).json({ error: "Failed to upsert rule", detail: e.message });
  }
});

app.post("/collector/discovery", async (req, res) => {
  const authz = await authorizeCollector(req);
  if (!authz.ok) return res.status(authz.status).json({ error: authz.error });

  try {
    const agent_id = sanitize(req.body?.agent_id || "");
    const client_id_raw = req.body?.client_id ? parseInt(req.body.client_id) : null;
    const items = Array.isArray(req.body?.items) ? req.body.items : [];

    if (!agent_id) return res.status(400).json({ error: "agent_id required" });
    if (items.length === 0) return res.json({ ok: true, upserted: 0 });

    let upserted = 0;
    let adopted = 0;
    for (const it of items) {
      const ip_address = sanitize(it?.ip_address || "");
      if (!ip_address) continue;
      const mac_address = sanitize(it?.mac_address || "");
      const hostname = sanitize(it?.hostname || "");
      const vendor = sanitize(it?.vendor || "");
      const guess_type = sanitize(it?.guess_type || "");
      const onvif_xaddrs = sanitize(it?.onvif_xaddrs || "");
      const open_ports_raw = Array.isArray(it?.open_ports) ? it.open_ports : [];
      const open_ports = open_ports_raw
        .map((p) => parseInt(p))
        .filter((p) => Number.isFinite(p) && p > 0 && p <= 65535);
      const raw = it?.raw && typeof it.raw === "object" ? it.raw : {};

      const targetClientId = (Number.isFinite(client_id_raw) && client_id_raw > 0 ? client_id_raw : null) || DEFAULT_DISCOVERY_CLIENT_ID || null;
      const up = await pool.query(
        `
        INSERT INTO discovered_devices (
          agent_id, client_id, ip_address, mac_address, hostname, vendor, guess_type,
          open_ports, onvif_xaddrs, raw, first_seen, last_seen
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,NOW(),NOW())
        ON CONFLICT (agent_id, ip_address) DO UPDATE SET
          client_id=COALESCE(EXCLUDED.client_id, discovered_devices.client_id),
          mac_address=CASE WHEN EXCLUDED.mac_address <> '' THEN EXCLUDED.mac_address ELSE discovered_devices.mac_address END,
          hostname=CASE WHEN EXCLUDED.hostname <> '' THEN EXCLUDED.hostname ELSE discovered_devices.hostname END,
          vendor=CASE WHEN EXCLUDED.vendor <> '' THEN EXCLUDED.vendor ELSE discovered_devices.vendor END,
          guess_type=CASE WHEN EXCLUDED.guess_type <> '' THEN EXCLUDED.guess_type ELSE discovered_devices.guess_type END,
          open_ports=EXCLUDED.open_ports,
          onvif_xaddrs=CASE WHEN EXCLUDED.onvif_xaddrs <> '' THEN EXCLUDED.onvif_xaddrs ELSE discovered_devices.onvif_xaddrs END,
          raw=EXCLUDED.raw,
          last_seen=NOW()
        RETURNING id, device_id, client_id
        `,
        [agent_id, targetClientId, ip_address, mac_address, hostname, vendor, guess_type, open_ports, onvif_xaddrs, JSON.stringify(raw)]
      );
      upserted += 1;

      const dd = up.rows[0];
      if (!AUTO_ADOPT_DISCOVERY) continue;
      if (!dd || dd.device_id) continue;
      if (!dd.client_id) continue;
      const ports = new Set(open_ports || []);
      const eligible =
        !!onvif_xaddrs ||
        ports.has(554) ||
        ports.has(80) ||
        ports.has(443) ||
        ports.has(22) ||
        ports.has(161) ||
        ports.has(9100) ||
        ports.has(3389);
      if (!eligible) continue;

      const existing = await pool.query("SELECT id FROM devices WHERE client_id=$1 AND ip_address=$2 LIMIT 1", [dd.client_id, ip_address]);
      if (existing.rows.length > 0) {
        await pool.query("UPDATE discovered_devices SET device_id=$1 WHERE id=$2", [existing.rows[0].id, dd.id]);
        adopted += 1;
        continue;
      }

      const device_type =
        (guess_type && guess_type !== "other" ? guess_type : "") ||
        (ports.has(554) || onvif_xaddrs ? "camera" : ports.has(9100) ? "printer" : ports.has(3389) ? "windows" : ports.has(22) ? "server" : ports.has(161) ? "snmp" : "other");
      const monitor_port = ports.has(80) ? 80 : ports.has(443) ? 443 : ports.has(554) ? 554 : ports.has(22) ? 22 : 0;
      const name = hostname || `${device_type}-${ip_address.replace(/\./g, "-")}`;
      const token = crypto.randomBytes(32).toString("hex");

      const ins = await pool.query(
        `
        INSERT INTO devices (
          name, description, location, token, device_type, ip_address, tags,
          ddns_address, monitor_port, monitor_ping, monitor_agent, notes, client_id,
          snmp_community, snmp_version, ssh_user, ssh_port,
          mac_address, serial_number
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
        RETURNING id
        `,
        [
          name,
          "Descoberto automaticamente pelo agente local",
          "",
          token,
          device_type,
          ip_address,
          [device_type, "discovered", onvif_xaddrs ? "onvif" : ""].filter(Boolean),
          "",
          monitor_port,
          true,
          true,
          onvif_xaddrs || "",
          dd.client_id,
          "public",
          "2c",
          "",
          22,
          mac_address,
          "",
        ]
      );
      await pool.query("UPDATE discovered_devices SET device_id=$1 WHERE id=$2", [ins.rows[0].id, dd.id]);
      adopted += 1;
    }

    res.json({ ok: true, upserted, adopted });
  } catch (e) {
    console.error("/collector/discovery error:", e.message);
    res.status(500).json({ error: "Failed to save discovery", detail: e.message });
  }
});

app.get("/discovered-devices", auth, async (req, res) => {
  try {
    const cid = clientFilter(req);
    const params = [];
    let where = "dd.last_seen > NOW() - interval '24 hours'";
    if (String(req.query.all || "") === "1") where = "1=1";
    if (cid) {
      params.push(cid);
      where += ` AND dd.client_id=$${params.length}`;
    }

    const r = await pool.query(
      `
      SELECT dd.*, d.name as adopted_device_name
      FROM discovered_devices dd
      LEFT JOIN devices d ON d.id = dd.device_id
      WHERE ${where}
      ORDER BY dd.last_seen DESC
      LIMIT 200
      `,
      params
    );
    res.json(r.rows);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/discovered-devices/:id/adopt", auth, async (req, res) => {
  const id = parseInt(req.params.id);
  if (!id) return res.status(400).json({ error: "Invalid id" });

  try {
    const dr = await pool.query("SELECT * FROM discovered_devices WHERE id=$1", [id]);
    if (dr.rows.length === 0) return res.status(404).json({ error: "Not found" });
    const dd = dr.rows[0];

    const requestedClientId = req.user.role === "superadmin" ? (req.body?.client_id ? parseInt(req.body.client_id) : null) : req.user.client_id;
    const targetClientId = requestedClientId || dd.client_id || null;

    if (req.user.role !== "superadmin") {
      if (dd.client_id && dd.client_id !== req.user.client_id) return res.status(403).json({ error: "Forbidden" });
      if (!targetClientId) return res.status(400).json({ error: "client_id required" });
    }

    const name = sanitize(req.body?.name || dd.hostname || `${dd.guess_type || "device"}-${dd.ip_address}`);
    if (!name) return res.status(400).json({ error: "Name required" });

    const open_ports = Array.isArray(dd.open_ports) ? dd.open_ports : [];
    const guess = sanitize(dd.guess_type || "");
    const device_type = guess || (open_ports.includes(554) ? "camera" : "other");
    const monitor_port = open_ports.includes(80) ? 80 : open_ports.includes(443) ? 443 : open_ports.includes(554) ? 554 : open_ports.includes(22) ? 22 : 0;
    const token = crypto.randomBytes(32).toString("hex");

    const ins = await pool.query(
      `
      INSERT INTO devices (
        name, description, location, token, device_type, ip_address, tags,
        ddns_address, monitor_port, monitor_ping, monitor_agent, notes, client_id,
        snmp_community, snmp_version, ssh_user, ssh_port,
        mac_address, serial_number
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
      RETURNING *
      `,
      [
        name,
        "Descoberto pelo agente local",
        "",
        token,
        device_type || "other",
        dd.ip_address || "",
        [device_type || "device", "discovered"],
        "",
        monitor_port,
        true,
        true,
        dd.onvif_xaddrs || "",
        targetClientId,
        "public",
        "2c",
        "",
        22,
        dd.mac_address || "",
        "",
      ]
    );

    await pool.query("UPDATE discovered_devices SET device_id=$1 WHERE id=$2", [ins.rows[0].id, id]);
    res.status(201).json(ins.rows[0]);
  } catch (e) {
    res.status(500).json({ error: "Failed to adopt device", detail: e.message });
  }
});

// ── Solar Inverters ──────────────────────────────────────────
app.get("/solar/inverters", auth, async (req, res) => {
  try {
    const cid = clientFilter(req);
    let query = `
      SELECT 
        si.*,
        c.name as client_name,
        sm.power_w as last_power,
        sm.energy_today_kwh as last_energy_today,
        sm.energy_total_kwh as last_energy_total,
        sm.revenue_today as last_revenue_today,
        sm.revenue_total as last_revenue_total,
        sm.inverter_status as last_status,
        sm.time as last_update
      FROM solar_inverters si
      LEFT JOIN clients c ON si.client_id = c.id
      LEFT JOIN LATERAL (
        SELECT * FROM solar_metrics 
        WHERE inverter_id = si.id 
        ORDER BY time DESC LIMIT 1
      ) sm ON true
      WHERE 1=1
    `;
    const params = [];
    if (cid) { params.push(cid); query += " AND si.client_id=$1"; }
    const r = await pool.query(query, params);
    res.json(r.rows);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.post("/solar/inverters", auth, async (req, res) => {
  const { name, brand, model, location, capacity_kwp, tariff_kwh, client_id, notes, ...creds } = req.body;
  const cid = req.user.role === "superadmin" ? (client_id || null) : req.user.client_id;
  try {
    const r = await pool.query(`
      INSERT INTO solar_inverters (
        name, brand, model, location, capacity_kwp, tariff_kwh, client_id, notes,
        growatt_user, growatt_pass, growatt_plant_id,
        fronius_ip, fronius_device_id,
        solarman_token, solarman_app_id, solarman_logger_sn,
        sma_user, sma_pass, sma_plant_id,
        goodwe_user, goodwe_pass, goodwe_station_id,
        huawei_user, huawei_pass, huawei_station_id,
        saj_user, saj_pass, saj_plant_id,
        api_url, api_key
      ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30)
      RETURNING *
    `, [
      name, brand, model||"", location||"", parseFloat(capacity_kwp)||0, parseFloat(tariff_kwh)||0.85, cid, notes||"",
      creds.growatt_user||"", creds.growatt_pass||"", creds.growatt_plant_id||"",
      creds.fronius_ip||"", parseInt(creds.fronius_device_id)||1,
      creds.solarman_token||"", creds.solarman_app_id||"", creds.solarman_logger_sn||"",
      creds.sma_user||"", creds.sma_pass||"", creds.sma_plant_id||"",
      creds.goodwe_user||"", creds.goodwe_pass||"", creds.goodwe_station_id||"",
      creds.huawei_user||"", creds.huawei_pass||"", creds.huawei_station_id||"",
      creds.saj_user||"", creds.saj_pass||"", creds.saj_plant_id||"",
      creds.api_url||"", creds.api_key||""
    ]);
    res.status(201).json(r.rows[0]);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.put("/solar/inverters/:id", auth, async (req, res) => {
  const { name, brand, model, location, capacity_kwp, tariff_kwh, notes, ...creds } = req.body;
  try {
    const r = await pool.query(`
      UPDATE solar_inverters SET
        name=$1, brand=$2, model=$3, location=$4, capacity_kwp=$5, tariff_kwh=$6, notes=$7,
        growatt_user=$8, growatt_pass=$9, growatt_plant_id=$10,
        fronius_ip=$11, fronius_device_id=$12,
        solarman_token=$13, solarman_app_id=$14, solarman_logger_sn=$15,
        sma_user=$16, sma_pass=$17, sma_plant_id=$18,
        goodwe_user=$19, goodwe_pass=$20, goodwe_station_id=$21,
        huawei_user=$22, huawei_pass=$23, huawei_station_id=$24,
        saj_user=$25, saj_pass=$26, saj_plant_id=$27,
        api_url=$28, api_key=$29
      WHERE id=$30 RETURNING *
    `, [
      name, brand, model||"", location||"", parseFloat(capacity_kwp)||0, parseFloat(tariff_kwh)||0.85, notes||"",
      creds.growatt_user||"", creds.growatt_pass||"", creds.growatt_plant_id||"",
      creds.fronius_ip||"", parseInt(creds.fronius_device_id)||1,
      creds.solarman_token||"", creds.solarman_app_id||"", creds.solarman_logger_sn||"",
      creds.sma_user||"", creds.sma_pass||"", creds.sma_plant_id||"",
      creds.goodwe_user||"", creds.goodwe_pass||"", creds.goodwe_station_id||"",
      creds.huawei_user||"", creds.huawei_pass||"", creds.huawei_station_id||"",
      creds.saj_user||"", creds.saj_pass||"", creds.saj_plant_id||"",
      creds.api_url||"", creds.api_key||"",
      req.params.id
    ]);
    res.json(r.rows[0]);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.delete("/solar/inverters/:id", auth, async (req, res) => {
  await pool.query("DELETE FROM solar_inverters WHERE id=$1", [req.params.id]);
  res.json({ ok: true });
});

app.get("/solar/brands", auth, (req, res) =>
  res.json([
    { value: "growatt", label: "Growatt" },
    { value: "fronius", label: "Fronius" },
    { value: "deye", label: "Deye" },
    { value: "solis", label: "Solis" },
    { value: "sma", label: "SMA" },
    { value: "goodwe", label: "GoodWe" },
    { value: "huawei", label: "Huawei" },
    { value: "saj", label: "SAJ" },
    { value: "canadian", label: "Canadian" },
    { value: "risen", label: "Risen" },
    { value: "other", label: "Outro" },
  ])
);

app.get("/solar/inverters/:id/metrics", auth, async (req, res) => {
  const hours = parseInt(req.query.hours) || 24;
  const r = await pool.query(`
    SELECT * FROM solar_metrics 
    WHERE inverter_id=$1 AND time > NOW() - interval '${hours} hours'
    ORDER BY time ASC
  `, [req.params.id]);
  res.json(r.rows);
});

app.get("/solar/summary", auth, async (req, res) => {
  const cid = clientFilter(req);
  const params = [];
  let where = "si.status='active'";
  if (cid) {
    params.push(cid);
    where += ` AND si.client_id=$${params.length}`;
  }

  const r = await pool.query(
    `
    WITH latest AS (
      SELECT DISTINCT ON (inverter_id)
        inverter_id,
        power_w,
        energy_today_kwh,
        revenue_today
      FROM solar_metrics
      ORDER BY inverter_id, time DESC
    )
    SELECT
      COUNT(si.id)::int as total_inverters,
      COALESCE(SUM(latest.power_w), 0) as total_power_w,
      COALESCE(SUM(latest.energy_today_kwh), 0) as energy_today_kwh,
      COALESCE(SUM(latest.revenue_today), 0) as revenue_today
    FROM solar_inverters si
    LEFT JOIN latest ON latest.inverter_id = si.id
    WHERE ${where}
    `,
    params
  );

  const row = r.rows[0] || {};
  res.json({
    total_inverters: Number(row.total_inverters || 0),
    total_power_w: Number(row.total_power_w || 0),
    energy_today_kwh: Number(row.energy_today_kwh || 0),
    revenue_today: Number(row.revenue_today || 0),
    total_power: Number(row.total_power_w || 0),
    total_energy_today: Number(row.energy_today_kwh || 0),
    total_revenue_today: Number(row.revenue_today || 0),
  });
});

app.get("/solar/health", auth, async (req, res) => {
  const cid = clientFilter(req);
  const params = [];
  let where = "si.status='active'";
  if (cid) {
    params.push(cid);
    where += ` AND si.client_id=$${params.length}`;
  }

  const r = await pool.query(
    `
    WITH latest AS (
      SELECT DISTINCT ON (inverter_id)
        inverter_id,
        time
      FROM solar_metrics
      ORDER BY inverter_id, time DESC
    )
    SELECT
      COUNT(si.id)::int as total_inverters,
      COUNT(latest.inverter_id)::int as with_data,
      COUNT(latest.inverter_id) FILTER (WHERE latest.time > NOW() - interval '15 minutes')::int as reporting_15m,
      MAX(latest.time) as last_update
    FROM solar_inverters si
    LEFT JOIN latest ON latest.inverter_id = si.id
    WHERE ${where}
    `,
    params
  );

  const row = r.rows[0] || {};
  const lastUpdate = row.last_update ? new Date(row.last_update) : null;
  const secondsSinceLastUpdate = lastUpdate ? Math.floor((Date.now() - lastUpdate.getTime()) / 1000) : null;

  res.json({
    total_inverters: Number(row.total_inverters || 0),
    with_data: Number(row.with_data || 0),
    reporting_15m: Number(row.reporting_15m || 0),
    last_update: row.last_update || null,
    seconds_since_last_update: secondsSinceLastUpdate,
  });
});

app.post("/devices/:id/regenerate-token", auth, async (req, res) => {
  const token = crypto.randomBytes(32).toString("hex");
  const r = await pool.query("UPDATE devices SET token=$1 WHERE id=$2 RETURNING token", [token, req.params.id]);
  res.json({ token: r.rows[0].token });
});

app.post("/devices/:id/test", auth, async (req, res) => {
  try {
    const dr = await pool.query("SELECT name, ip_address, ddns_address, monitor_port, last_seen, status FROM devices WHERE id=$1", [req.params.id]);
    const { name, ip_address, ddns_address, monitor_port, last_seen, status } = dr.rows[0];
    
    // Se o dispositivo enviou sinal recentemente via Auto Registro (Push), consideramos OK
    const now = new Date();
    const isRecentlySeen = last_seen && (now - new Date(last_seen)) < 120000; // 2 minutos

    if (isRecentlySeen && status === 'online') {
      return res.json({ alive: true, message: `✅ ${name} está conectado via Auto Registro / Cloud Push!` });
    }

    const targetHost = ddns_address || ip_address;
    if (!targetHost || !monitor_port) return res.status(400).json({ error: "Endereço (IP/DDNS) ou Porta não configurados" });
    
    // Se for IP local, avisamos que precisa do Auto Registro
    if (targetHost.startsWith("192.168.") || targetHost.startsWith("10.") || targetHost.startsWith("172.")) {
      return res.json({ 
        alive: false, 
        message: `ℹ️ O dispositivo usa IP local (${targetHost}). Certifique-se de que o Auto Registro está configurado na câmera apontando para o nosso servidor.` 
      });
    }

    const socket = new net.Socket();
    socket.setTimeout(8000);
    socket.on("connect", () => { socket.destroy(); res.json({ alive: true, message: `Conectado com sucesso em ${targetHost}:${monitor_port}!` }); });
    socket.on("timeout", () => { socket.destroy(); res.json({ alive: false, message: `Timeout ao tentar conectar em ${targetHost}:${monitor_port}.` }); });
    socket.on("error", (err) => { socket.destroy(); res.json({ alive: false, message: `Erro de conexão (${err.code}) em ${targetHost}:${monitor_port}.` }); });
    socket.connect(monitor_port, targetHost);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// ── Clients ──────────────────────────────────────────────────
app.get("/clients", auth, superadmin, async (req, res) => {
  const r = await pool.query(
    `
    SELECT
      id, name, document, email, phone, address, city, state, plan, status,
      telegram_token, telegram_chat_id, alert_email, wa_instance, wa_token, wa_number, notes,
      created_at,
      (collector_key_hash <> '') AS collector_key_set,
      collector_key_rotated_at
    FROM clients
    ORDER BY name
    `
  );
  res.json(r.rows);
});

app.post("/clients", auth, superadmin, async (req, res) => {
  const { 
    name, document, email, phone, address, city, state, 
    plan, status, telegram_token, telegram_chat_id, 
    alert_email, wa_instance, wa_token, wa_number, notes 
  } = req.body;
  const collectorKey = _collectorRawKey();
  const collectorHash = _collectorHash(collectorKey);
  const r = await pool.query(`
    INSERT INTO clients (
      name, document, email, phone, address, city, state, 
      plan, status, telegram_token, telegram_chat_id, 
      alert_email, wa_instance, wa_token, wa_number, notes,
      collector_key_hash, collector_key_rotated_at
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,NOW())
    RETURNING id, name, document, email, phone, address, city, state, plan, status,
      telegram_token, telegram_chat_id, alert_email, wa_instance, wa_token, wa_number, notes,
      created_at, collector_key_rotated_at
  `, [
    name, document||"", email||"", phone||"", address||"", city||"", state||"", 
    plan||"basic", status||"active", telegram_token||"", telegram_chat_id||"", 
    alert_email||"", wa_instance||"", wa_token||"", wa_number||"", notes||"",
    collectorHash
  ]);
  res.status(201).json({
    ...r.rows[0],
    collector_key_set: true,
    collector_key: collectorKey,
  });
});

app.post("/clients/:id/collector-key/rotate", auth, superadmin, async (req, res) => {
  const id = parseInt(req.params.id, 10);
  if (!id || !Number.isFinite(id) || id <= 0) return res.status(400).json({ error: "Invalid id" });
  const collectorKey = _collectorRawKey();
  const collectorHash = _collectorHash(collectorKey);
  const r = await pool.query(
    "UPDATE clients SET collector_key_hash=$1, collector_key_rotated_at=NOW() WHERE id=$2 RETURNING collector_key_rotated_at",
    [collectorHash, id]
  );
  if (r.rows.length === 0) return res.status(404).json({ error: "not_found" });
  res.json({ ok: true, id, collector_key: collectorKey, collector_key_rotated_at: r.rows[0].collector_key_rotated_at });
});

app.put("/clients/:id", auth, superadmin, async (req, res) => {
  const { 
    name, document, email, phone, address, city, state, 
    plan, status, telegram_token, telegram_chat_id, 
    alert_email, wa_instance, wa_token, wa_number, notes 
  } = req.body;
  const r = await pool.query(`
    UPDATE clients SET 
      name=$1, document=$2, email=$3, phone=$4, address=$5, city=$6, state=$7, 
      plan=$8, status=$9, telegram_token=$10, telegram_chat_id=$11, 
      alert_email=$12, wa_instance=$13, wa_token=$14, wa_number=$15, notes=$16
    WHERE id=$17
    RETURNING id, name, document, email, phone, address, city, state, plan, status,
      telegram_token, telegram_chat_id, alert_email, wa_instance, wa_token, wa_number, notes,
      created_at, (collector_key_hash <> '') AS collector_key_set, collector_key_rotated_at
  `, [
    name, document||"", email||"", phone||"", address||"", city||"", state||"", 
    plan||"basic", status||"active", telegram_token||"", telegram_chat_id||"", 
    alert_email||"", wa_instance||"", wa_token||"", wa_number||"", notes||"",
    req.params.id
  ]);
  res.json(r.rows[0]);
});

app.delete("/clients/:id", auth, superadmin, async (req, res) => {
  await pool.query("DELETE FROM clients WHERE id=$1", [req.params.id]);
  res.json({ ok: true });
});

app.post("/clients/:id/users", auth, superadmin, async (req, res) => {
  try {
    const { username, password, access_level } = req.body || {};
    const u = String(username || "").trim();
    const p = String(password || "");
    if (!u) return res.status(400).json({ error: "username required" });
    if (!p || p.length < 6) return res.status(400).json({ error: "password too short" });
    const lvl = Math.max(1, Math.min(3, parseInt(access_level || 1, 10) || 1));
    const hash = await bcrypt.hash(p, 10);
    await pool.query(
      "INSERT INTO users (username, password_hash, role, access_level, client_id) VALUES ($1,$2,'client',$3,$4)",
      [u, hash, lvl, req.params.id]
    );
    res.json({ ok: true, username: u });
  } catch (e) {
    if (e && e.code === "23505") {
      return res.status(409).json({ error: "username already exists" });
    }
    console.error("Create client user error:", e);
    return res.status(500).json({ error: "internal_error" });
  }
});

app.get("/clients/:id/stats", auth, superadmin, async (req, res) => {
  const id = req.params.id;
  const total = await pool.query("SELECT COUNT(*) FROM devices WHERE client_id=$1", [id]);
  const online = await pool.query("SELECT COUNT(*) FROM devices WHERE client_id=$1 AND status='online'", [id]);
  const alerts = await pool.query("SELECT COUNT(*) FROM metrics m JOIN devices d ON d.id=m.device_id WHERE d.client_id=$1 AND m.status='offline' AND m.time > NOW() - interval '24 hours'", [id]);
  res.json({
    total: parseInt(total.rows[0].count),
    online: parseInt(online.rows[0].count),
    offline: parseInt(total.rows[0].count) - parseInt(online.rows[0].count),
    alerts: parseInt(alerts.rows[0].count)
  });
});

// ── Metrics ──────────────────────────────────────────────────
app.get("/metrics/:host", auth, async (req, res) => {
  const hours = parseInt(req.query.hours) || 24;
  const r = await pool.query(`
    SELECT * FROM metrics 
    WHERE host=$1 AND time > NOW() - interval '${hours} hours'
    ORDER BY time ASC
  `, [req.params.host]);
  res.json(r.rows);
});

app.get("/hosts", auth, async (req, res) => {
  const cid = clientFilter(req);
  let query = "SELECT DISTINCT host as name FROM metrics WHERE time > NOW() - interval '24 hours'";
  const params = [];
  if (cid) {
    query = `
      SELECT DISTINCT m.host as name 
      FROM metrics m
      JOIN devices d ON d.id = m.device_id
      WHERE d.client_id = $1 AND m.time > NOW() - interval '24 hours'
    `;
    params.push(cid);
  }
  const r = await pool.query(query, params);
  res.json(r.rows);
});

app.get("/triggers", auth, async (req, res) => {
  const cid = clientFilter(req);
  let query = "SELECT * FROM triggers";
  const params = [];
  if (cid) { query += " WHERE client_id=$1 OR client_id IS NULL"; params.push(cid); }
  const r = await pool.query(query, params);
  res.json(r.rows);
});

app.post("/triggers", auth, superadmin, async (req, res) => {
  const { name, expression, threshold, enabled, client_id } = req.body;
  const cid = req.user.role === "superadmin" ? (client_id || null) : req.user.client_id;
  const isEnabled = enabled !== undefined ? enabled : true;
  const r = await pool.query("INSERT INTO triggers (name, expression, threshold, enabled, client_id) VALUES ($1,$2,$3,$4,$5) RETURNING *", [name, expression, threshold, isEnabled, cid]);
  res.status(201).json(r.rows[0]);
});

app.put("/triggers/:id", auth, async (req, res) => {
  const { name, expression, threshold, enabled } = req.body;
  const r = await pool.query(
    "UPDATE triggers SET name=$1, expression=$2, threshold=$3, enabled=$4 WHERE id=$5 RETURNING *",
    [name, expression, threshold, enabled !== false, req.params.id]
  );
  res.json(r.rows[0]);
});

app.delete("/triggers/:id", auth, async (req, res) => {
  await pool.query("DELETE FROM triggers WHERE id=$1", [req.params.id]);
  res.json({ ok: true });
});

app.get("/alerts", auth, async (req, res) => {
  const cid = clientFilter(req);
  let query = `
    SELECT a.*,
           d.name as device_name,
           d.mac_address,
           d.serial_number,
           d.description as device_description,
           d.location as device_location,
           c.name as client_name
    FROM alerts a
    LEFT JOIN devices d ON d.id = a.device_id
    LEFT JOIN clients c ON c.id = d.client_id
    WHERE a.fired_at > NOW() - interval '24 hours'
  `;
  const params = [];
  if (cid) { params.push(cid); query += ` AND a.client_id=$1`; }
  query += " ORDER BY a.fired_at DESC LIMIT 50";
  
  try {
    const r = await pool.query(query, params);
    // Format the response to match what the frontend expects
    const formattedAlerts = r.rows.map(row => ({
      ...row,
      time: row.fired_at,
      status: row.resolved_at ? 'resolved' : 'firing'
    }));
    res.json(formattedAlerts);
  } catch (err) {
    console.error("Error fetching alerts:", err);
    res.status(500).json({ error: "Failed to fetch alerts" });
  }
});

// ── PUSH UNIVERSAL (Recepcionista Cloud) ─────────────────────
app.post("/push", metricsLimiter, async (req, res) => {
  const start = Date.now();
  // Tenta pegar o token de várias formas (Header, Body, XML, ou Query)
  const body = req.body || {};
  const xmlData = body.eventnotificationalert || body.event || {};
  const latency = Date.now() - start;

  const token =
    req.headers["x-device-token"] ||
    body.token ||
    req.query.token ||
    body.SN ||
    body.SerialNumber ||
    xmlData.serialnumber ||
    body.MAC ||
    xmlData.macaddress ||
    req.query.sn ||
    req.query.serial ||
    req.query.mac;

  const { 
    status, cpu, memory, disk, 
    event_type, channel, description, severity,
    type,
    solar_v, batt_v, batt_p, charge_a, load_a // Campos para telemetria solar
  } = body;
  
  // Usa a latência enviada pela câmera ou calcula a do processamento
  const finalLatency = body.latency || latency;

  // Normalização de dados solares
  const solar_voltage = solar_v || body.solar_voltage || 0;
  const battery_voltage = batt_v || body.battery_voltage || 0;
  const battery_percent = batt_p || body.battery_percent || 0;
  const charge_current = charge_a || body.charge_current || 0;
  const load_current = load_a || body.load_current || 0;

  // Extração de eventos do XML (Intelbras/Hikvision)
  const rawEventType = event_type || type || xmlData.eventtype || xmlData.event;
  let finalEventType = rawEventType;
  const finalChannel = channel || xmlData.channelid || xmlData.channel || 0;
  let finalDescription = description || xmlData.eventdescription || xmlData.description || "";
  const source = String(req.headers["x-event-source"] || body.source || (Object.keys(xmlData || {}).length ? "isapi" : "push"));

  const payloadObj = { ...body };
  delete payloadObj.token;
  delete payloadObj.SN;
  delete payloadObj.SerialNumber;
  delete payloadObj.MAC;

  // Mapeamento de Analíticos de Vídeo (Intelbras/Hikvision)
  const eventMap = {
    'videoloss': 'Perda de Vídeo',
    'videoloss_alarm': 'Perda de Vídeo',
    'videoloss_started': 'Perda de Vídeo',
    'videoloss_stopped': 'Vídeo Recuperado',
    'motion': 'Movimento Detectado',
    'motion_detection': 'Movimento Detectado',
    'vca': 'Analítico de Vídeo',
    'linedetection': 'Linha Virtual Atravessada',
    'fielddetection': 'Intrusão em Área',
    'tamperdetection': 'Câmera Obstruída (Tamper)',
    'shelteralarm': 'Câmera Obstruída (Tamper)',
    'diskfull': 'HD Cheio',
    'diskerror': 'Erro no HD'
  };

  if (finalEventType && eventMap[finalEventType.toLowerCase()]) {
    finalDescription = `${eventMap[finalEventType.toLowerCase()]} - Canal: ${finalChannel}`;
    finalEventType = eventMap[finalEventType.toLowerCase()];
  } else if (finalEventType) {
    finalDescription = `${finalEventType} - Canal: ${finalChannel} ${finalDescription}`;
  }

  const isEdgeHeartbeat =
    (typeof rawEventType === "string" && rawEventType.toLowerCase() === "edge_heartbeat") ||
    (typeof finalEventType === "string" && finalEventType.toLowerCase() === "edge_heartbeat");

  if (!token) {
    console.log("[Push] Requisição sem identificador recebida");
    return res.status(401).json({ error: "Identification (Token/SN/MAC) required" });
  }

  try {
    const cleanToken = String(token).replace(/[:-]/g, "").toUpperCase();
    const dr = await pool.query(`
      SELECT
        d.id,
        d.client_id,
        d.name,
        c.telegram_token,
        c.telegram_chat_id,
        c.wa_instance,
        c.wa_token,
        c.wa_number
      FROM devices d
      LEFT JOIN clients c ON c.id = d.client_id
      WHERE (d.token=$1 OR d.serial_number = $1 OR UPPER(REPLACE(REPLACE(d.mac_address, ':', ''), '-', '')) = $2)
        AND ($3::int IS NULL OR d.client_id = $3)
      LIMIT 1
    `, [token, cleanToken, body.client_id || req.query.client_id || null]);

    if (dr.rows.length === 0) {
    console.log(`[Push] Token/MAC/SN não encontrado: ${maskTokenLike(token)}`);
      return res.status(401).json({ error: "Invalid identification" });
    }
    const dev = dr.rows[0];

    console.log(`[Push] SINAL DE VIDA: ${dev.name} (${maskTokenLike(token)})`);

    // 1. Atualizar Sinal de Vida (Heartbeat)
    // Atualizamos o last_seen e o status para online imediatamente para o Dashboard
    await pool.query("UPDATE devices SET last_seen=NOW(), status='online' WHERE id=$1", [dev.id]);
    
    // Garante que o host existe na tabela hosts e pega o id
    const hr = await pool.query("INSERT INTO hosts (name) VALUES ($1) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id", [dev.name]);
    const hostId = hr.rows[0].id;

    // Grava métrica de latência e solar
    await pool.query(`
      INSERT INTO metrics (time, host_id, host, device_id, latency_ms, status, solar_voltage, battery_voltage, battery_percent, charge_current, load_current)
      VALUES (NOW(), $1, $2, $3, $4, 'online', $5, $6, $7, $8, $9)
    `, [hostId, dev.name, dev.id, finalLatency, solar_voltage, battery_voltage, battery_percent, charge_current, load_current]);

    // 2. Registrar Eventos
    if (finalEventType && !isEdgeHeartbeat) {
      await pool.query(`
        INSERT INTO events (device_id, event_type, channel, description, severity, source, raw_event_type, payload)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
      `, [dev.id, finalEventType, finalChannel, finalDescription, severity || "info", source, rawEventType || "", JSON.stringify(payloadObj || {})]);
      
      console.log(`[Push] Evento: ${finalEventType} em ${dev.name}`);

      // ── Alertas (Centralizados no Processor) ──
      // O Processor (Python) monitora a tabela 'events' e envia para Telegram/WhatsApp
      // garantindo fuso horário correto e formatação padronizada.
      _sendInstantAnalyticsAlerts(dev, finalEventType, finalChannel, finalDescription).catch(() => {});
    } else if (finalEventType && isEdgeHeartbeat) {
      console.log(`[Push] Ignorando edge_heartbeat como evento (apenas métrica): ${dev.name}`);
    }

    // 3. WebSocket (Realtime)
    if (WEBSOCKET_URL) {
      // Broadcast para o dashboard saber que o dispositivo está online
      fetch(`${WEBSOCKET_URL.replace(/\/$/, "")}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "METRIC",
          device_id: dev.id,
          client_id: dev.client_id,
          status: "online",
          time: new Date().toISOString()
        }),
      }).catch(() => {});
    }

    res.json({ ok: true });
  } catch (e) {
    console.error("[Push Error]:", e.message);
    res.status(500).json({ error: e.message });
  }
});

app.get("/events", auth, async (req, res) => {
  try {
    const cid = clientFilter(req);
    let query = `
      SELECT e.*, d.name as device_name, c.name as client_name
      FROM events e
      JOIN devices d ON d.id = e.device_id
      JOIN clients c ON c.id = d.client_id
      WHERE 1=1
    `;
    const params = [];
    if (cid) { params.push(cid); query += ` AND d.client_id=$1`; }
    query += " ORDER BY e.time DESC LIMIT 100";
    const r = await pool.query(query, params);
    res.json(r.rows);
  } catch (e) { res.status(500).json({ error: e.message }); }
});

app.get("/events/:id/snapshot", auth, async (req, res) => {
  const id = parseInt(req.params.id);
  if (!id) return res.status(400).json({ error: "Invalid id" });
  const r = await pool.query(
    `
    SELECT e.payload, d.client_id
    FROM events e
    JOIN devices d ON d.id = e.device_id
    WHERE e.id=$1
    `,
    [id]
  );
  if (r.rows.length === 0) return res.status(404).json({ error: "Not found" });
  const row = r.rows[0];
  if (req.user.role !== "superadmin" && row.client_id !== req.user.client_id) {
    return res.status(403).json({ error: "Forbidden" });
  }
  const payload = row.payload || {};
  const snapshot = payload.snapshot || {};
  const snapPath = snapshot.path ? String(snapshot.path) : "";
  const safeBase = path.join(__dirname, "uploads", "snapshots");
  if (!snapPath || !snapPath.startsWith(safeBase)) return res.status(404).json({ error: "Snapshot not available" });
  if (!fs.existsSync(snapPath)) return res.status(404).json({ error: "Snapshot not found" });
  const buf = fs.readFileSync(snapPath);
  const img = detectImageExt(buf, snapshot.mime || "");
  res.setHeader("Content-Type", img.mime);
  res.setHeader("Cache-Control", "no-store");
  res.end(buf);
});

app.post("/metrics", metricsLimiter, async (req, res) => {
  const token = req.headers["x-device-token"] || req.body.device_token;
  const { host, cpu, memory, latency_ms, status, disk_percent, uptime_seconds, load_avg, processes, temperature } = req.body;
  try {
    const dr = await pool.query("SELECT id, client_id FROM devices WHERE token=$1", [token]);
    if (dr.rows.length === 0) return res.status(401).json({ error: "Invalid token" });
    const devId = dr.rows[0].id;
    const cid = dr.rows[0].client_id;
    // Deixamos o processor atualizar o status para 'online' e enviar o alerta
    await pool.query("UPDATE devices SET last_seen=NOW() WHERE id=$1", [devId]);
    const hr = await pool.query("INSERT INTO hosts (name) VALUES ($1) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id", [host]);
    const hostId = hr.rows[0].id;
    
    await pool.query(`
      INSERT INTO metrics (
        time, host_id, host, device_id, cpu, memory, disk_percent, 
        latency_ms, status, uptime_seconds, load_avg, processes, temperature
      ) VALUES (NOW(), $1, $2, $3, $4, $5, $6, $7, 'online', $8, $9, $10, $11)
    `, [
      hostId, host, devId, cpu||0, memory||0, disk_percent||0, 
      latency_ms||0, uptime_seconds||0, load_avg||0, processes||0, temperature||0
    ]);
    
    // Publish to WebSocket
    if (WEBSOCKET_URL) {
      const wsPublishUrl = `${WEBSOCKET_URL.replace(/\/$/, "")}/publish`;
      fetch(wsPublishUrl, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          host, cpu, memory, disk_percent, latency_ms, uptime_seconds, 
          load_avg, processes, temperature, device_id: devId, client_id: cid, 
          time: new Date().toISOString() 
        }),
      }).catch(() => {});
    }

    res.status(201).json({ ok: true });
  } catch (e) { res.status(500).json({ error: e.message }); }
});

// ── Utils ────────────────────────────────────────────────────
app.get("/stats", auth, async (req, res) => {
  const cid = clientFilter(req);
  const loc = sanitize(req.query.location || "");
  
  let filter = cid ? `WHERE client_id=${cid}` : "";
  if (loc) {
    filter += (filter ? " AND " : " WHERE ") + `location = '${loc}'`;
  }

  try {
    const total = await pool.query(`SELECT COUNT(*) FROM devices ${filter}`);
    const online = await pool.query(`SELECT COUNT(*) FROM devices ${filter ? (filter + " AND") : "WHERE"} status='online'`);
    const clients = await pool.query("SELECT COUNT(*) FROM clients");
    
    // Tenta pegar o IP do Gateway (primeiro roteador/routerboard do ponto)
    const gateway = await pool.query(`SELECT ip_address FROM devices ${filter ? (filter + " AND") : "WHERE"} device_type IN ('router', 'routerboard') LIMIT 1`);
    
    const totalCount = parseInt(total.rows[0].count);
    const onlineCount = parseInt(online.rows[0].count);
    
    res.json({ 
      devices: totalCount, 
      online: onlineCount, 
      offline: totalCount - onlineCount, 
      clients: parseInt(clients.rows[0].count),
      gateway_ip: gateway.rows[0]?.ip_address || "127.0.0.1"
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/speedtest/run", auth, async (req, res) => {
  const cid = req.user.role === "superadmin" ? (req.body.client_id || null) : req.user.client_id;
  
  try {
    if (WEBSOCKET_URL) {
      // Envia comando via WebSocket para o agente que está ouvindo
      fetch(`${WEBSOCKET_URL.replace(/\/$/, "")}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "COMMAND",
          action: "RUN_SPEEDTEST",
          client_id: cid
        }),
      }).catch(() => {});
    }
    res.json({ ok: true, message: "Comando enviado ao agente" });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get("/locations", auth, async (req, res) => {
  const cid = clientFilter(req);
  if (!cid) return res.json([]);
  try {
    const r = await pool.query("SELECT DISTINCT location FROM devices WHERE client_id=$1 AND location IS NOT NULL AND location != '' ORDER BY location", [cid]);
    res.json(r.rows.map(x => x.location));
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/speedtest", auth, async (req, res) => {
  const { download, upload, ping, client_id } = req.body;
  const cid = req.user.role === "superadmin" ? (client_id || null) : req.user.client_id;
  
  try {
    // Salva o teste no banco para histórico
    await pool.query(
      "INSERT INTO speedtests (client_id, download, upload, ping, time) VALUES ($1, $2, $3, $4, NOW())",
      [cid, download, upload, ping]
    );
    
    // Notifica o WebSocket para atualizar a tela do dashboard instantaneamente
    if (WEBSOCKET_URL) {
      fetch(`${WEBSOCKET_URL.replace(/\/$/, "")}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "SPEEDTEST",
          client_id: cid,
          download,
          upload,
          ping,
          time: new Date().toISOString()
        }),
      }).catch(() => {});
    }
    
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get("/tags", auth, async (req, res) => {
  const r = await pool.query("SELECT DISTINCT unnest(tags) as tag FROM devices");
  res.json(r.rows.map(x => x.tag));
});

app.get("/device-types", auth, (req, res) => res.json([
  { value: "server", label: "Servidor", icon: "🖥️" },
  { value: "camera", label: "Câmera IP", icon: "📷" },
  { value: "router", label: "Roteador", icon: "🌐" },
  { value: "switch", label: "Switch", icon: "🔀" },
  { value: "other", label: "Outro", icon: "📦" }
]));

// ── Cloud Monitor Logic (SSTP/VPN/Subnet Support) ────────────
async function cloudMonitor(deviceId = null) {
  try {
    const query = deviceId ? 
      ["SELECT * FROM devices WHERE id=$1", [deviceId]] : 
      ["SELECT * FROM devices WHERE (ddns_address != '' AND monitor_port > 0) OR (ip_address != '' AND monitor_port > 0)", []];
    
    const r = await pool.query(...query);
    
    for (const dev of r.rows) {
      const start = Date.now();
      const targetHost = dev.ddns_address || dev.ip_address;
      if (!targetHost || !dev.monitor_port) continue;

      const isPrivate = targetHost.startsWith("192.168.") || targetHost.startsWith("10.") || targetHost.startsWith("172.");
      
      // Se for IP privado e não tiver DDNS, o servidor cloud não consegue alcançar.
      // Ignora para não gerar status 'offline' indevido.
      if (isPrivate && !dev.ddns_address) continue;

      const updateStatus = async (status, latency = 0, error = null) => {
        const notePrefix = isPrivate ? "🛡️ VPN " : "☁️ Cloud ";
        const lastSeenUpdate = status === "online" ? ", last_seen=NOW()" : "";
        await pool.query(`UPDATE devices SET status=$1${lastSeenUpdate}, notes=$2 WHERE id=$3`, [status, error ? `${notePrefix}Error: ${error}` : `${notePrefix}OK`, dev.id]);
        
        // Garante que o host existe na tabela hosts e pega o id
        const hr = await pool.query("INSERT INTO hosts (name) VALUES ($1) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id", [targetHost]);
        const hostId = hr.rows[0].id;

        await pool.query(`
          INSERT INTO metrics (time, host_id, host, device_id, latency_ms, status) 
          VALUES (NOW(), $1, $2, $3, $4, $5)
        `, [hostId, targetHost, dev.id, latency, status]);
        
        if (WEBSOCKET_URL) {
          fetch(`${WEBSOCKET_URL}/publish`, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ host: targetHost, latency_ms: latency, status, device_id: dev.id, client_id: dev.client_id, time: new Date().toISOString() }),
          }).catch(() => {});
        }
      };

      if (false) { // VPN desativada temporariamente para estabilidade
      } else {
        // Conexão direta (DDNS ou IP Público)
        const socket = new net.Socket();
        socket.setTimeout(8000);
        socket.on("connect", () => { socket.destroy(); updateStatus("online", Date.now() - start); });
        socket.on("timeout", () => { socket.destroy(); updateStatus("offline", 0, "Timeout"); });
        socket.on("error", (err) => { socket.destroy(); updateStatus("offline", 0, err.code); });
        socket.connect(dev.monitor_port, targetHost);
      }
    }
  } catch (e) { console.error("Cloud Monitor Error:", e.message); }
}
// O CloudMonitor foi desativado aqui pois o Processor (Python) já faz essa checagem de forma mais eficiente e com alertas centralizados.
// setInterval(cloudMonitor, 60000);

const PORT = process.env.PORT || 3000;
const TCP_PORT = process.env.TCP_PORT || 3002; // Porta para o Registro Automático da Intelbras (Alterada de 3001 para 3002 para evitar conflito com WebSocket)

// ── Servidor TCP para Registro Automático (Protocolo Binário Intelbras) ──
const tcpServer = net.createServer((socket) => {
  console.log(`[TCP] Nova conexão recebida`);

  socket.on("data", async (data) => {
    try {
      // Converte o buffer em string para procurar o Serial Number
      const rawData = data.toString("utf8");
      const hexData = data.toString("hex").toUpperCase();
      
      console.log(`[TCP] Dados recebidos: ${rawData.substring(0, 50)}...`);

      // Busca no banco por qualquer dispositivo que tenha o SN presente nos dados binários
      // O protocolo da Intelbras envia o SN em texto plano em algum momento
      const devicesRes = await pool.query("SELECT id, name, serial_number, mac_address, client_id, status FROM devices");
      
      for (const dev of devicesRes.rows) {
        const cleanMac = dev.mac_address ? dev.mac_address.replace(/[:-]/g, "").toUpperCase() : null;
        
        if ((dev.serial_number && rawData.includes(dev.serial_number)) || (cleanMac && hexData.includes(cleanMac))) {
          
          console.log(`[TCP] SINAL DE VIDA: ${dev.name} (${dev.serial_number || dev.mac_address})`);
          
          // Atualiza sinal de vida (last_seen) e status para online imediatamente
          await pool.query("UPDATE devices SET last_seen=NOW(), status='online' WHERE id=$1", [dev.id]);
          
          // Garante que o host existe na tabela hosts e pega o id
          const hr = await pool.query("INSERT INTO hosts (name) VALUES ($1) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING id", [dev.name]);
          const hostId = hr.rows[0].id;

          // Grava métrica de sinal de vida (latência fictícia baixa para TCP direto)
          // O Processor usa a tabela metrics e last_seen para decidir o status
          await pool.query(`
            INSERT INTO metrics (time, host_id, host, device_id, latency_ms, status)
            VALUES (NOW(), $1, $2, $3, $4, 'online')
          `, [hostId, dev.name, dev.id, 1]);

          // Notifica WebSocket (Dashboard real-time)
          if (WEBSOCKET_URL) {
            fetch(`${WEBSOCKET_URL.replace(/\/$/, "")}/publish`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                type: "METRIC",
                device_id: dev.id,
                client_id: dev.client_id,
                name: dev.name,
                status: "online",
                latency_ms: 1,
                time: new Date().toISOString()
              }),
            }).catch(() => {});
          }
          break; 
        }
      }
    } catch (err) {
      console.error("[TCP Error]:", err.message);
    }
  });

  socket.on("error", (err) => console.error(`[TCP Socket Error]: ${err.message}`));
  socket.setTimeout(120000); // 2 minutos de timeout
  socket.on("timeout", () => socket.end());
});

tcpServer.listen(TCP_PORT, "0.0.0.0", () => {
  console.log(`=========================================`);
  console.log(`📡 TCP Proxy Online na Porta: ${TCP_PORT}`);
  console.log(`=========================================`);
});

// O MONITORAMENTO DE QUEDA E RETORNO FOI CENTRALIZADO NO PROCESSOR (PYTHON)
// PARA EVITAR DUPLICIDADE DE ALERTAS E GARANTIR FORMATAÇÃO PADRONIZADA.

app.listen(PORT, "0.0.0.0", () => {
  console.log(`=========================================`);
  console.log(`🚀 ETI SENTINEL API Online na Porta: ${PORT}`);
  console.log(`=========================================`);
});

if (hasFrontend) {
  app.get("*", (req, res, next) => {
    if (req.method !== "GET") return next();
    res.sendFile(frontendIndex);
  });
}

// Middleware 404 movido para o final de tudo
app.use((req, res) => res.status(404).json({ error: "Route not found" }));
