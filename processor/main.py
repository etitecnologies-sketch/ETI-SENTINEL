import os, time, logging, smtplib, requests, datetime, subprocess, html, re, json
from email.mime.text import MIMEText
from contextlib import contextmanager
import psycopg2
import concurrent.futures

print("==================================================")
print(">>> NEXUSWATCH PROCESSOR STARTING UP... <<<")
print(f">>> TIME: {datetime.datetime.now()} <<<")
print("==================================================")

# Configuração de fuso horário local (Brasil/Brasília)
TIMEZONE_DISPLAY = datetime.timezone(datetime.timedelta(hours=-3))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

APP_NAME        = "ETI SENTINEL"

def sanitize(val): return re.sub(r'["\'`\s]', '', val) if val else ""
def escape_html(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def now_display():
    """Retorna o horário atual formatado para o Brasil (YYYY.MM.DD-HH:MM:SS)"""
    return datetime.datetime.now(TIMEZONE_DISPLAY).strftime("%Y.%m.%d-%H:%M:%S")

DATABASE_URL    = sanitize(os.environ.get("DATABASE_URL", ""))
EVAL_INTERVAL   = int(os.getenv("EVAL_INTERVAL", "1")) # Ciclo ultra-rápido: 1s
OFFLINE_TIMEOUT = int(os.getenv("OFFLINE_TIMEOUT", "30")) # Timeout mais equilibrado: 30s (ajustado de 10s para evitar alertas falsos)
ALERT_COOLDOWN  = int(os.getenv("ALERT_COOLDOWN", "60"))
PING_TIMEOUT    = int(os.getenv("PING_TIMEOUT", "2"))
PING_COUNT      = int(os.getenv("PING_COUNT", "1"))

# Telegram/Email globais (superadmin)
TG_TOKEN    = sanitize(os.getenv("TELEGRAM_TOKEN", ""))
TG_CHAT_ID  = sanitize(os.getenv("TELEGRAM_CHAT_ID", ""))
SMTP_HOST   = sanitize(os.getenv("SMTP_HOST", ""))
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER   = sanitize(os.getenv("SMTP_USER", ""))
SMTP_PASS   = sanitize(os.getenv("SMTP_PASS", ""))
ALERT_EMAIL = sanitize(os.getenv("ALERT_EMAIL", ""))

TWILIO_ACCOUNT_SID = sanitize(os.getenv("TWILIO_ACCOUNT_SID", ""))
TWILIO_AUTH_TOKEN = sanitize(os.getenv("TWILIO_AUTH_TOKEN", ""))
TWILIO_WHATSAPP_NUMBER = sanitize(os.getenv("TWILIO_WHATSAPP_NUMBER", ""))
TWILIO_CONTENT_SID = sanitize(os.getenv("TWILIO_CONTENT_SID", ""))

WA_INSTANCE = sanitize(os.getenv("WA_INSTANCE", ""))  # compat
WA_TOKEN    = sanitize(os.getenv("WA_TOKEN", ""))  # compat
WA_NUMBER   = sanitize(os.getenv("WA_NUMBER", ""))  # compat
WA_API_URL  = sanitize(os.getenv("WA_API_URL", ""))  # compat

# Limpeza e log de inicialização
if not TG_TOKEN or not TG_CHAT_ID:
    logger.warning("⚠️ ALERTA: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID globais não configurados!")
else:
    logger.info(f"✅ Telegram Global Configurado: {TG_TOKEN[:10]}... | ChatID: {TG_CHAT_ID}")

if not DATABASE_URL:
    logger.error("❌ ERRO CRÍTICO: DATABASE_URL não configurada!")

device_online_state = {}
alert_cooldown_map  = {}
ping_state          = {}
last_summary_time   = 0
last_event_id       = 0
threshold_stability = {}

DEVICE_TYPE_ICONS = {
    "server":"🖥️","camera":"📷","router":"🌐","switch":"🔀",
    "routerboard":"📡","unifi":"📶","firewall":"🛡️","printer":"🖨️",
    "iot":"💡","workstation":"💻","dvr":"📹","nvr":"🎥","other":"📦",
}
SEVERITY = {
    "cpu":{"icon":"🔥","label":"CPU"},"memory":{"icon":"🧠","label":"Memória"},
    "disk_percent":{"icon":"💾","label":"Disco"},"latency_ms":{"icon":"📡","label":"Latência"},
    "load_avg":{"icon":"⚙️","label":"Load"},"temperature":{"icon":"🌡️","label":"Temp"},
}
UNITS = {"latency_ms":"ms","load_avg":"","processes":"","temperature":"°C"}
SNMP_OIDS = {
    "cpu":"1.3.6.1.4.1.2021.11.11.0","memory":"1.3.6.1.4.1.2021.4.6.0",
    "mem_total":"1.3.6.1.4.1.2021.4.5.0","mikrotik_cpu":"1.3.6.1.2.1.25.3.3.1.2.1",
    "mikrotik_mem_used":"1.3.6.1.2.1.25.2.3.1.6.1","mikrotik_mem_total":"1.3.6.1.2.1.25.2.3.1.5.1",
    "uptime":"1.3.6.1.2.1.1.3.0",
}

def get_unit(expr):  return UNITS.get(expr, "%")
def device_icon(t):  return DEVICE_TYPE_ICONS.get((t or "other").lower(), "📦")
def now_str():       return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_severity_level(expr, value, threshold):
    ratio = float(value)/float(threshold) if float(threshold)>0 else 2
    if ratio>=1.5: return "CRÍTICO","🔴"
    elif ratio>=1.2: return "ALTO","🟠"
    else: return "ATENÇÃO","🟡"

def threshold_margins(expr, threshold):
    t = float(threshold) if threshold is not None else 0.0
    if t < 0:
        t = 0.0
    confirm_fire = int(os.getenv("THRESHOLD_FIRE_CONFIRM", "2") or 2)
    confirm_resolve = int(os.getenv("THRESHOLD_RESOLVE_CONFIRM", "2") or 2)
    confirm_fire = max(1, confirm_fire)
    confirm_resolve = max(1, confirm_resolve)

    fire_pct = float(os.getenv("THRESHOLD_FIRE_MARGIN_PCT", "0.02") or 0.02)
    resolve_pct = float(os.getenv("THRESHOLD_RESOLVE_MARGIN_PCT", "0.05") or 0.05)
    fire_pct = max(0.0, fire_pct)
    resolve_pct = max(0.0, resolve_pct)

    if str(expr or "") == "latency_ms":
        fire_abs = float(os.getenv("LATENCY_FIRE_MARGIN_MS", "20") or 20)
        resolve_abs = float(os.getenv("LATENCY_RESOLVE_MARGIN_MS", "30") or 30)
        fire_abs = max(0.0, fire_abs)
        resolve_abs = max(0.0, resolve_abs)
        fire_th = t + fire_abs
        resolve_th = max(0.0, t - resolve_abs)
        return fire_th, resolve_th, confirm_fire, confirm_resolve

    fire_th = t * (1.0 + fire_pct)
    resolve_th = t * (1.0 - resolve_pct)
    return fire_th, resolve_th, confirm_fire, confirm_resolve

@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try: yield conn
    finally: conn.close()

# ── Notificações por cliente ──────────────────────────────────
def get_client_config(cur, client_id):
    """Retorna config de telegram/email/whatsapp do cliente"""
    if not client_id: return None, None, None, None, None, None, None
    try:
        cur.execute("""
            SELECT telegram_token, telegram_chat_id, alert_email, name,
                   wa_instance, wa_token, wa_number
            FROM clients WHERE id=%s
        """, (client_id,))
        row = cur.fetchone()
        if row: return row[0], row[1], row[2], row[3], row[4], row[5], row[6]
    except: pass
    return None, None, None, None, None, None, None

def send_whatsapp(message, instance=None, token=None, number=None):
    """Envia mensagem via API Oficial do Twilio para o cliente ou superadmin"""
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
            logger.info(f"WhatsApp (Twilio) ✓ sent to {dest_num}")
        else:
            logger.error(f"WhatsApp (Twilio) error ({r.status_code}): {r.text}")
    except Exception as e:
        logger.error(f"WhatsApp (Twilio) exception: {e}")

def send_telegram(message, token=None, chat_id=None):
    """Envia para o telegram do cliente ou do superadmin com tratamento de erro e escape HTML"""
    targets = []
    
    # Adiciona o target do cliente se configurado
    if token and chat_id:
        targets.append((str(token).strip(), str(chat_id).strip()))
    
    # Adiciona o target global se configurado (Superadmin)
    if TG_TOKEN and TG_CHAT_ID:
        targets.append((str(TG_TOKEN).strip(), str(TG_CHAT_ID).strip()))
    
    if not targets:
        logger.error("Nenhum target de Telegram configurado (Token ou ChatID vazios)!")
        return
        
    for tok, cid in set(targets):
        try:
            # Garante que o token esteja no formato correto para a URL
            # Telegram espera o formato bot<token>/sendMessage
            clean_tok = tok[3:] if tok.lower().startswith("bot") else tok
            url = f"https://api.telegram.org/bot{clean_tok}/sendMessage"
            
            payload = {"chat_id": cid, "text": message, "parse_mode": "HTML"}
            logger.info(f"Enviando Telegram para {cid}...")
            
            r = requests.post(url, json=payload, timeout=15)
            
            if r.status_code == 200:
                logger.info(f"Telegram ✓ enviado para {cid}")
            else:
                logger.error(f"Telegram erro {r.status_code} ({cid}): {r.text}")
                # Se falhou por causa do HTML, tenta enviar como texto puro como fallback
                if "can't parse entities" in r.text.lower():
                    logger.info(f"Tentando fallback para texto puro (sem HTML) para {cid}...")
                    payload.pop("parse_mode")
                    r2 = requests.post(url, json=payload, timeout=15)
                    if r2.status_code == 200:
                        logger.info(f"Telegram ✓ enviado com fallback para {cid}")
                    else:
                        logger.error(f"Telegram fallback também falhou {r2.status_code}: {r2.text}")
        except Exception as e:
            logger.error(f"Telegram exceção ao enviar para {cid}: {e}")

def send_email(subject, body, to_email=None):
    emails = list(set(filter(None, [to_email, ALERT_EMAIL])))
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS]) or not emails: return
    for email in emails:
        try:
            msg=MIMEText(body); msg["Subject"]=subject; msg["From"]=SMTP_USER; msg["To"]=email
            with smtplib.SMTP(SMTP_HOST,SMTP_PORT) as s:
                s.starttls(); s.login(SMTP_USER,SMTP_PASS); s.sendmail(SMTP_USER,[email],msg.as_string())
            logger.info(f"Email ✓ sent to {email}")
        except Exception as e: logger.error(f"Email error: {e}")

def is_in_cooldown(host,expr): return (time.time()-alert_cooldown_map.get((host,expr),0))<ALERT_COOLDOWN
def set_cooldown(host,expr): alert_cooldown_map[(host,expr)]=time.time()

def ping(ip, timeout=3):
    if not ip: return False, 0
    try:
        start=time.time()
        result=subprocess.run(["ping","-c",str(PING_COUNT),"-W",str(timeout),ip],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout+1)
        return result.returncode==0, round((time.time()-start)*1000,1)
    except: return False, 0

def snmp_get(ip, community, oid, version="2c", timeout=3):
    try:
        cmd=["snmpget","-v",version,"-c",community,"-t",str(timeout),"-r","1",ip,oid]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout+1)
        if result.returncode!=0: return None
        parts=result.stdout.strip().split(":")
        if len(parts)>=2:
            try: return float(parts[-1].strip().split()[0])
            except: return None
    except: return None

def collect_snmp(ip, community, version="2c"):
    m={}
    cpu=snmp_get(ip,community,"1.3.6.1.2.1.25.3.3.1.2.1",version)
    if cpu is None:
        idle=snmp_get(ip,community,SNMP_OIDS["cpu"],version)
        if idle is not None: cpu=max(0,100-idle)
    if cpu is not None: m["cpu"]=cpu
    mu=snmp_get(ip,community,SNMP_OIDS["mikrotik_mem_used"],version)
    mt=snmp_get(ip,community,SNMP_OIDS["mikrotik_mem_total"],version)
    if mu and mt and mt>0: m["memory"]=(mu/mt)*100
    upt=snmp_get(ip,community,SNMP_OIDS["uptime"],version)
    if upt: m["uptime_seconds"]=int(upt/100)
    return m

def check_ping_devices(cur, conn):
    cur.execute("""SELECT d.id,d.name,d.ip_address,d.device_type,d.tags,d.status,
        d.snmp_community,d.snmp_version,d.monitor_snmp,d.hostname,d.client_id,d.ddns_address,d.monitor_port,
        d.mac_address,d.serial_number,
        (SELECT latency_ms FROM metrics WHERE device_id=d.id ORDER BY time DESC LIMIT 1) as last_latency
        FROM devices d WHERE (d.ip_address IS NOT NULL AND d.ip_address!='' AND (d.monitor_ping=TRUE OR d.monitor_port > 0))
        OR (d.ddns_address IS NOT NULL AND d.ddns_address!='' AND d.monitor_port > 0)""")
    devices=cur.fetchall()
    if not devices: return

    def check_one(dev):
        dev_id,dev_name,ip,dtype,tags,db_status,sc,sv,do_snmp,hostname,client_id,ddns,port,mac,sn,last_latency=dev
        
        alive = False
        latency = 0
        method = "NONE"
        
        # Ignora IPs privados (192.168.x, 10.x, 172.16-31.x) pois o servidor cloud não alcança
        # Esses dispositivos serão monitorados apenas pelo 'last_seen' (Heartbeat/Push)
        is_private = ip and (ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."))
        
        if is_private and not ddns:
            return None # Ignora este dispositivo no monitoramento de Ping direto

        # 1. Tenta DDNS se disponível
        if ddns and port:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(PING_TIMEOUT)
                start = time.time()
                result = s.connect_ex((ddns, int(port)))
                latency = round((time.time() - start) * 1000, 1)
                s.close()
                if result == 0:
                    alive = True
                    method = f"TCP:{port}"
            except:
                pass
                
        # 2. Se não funcionou DDNS ou não tem, tenta TCP no IP (caso de VPN/Private IP)
        if not alive and ip and port:
            import socket
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(PING_TIMEOUT)
                start = time.time()
                result = s.connect_ex((ip, int(port)))
                latency = round((time.time() - start) * 1000, 1)
                s.close()
                if result == 0:
                    alive = True
                    method = f"VPN-TCP:{port}"
            except:
                pass

        # 3. Se ainda não funcionou ou não tem porta, tenta Ping se tiver IP
        if not alive and ip:
            alive, latency = ping(ip, PING_TIMEOUT)
            method = "PING"

        # 4. Caso seja monitorado apenas por sinal de vida (Auto Registro / Push)
        # Não tentamos 'alive' aqui, deixamos para o check_offline_devices
        
        return dev_id,dev_name,ip or ddns,dtype,tags,db_status,sc,sv,do_snmp,hostname,client_id,alive,latency,method,mac,sn,last_latency

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as ex:
        results=list(ex.map(check_one,devices))

    for r in results:
        if r is None: continue
        dev_id,dev_name,target,dtype,tags,db_status,sc,sv,do_snmp,hostname,client_id,alive,latency,method,mac,sn,last_latency=r
        d_icon=device_icon(dtype)
        tags_list=tags if tags else []
        tags_str=" ".join([f"#{t}" for t in tags_list]) if tags_list else ""
        
        # Estado atual do banco
        was_down = (db_status == 'offline')

        # Buscar config do cliente
        tg_tok, tg_cid, cl_email, cl_name, wa_inst, wa_tok, wa_num = get_client_config(cur, client_id)

        # Se o monitoramento ativo (Ping/TCP) detectou que está vivo
        if alive:
            try:
                cur.execute("UPDATE devices SET last_seen=NOW(),status='online' WHERE id=%s",(dev_id,))
                conn.commit()
            except: conn.rollback()
            
            # Registrar métrica de latência
            if latency>0:
                try:
                    hl=hostname or target or dev_name
                    cur.execute("INSERT INTO hosts(name) VALUES(%s) ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name",(hl,))
                    cur.execute("""INSERT INTO metrics(time,host_id,host,device_id,cpu,memory,disk_used,
                        disk_total,disk_percent,net_rx_bytes,net_tx_bytes,latency_ms,uptime_seconds,load_avg,processes,temperature,status)
                        VALUES(NOW(),(SELECT id FROM hosts WHERE name=%s),%s,%s,0,0,0,0,0,0,0,%s,0,0,0,0,'online')""",
                        (hl,hl,dev_id,latency))
                    conn.commit()
                except Exception as e: logger.debug(f"Ping metric: {e}"); conn.rollback()

            # Alerta de retorno ONLINE (para dispositivos com monitoramento ativo)
            if was_down:
                logger.info(f"✅ DEVICE ONLINE (Active): {dev_name} ({target}) via {method}")
                edev_name = escape_html(dev_name)
                etarget = escape_html(target)
                ecl_name = escape_html(cl_name) if cl_name else ""
                msg=(f"✅ <b>{edev_name}</b>\n"
                     f"<b>CONEXÃO RESTABELECIDA</b>\n"
                     f"Status: O dispositivo voltou a responder via {method}\n\n"
                     f"Latência: <b>{latency:.1f}ms</b>\n"
                     f"Data/Hora: <b>{now_display()}</b>\n"
                     f"Detalhes: {d_icon} {escape_html(dtype or 'other')}\n"
                     +(f"MAC: {escape_html(mac)}\n" if mac else "")
                     +(f"SN: {escape_html(sn)}\n" if sn else "")
                     +(f"Cliente: {ecl_name}\n" if cl_name else ""))
                
                send_telegram(msg, tg_tok, tg_cid)
                send_whatsapp(msg.replace("<b>","*").replace("</b>","*"), wa_inst, wa_tok, wa_num)

        # Se o monitoramento ativo detectou queda (e não é apenas via Push)
        elif not alive and not was_down and method != "NONE":
            logger.warning(f"🚨 DEVICE OFFLINE (Active): {dev_name} ({target})")
            try:
                # Busca ou cria o host_id
                cur.execute("INSERT INTO hosts(name) VALUES(%s) ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name RETURNING id", (target or dev_name,))
                host_id = cur.fetchone()[0]

                cur.execute("INSERT INTO alerts(device_id,host,expression,value,threshold,alert_type,client_id) VALUES(%s,%s,'offline',1,0,'offline',%s)",(dev_id,target or dev_name,client_id))
                cur.execute("UPDATE devices SET status='offline' WHERE id=%s",(dev_id,))
                cur.execute("INSERT INTO metrics(time,host_id,host,device_id,latency_ms,status) VALUES(NOW(),%s,%s,%s,0,'offline')", (host_id, target or dev_name, dev_id))
                conn.commit()
            except Exception as e: logger.error(f"Alert DB save error: {e}"); conn.rollback()
            
            edev_name = escape_html(dev_name)
            etarget = escape_html(target)
            ecl_name = escape_html(cl_name) if cl_name else ""
            msg=(f"❌ <b>{edev_name}</b>\n"
                 f"<b>DISPOSITIVO OFFLINE</b>\n"
                 f"Falha detectada via {method}\n\n"
                 f"Última Latência: <b>{last_latency if last_latency else 0:.1f}ms</b>\n"
                 f"Data do Evento: <b>{now_display()}</b>\n"
                 f"Detalhes: {d_icon} {escape_html(dtype or 'other')}\n"
                 +(f"MAC: {escape_html(mac)}\n" if mac else "")
                 +(f"SN: {escape_html(sn)}\n" if sn else "")
                 +(f"Cliente: {ecl_name}\n" if cl_name else ""))
            
            send_telegram(msg, tg_tok, tg_cid)
            send_whatsapp(msg.replace("<b>","*").replace("</b>","*"), wa_inst, wa_tok, wa_num)

def check_offline_devices(cur, conn):
    # 1. DETECÇÃO DE QUEDA POR TIMEOUT (Para Auto Registro / Push / Agent)
    # Selecionar dispositivos que deveriam estar offline usando comparação de segundos absoluta
    cur.execute(f"""
        SELECT id, name, client_id, device_type, mac_address, serial_number, description
        FROM devices 
        WHERE last_seen IS NOT NULL 
          AND status != 'offline'
          AND EXTRACT(EPOCH FROM (NOW() - last_seen)) > {OFFLINE_TIMEOUT}
    """)
    dropped = cur.fetchall()
    
    for dev_id, dev_name, client_id, dtype, mac, sn, device_description in dropped:
        if is_in_cooldown(dev_name, "offline"):
            continue
        logger.warning(f"🚨 QUEDA POR TIMEOUT: {dev_name}")
        try:
            cur.execute("SELECT 1 FROM alerts WHERE device_id=%s AND alert_type='offline' AND resolved_at IS NULL LIMIT 1", (dev_id,))
            has_open_offline = cur.fetchone() is not None

            # Busca ou cria o host_id
            cur.execute("INSERT INTO hosts(name) VALUES(%s) ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name RETURNING id", (dev_name,))
            host_id = cur.fetchone()[0]

            # Atualiza o status para offline no banco
            cur.execute("UPDATE devices SET status='offline' WHERE id=%s", (dev_id,))
            if not has_open_offline:
                cur.execute("INSERT INTO alerts(device_id,host,expression,value,threshold,alert_type,client_id,fired_at) VALUES(%s,%s,'offline',1,0,'offline',%s,NOW())",(dev_id,dev_name,client_id))
            cur.execute("INSERT INTO metrics(time,host_id,host,device_id,latency_ms,status) VALUES(NOW(),%s,%s,%s,0,'offline')", (host_id, dev_name, dev_id))
            conn.commit()
            
            # Notificar WebSocket para atualizar o Dashboard em tempo real
            if WA_API_URL: # Usamos WA_API_URL apenas como flag para saber se o servidor tem rede
                try:
                    # Tenta avisar o websocket via ingest-api (proxy) ou direto se estiver no mesmo docker
                    ws_url = os.getenv("WEBSOCKET_URL", "http://websocket:3001").rstrip("/")
                    requests.post(f"{ws_url}/publish", json={
                        "type": "METRIC",
                        "device_id": dev_id,
                        "client_id": client_id,
                        "name": dev_name,
                        "status": "offline",
                        "latency_ms": 0,
                        "time": datetime.datetime.now().isoformat()
                    }, timeout=2)
                except: pass

            tg_tok, tg_cid, cl_email, cl_name, wa_inst, wa_tok, wa_num = get_client_config(cur, client_id)
            
            # Formato solicitado pelo usuário
            if not has_open_offline:
                msg=(
                    f"❌ <b>{escape_html(dev_name)}</b>\n"
                    f"Problema: O dispositivo está indisponível há mais de {OFFLINE_TIMEOUT}s\n\n"
                    f"Host: <b>{escape_html(dev_name)}</b>\n"
                    f"Data do Evento: <b>{now_display()}</b>\n"
                    f"Detalhes do Equipamento: {escape_html(dtype or 'other')} - {escape_html(mac or sn or 'N/A')}\n"
                    f"Descrição: {escape_html(cl_name or 'ETI SENTINEL')}\n"
                    + (f"Empresa: {escape_html(device_description)}\n" if device_description else "")
                    + "Indicação: Verifique a conectividade e energia do dispositivo."
                )
                
                send_telegram(msg, tg_tok, tg_cid)
                send_whatsapp(msg.replace("<b>","*").replace("</b>","*"), wa_inst, wa_tok, wa_num)
                set_cooldown(dev_name, "offline")
        except Exception as e: logger.error(f"Erro Queda Timeout: {e}"); conn.rollback()

    cur.execute(f"""
        SELECT a.id, d.id, d.name, d.client_id, d.device_type, d.mac_address, d.serial_number, d.description
        FROM alerts a
        JOIN devices d ON d.id = a.device_id
        WHERE a.alert_type = 'offline'
          AND a.resolved_at IS NULL
          AND d.last_seen IS NOT NULL
          AND EXTRACT(EPOCH FROM (NOW() - d.last_seen)) < {OFFLINE_TIMEOUT}
    """)
    recovered_by_alert = cur.fetchall()
    for alert_id, dev_id, dev_name, client_id, dtype, mac, sn, device_description in recovered_by_alert:
        if is_in_cooldown(dev_name, "recovered"):
            continue
        logger.info(f"✅ RETORNO POR SINAL: {dev_name}")
        try:
            cur.execute("UPDATE alerts SET resolved_at=NOW() WHERE id=%s", (alert_id,))
            cur.execute("UPDATE devices SET status='online' WHERE id=%s", (dev_id,))
            conn.commit()
            tg_tok, tg_cid, cl_email, cl_name, wa_inst, wa_tok, wa_num = get_client_config(cur, client_id)
            msg=(
                f"✅ <b>{escape_html(dev_name)}</b>\n"
                f"Normalizado: O dispositivo voltou a responder ao sistema\n\n"
                f"Host: <b>{escape_html(dev_name)}</b>\n"
                f"Data da Normalização: <b>{now_display()}</b>\n"
                f"Detalhes do Equipamento: {escape_html(dtype or 'other')} - {escape_html(mac or sn or 'N/A')}\n"
                f"Descrição: {escape_html(cl_name or 'ETI SENTINEL')}\n"
                + (f"Empresa: {escape_html(device_description)}" if device_description else "")
            )
            send_telegram(msg, tg_tok, tg_cid)
            send_whatsapp(msg.replace("<b>","*").replace("</b>","*"), wa_inst, wa_tok, wa_num)
            set_cooldown(dev_name, "recovered")
        except Exception as e:
            logger.error(f"Erro Retorno Timeout: {e}")


def fire_alert(cur,conn,trigger_id,name,host,expr,value,threshold,device_id=None,client_id=None):
    if is_in_cooldown(host,expr): return
    try:
        cur.execute("INSERT INTO alerts(trigger_id,device_id,host,expression,value,threshold,alert_type,client_id) VALUES(%s,%s,%s,%s,%s,%s,'threshold',%s)",
            (trigger_id,device_id,host,expr,float(value),float(threshold),client_id))
        conn.commit()
    except Exception as e: logger.error(f"Alert save: {e}"); conn.rollback()
    set_cooldown(host,expr)
    unit=get_unit(expr)
    sev_label,sev_icon=get_severity_level(expr,value,threshold)
    meta=SEVERITY.get(expr,{"icon":"📊","label":expr})
    dtype,tags,dname,mac,sn=None,[],None,None,None
    tg_tok, tg_cid, cl_email, cl_name, wa_inst, wa_tok, wa_num = get_client_config(cur, client_id)
    if device_id:
        try:
            cur.execute("SELECT device_type,tags,name,mac_address,serial_number FROM devices WHERE id=%s",(device_id,))
            row=cur.fetchone()
            if row: dtype,tags,dname,mac,sn=row[0],row[1] or [],row[2],row[3],row[4]
        except: pass
    d_icon=device_icon(dtype)
    tags_str=" ".join([f"#{t}" for t in tags]) if tags else ""
    mac_sn_str = f"MAC: {escape_html(mac)} | SN: {escape_html(sn)}\n" if mac or sn else ""
    client_suffix = f"\n🏢 Cliente: <b>{escape_html(cl_name)}</b>" if cl_name else ""
    logger.warning(f"ALERT [{sev_label}] {name} | {host} | {expr}={value:.1f}{unit}")
    
    # Escapando variáveis dinâmicas para evitar erro no Telegram HTML
    ename = escape_html(name)
    ehost = escape_html(host)
    edname = escape_html(dname or host)
    emeta_label = escape_html(meta['label'])
    esev_label = escape_html(sev_label)
    ecl_name = escape_html(cl_name)
    etags_str = escape_html(tags_str)

    msg=(f"{sev_icon} <b>{edname}</b>\n"
         f"Problema: {emeta_label} atingiu {value:.1f}{unit} (limite: {threshold}{unit})\n\n"
         f"Host: <b>{ehost}</b>\n"
         f"Data do Evento: <b>{now_display()}</b>\n"
         f"Detalhes do Equipamento: {escape_html(dtype or 'other')} - {escape_html(mac or sn or 'N/A')}\n"
         f"Descrição: {escape_html(cl_name or 'ETI SENTINEL')}\n"
         f"Indicação: {esev_label} — verifique o dispositivo.")
    send_telegram(msg, tg_tok, tg_cid)
    send_whatsapp(msg.replace("<b>", "*").replace("</b>", "*"), wa_inst, wa_tok, wa_num)
    send_email(f"[{APP_NAME}] {sev_icon} {sev_label}: {name} em {host}",
        f"ALERTA {sev_label}\n\nTrigger: {name}\nHost: {host}\nDevice: {dname or 'N/A'}\nMAC: {mac}\nSN: {sn}\nCliente: {cl_name or 'N/A'}\nMétrica: {meta['label']} = {value:.1f}{unit}\nLimite: {threshold}{unit}\nHorário: {now_str()}", cl_email)

def resolve_threshold_alert(cur, conn, alert_id, trigger_name, host, expr, value, threshold, device_id=None, client_id=None):
    try:
        cur.execute("UPDATE alerts SET resolved_at=NOW() WHERE id=%s", (alert_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Alert resolve: {e}")
        conn.rollback()
        return

    unit=get_unit(expr)
    meta=SEVERITY.get(expr,{"icon":"📊","label":expr})
    dtype,tags,dname,mac,sn,ddesc=None,[],None,None,None,None
    tg_tok, tg_cid, cl_email, cl_name, wa_inst, wa_tok, wa_num = get_client_config(cur, client_id)
    if device_id:
        try:
            cur.execute("SELECT device_type,tags,name,mac_address,serial_number,description FROM devices WHERE id=%s",(device_id,))
            row=cur.fetchone()
            if row: dtype,tags,dname,mac,sn,ddesc=row[0],row[1] or [],row[2],row[3],row[4],row[5]
        except: pass

    edname = escape_html(dname or host)
    ehost = escape_html(host)
    emeta_label = escape_html(meta["label"])
    etrigger_name = escape_html(trigger_name)
    msg=(
        f"✅ <b>{edname}</b>\n"
        f"Normalizado: {emeta_label} voltou ao normal\n\n"
        f"Trigger: <b>{etrigger_name}</b>\n"
        f"Host: <b>{ehost}</b>\n"
        f"Valor atual: <b>{float(value):.1f}{unit}</b> (limite: {float(threshold):.1f}{unit})\n"
        f"Data da Normalização: <b>{now_display()}</b>\n"
        f"Detalhes do Equipamento: {escape_html(dtype or 'other')} - {escape_html(mac or sn or 'N/A')}\n"
        f"Descrição: {escape_html(cl_name or 'ETI SENTINEL')}\n"
        + (f"Empresa: {escape_html(ddesc)}\n" if ddesc else "")
        + "Indicação: Nenhuma ação necessária."
    )
    send_telegram(msg, tg_tok, tg_cid)
    send_whatsapp(msg.replace("<b>", "*").replace("</b>", "*"), wa_inst, wa_tok, wa_num)

def send_status_summary(cur):
    global last_summary_time
    if (time.time()-last_summary_time)<3600: return
    last_summary_time=time.time()
    cur.execute("SELECT COUNT(*) FROM devices WHERE status='online'")
    online=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM devices WHERE status='offline'")
    offline=cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM clients WHERE status='active'")
    clients_count=cur.fetchone()[0]
    lines=[f"📊 <b>STATUS REPORT — {APP_NAME}</b>",f"━━━━━━━━━━━━━━━━━━━━",
           f"🏢 Clientes ativos: <b>{clients_count}</b>",
           f"🟢 Devices online: <b>{online}</b>  🔴 Offline: <b>{offline}</b>",f"━━━━━━━━━━━━━━━━━━━━",f"🕐 {now_str()}"]
    send_telegram("\n".join(lines))
    send_whatsapp("\n".join(lines).replace("<b>", "*").replace("</b>", "*"))
    logger.info("Status summary sent")

def evaluate_triggers(cur, conn):
    cur.execute("SELECT id,name,expression,threshold,client_id FROM triggers WHERE enabled=TRUE")
    triggers=cur.fetchall()
    if not triggers: return

    # Get latest metrics with device info in one query
    cur.execute("""
        SELECT DISTINCT ON(m.host) 
            m.host, m.cpu, m.memory, m.disk_percent, m.latency_ms, m.load_avg, m.temperature, 
            m.device_id, d.client_id
        FROM metrics m
        LEFT JOIN devices d ON d.id = m.device_id
        WHERE m.time > NOW() - INTERVAL '1 minute'
        ORDER BY m.host, m.time DESC
    """)
    metrics=cur.fetchall()
    if not metrics: return

    cur.execute("""
        SELECT id, trigger_id, device_id, host, expression, threshold, client_id
        FROM alerts
        WHERE alert_type='threshold' AND resolved_at IS NULL
    """)
    open_rows = cur.fetchall()
    open_by_key = {}
    for aid, trig_id, dev_id, host, expr, thr, cid in open_rows:
        k = (int(trig_id or 0), int(dev_id or 0), str(host or ""), str(expr or ""), int(cid or 0))
        prev = open_by_key.get(k)
        if prev is None or int(aid) > int(prev[0]):
            open_by_key[k] = (aid, thr)

    expr_idx={"cpu":1,"memory":2,"disk_percent":3,"latency_ms":4,"load_avg":5,"temperature":6}
    for trigger_id,name,expr,threshold,trigger_client_id in triggers:
        idx=expr_idx.get(expr)
        if idx is None: continue
        
        for row in metrics:
            host,cpu,memory,disk,latency,load,temp,device_id,device_client_id=row
            
            # Filter by client_id if trigger is client-specific
            if trigger_client_id and device_client_id and trigger_client_id != device_client_id:
                continue
                
            vals=[None,cpu,memory,disk,latency,load,temp]
            value=vals[idx]
            
            eff_client_id = device_client_id or trigger_client_id
            if value is None:
                continue
            k = (int(trigger_id or 0), int(device_id or 0), str(host or ""), str(expr or ""), int(eff_client_id or 0))
            open_alert = open_by_key.get(k)
            open_alert_id = open_alert[0] if open_alert else None
            open_thr = open_alert[1] if open_alert else None

            fire_th, resolve_th, confirm_fire, confirm_resolve = threshold_margins(expr, open_thr if open_thr is not None else threshold)
            st = threshold_stability.get(k) or {"above": 0, "below": 0}

            if float(value) >= float(fire_th):
                st["above"] = int(st.get("above") or 0) + 1
            else:
                st["above"] = 0

            if float(value) <= float(resolve_th):
                st["below"] = int(st.get("below") or 0) + 1
            else:
                st["below"] = 0

            threshold_stability[k] = st

            if not open_alert_id:
                if st["above"] >= confirm_fire and not is_in_cooldown(host, f"threshold:{expr}:{trigger_id}:fire"):
                    fire_alert(cur,conn,trigger_id,name,host,expr,value,threshold,device_id,eff_client_id)
                    set_cooldown(host, f"threshold:{expr}:{trigger_id}:fire")
                    st["above"] = 0
            else:
                if st["below"] >= confirm_resolve and not is_in_cooldown(host, f"resolved:{expr}:{trigger_id}"):
                    resolve_threshold_alert(cur, conn, open_alert_id, name, host, expr, value, open_thr, device_id, eff_client_id)
                    set_cooldown(host, f"resolved:{expr}:{trigger_id}")
                    open_by_key.pop(k, None)
                    st["below"] = 0

def check_new_events(cur, conn):
    """Monitora a tabela de eventos (analíticos) e envia para o Telegram"""
    global last_event_id
    
    # Na primeira execução, pega o ID do último evento para não enviar histórico antigo
    if last_event_id == 0:
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM events")
        last_event_id = cur.fetchone()[0]
        return

    cur.execute("""
        SELECT e.id, e.event_type, e.channel, e.description, e.severity, e.time,
               d.name as device_name, d.client_id, d.device_type, d.mac_address, d.serial_number, d.description, d.location
        FROM events e
        JOIN devices d ON d.id = e.device_id
        WHERE e.id > %s
        ORDER BY e.id ASC
    """, (last_event_id,))
    
    events = cur.fetchall()
    for ev in events:
        eid, etype, channel, desc, sev, etime, dname, cid, dtype, mac, sn, ddesc, dloc = ev
        last_event_id = eid

        if (etype or "").lower() == "edge_heartbeat":
            continue

        cooldown_key = f"event:{etype}"
        if (sev or "").lower() != "critical" and is_in_cooldown(dname, cooldown_key):
            continue
        
        # Prepara a mensagem de alerta analítico
        edname = escape_html(dname)
        etype_display = escape_html(etype.replace("_", " ").upper())
        edesc = escape_html(desc)
        etime_str = etime.astimezone(TIMEZONE_DISPLAY).strftime("%d/%m/%Y %H:%M:%S")
        eddesc = escape_html(ddesc) if ddesc else ""
        edloc = escape_html(dloc) if dloc else ""
        
        # Ícone baseado na severidade ou tipo
        icon = "🎬"
        if "pessoa" in etype.lower() or "human" in etype.lower(): icon = "👤"
        elif "veiculo" in etype.lower() or "car" in etype.lower(): icon = "🚗"
        elif sev.lower() == "critical": icon = "🚨"

        tg_tok, tg_cid, cl_email, cl_name, wa_inst, wa_tok, wa_num = get_client_config(cur, cid)
        
        msg = (
            f"{icon} <b>ALERTA ANALÍTICO</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📷 <b>{edname}</b>\n"
            f"Evento: <b>{etype_display}</b>\n"
            f"Canal: {channel}\n"
            f"Horário: {etime_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 {edesc}\n"
            + (f"📍 Local: {edloc}\n" if edloc else "")
            + (f"🏢 Empresa: {eddesc}\n" if eddesc else "")
            + f"👤 Cliente: {escape_html(cl_name or 'ETI SENTINEL')}"
        )
        
        send_telegram(msg, tg_tok, tg_cid)
        if cl_email:
            try:
                subject = f"[ETI SENTINEL] {etype_display} - {dname}"
                body = msg.replace("<b>", "").replace("</b>", "")
                send_email(cl_email, subject, body)
            except Exception as e:
                logger.error(f"Email send error: {e}")

        send_whatsapp(msg.replace("<b>", "*").replace("</b>", "*"), wa_inst, wa_tok, wa_num)
        
        set_cooldown(dname, cooldown_key)

def evaluate_once():
    # Batimento cardíaco com resumo rápido
    with get_conn() as conn:
        cur=conn.cursor()
        
        # 1. Checar dispositivos via Ping/TCP (Monitoramento Ativo)
        check_ping_devices(cur,conn)
        
        # 2. Checar dispositivos via Timeout (Monitoramento Passivo - Agent/Push)
        check_offline_devices(cur,conn)
        
        # 3. Analisar novos eventos (Intrusão, Movimento, etc.)
        check_new_events(cur,conn)
        
        # 4. Enviar resumo de status se necessário
        send_status_summary(cur)
        
        # 5. Avaliar gatilhos de métricas (CPU, RAM, etc.)
        evaluate_triggers(cur,conn)
        
        # Log de progresso
        cur.execute("SELECT COUNT(*) FROM devices")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM devices WHERE status='online'")
        online = cur.fetchone()[0]
        print(f"[{now_display()}] Monitoramento OK. Devices: {total} (Online: {online})")

def main():
    logger.info(f"{'='*52}")
    logger.info(f"  {APP_NAME} — Multi-tenant Monitor")
    logger.info(f"  interval={EVAL_INTERVAL}s | ping_timeout={PING_TIMEOUT}s")
    logger.info(f"  offline_timeout={OFFLINE_TIMEOUT}s | cooldown={ALERT_COOLDOWN}s")
    
    # Teste de envio IMEDIATO ao iniciar para diagnosticar credenciais
    if TG_TOKEN and TG_CHAT_ID:
        logger.info(f"Enviando alerta de teste de inicialização para {TG_CHAT_ID}...")
        test_msg = f"🔧 <b>{APP_NAME}</b>: Monitor de Alertas Reiniciado.\nVerificando conectividade... ✅"
        send_telegram(test_msg)
        send_whatsapp(test_msg.replace("<b>", "*").replace("</b>", "*"))
    else:
        logger.error("ERRO: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não configurados!")

    logger.info(f"  telegram={'ON' if TG_TOKEN else 'OFF'} | chat_id={TG_CHAT_ID[:5]}***")
    logger.info(f"  email={'ON' if SMTP_HOST else 'OFF'}")
    logger.info(f"{'='*52}")
    startup_msg = (
        f"🚀 <b>{APP_NAME} iniciado!</b>\n━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱ Checagem: <b>{EVAL_INTERVAL}s</b>\n📡 Ping: <b>{PING_TIMEOUT}s timeout</b>\n"
        f"📴 Offline timeout: <b>{OFFLINE_TIMEOUT}s</b>\n🔕 Cooldown: <b>{ALERT_COOLDOWN}s</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n✅ Multi-tenant ATIVO\n✅ Ping Monitor ATIVO\n✅ SNMP Monitor ATIVO\n"
        f"━━━━━━━━━━━━━━━━━━━━\n🕐 {now_str()} #etisentinel"
    )
    send_telegram(startup_msg)
    send_whatsapp(startup_msg.replace("<b>", "*").replace("</b>", "*"))
    while True:
        try: evaluate_once()
        except Exception as e: logger.exception(f"Error: {e}")
        time.sleep(EVAL_INTERVAL)

if __name__ == "__main__": main()
