import json
import logging
import os
import threading
import time
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple

import requests
from dotenv import load_dotenv


def _truthy(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "on", "active", "started"}:
        return True
    if s in {"0", "false", "no", "off", "inactive", "stopped"}:
        return False
    return None


def _deep_get(obj: Any, path: Tuple[str, ...]) -> Any:
    cur = obj
    for p in path:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            cur = getattr(cur, p, None)
    return cur


def _iter_simple_items(container: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if container is None:
        return out
    simple_items = getattr(container, "SimpleItem", None)
    if simple_items is None and isinstance(container, dict):
        simple_items = container.get("SimpleItem")
    if simple_items is None:
        return out
    if not isinstance(simple_items, list):
        simple_items = [simple_items]
    for it in simple_items:
        name = getattr(it, "Name", None) if not isinstance(it, dict) else it.get("Name")
        value = getattr(it, "Value", None) if not isinstance(it, dict) else it.get("Value")
        if name is not None:
            out[str(name)] = value
    return out


def _extract_notification(nm: Any) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    topic = _deep_get(nm, ("Topic", "_value_1")) or _deep_get(nm, ("Topic",)) or ""
    msg = _deep_get(nm, ("Message", "Message")) or _deep_get(nm, ("Message",)) or {}
    src = _deep_get(msg, ("Source",)) or {}
    data = _deep_get(msg, ("Data",)) or {}
    return str(topic), _iter_simple_items(src), _iter_simple_items(data)


def _normalize_event(topic: str, src: Dict[str, Any], data: Dict[str, Any]) -> Tuple[Optional[str], Optional[int], str, str]:
    t = (topic or "").lower()
    merged: Dict[str, Any] = {}
    merged.update({k.lower(): v for k, v in src.items()})
    merged.update({k.lower(): v for k, v in data.items()})

    state = _truthy(merged.get("state")) or _truthy(merged.get("value")) or _truthy(merged.get("active"))

    channel = None
    if merged.get("channel") is not None:
        try:
            channel = int(str(merged.get("channel")))
        except Exception:
            channel = None

    event_type = None
    severity = "info"
    description = ""

    if "videoloss" in t or ("video" in t and "loss" in t) or "signalloss" in t:
        event_type = "videoloss_started" if state is not False else "videoloss_stopped"
        severity = "warn"
    elif "tamper" in t or "shelteralarm" in t:
        event_type = "tamperdetection"
        severity = "warn"
    elif "motion" in t:
        event_type = "motion"
        severity = "info"
    elif "disk" in t and ("error" in t or "fail" in t):
        event_type = "diskerror"
        severity = "warn"
    elif "disk" in t and ("full" in t or "space" in t):
        event_type = "diskfull"
        severity = "warn"
    else:
        event_type = "vca"
        description = f"ONVIF: {topic} | src={json.dumps(src, ensure_ascii=False)} | data={json.dumps(data, ensure_ascii=False)}"

    return event_type, channel, description, severity


def _post_push(ingest_api_url: str, token: str, device_id: int, event_type: str, channel: int, description: str, severity: str) -> None:
    edge_push = _sanitize(os.getenv("EDGE_PUSH_URL") or "")
    url = edge_push or (ingest_api_url.rstrip("/") + "/push")
    payload: Dict[str, Any] = {
        "token": token,
        "device_id": int(device_id or 0),
        "event_type": event_type,
        "channel": channel,
        "severity": severity,
    }
    if description:
        payload["description"] = description
    requests.post(url, json=payload, headers={"x-event-source": "onvif"}, timeout=8)


def _get_channel_from_tokens(
    src: Dict[str, Any],
    data: Dict[str, Any],
    channel_map: Dict[str, Any],
    fallback_channel: Optional[int],
) -> int:
    if fallback_channel is not None and fallback_channel > 0:
        return fallback_channel
    merged = {}
    merged.update(src)
    merged.update(data)
    for k in ("VideoSourceConfigurationToken", "VideoSourceToken", "Source", "source", "InputToken", "Input"):
        v = merged.get(k)
        if v is None:
            continue
        if str(v) in channel_map:
            try:
                return int(channel_map[str(v)])
            except Exception:
                pass
        digits = "".join(ch for ch in str(v) if ch.isdigit())
        if digits:
            try:
                n = int(digits)
                if n > 0:
                    return n
            except Exception:
                pass
    return 0


def _run_device(
    cfg: Dict[str, Any],
    ingest_api_url: str,
    pull_timeout_seconds: int,
    message_limit: int,
    reconnect_seconds: int,
    stop_event: Optional[threading.Event],
) -> None:
    name = cfg.get("name") or cfg.get("host") or "onvif-device"
    host = cfg["host"]
    port = int(cfg.get("port") or 80)
    username = cfg.get("username") or ""
    password = cfg.get("password") or ""
    token = cfg["token"]
    channel_map = cfg.get("channel_map") or {}

    last_state: Dict[Tuple[str, int], Optional[bool]] = {}
    last_err: str = ""
    last_err_ts: float = 0.0
    backoff: float = float(max(1, reconnect_seconds))

    while True:
        if stop_event and stop_event.is_set():
            return
        try:
            from onvif import ONVIFCamera

            cam = ONVIFCamera(host, port, username, password)
            events = cam.create_events_service()
            sub = None
            last_sub_exc: Optional[Exception] = None
            for term in (None, "PT10M", "PT30M"):
                if stop_event and stop_event.is_set():
                    return
                try:
                    if term is None:
                        sub = events.CreatePullPointSubscription()
                    else:
                        sub = events.CreatePullPointSubscription(InitialTerminationTime=term)
                    break
                except Exception as e:
                    last_sub_exc = e
                    sub = None
                    time.sleep(0.4)
            if sub is None:
                raise RuntimeError(f"Subscribe Creation Failed: {last_sub_exc}")
            addr = _deep_get(sub, ("SubscriptionReference", "Address", "_value_1")) or _deep_get(
                sub, ("SubscriptionReference", "Address")
            )
            if not addr:
                raise RuntimeError("SubscriptionReference.Address não retornou um endereço válido")

            zeep_client = getattr(events, "zeep_client", None) or getattr(events, "_client", None)
            if zeep_client is None:
                raise RuntimeError("Events zeep_client não disponível")
            pullpoint = zeep_client.create_service(
                "{http://www.onvif.org/ver10/events/wsdl}PullPointSubscriptionBinding",
                str(addr),
            )

            logging.info("[%s] ONVIF conectado. Escutando eventos...", name)
            backoff = float(max(1, reconnect_seconds))
            while True:
                if stop_event and stop_event.is_set():
                    return
                r = pullpoint.PullMessages(Timeout=timedelta(seconds=pull_timeout_seconds), MessageLimit=message_limit)
                nms = getattr(r, "NotificationMessage", None) or []
                if not isinstance(nms, list):
                    nms = [nms]
                for nm in nms:
                    if stop_event and stop_event.is_set():
                        return
                    try:
                        topic, src, data = _extract_notification(nm)
                        event_type, channel_hint, description, severity = _normalize_event(topic, src, data)
                        if not event_type:
                            continue
                        channel = _get_channel_from_tokens(src, data, channel_map, channel_hint)

                        state = _truthy((data.get("State") or data.get("Value") or data.get("Active")))
                        key = (event_type, channel)
                        if key in last_state and state is not None and last_state[key] == state:
                            continue
                        last_state[key] = state

                        _post_push(ingest_api_url, token, device_id, event_type, channel, description, severity)
                        logging.info("[%s] Evento enviado: %s ch=%s", name, event_type, channel)
                    except Exception as e:
                        logging.warning("[%s] Falha ao processar evento: %s", name, e)
        except Exception as e:
            err = str(e)
            now = time.time()
            if err != last_err or (now - last_err_ts) > 60:
                logging.error("[%s] ONVIF desconectado/erro: %s", name, e)
                last_err = err
                last_err_ts = now
            time.sleep(backoff)
            backoff = min(backoff * 2.0, 120.0)


def _load_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _fetch_remote_devices(ingest_api_url: str, collector_key: str, client_id: Optional[int]) -> Dict[int, Dict[str, Any]]:
    url = ingest_api_url.rstrip("/") + "/collector/onvif-config"
    params = {}
    if client_id:
        params["client_id"] = client_id
    r = requests.get(url, headers={"x-collector-key": collector_key}, params=params, timeout=10)
    r.raise_for_status()
    items = r.json() or []
    out: Dict[int, Dict[str, Any]] = {}
    for it in items:
        did = int(it.get("device_id"))
        out[did] = {
            "enabled": True,
            "device_id": did,
            "name": it.get("name") or f"device-{did}",
            "host": it.get("host") or "",
            "port": int(it.get("port") or 80),
            "username": it.get("username") or "",
            "password": it.get("password") or "",
            "token": it.get("token") or "",
            "channel_map": it.get("channel_map") or {},
        }
    return out


def _cfg_sig(d: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "host": d.get("host"),
            "port": d.get("port"),
            "username": d.get("username"),
            "password": d.get("password"),
            "token": d.get("token"),
            "channel_map": d.get("channel_map") or {},
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def main() -> None:
    here = os.path.dirname(__file__)
    load_dotenv(os.path.join(here, ".env"), override=True)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(message)s")

    cfg_path = os.getenv("ONVIF_CONFIG", os.path.join(os.path.dirname(__file__), "config.json"))
    cfg = _load_config(cfg_path)

    ingest_api_url = os.getenv("INGEST_API_URL") or cfg.get("ingest_api_url") or "http://localhost:3000"
    pull_timeout_seconds = int(os.getenv("PULL_TIMEOUT_SECONDS") or cfg.get("pull_timeout_seconds") or 10)
    message_limit = int(os.getenv("MESSAGE_LIMIT") or cfg.get("message_limit") or 10)
    reconnect_seconds = int(os.getenv("RECONNECT_SECONDS") or cfg.get("reconnect_seconds") or 5)

    remote = str(os.getenv("ONVIF_REMOTE") or cfg.get("remote") or "").strip().lower() in {"1", "true", "yes", "on"}
    collector_key = os.getenv("COLLECTOR_KEY") or ""
    client_id = os.getenv("CLIENT_ID")
    client_id_int = int(client_id) if client_id and str(client_id).isdigit() else None
    refresh_seconds = int(os.getenv("REMOTE_REFRESH_SECONDS") or cfg.get("remote_refresh_seconds") or 60)

    threads = []
    if remote:
        if not collector_key:
            raise SystemExit("COLLECTOR_KEY obrigatório para modo remoto")

        stop_map: Dict[int, threading.Event] = {}
        sig_map: Dict[int, str] = {}

        while True:
            try:
                devices_map = _fetch_remote_devices(ingest_api_url, collector_key, client_id_int)

                for did, d in devices_map.items():
                    sig = _cfg_sig(d)
                    if did in sig_map and sig_map[did] == sig:
                        continue

                    if did in stop_map:
                        stop_map[did].set()
                        del stop_map[did]

                    ev = threading.Event()
                    stop_map[did] = ev
                    sig_map[did] = sig

                    t = threading.Thread(
                        target=_run_device,
                        args=(d, ingest_api_url, pull_timeout_seconds, message_limit, reconnect_seconds, ev),
                        daemon=True,
                    )
                    t.start()
                    threads.append(t)

                for did in list(stop_map.keys()):
                    if did not in devices_map:
                        stop_map[did].set()
                        del stop_map[did]
                        sig_map.pop(did, None)
            except Exception as e:
                logging.error("Falha ao buscar config remota ONVIF: %s", e)

            time.sleep(max(5, refresh_seconds))
    else:
        devices = cfg.get("devices") or []
        for d in devices:
            if d.get("enabled", True) is False:
                continue
            t = threading.Thread(
                target=_run_device,
                args=(d, ingest_api_url, pull_timeout_seconds, message_limit, reconnect_seconds, None),
                daemon=True,
            )
            t.start()
            threads.append(t)

        if not threads:
            raise SystemExit("Nenhum device ONVIF habilitado no config")

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
