import concurrent.futures
import ipaddress
import os
import re
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil
import requests
from dotenv import load_dotenv


def _sanitize(s: Any) -> str:
    v = str(s or "").strip()
    v = v.replace("`", "").replace('"', "").replace("'", "").strip()
    return v


def _sanitize_base_url(url: str) -> str:
    u = _sanitize(url)
    if not u:
        return u
    if not u.startswith("http://") and not u.startswith("https://"):
        u = "https://" + u
    return u.rstrip("/")


def _bool(v: Any) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _get_agent_id() -> str:
    return _sanitize(os.getenv("AGENT_ID") or socket.gethostname())


def _ping(ip: str, timeout_ms: int) -> bool:
    try:
        if os.name == "nt":
            args = ["ping", "-n", "1", "-w", str(int(timeout_ms)), ip]
        else:
            args = ["ping", "-c", "1", "-W", str(max(1, int(timeout_ms / 1000))), ip]
        p = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=max(2, int(timeout_ms / 1000) + 2))
        return p.returncode == 0
    except Exception:
        return False


def _tcp_open(ip: str, port: int, timeout_s: float) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout_s)
        rc = s.connect_ex((ip, int(port)))
        return rc == 0
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _arp_mac(ip: str) -> str:
    if not ip:
        return ""
    try:
        if os.name == "nt":
            p = subprocess.run(["arp", "-a", ip], capture_output=True, text=True, timeout=2)
            txt = (p.stdout or "") + "\n" + (p.stderr or "")
            m = re.search(rf"\b{re.escape(ip)}\s+([0-9a-fA-F:-]{{11,17}})\b", txt)
            if m:
                return m.group(1).replace("-", ":").lower()
            return ""
        p = subprocess.run(["ip", "neigh", "show", ip], capture_output=True, text=True, timeout=2)
        txt = (p.stdout or "") + "\n" + (p.stderr or "")
        m = re.search(r"lladdr\s+([0-9a-fA-F:]{17})", txt)
        if m:
            return m.group(1).lower()
        return ""
    except Exception:
        return ""


def _guess_type(open_ports: Set[int]) -> str:
    if 554 in open_ports:
        return "camera"
    if 9100 in open_ports:
        return "printer"
    if 3389 in open_ports:
        return "windows"
    if 22 in open_ports:
        return "server"
    if 161 in open_ports:
        return "snmp"
    return "other"


def _networks_to_scan() -> List[ipaddress.IPv4Network]:
    env = _sanitize(os.getenv("DISCOVERY_SUBNETS") or "")
    if env:
        out = []
        for part in env.split(","):
            p = part.strip()
            if not p:
                continue
            try:
                out.append(ipaddress.IPv4Network(p, strict=False))
            except Exception:
                continue
        return out

    nets: List[ipaddress.IPv4Network] = []
    for ifname, addrs in psutil.net_if_addrs().items():
        stats = psutil.net_if_stats().get(ifname)
        if stats and not stats.isup:
            continue
        for a in addrs:
            if a.family != socket.AF_INET:
                continue
            ip = a.address
            mask = a.netmask
            if not ip or not mask:
                continue
            try:
                iface = ipaddress.IPv4Interface(f"{ip}/{mask}")
            except Exception:
                continue
            if iface.ip.is_loopback or iface.ip.is_link_local:
                continue
            if not iface.ip.is_private:
                continue
            net = iface.network
            if net.prefixlen < 24:
                net = ipaddress.IPv4Network(f"{iface.ip}/24", strict=False)
            nets.append(net)
    seen = set()
    out = []
    for n in nets:
        k = str(n)
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out


def _resolve_hostname(ip: str) -> str:
    if not ip:
        return ""
    try:
        host, _, _ = socket.gethostbyaddr(ip)
        return _sanitize(host)
    except Exception:
        return ""


def _probe_ws_discovery(timeout_seconds: int) -> Dict[str, str]:
    try:
        import uuid

        msg_id = f"uuid:{uuid.uuid4()}"
        probe = f"""<?xml version="1.0" encoding="UTF-8"?>
<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
  <e:Header>
    <w:MessageID>{msg_id}</w:MessageID>
    <w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>
    <w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>
  </e:Header>
  <e:Body>
    <d:Probe>
      <d:Types>dn:NetworkVideoTransmitter</d:Types>
    </d:Probe>
  </e:Body>
</e:Envelope>""".encode("utf-8")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.4)
        try:
            sock.sendto(probe, ("239.255.255.250", 3702))
        except Exception:
            sock.close()
            return {}

        found: Dict[str, str] = {}
        deadline = time.time() + max(1, timeout_seconds)
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except Exception:
                break
            ip = addr[0]
            text = data.decode("utf-8", errors="ignore")
            xaddrs = ""
            if "XAddrs" in text:
                try:
                    start = text.index("<XAddrs>") + len("<XAddrs>")
                    end = text.index("</XAddrs>")
                    xaddrs = text[start:end].strip()
                except Exception:
                    xaddrs = ""
            if xaddrs:
                found[ip] = xaddrs
        sock.close()
        return found
    except Exception:
        return {}


def _scan_host(
    ip: str,
    ports: List[int],
    ping_timeout_ms: int,
    port_timeout_s: float,
    require_ping: bool,
    resolve_dns: bool,
) -> Optional[Dict[str, Any]]:
    ping_ok = _ping(ip, ping_timeout_ms)
    if require_ping and not ping_ok:
        return None

    open_ports: Set[int] = set()
    for p in ports:
        if _tcp_open(ip, p, port_timeout_s):
            open_ports.add(int(p))

    if (not ping_ok) and (len(open_ports) == 0):
        return None

    mac = _arp_mac(ip)
    guess = _guess_type(open_ports)
    hostname = _resolve_hostname(ip) if resolve_dns else ""
    return {
        "ip_address": ip,
        "mac_address": mac,
        "hostname": hostname,
        "vendor": "",
        "guess_type": guess,
        "open_ports": sorted(open_ports),
        "onvif_xaddrs": "",
        "raw": {"source": "ping+ports", "ping": ping_ok},
    }


def _post_discovery(ingest_api_url: str, collector_key: str, agent_id: str, client_id: Optional[int], items: List[Dict[str, Any]]) -> None:
    url = ingest_api_url.rstrip("/") + "/collector/discovery"
    body: Dict[str, Any] = {"agent_id": agent_id, "items": items}
    if client_id:
        body["client_id"] = client_id
    requests.post(url, headers={"x-collector-key": collector_key}, json=body, timeout=20)


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(here, ".env"))

    ingest_api_url = _sanitize_base_url(os.getenv("INGEST_API_URL") or "http://localhost:3000")
    collector_key = _sanitize(os.getenv("COLLECTOR_KEY") or "")
    client_id = _sanitize(os.getenv("CLIENT_ID") or "")
    client_id_int = int(client_id) if client_id.isdigit() else None
    agent_id = _get_agent_id()

    interval_seconds = int(os.getenv("DISCOVERY_INTERVAL_SECONDS") or 300)
    ping_timeout_ms = int(os.getenv("DISCOVERY_PING_TIMEOUT_MS") or 700)
    port_timeout_s = float(os.getenv("DISCOVERY_PORT_TIMEOUT_S") or 0.25)
    max_hosts = int(os.getenv("DISCOVERY_MAX_HOSTS") or 512)
    workers = int(os.getenv("DISCOVERY_WORKERS") or 120)
    ports_csv = _sanitize(os.getenv("DISCOVERY_PORTS") or "80,443,554,22,161,8080,8000,3000,8899")
    ports = [int(x) for x in ports_csv.split(",") if x.strip().isdigit()]
    enable_ws_discovery = _bool(os.getenv("DISCOVERY_ONVIF_WS") or "1")
    ws_timeout = int(os.getenv("DISCOVERY_WS_TIMEOUT_SECONDS") or 2)
    require_ping = _bool(os.getenv("DISCOVERY_REQUIRE_PING") or "1")
    resolve_dns = _bool(os.getenv("DISCOVERY_RESOLVE_DNS") or "1")
    include_self = _bool(os.getenv("DISCOVERY_INCLUDE_SELF") or "0")
    my_ips = {a.address for addrs in psutil.net_if_addrs().values() for a in addrs if getattr(a, "family", None) == socket.AF_INET}

    if not collector_key:
        raise SystemExit("COLLECTOR_KEY obrigatório")

    while True:
        items: List[Dict[str, Any]] = []
        by_ip: Dict[str, Dict[str, Any]] = {}

        nets = _networks_to_scan()
        hosts: List[str] = []
        for n in nets:
            for ip in n.hosts():
                s = str(ip)
                if (not include_self) and (s in my_ips):
                    continue
                hosts.append(s)
                if len(hosts) >= max_hosts:
                    break
            if len(hosts) >= max_hosts:
                break

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            futs = [ex.submit(_scan_host, ip, ports, ping_timeout_ms, port_timeout_s, require_ping, resolve_dns) for ip in hosts]
            for f in concurrent.futures.as_completed(futs):
                try:
                    r = f.result()
                    if not r:
                        continue
                    by_ip[r["ip_address"]] = r
                except Exception:
                    continue

        if enable_ws_discovery:
            onvif = _probe_ws_discovery(ws_timeout)
            for ip, xaddrs in onvif.items():
                if ip not in by_ip:
                    by_ip[ip] = {
                        "ip_address": ip,
                        "mac_address": "",
                        "hostname": "",
                        "vendor": "",
                        "guess_type": "camera",
                        "open_ports": [80],
                        "onvif_xaddrs": xaddrs,
                        "raw": {"source": "ws-discovery"},
                    }
                else:
                    by_ip[ip]["guess_type"] = by_ip[ip].get("guess_type") or "camera"
                    by_ip[ip]["onvif_xaddrs"] = xaddrs
                    raw = by_ip[ip].get("raw") or {}
                    raw["ws_discovery"] = True
                    by_ip[ip]["raw"] = raw

        items = list(by_ip.values())
        if items:
            try:
                _post_discovery(ingest_api_url, collector_key, agent_id, client_id_int, items)
            except Exception:
                pass

        time.sleep(max(30, interval_seconds))


if __name__ == "__main__":
    main()
