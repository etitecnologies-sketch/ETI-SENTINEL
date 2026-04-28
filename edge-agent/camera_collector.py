import concurrent.futures
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
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
    v = v.replace("`", "").replace("´", "").replace('"', "").replace("'", "").strip()
    return v


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
                    if url.startswith("http") and url not in xaddrs:
                        xaddrs.append(url)
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
                a = _sanitize(addr)
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


def fetch_onvif_camera_details(xaddr: str, user: str, password: str, timeout: float) -> Dict[str, Any]:
    xaddr_s = _sanitize(xaddr)
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
    }

    if not _HAS_ONVIF:
        out["error"] = "onvif-zeep not installed"
        return out

    try:
        cam = ONVIFCamera(host, port, _sanitize(user), _sanitize(password))
        try:
            cam.devicemgmt.service_client.settings.strict = False
        except Exception:
            pass

        try:
            dev = cam.devicemgmt.GetDeviceInformation()
            out["manufacturer"] = _sanitize(getattr(dev, "Manufacturer", "") or "")
            out["model"] = _sanitize(getattr(dev, "Model", "") or "")
            out["firmware"] = _sanitize(getattr(dev, "FirmwareVersion", "") or "")
            out["serial"] = _sanitize(getattr(dev, "SerialNumber", "") or "")
        except Exception:
            pass

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
        except Exception:
            pass

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

        out["status"] = "online"
        return out
    except Exception as e:
        out["error"] = _sanitize(str(e))
        return out


def discover_cameras(timeout: float = 6.0, user: str = "admin", password: str = "", workers: int = 32) -> List[Dict[str, Any]]:
    xaddrs = ws_discover_onvif_xaddrs(timeout)
    if not xaddrs:
        return []

    results: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
        futs = [ex.submit(fetch_onvif_camera_details, xa, user, password, timeout) for xa in xaddrs]
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
