import os, time, logging, requests, datetime, hashlib, json, re
from contextlib import contextmanager
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

APP_NAME     = "ETI SENTINEL Solar"
DATABASE_URL = os.environ["DATABASE_URL"]
TG_TOKEN     = os.getenv("TELEGRAM_TOKEN", "")
TG_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
SOLAR_INTERVAL = int(os.getenv("SOLAR_INTERVAL", "60"))  # coleta a cada 60s
ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", "3600")) # alerta a cada 1h

def sanitize(val): return re.sub(r'["\'`\s]', '', val) if val else ""

TWILIO_ACCOUNT_SID = sanitize(os.getenv("TWILIO_ACCOUNT_SID", ""))
TWILIO_AUTH_TOKEN = sanitize(os.getenv("TWILIO_AUTH_TOKEN", ""))
TWILIO_WHATSAPP_NUMBER = sanitize(os.getenv("TWILIO_WHATSAPP_NUMBER", ""))
TWILIO_CONTENT_SID = sanitize(os.getenv("TWILIO_CONTENT_SID", ""))

WA_INSTANCE = sanitize(os.getenv("WA_INSTANCE", ""))
WA_TOKEN    = sanitize(os.getenv("WA_TOKEN", ""))
WA_NUMBER   = sanitize(os.getenv("WA_NUMBER", ""))

alert_cooldown_map = {}
inverter_state     = {}  # id -> ultimo status

def now_str(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def escape_html(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def is_daytime():
    h = datetime.datetime.now().hour
    return 6 <= h <= 20

@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try: yield conn
    finally: conn.close()

def is_in_cooldown(key):
    return (time.time() - alert_cooldown_map.get(key, 0)) < ALERT_COOLDOWN

def set_cooldown(key):
    alert_cooldown_map[key] = time.time()

# ── Telegram ─────────────────────────────────────────────────
def send_telegram(message, token=None, chat_id=None):
    targets = []
    if token and chat_id: targets.append((str(token).strip(), str(chat_id).strip()))
    if TG_TOKEN and TG_CHAT_ID: targets.append((str(TG_TOKEN).strip(), str(TG_CHAT_ID).strip()))
    
    for tok, cid in set(targets):
        try:
            # Garante que o token não tenha o prefixo 'bot' duplicado
            clean_tok = tok.replace("bot", "") if tok.startswith("bot") else tok
            url = f"https://api.telegram.org/bot{clean_tok}/sendMessage"
            
            payload = {"chat_id": cid, "text": message, "parse_mode": "HTML"}
            r = requests.post(url, json=payload, timeout=15)
            
            if r.status_code == 200:
                logger.info(f"Telegram ✓ solar -> {cid}")
            else:
                logger.error(f"Telegram erro {r.status_code} para {cid}: {r.text}")
                # Fallback para texto puro se HTML falhar
                if "can't parse entities" in r.text.lower():
                    payload.pop("parse_mode")
                    requests.post(url, json=payload, timeout=15)
                    logger.info(f"Telegram ✓ solar fallback -> {cid}")
        except Exception as e: logger.error(f"Telegram: {e}")

def send_whatsapp(message, instance=None, token=None, number=None):
    account_sid = sanitize(instance) or TWILIO_ACCOUNT_SID or WA_INSTANCE
    auth_token = sanitize(token) or TWILIO_AUTH_TOKEN or WA_TOKEN
    num = sanitize(number) or WA_NUMBER
    if not account_sid or not auth_token or not num:
        return

    try:
        auth = (account_sid, auth_token)
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

        dest_num = num if num.startswith("+") else f"+{num}"
        if not dest_num.startswith("whatsapp:"):
            dest_num = f"whatsapp:{dest_num}"

        sender_num = TWILIO_WHATSAPP_NUMBER or os.getenv("TWILIO_WHATSAPP_NUMBER", "") or "whatsapp:+14155238886"

        payload = {"To": dest_num, "From": sender_num}
        content_sid = TWILIO_CONTENT_SID or os.getenv("TWILIO_CONTENT_SID", "")
        if content_sid:
            payload["ContentSid"] = content_sid
            payload["ContentVariables"] = json.dumps({"1": message[:1500]}, ensure_ascii=False)
        else:
            payload["Body"] = message

        r = requests.post(url, data=payload, auth=auth, timeout=15)
        if r.status_code in [200, 201]:
            logger.info(f"WhatsApp (Twilio) ✓ solar -> {dest_num}")
        else:
            logger.error(f"WhatsApp (Twilio) error ({r.status_code}): {r.text}")
    except Exception as e:
        logger.error(f"WhatsApp (Twilio) exception: {e}")

def get_client_config(cur, client_id):
    if not client_id: return None, None, None, None, None
    try:
        cur.execute("SELECT telegram_token, telegram_chat_id, wa_instance, wa_token, wa_number FROM clients WHERE id=%s", (client_id,))
        row = cur.fetchone()
        if row: return row[0], row[1], row[2], row[3], row[4]
    except: pass
    return None, None, None, None, None

# ── Salvar métrica ────────────────────────────────────────────
def save_metric(cur, conn, inv, data):
    tariff = float(inv.get("tariff_kwh") or 0.85)
    energy_today = data.get("energy_today_kwh", 0) or 0
    energy_month = data.get("energy_month_kwh", 0) or 0
    energy_total = data.get("energy_total_kwh", 0) or 0

    revenue_today = energy_today * tariff
    revenue_month = energy_month * tariff
    revenue_total = energy_total * tariff

    try:
        cur.execute("""
            INSERT INTO solar_metrics (time, inverter_id, client_id,
                power_w, energy_today_kwh, energy_month_kwh, energy_total_kwh,
                voltage_pv, voltage_ac, current_ac, frequency_hz, temperature_c,
                revenue_today, revenue_month, revenue_total,
                inverter_status, fault_code, last_update)
            VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            inv["id"], inv.get("client_id"),
            data.get("power_w", 0), energy_today, energy_month, energy_total,
            data.get("voltage_pv", 0), data.get("voltage_ac", 0),
            data.get("current_ac", 0), data.get("frequency_hz", 50),
            data.get("temperature_c", 0),
            revenue_today, revenue_month, revenue_total,
            data.get("status", "unknown"), data.get("fault_code", ""),
        ))
        conn.commit()
        logger.info(f"☀️ {inv['name']}: {data.get('power_w',0):.0f}W | "
                    f"{energy_today:.2f}kWh hoje | R${revenue_today:.2f}")
    except Exception as e:
        logger.error(f"Save solar metric: {e}")
        conn.rollback()

# ── Verificar alertas ─────────────────────────────────────────
def check_solar_alerts(cur, inv, data, tg_tok, tg_cid, wa_inst, wa_tok, wa_num):
    inv_id   = inv["id"]
    inv_name = inv["name"]
    status   = data.get("status", "unknown")
    power    = data.get("power_w", 0) or 0
    energy   = data.get("energy_today_kwh", 0) or 0
    tariff   = float(inv.get("tariff_kwh") or 0.85)
    capacity = float(inv.get("capacity_kwp") or 0)
    prev_status = inverter_state.get(inv_id, "unknown")

    # Alerta: inversor parou de geração (durante o dia)
    if is_daytime() and status in ("offline","fault","idle") and prev_status == "generating":
        key = f"solar_offline_{inv_id}"
        if not is_in_cooldown(key):
            set_cooldown(key)
            einv_name = escape_html(inv_name)
            elocation = escape_html(inv.get('location','—'))
            msg = (f"❌ <b>{einv_name}</b>\n"
                   f"Problema: Inversor solar parou de gerar energia\n"
                   f"Host: {einv_name}\n"
                   f"Data do Evento: {now_str()}\n"
                   f"Local: {elocation}\n"
                   f"Status: {status.upper()}\n"
                   f"Indicação: Verifique o inversor e a conexão com a rede.")
            send_telegram(msg, tg_tok, tg_cid)
            send_whatsapp(msg.replace("<b>", "*").replace("</b>", "*"), wa_inst, wa_tok, wa_num)
            logger.warning(f"SOLAR OFFLINE: {inv_name}")

    # Alerta: inversor voltou a gerar
    if status == "generating" and prev_status in ("offline","fault","idle","unknown"):
        if prev_status != "unknown":
            einv_name = escape_html(inv_name)
            elocation = escape_html(inv.get('location','—'))
            msg = (f"✅ <b>{einv_name}</b>\n"
                   f"Normalizado: Inversor voltou a gerar energia\n"
                   f"Host: {einv_name}\n"
                   f"Data da Normalização: {now_str()}\n"
                   f"Local: {elocation}\n"
                   f"Potência atual: {power:.0f}W")
            send_telegram(msg, tg_tok, tg_cid)
            send_whatsapp(msg.replace("<b>", "*").replace("</b>", "*"), wa_inst, wa_tok, wa_num)

    inverter_state[inv_id] = status

    # Resumo diário (uma vez por dia às 18h)
    now = datetime.datetime.now()
    if now.hour == 18 and now.minute < 1:
        key = f"solar_daily_{inv_id}_{now.date()}"
        if not is_in_cooldown(key):
            set_cooldown(key)
            revenue = energy * tariff
            performance = ""
            if capacity > 0:
                expected = capacity * 4.5  # média 4.5h sol
                pct = (energy / expected * 100) if expected > 0 else 0
                performance = f"\n📈 Performance: <b>{pct:.0f}%</b> do esperado"

            einv_name = escape_html(inv_name)
            elocation = escape_html(inv.get('location','—'))
            msg = (f"☀️ <b>RELATÓRIO SOLAR DIÁRIO — {APP_NAME}</b>\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n"
                   f"🔆 Inversor: <b>{einv_name}</b>\n"
                   f"📍 Local: <b>{elocation}</b>\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n"
                   f"⚡ Energia hoje: <b>{energy:.2f} kWh</b>\n"
                   f"💰 Receita hoje: <b>R$ {revenue:.2f}</b>\n"
                   f"📊 Total gerado: <b>{data.get('energy_total_kwh',0):.1f} kWh</b>\n"
                   f"💵 Receita total: <b>R$ {data.get('energy_total_kwh',0)*tariff:.2f}</b>"
                   f"{performance}\n"
                   f"━━━━━━━━━━━━━━━━━━━━\n"
                   f"🕐 {now_str()} #solar #etisentinel")
            send_telegram(msg, tg_tok, tg_cid)
            send_whatsapp(msg.replace("<b>", "*").replace("</b>", "*"), wa_inst, wa_tok, wa_num)

# ════════════════════════════════════════════════════════════
#  COLETORES POR MARCA
# ════════════════════════════════════════════════════════════

# ── GROWATT ──────────────────────────────────────────────────
def collect_growatt(inv):
    """Coleta dados do Growatt via ShineServer API"""
    try:
        user = inv.get("growatt_user","")
        pwd  = inv.get("growatt_pass","")
        if not user or not pwd: return None

        session = requests.Session()
        # Login
        r = session.post("https://server.growatt.com/login",
            data={"account": user, "password": hashlib.md5(pwd.encode()).hexdigest()},
            timeout=15)
        if r.status_code != 200: return None

        # Listar plantas
        plant_id = inv.get("growatt_plant_id","")
        if not plant_id:
            r2 = session.post("https://server.growatt.com/index/getPlantListTitle", timeout=10)
            plants = r2.json().get("data", [])
            if plants: plant_id = plants[0].get("id","")

        if not plant_id: return None

        # Dados da planta
        r3 = session.post(f"https://server.growatt.com/panel/getDevicesByPlantList",
            data={"plantId": plant_id, "currPage": 1}, timeout=10)
        d = r3.json()

        # Dados de energia hoje
        r4 = session.post("https://server.growatt.com/panel/plant/getPlantData",
            data={"plantId": plant_id}, timeout=10)
        pd = r4.json().get("data", {})

        power_w       = float(pd.get("currentPower","0").replace("kW","").strip() or 0) * 1000
        energy_today  = float(pd.get("todayEnergy","0").replace("kWh","").strip() or 0)
        energy_total  = float(pd.get("totalEnergy","0").replace("kWh","").strip() or 0)
        energy_month  = float(pd.get("monthEnergy","0").replace("kWh","").strip() or 0)

        status = "generating" if power_w > 0 else ("idle" if is_daytime() else "offline")

        return {
            "power_w": power_w,
            "energy_today_kwh": energy_today,
            "energy_month_kwh": energy_month,
            "energy_total_kwh": energy_total,
            "status": status,
        }
    except Exception as e:
        logger.error(f"Growatt error [{inv['name']}]: {e}")
        return None

# ── FRONIUS (API local) ───────────────────────────────────────
def collect_fronius(inv):
    """Coleta dados Fronius via Solar API local"""
    try:
        ip = inv.get("fronius_ip","")
        if not ip: return None
        dev_id = inv.get("fronius_device_id", 1)

        base = f"http://{ip}/solar_api/v1"

        # Potência atual
        r = requests.get(f"{base}/GetInverterRealtimeData.cgi?Scope=Device&DeviceId={dev_id}&DataCollection=CommonInverterData", timeout=10)
        d = r.json().get("Body",{}).get("Data",{})

        power_w      = d.get("PAC",{}).get("Value", 0) or 0
        energy_today = (d.get("DAY_ENERGY",{}).get("Value", 0) or 0) / 1000
        energy_total = (d.get("TOTAL_ENERGY",{}).get("Value", 0) or 0) / 1000
        energy_year  = (d.get("YEAR_ENERGY",{}).get("Value", 0) or 0) / 1000
        voltage_ac   = d.get("UAC",{}).get("Value", 0) or 0
        current_ac   = d.get("IAC",{}).get("Value", 0) or 0
        freq         = d.get("FAC",{}).get("Value", 50) or 50
        temp         = d.get("DeviceStatus",{}).get("StatusCode", 0)
        voltage_pv   = d.get("UDC",{}).get("Value", 0) or 0

        status_code = d.get("DeviceStatus",{}).get("StatusCode", 0)
        if power_w > 0: status = "generating"
        elif status_code == 7: status = "idle"
        elif status_code in (1,2,3): status = "fault"
        else: status = "offline" if is_daytime() else "idle"

        return {
            "power_w": power_w,
            "energy_today_kwh": energy_today,
            "energy_month_kwh": energy_year / 12,
            "energy_total_kwh": energy_total,
            "voltage_pv": voltage_pv,
            "voltage_ac": voltage_ac,
            "current_ac": current_ac,
            "frequency_hz": freq,
            "status": status,
        }
    except Exception as e:
        logger.error(f"Fronius error [{inv['name']}]: {e}")
        return None

# ── DEYE / SOLIS (SolarmanPV) ─────────────────────────────────
def collect_deye(inv):
    """Coleta dados Deye/Solis via SolarmanPV API"""
    try:
        token   = inv.get("solarman_token","")
        app_id  = inv.get("solarman_app_id","")
        logger_sn = inv.get("solarman_logger_sn","")
        if not token or not logger_sn: return None

        url = "https://globalapi.solarmanpv.com/device/v1.0/currentData"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        body = {"appId": app_id, "deviceSn": logger_sn}

        r = requests.post(url, json=body, headers=headers, timeout=15)
        d = r.json()

        if d.get("code") != "0": return None

        data_list = d.get("dataList", [])
        vals = {item["key"]: item.get("value", "0") for item in data_list}

        power_w      = float(vals.get("generationPower", vals.get("AC_ActivePower","0")) or 0)
        energy_today = float(vals.get("generationToday", vals.get("dailyProduction","0")) or 0)
        energy_total = float(vals.get("generationTotal", vals.get("totalProduction","0")) or 0)
        energy_month = float(vals.get("generationMonth","0") or 0)
        temp         = float(vals.get("temperature","0") or 0)
        voltage_ac   = float(vals.get("AC_Voltage_R", vals.get("gridVoltage","0")) or 0)

        status = "generating" if power_w > 0 else ("idle" if is_daytime() else "offline")

        return {
            "power_w": power_w,
            "energy_today_kwh": energy_today,
            "energy_month_kwh": energy_month,
            "energy_total_kwh": energy_total,
            "voltage_ac": voltage_ac,
            "temperature_c": temp,
            "status": status,
        }
    except Exception as e:
        logger.error(f"Deye error [{inv['name']}]: {e}")
        return None

# ── SMA ──────────────────────────────────────────────────────
def collect_sma(inv):
    """Coleta dados SMA via Sunny Portal API"""
    try:
        ip = inv.get("api_url","")
        if not ip: return None

        # SMA Sunny Boy / Tripower — API local via JSON
        r = requests.get(f"http://{ip}/dyn/getDashValues.json", timeout=10)
        d = r.json()

        result = d.get("result",{})
        power_w = 0
        energy_today = 0
        energy_total = 0

        for key, val in result.items():
            if isinstance(val, dict):
                for k2, v2 in val.items():
                    if isinstance(v2, dict):
                        v = v2.get("val", 0) or 0
                        if "6100_40263F00" in k2: power_w = float(v)
                        if "6400_00262200" in k2: energy_today = float(v) / 1000
                        if "6400_00260100" in k2: energy_total = float(v) / 1000

        status = "generating" if power_w > 0 else ("idle" if is_daytime() else "offline")
        return {
            "power_w": power_w,
            "energy_today_kwh": energy_today,
            "energy_total_kwh": energy_total,
            "status": status,
        }
    except Exception as e:
        logger.error(f"SMA error [{inv['name']}]: {e}")
        return None

# ── GOODWE (SEMS Portal) ──────────────────────────────────────
def collect_goodwe(inv):
    """Coleta dados GoodWe via SEMS Portal"""
    try:
        user     = inv.get("goodwe_user","")
        pwd      = inv.get("goodwe_pass","")
        plant_id = inv.get("saj_plant_id", inv.get("goodwe_station_id",""))
        if not user or not pwd: return None

        session = requests.Session()
        # Login SEMS
        r = session.post("https://www.semsportal.com/api/v1/Common/CrossLogin",
            json={"account": user, "pwd": hashlib.md5(pwd.encode()).hexdigest(),
                  "langCode": "pt-br", "client": "web", "version": ""},
            headers={"Content-Type": "application/json", "Token": '{"version":"","client":"web","language":"pt-br"}'},
            timeout=15)
        d = r.json()
        if d.get("msg") != "success": return None

        token = json.dumps(d.get("data",{}).get("token",""))

        # Dados da planta
        r2 = session.post("https://www.semsportal.com/api/v1/PowerStation/GetMonitorDetailByPowerstationId",
            json={"powerStationId": plant_id},
            headers={"Token": token},
            timeout=15)
        pd = r2.json().get("data",{}).get("kpi",{})

        power_w      = float(pd.get("pac", 0) or 0) * 1000
        energy_today = float(pd.get("power", 0) or 0)
        energy_total = float(pd.get("total_power", 0) or 0)
        energy_month = float(pd.get("month_generation", 0) or 0)

        status = "generating" if power_w > 0 else ("idle" if is_daytime() else "offline")
        return {
            "power_w": power_w,
            "energy_today_kwh": energy_today,
            "energy_month_kwh": energy_month,
            "energy_total_kwh": energy_total,
            "status": status,
        }
    except Exception as e:
        logger.error(f"GoodWe error [{inv['name']}]: {e}")
        return None

# ── HUAWEI (FusionSolar) ──────────────────────────────────────
def collect_huawei(inv):
    """Coleta dados Huawei via FusionSolar — suporte a API Northbound e Web-Scraping Fallback"""
    try:
        user = inv.get("huawei_user", "")
        pwd  = inv.get("huawei_pass", "")
        station_id = str(inv.get("huawei_station_id", "")).replace("NE=", "").strip()
        
        if not user or not pwd or not station_id: 
            logger.error(f"Huawei [{inv['name']}]: Credenciais incompletas.")
            return None

        REGIONS = [
            "https://intl.fusionsolar.huawei.com",
            "https://la5.fusionsolar.huawei.com",
            "https://region01eu5.fusionsolar.huawei.com"
        ]

        for BASE in REGIONS:
            logger.info(f"Tentando Huawei em {BASE} para {inv['name']}...")
            try:
                session = requests.Session()
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Content-Type": "application/json"
                })

                # Tentativa 1: API Northbound (Mais estável se ativa)
                login_payload = {"userName": user, "systemCode": pwd}
                r = session.post(f"{BASE}/rest/openapi/login", json=login_payload, timeout=20)
                
                if r.status_code == 200:
                    login_data = r.json()
                    token = login_data.get("data")
                    if token:
                        session.headers.update({"XSRF-TOKEN": token})
                        # stationCodes deve ser uma string com IDs separados por vírgula
                        r2 = session.post(f"{BASE}/rest/openapi/pvms/v1/station/get-station-real-kpi", 
                                         json={"stationCodes": str(station_id)}, timeout=20)
                        
                        if r2.status_code == 200:
                            data_list = r2.json().get("data", [])
                            if data_list:
                                flow = data_list[0]
                                return {
                                    "power_w": float(flow.get("activePower", 0) or 0) * 1000,
                                    "energy_today_kwh": float(flow.get("dayPower", 0) or 0),
                                    "energy_total_kwh": float(flow.get("totalPower", 0) or 0),
                                    "status": "generating" if float(flow.get("activePower", 0) or 0) > 0 else "idle"
                                }
                        else:
                            logger.error(f"Huawei Northbound Error {r2.status_code}: {r2.text}")

                # Tentativa 2: Web Login (Fallback)
                logger.info(f"Tentando Web Login para {inv['name']} em {BASE}...")
                login_web = {
                    "username": user, "password": pwd,
                    "clientObject": {"clientType": "WEB", "lang": "pt_BR"}
                }
                r_web = session.post(f"{BASE}/rest/neteco/web/sequence/v2/user/login", json=login_web, timeout=20)
                
                if r_web.status_code == 200:
                    # Tenta pegar dados via Energy Flow (mais detalhado)
                    r_flow = session.post(f"{BASE}/rest/pvms/web/station/v1/overview/energy-flow", 
                                         json={"stationDn": station_id}, timeout=20)
                    
                    if r_flow.status_code == 200:
                        d = r_flow.json().get("data", {}) or {}
                        return {
                            "power_w": float(d.get("productPower", d.get("realTimePower", 0)) or 0) * 1000,
                            "energy_today_kwh": float(d.get("dailyEnergy", d.get("dayPower", 0)) or 0),
                            "energy_total_kwh": float(d.get("cumulativeEnergy", d.get("totalEnergy", 0)) or 0),
                            "status": "generating" if float(d.get("productPower", 0) or 0) > 0 else "idle"
                        }
                    
                    # Se falhou flow, tenta KPI básico
                    r_data = session.post(f"{BASE}/rest/pvms/web/station/v1/overview/base-kpi", 
                                         json={"stationDn": station_id}, timeout=20)
                    if r_data.status_code == 200:
                        d = r_data.json().get("data", {}) or {}
                        return {
                            "power_w": float(d.get("realTimePower", 0) or 0) * 1000,
                            "energy_today_kwh": float(d.get("dailyEnergy", 0) or 0),
                            "energy_total_kwh": float(d.get("cumulativeEnergy", 0) or 0),
                            "status": "generating" if float(d.get("realTimePower", 0) or 0) > 0 else "idle"
                        }
                else:
                    logger.error(f"Huawei Web Login Error {r_web.status_code}: {r_web.text}")
            except Exception as e:
                logger.error(f"Falha na região {BASE}: {str(e)}")
                continue
        
        logger.error(f"Huawei [{inv['name']}]: Todas as tentativas de login falharam.")
        return None
    except Exception as e:
        logger.error(f"Huawei major error [{inv['name']}]: {e}")
        return None


# ── SAJ (elekeeper) ──────────────────────────────────────────
def collect_saj(inv):
    """Coleta dados SAJ via elekeeper API (login com e-mail do proprietario)"""
    try:
        user = inv.get("saj_user", inv.get("goodwe_user",""))
        pwd  = inv.get("saj_pass", inv.get("goodwe_pass",""))
        if not user or not pwd: return None

        # Região: EU por padrão (ajustar se necessário)
        BASE = "https://fop.saj-electric.com"

        session = requests.Session()
        session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        })

        # Login
        r = session.post(f"{BASE}/cloud/login",
            json={"username": user, "password": pwd, "local": "en"},
            timeout=15)

        try:
            login = r.json()
        except Exception:
            logger.error(f"SAJ login resposta invalida [{inv['name']}]: {r.text[:200]}")
            return None

        if login.get("status") != 1 and not login.get("token"):
            logger.error(f"SAJ login falhou [{inv['name']}]: {login.get('msg','')} ")
            return None

        token = login.get("token","")
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})

        # Buscar lista de plantas
        plant_id = inv.get("saj_plant_id", inv.get("goodwe_station_id",""))
        if not plant_id:
            r2 = session.post(f"{BASE}/cloud/station/list",
                json={"pageNo": 1, "pageSize": 10},
                timeout=15)
            try:
                plants = r2.json().get("data",{}).get("list",[])
                if plants:
                    plant_id = str(plants[0].get("stationDn","") or plants[0].get("id",""))
            except Exception as e:
                logger.debug(f"SAJ plant list: {e}")

        if not plant_id:
            logger.error(f"SAJ: nenhuma planta encontrada [{inv['name']}]")
            return None

        # Dados em tempo real
        r3 = session.post(f"{BASE}/cloud/station/real",
            json={"stationDn": plant_id},
            timeout=15)

        try:
            d = r3.json().get("data",{}) or {}
        except Exception:
            logger.error(f"SAJ dados invalidos [{inv['name']}]: {r3.text[:200]}")
            return None

        power_w      = float(d.get("nowPower", d.get("currentPower", 0)) or 0)
        energy_today = float(d.get("todayElectricity", d.get("dayEnergy", 0)) or 0)
        energy_month = float(d.get("monthElectricity", 0) or 0)
        energy_total = float(d.get("totalElectricity", d.get("totalEnergy", 0)) or 0)

        running = str(d.get("runningState","0"))
        if power_w > 0:        status = "generating"
        elif running == "1":   status = "generating"
        elif running == "0":   status = "idle" if is_daytime() else "offline"
        else:                  status = "idle" if is_daytime() else "offline"

        logger.info(f"SAJ OK [{inv['name']}]: {power_w:.0f}W | {energy_today:.2f}kWh hoje")
        return {
            "power_w": power_w,
            "energy_today_kwh": energy_today,
            "energy_month_kwh": energy_month,
            "energy_total_kwh": energy_total,
            "status": status,
        }
    except Exception as e:
        logger.error(f"SAJ error [{inv['name']}]: {e}")
        return None

# ── CANADIAN / GENÉRICO (API HTTP local) ─────────────────────
def collect_generic(inv):
    """Coleta dados via endpoint HTTP genérico (JSON)"""
    try:
        api_url = inv.get("api_url","")
        api_key = inv.get("api_key","")
        if not api_url: return None

        headers = {}
        if api_key: headers["Authorization"] = f"Bearer {api_key}"

        r = requests.get(api_url, headers=headers, timeout=10)
        d = r.json()

        # Tenta vários formatos comuns de resposta
        power_w      = float(d.get("power_w", d.get("current_power", d.get("pac", 0))) or 0)
        energy_today = float(d.get("energy_today", d.get("today_energy", d.get("day_energy", 0))) or 0)
        energy_total = float(d.get("energy_total", d.get("total_energy", 0)) or 0)
        energy_month = float(d.get("energy_month", d.get("month_energy", 0)) or 0)
        temp         = float(d.get("temperature", d.get("temp", 0)) or 0)
        voltage_ac   = float(d.get("voltage_ac", d.get("vac", d.get("grid_voltage", 0))) or 0)

        status = "generating" if power_w > 0 else ("idle" if is_daytime() else "offline")
        return {
            "power_w": power_w,
            "energy_today_kwh": energy_today,
            "energy_month_kwh": energy_month,
            "energy_total_kwh": energy_total,
            "voltage_ac": voltage_ac,
            "temperature_c": temp,
            "status": status,
        }
    except Exception as e:
        logger.error(f"Generic solar error [{inv['name']}]: {e}")
        return None

# ── Dispatcher por marca ──────────────────────────────────────
COLLECTORS = {
    "growatt":   collect_growatt,
    "fronius":   collect_fronius,
    "deye":      collect_deye,
    "solis":     collect_deye,      # Solis usa SolarmanPV
    "sma":       collect_sma,
    "goodwe":    collect_goodwe,
    "saj":       collect_saj,
    "huawei":    collect_huawei,
    "canadian":  collect_generic,
    "risen":     collect_generic,
    "other":     collect_generic,
}

def collect_inverter(inv):
    brand = (inv.get("brand") or "other").lower()
    collector = COLLECTORS.get(brand, collect_generic)
    return collector(inv)

def ensure_solar_schema(cur, conn):
    cur.execute("ALTER TABLE IF EXISTS solar_inverters ADD COLUMN IF NOT EXISTS saj_user TEXT DEFAULT ''")
    cur.execute("ALTER TABLE IF EXISTS solar_inverters ADD COLUMN IF NOT EXISTS saj_pass TEXT DEFAULT ''")
    cur.execute("ALTER TABLE IF EXISTS solar_inverters ADD COLUMN IF NOT EXISTS saj_plant_id TEXT DEFAULT ''")
    conn.commit()

# ── Loop principal ────────────────────────────────────────────
def run_solar_monitor():
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT id, client_id, name, brand, model, location, capacity_kwp, tariff_kwh,
                       growatt_user, growatt_pass, growatt_plant_id,
                       fronius_ip, fronius_device_id,
                       solarman_token, solarman_app_id, solarman_logger_sn,
                       sma_user, sma_pass, sma_plant_id,
                       goodwe_user, goodwe_pass, goodwe_station_id,
                       huawei_user, huawei_pass, huawei_station_id,
                       saj_user, saj_pass, saj_plant_id,
                       api_url, api_key, api_type, notes
                FROM solar_inverters WHERE status='active'
            """)
        except Exception as e:
            if "saj_user" in str(e):
                ensure_solar_schema(cur, conn)
                cur.execute("""
                    SELECT id, client_id, name, brand, model, location, capacity_kwp, tariff_kwh,
                           growatt_user, growatt_pass, growatt_plant_id,
                           fronius_ip, fronius_device_id,
                           solarman_token, solarman_app_id, solarman_logger_sn,
                           sma_user, sma_pass, sma_plant_id,
                           goodwe_user, goodwe_pass, goodwe_station_id,
                           huawei_user, huawei_pass, huawei_station_id,
                           saj_user, saj_pass, saj_plant_id,
                           api_url, api_key, api_type, notes
                    FROM solar_inverters WHERE status='active'
                """)
            else:
                raise
        inverters = cur.fetchall()
        cols = ["id","client_id","name","brand","model","location","capacity_kwp","tariff_kwh",
                "growatt_user","growatt_pass","growatt_plant_id",
                "fronius_ip","fronius_device_id",
                "solarman_token","solarman_app_id","solarman_logger_sn",
                "sma_user","sma_pass","sma_plant_id",
                "goodwe_user","goodwe_pass","goodwe_station_id",
                "huawei_user","huawei_pass","huawei_station_id",
                "saj_user","saj_pass","saj_plant_id",
                "api_url","api_key","api_type","notes"]

        if not inverters:
            logger.debug("Nenhum inversor solar cadastrado")
            return

        for row in inverters:
            inv = dict(zip(cols, row))
            try:
                data = collect_inverter(inv)
                if data:
                    save_metric(cur, conn, inv, data)
                    tg_tok, tg_cid, wa_inst, wa_tok, wa_num = get_client_config(cur, inv.get("client_id"))
                    check_solar_alerts(cur, inv, data, tg_tok, tg_cid, wa_inst, wa_tok, wa_num)
                else:
                    logger.warning(f"Sem dados: {inv['name']} ({inv['brand']})")
            except Exception as e:
                logger.exception(f"Solar collect error [{inv['name']}]: {e}")

def main():
    logger.info(f"{'='*52}")
    logger.info(f"  {APP_NAME}")
    logger.info(f"  Intervalo: {SOLAR_INTERVAL}s")
    logger.info(f"  Marcas suportadas: Growatt, Fronius, Deye, Solis, SMA, GoodWe, Huawei, Genérico")
    logger.info(f"{'='*52}")

    while True:
        try: 
            logger.info("--- CICLO DE COLETA SOLAR INICIADO ---")
            run_solar_monitor()
            logger.info("--- CICLO DE COLETA SOLAR FINALIZADO ---")
        except Exception as e: 
            logger.exception(f"Solar error: {e}")
        time.sleep(SOLAR_INTERVAL)

if __name__ == "__main__": main()
