import concurrent.futures
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


try:
    from onvif import ONVIFCamera  # type: ignore
    _HAS_ONVIF = True
except Exception:
    _HAS_ONVIF = False

try:
    from wsdiscovery.discovery import ThreadedWSDiscovery as WSDiscovery  # type: ignore
    from wsdiscovery import QName  # type: ignore
    _HAS_WSD = True
except Exception:
    _HAS_WSD = False


def _sanitize(s: Any) -> str:
    v = str(s or "").strip()
    v = v.replace("`", "").replace("´", "").replace("“", "").replace("”", "").replace("‘", "").replace("’", "").replace('"', "").replace("'", "").strip()
    return v


def _extract_http_url(s: Any) -> str:
    t = str(s or "")
    m = re.search(r"(https?://[^\s\"'`<>]+)", t, flags=re.IGNORECASE)
    if not m:
        return _sanitize(s)
    return _sanitize(m.group(1))


def _wsd_manual(timeout: float) -> List[str]:
    probe = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
        ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"'
        ' xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        "<e:Header>"
        "<w:MessageID>uuid:eti-sentinel-probe</w:MessageID>"
        "<w:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>"
        "<w:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>"
        "</e:Header>"
        "<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>"
        "</e:Envelope>"
    )
    mcast = ("239.255.255.250", 3702)
    xaddrs: List[str] = []

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        sock.settimeout(0.7)
        sock.sendto(probe.encode("utf-8"), mcast)

        deadline = time.time() + max(1.0, float(timeout))
        while time.time() < deadline:
            try:
                data, _ = sock.recvfrom(65535)
            except socket.timeout:
                try:
                    sock.sendto(probe.encode("utf-8"), mcast)
                except Exception:
                    pass
                continue
            except Exception:
                continue

            text = data.decode(errors="ignore")
            matches = re.findall(r"<[^>]*XAddrs[^>]*>(.*?)</[^>]*XAddrs[^>]*>", text, flags=re.IGNORECASE)
            for m in matches:
                for url in _sanitize(m).split():
                    u = _extract_http_url(url)
                    if u.startswith("http") and u not in xaddrs:
                        xaddrs.append(u)
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass

    return xaddrs


def _wsd_lib(timeout: float) -> List[str]:
    if not _HAS_WSD:
        return []
    xaddrs: List[str] = []
    wsd = None
    try:
        wsd = WSDiscovery()
        wsd.start()
        services = wsd.searchServices(
            types=[QName("http://www.onvif.org/ver10/network/wsdl", "NetworkVideoTransmitter")],
            timeout=timeout,
        )
        for svc in services:
            for addr in svc.getXAddrs():
                a = _extract_http_url(addr)
                if a and a not in xaddrs:
                    xaddrs.append(a)
    except Exception:
        return []
    finally:
        try:
            if wsd:
                wsd.stop()
        except Exception:
            pass
    return xaddrs


def ws_discover_onvif_xaddrs(timeout: float) -> List[str]:
    xaddrs = _wsd_lib(timeout)
    if xaddrs:
        return xaddrs
    return _wsd_manual(timeout)


@dataclass
class CameraProfile:
    token: str
    name: str
    encoding: str
    width: Optional[int]
    height: Optional[int]
    fps: Optional[int]
    rtsp_url_template: str


def _to_profile(p: Any, rtsp: str) -> CameraProfile:
    enc = ""
    w = None
    h = None
    fps = None

    try:
        ve = getattr(p, "VideoEncoderConfiguration", None)
        if ve:
            enc = str(getattr(ve, "Encoding", "") or "")
            res = getattr(ve, "Resolution", None)
            if res:
                w = int(getattr(res, "Width", 0) or 0) or None
                h = int(getattr(res, "Height", 0) or 0) or None
            rc = getattr(ve, "RateControl", None)
            if rc:
                fps_v = getattr(rc, "FrameRateLimit", None)
                fps = int(fps_v) if fps_v is not None else None
    except Exception:
        pass

    return CameraProfile(
        token=str(getattr(p, "token", "") or ""),
        name=str(getattr(p, "Name", "") or ""),
        encoding=enc,
        width=w,
        height=h,
        fps=fps,
        rtsp_url_template=rtsp,
    )


def _stream_uri_template(media: Any, profile_token: str) -> str:
    resp = media.GetStreamUri(
        {
            "StreamSetup": {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}},
            "ProfileToken": profile_token,
        }
    )
    uri = _sanitize(getattr(resp, "Uri", "") or "")
    if not uri.startswith("rtsp://"):
        return uri
    if "@" in uri:
        return uri
    return uri.replace("rtsp://", "rtsp://{username}:{password}@", 1)


def _looks_like_auth_error(msg: str) -> bool:
    m = (msg or "").lower()
    return (
        ("notauthorized" in m)
        or ("not authorized" in m)
        or ("sender not authorized" in m)
        or ("unauthorized" in m)
        or ("invalid username" in m)
        or ("invalid password" in m)
        or ("bad username" in m)
        or ("bad password" in m)
        or ("401" in m)
        or ("forbidden" in m)
        or ("403" in m)
    )


def fetch_onvif_camera_details(xaddr: str, user: str, password: str, timeout: float) -> Dict[str, Any]:
    xaddr_s = _extract_http_url(xaddr)
    parsed = urlparse(xaddr_s)
    host = parsed.hostname or ""
    port = parsed.port or 80

    out: Dict[str, Any] = {
        "xaddr": xaddr_s,
        "ip": host,
        "port": port,
        "status": "error",
        "manufacturer": "",
        "model": "",
        "firmware": "",
        "serial": "",
        "profiles": [],
        "ptz": False,
        "device_info_error": "",
        "profiles_error": "",
    }

    if not host:
        out["error"] = "invalid_xaddr"
        return out

    if not _HAS_ONVIF:
        out["error"] = "onvif-zeep not installed"
        return out

    try:
        cam = ONVIFCamera(host, port, _sanitize(user), _sanitize(password))
        try:
            cam.devicemgmt.service_client.settings.strict = False
        except Exception:
            pass

        got_any_details = False
        try:
            dev = cam.devicemgmt.GetDeviceInformation()
            out["manufacturer"] = _sanitize(getattr(dev, "Manufacturer", "") or "")
            out["model"] = _sanitize(getattr(dev, "Model", "") or "")
            out["firmware"] = _sanitize(getattr(dev, "FirmwareVersion", "") or "")
            out["serial"] = _sanitize(getattr(dev, "SerialNumber", "") or "")
            got_any_details = True
        except Exception as e:
            msg = _sanitize(str(e))
            out["device_info_error"] = msg
            if _looks_like_auth_error(msg):
                out["status"] = "auth_failed"
                out["error"] = msg
                return out

        profiles: List[CameraProfile] = []
        try:
            media = cam.create_media_service()
            ps = media.GetProfiles() or []
            for p in ps:
                try:
                    rtsp = _stream_uri_template(media, str(getattr(p, "token", "") or ""))
                except Exception:
                    rtsp = ""
                profiles.append(_to_profile(p, rtsp))
            got_any_details = got_any_details or (len(ps) > 0)
        except Exception as e:
            try:
                if hasattr(cam, "create_media2_service"):
                    media2 = cam.create_media2_service()
                    ps2 = media2.GetProfiles() or []
                    for p in ps2:
                        try:
                            rtsp = _stream_uri_template(media2, str(getattr(p, "token", "") or ""))
                        except Exception:
                            rtsp = ""
                        profiles.append(_to_profile(p, rtsp))
                    got_any_details = got_any_details or (len(ps2) > 0)
                else:
                    raise RuntimeError("media service unavailable")
            except Exception as e:
                msg = _sanitize(str(e))
                out["profiles_error"] = msg
                if _looks_like_auth_error(msg):
                    out["status"] = "auth_failed"
                    out["error"] = msg
                    return out
            if not out["profiles_error"]:
                msg = _sanitize(str(e))
                out["profiles_error"] = msg
                if _looks_like_auth_error(msg):
                    out["status"] = "auth_failed"
                    out["error"] = msg
                    return out

        out["profiles"] = [
            {
                "token": pr.token,
                "name": pr.name,
                "encoding": pr.encoding,
                "width": pr.width,
                "height": pr.height,
                "fps": pr.fps,
                "rtsp_url_template": pr.rtsp_url_template,
            }
            for pr in profiles
            if pr.token
        ]

        try:
            ptz = cam.create_ptz_service()
            nodes = ptz.GetNodes() or []
            out["ptz"] = len(nodes) > 0
        except Exception:
            out["ptz"] = False

        out["status"] = "online" if got_any_details else "reachable"
        return out
    except Exception as e:
        msg = _sanitize(str(e))
        out["error"] = msg
        out["status"] = "auth_failed" if _looks_like_auth_error(msg) else "error"
        return out


def discover_cameras(
    timeout: float = 6.0,
    user: str = "admin",
    password: str = "",
    workers: int = 32,
    creds_by_ip: Optional[Dict[str, List[Dict[str, str]]]] = None,
    max_cred_tries: int = 2,
) -> List[Dict[str, Any]]:
    xaddrs = ws_discover_onvif_xaddrs(timeout)
    if not xaddrs:
        return []

    def pick_creds(ip: str) -> List[tuple[str, str, str]]:
        out: List[tuple[str, str, str]] = []
        if creds_by_ip and ip in creds_by_ip:
            for c in creds_by_ip.get(ip) or []:
                u = _sanitize(c.get("user") or "")
                p = _sanitize(c.get("password") or "")
                if not u:
                    continue
                out.append((u, p, "remote"))
        u0 = _sanitize(user)
        p0 = _sanitize(password)
        if u0:
            out.append((u0, p0, "request"))
        seen = set()
        dedup: List[tuple[str, str, str]] = []
        for u, p, src in out:
            k = u + "\n" + p + "\n" + src
            if k in seen:
                continue
            seen.add(k)
            dedup.append((u, p, src))
        return dedup[: max(1, int(max_cred_tries))]

    def fetch_for_xaddr(xa: str) -> Dict[str, Any]:
        x = _extract_http_url(xa)
        ip = urlparse(x).hostname or ""
        creds = pick_creds(ip)
        last: Optional[Dict[str, Any]] = None
        for u, p, src in creds:
            r = fetch_onvif_camera_details(x, u, p, timeout)
            r["used_username"] = u
            r["creds_source"] = src
            last = r
            st = str(r.get("status") or "")
            if st == "online":
                return r
            if st == "reachable" and (r.get("profiles") or r.get("manufacturer") or r.get("model")):
                return r
        return last or {"xaddr": x, "ip": ip, "status": "error", "error": "no_result"}

    results: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
        futs = [ex.submit(fetch_for_xaddr, xa) for xa in xaddrs]
        for f in concurrent.futures.as_completed(futs):
            try:
                r = f.result()
                if r:
                    results.append(r)
            except Exception:
                continue

    seen = set()
    out = []
    for r in results:
        k = (r.get("ip") or "") + "|" + (r.get("xaddr") or "")
        if not k.strip() or k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out
