"""Multi-format subscription source fetcher and proxy parser."""

import base64
import json
import logging
import re
import time
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, unquote

import requests
import yaml

from .config import SourceConfig, SettingsConfig

logger = logging.getLogger(__name__)

# Standard proxy URI scheme prefixes
PROXY_SCHEMES = {"vmess://", "vless://", "trojan://", "ss://", "ssr://",
                  "hysteria2://", "hy2://", "hysteria://", "tuic://",
                  "socks5://", "http://", "https://", "socks://"}


def fetch_source(source: SourceConfig, settings: SettingsConfig) -> Optional[str]:
    """Fetch raw content from a subscription source URL with retry logic."""
    urls_to_try = [source.url]

    # For L3 sources with CDN fallback, add CDN URLs as fallback
    if source.fallback_to_cdn and settings.gh_proxies:
        parsed = urlparse(source.url)
        path = parsed.path
        if "raw.githubusercontent.com" in source.url:
            for proxy in settings.gh_proxies:
                urls_to_try.append(f"{proxy}{path}")

    last_error = None
    for attempt in range(settings.max_retries):
        for url in urls_to_try:
            try:
                headers = {
                    "User-Agent": "FreeNodes-Aggregator/1.0",
                    "Accept": "*/*",
                }
                resp = requests.get(
                    url, timeout=settings.request_timeout, headers=headers,
                    allow_redirects=True
                )
                if resp.status_code == 200:
                    logger.info(f"  [OK] {source.name} <- {url}")
                    return resp.text
                else:
                    logger.warning(f"  [{resp.status_code}] {source.name} <- {url}")
            except requests.RequestException as e:
                last_error = e
                logger.debug(f"  [ERR] {source.name} <- {url}: {e}")

        if attempt < settings.max_retries - 1:
            time.sleep(2 ** attempt)

    logger.error(f"  [FAIL] {source.name}: all URLs exhausted. Last error: {last_error}")
    return None


def parse_proxies(raw_content: str, fmt: str) -> List[Dict]:
    """Parse proxy nodes from raw content based on format type."""
    if fmt == "clash":
        return _parse_clash_yaml(raw_content)
    elif fmt == "v2ray":
        return _parse_v2ray_plain(raw_content)
    elif fmt == "base64":
        return _parse_base64(raw_content)
    elif fmt == "singbox":
        return _parse_singbox(raw_content)
    else:
        logger.warning(f"Unknown format: {fmt}, trying auto-detect")
        return _parse_auto(raw_content)


def _parse_clash_yaml(content: str) -> List[Dict]:
    """Parse proxies from Clash YAML format."""
    proxies = []
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            return proxies

        raw_proxies = data.get("proxies", [])
        if not raw_proxies:
            return proxies

        for p in raw_proxies:
            if not isinstance(p, dict):
                continue
            proxy_type = p.get("type", "").lower()
            if not proxy_type:
                continue

            # Canonicalize proxy dict
            proxy = {
                "name": str(p.get("name", "")),
                "type": proxy_type,
                "server": str(p.get("server", "")),
                "port": int(p.get("port", 0)),
            }

            # Protocol-specific fields
            if proxy_type in ("vmess", "vless"):
                proxy["uuid"] = str(p.get("uuid", ""))
                proxy["network"] = p.get("network", "tcp")
                proxy["tls"] = p.get("tls", False)
                proxy["skip-cert-verify"] = p.get("skip-cert-verify", False)
                proxy["udp"] = p.get("udp", True)
                if "alterId" in p:
                    proxy["alterId"] = p.get("alterId", 0)
                if "cipher" in p:
                    proxy["cipher"] = p.get("cipher", "auto")
                if "servername" in p:
                    proxy["servername"] = str(p["servername"])
                if "sni" in p:
                    proxy["servername"] = str(p["sni"])
                if "flow" in p:
                    proxy["flow"] = str(p["flow"])
                if "client-fingerprint" in p:
                    proxy["client-fingerprint"] = str(p["client-fingerprint"])
                if "public-key" in p:
                    proxy["public-key"] = str(p["public-key"])
                if "short-id" in p:
                    proxy["short-id"] = str(p["short-id"])

                # WS/HTTP/gRPC opts
                for opt_key in ("ws-opts", "http-opts", "grpc-opts", "reality-opts",
                                "hysteria-opts", "tuic-opts"):
                    if opt_key in p and isinstance(p[opt_key], dict):
                        proxy[opt_key] = p[opt_key]

            elif proxy_type == "trojan":
                proxy["password"] = str(p.get("password", ""))
                proxy["sni"] = str(p.get("sni", p.get("servername", "")))
                proxy["tls"] = p.get("tls", True)
                proxy["skip-cert-verify"] = p.get("skip-cert-verify", False)
                proxy["udp"] = p.get("udp", True)
                if "network" in p:
                    proxy["network"] = p["network"]
                if "alpn" in p:
                    proxy["alpn"] = p["alpn"]

                for opt_key in ("ws-opts", "grpc-opts"):
                    if opt_key in p and isinstance(p[opt_key], dict):
                        proxy[opt_key] = p[opt_key]

            elif proxy_type == "ss":
                proxy["cipher"] = str(p.get("cipher", ""))
                proxy["password"] = str(p.get("password", ""))
                proxy["udp"] = p.get("udp", True)

            elif proxy_type == "hysteria2":
                proxy["password"] = str(p.get("password", ""))
                proxy["sni"] = str(p.get("sni", p.get("servername", "")))
                proxy["skip-cert-verify"] = p.get("skip-cert-verify", False)
                proxy["udp"] = p.get("udp", True)
                if "obfs" in p:
                    proxy["obfs"] = p["obfs"]
                if "obfs-password" in p:
                    proxy["obfs-password"] = p["obfs-password"]

            elif proxy_type == "socks5":
                proxy["udp"] = p.get("udp", True)
                if "username" in p:
                    proxy["username"] = p["username"]
                if "password" in p:
                    proxy["password"] = p["password"]

            # Detect region from name
            proxy["_credit"] = 0  # will be set by collector
            proxies.append(proxy)

    except yaml.YAMLError as e:
        logger.warning(f"Failed to parse Clash YAML: {e}")

    return proxies


def _parse_v2ray_plain(content: str) -> List[Dict]:
    """Parse V2Ray plain text format (one URI per line, may be base64-encoded)."""
    # Try base64 decode first
    decoded = content
    try:
        decoded = base64.b64decode(content.strip()).decode("utf-8", errors="ignore")
        if not any(scheme in decoded for scheme in PROXY_SCHEMES):
            decoded = content  # wasn't actually base64 proxy data
    except Exception:
        decoded = content

    return _parse_uri_lines(decoded)


def _parse_base64(content: str) -> List[Dict]:
    """Parse base64-encoded subscription content."""
    return _parse_v2ray_plain(content)


def _parse_singbox(content: str) -> List[Dict]:
    """Parse SingBox JSON format and convert to standard proxy dicts."""
    proxies = []
    try:
        data = json.loads(content)
        outbounds = data.get("outbounds", [])
        for ob in outbounds:
            if ob.get("type") in ("direct", "block", "dns"):
                continue
            proxy = _singbox_to_proxy(ob)
            if proxy:
                proxies.append(proxy)
    except json.JSONDecodeError:
        pass
    return proxies


def _parse_auto(content: str) -> List[Dict]:
    """Auto-detect format and parse."""
    # Try Clash YAML first
    if content.strip().startswith(("{", "proxies:", "mixed-port:", "port:")):
        proxies = _parse_clash_yaml(content)
        if proxies:
            return proxies

    # Try V2Ray/subscription format
    if any(scheme in content for scheme in PROXY_SCHEMES):
        return _parse_uri_lines(content)

    # Try SingBox JSON
    if '"outbounds"' in content or '"type":' in content:
        return _parse_singbox(content)

    # Last resort: try base64 decode then parse
    return _parse_base64(content)


def _parse_uri_lines(text: str) -> List[Dict]:
    """Parse proxy URIs (one per line) into proxy dicts."""
    proxies = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        proxy = _parse_single_uri(line)
        if proxy:
            proxies.append(proxy)
    return proxies


def _parse_single_uri(uri: str) -> Optional[Dict]:
    """Parse a single proxy URI into a standardized proxy dict."""
    # Extract name from # fragment
    name = ""
    if "#" in uri:
        uri, name = uri.rsplit("#", 1)
        name = unquote(name).strip()

    uri = uri.strip()

    if uri.startswith("vmess://"):
        return _parse_vmess_uri(uri, name)
    elif uri.startswith("vless://"):
        return _parse_vless_uri(uri, name)
    elif uri.startswith("trojan://"):
        return _parse_trojan_uri(uri, name)
    elif uri.startswith("ss://"):
        return _parse_ss_uri(uri, name)
    elif uri.startswith("ssr://"):
        return _parse_ssr_uri(uri, name)
    elif uri.startswith(("hysteria2://", "hy2://")):
        return _parse_hysteria2_uri(uri, name)
    elif uri.startswith("hysteria://"):
        return _parse_hysteria_uri(uri, name)
    elif uri.startswith("tuic://"):
        return _parse_tuic_uri(uri, name)
    elif uri.startswith("socks5://"):
        return _parse_socks5_uri(uri, name)

    return None


def _parse_vmess_uri(uri: str, name: str) -> Optional[Dict]:
    """Parse vmess:// base64-encoded JSON URI."""
    try:
        b64 = uri[len("vmess://"):]
        # Handle potential padding issues
        b64 = b64.strip()
        padding = 4 - len(b64) % 4
        if padding != 4:
            b64 += "=" * padding
        data = json.loads(base64.b64decode(b64).decode("utf-8"))
        proxy = {
            "name": name or str(data.get("ps", data.get("add", ""))),
            "type": "vmess",
            "server": str(data.get("add", "")),
            "port": int(data.get("port", 0)),
            "uuid": str(data.get("id", "")),
            "alterId": int(data.get("aid", 0)),
            "cipher": data.get("scy", "auto"),
            "network": data.get("net", "tcp"),
            "tls": data.get("tls", "") == "tls",
            "skip-cert-verify": False,
            "udp": True,
            "_credit": 3,
        }
        if data.get("host"):
            proxy["ws-opts"] = {
                "path": data.get("path", "/"),
                "headers": {"Host": data["host"]},
            }
        elif data.get("path"):
            proxy["ws-opts"] = {"path": data["path"]}
        if data.get("sni"):
            proxy["servername"] = data["sni"]
        return proxy
    except Exception:
        return None


def _parse_vless_uri(uri: str, name: str) -> Optional[Dict]:
    """Parse vless:// UUID@server:port?params#name URI."""
    try:
        rest = uri[len("vless://"):]
        uuid, rest = rest.split("@", 1)
        host_part, query = rest.split("?", 1) if "?" in rest else (rest, "")
        server, port_str = host_part.rsplit(":", 1) if ":" in host_part else (host_part, "443")

        params = {}
        if query:
            for kv in query.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[unquote(k)] = unquote(v)

        proxy = {
            "name": name or f"{server}:{port_str}",
            "type": "vless",
            "server": server.strip("[]"),
            "port": int(port_str),
            "uuid": uuid,
            "network": params.get("type", "tcp"),
            "tls": params.get("security", "") == "tls",
            "skip-cert-verify": params.get("allowInsecure") == "1",
            "servername": params.get("sni", ""),
            "flow": params.get("flow", ""),
            "client-fingerprint": params.get("fp", ""),
            "udp": True,
            "_credit": 3,
        }
        if "publicKey" in params:
            proxy["public-key"] = params["publicKey"]
        if "shortId" in params:
            proxy["short-id"] = params["shortId"]

        # Transport opts
        if params.get("type") == "ws" and "path" in params:
            proxy["ws-opts"] = {"path": params["path"]}
            if "host" in params:
                proxy["ws-opts"]["headers"] = {"Host": params["host"]}
        elif params.get("type") == "grpc" and "serviceName" in params:
            proxy["grpc-opts"] = {"grpc-service-name": params["serviceName"]}

        return proxy
    except Exception:
        return None


def _parse_trojan_uri(uri: str, name: str) -> Optional[Dict]:
    """Parse trojan:// password@server:port?params#name URI."""
    try:
        rest = uri[len("trojan://"):]
        password, rest = rest.split("@", 1)
        host_part, query = rest.split("?", 1) if "?" in rest else (rest, "")
        server, port_str = host_part.rsplit(":", 1) if ":" in host_part else (host_part, "443")

        params = {}
        if query:
            for kv in query.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[unquote(k)] = unquote(v)

        proxy = {
            "name": name or f"{server}:{port_str}",
            "type": "trojan",
            "server": server.strip("[]"),
            "port": int(port_str),
            "password": unquote(password),
            "sni": params.get("sni", ""),
            "tls": True,
            "skip-cert-verify": params.get("allowInsecure") == "1",
            "udp": True,
            "_credit": 3,
        }
        if params.get("type") == "ws":
            proxy["network"] = "ws"
            proxy["ws-opts"] = {
                "path": params.get("path", "/"),
            }
            if "host" in params:
                proxy["ws-opts"]["headers"] = {"Host": params["host"]}
        return proxy
    except Exception:
        return None


def _parse_ss_uri(uri: str, name: str) -> Optional[Dict]:
    """Parse ss:// base64(method:password)@server:port or ss:// base64(method:password@server:port)."""
    try:
        rest = uri[len("ss://"):]
        # SIP002 format: ss:// base64(method:password) @server:port
        if "@" in rest:
            userinfo, hostpart = rest.split("@", 1)
        else:
            # Legacy format: ss:// base64(method:password@server:port)
            try:
                decoded_full = base64.urlsafe_b64decode(rest + "=" * (4 - len(rest) % 4))
                decoded = decoded_full.decode("utf-8")
                userinfo, hostpart = decoded.split("@", 1)
            except Exception:
                return None

        # Decode userinfo
        if ":" in userinfo:
            try:
                padding = 4 - len(userinfo) % 4
                if padding != 4:
                    userinfo += "=" * padding
                decoded_info = base64.urlsafe_b64decode(userinfo).decode("utf-8")
                method, password = decoded_info.split(":", 1)
            except Exception:
                method, password = userinfo.split(":", 1)
        else:
            method, password = "", ""

        server, port_str = hostpart.rsplit(":", 1) if ":" in hostpart else (hostpart, "8388")

        return {
            "name": name or f"{server}:{port_str}",
            "type": "ss",
            "server": server.strip("[]"),
            "port": int(port_str.split("?")[0].split("#")[0]),
            "cipher": method,
            "password": password.split("?")[0].split("#")[0],
            "udp": True,
            "_credit": 3,
        }
    except Exception:
        return None


def _parse_ssr_uri(uri: str, name: str) -> Optional[Dict]:
    """Parse ssr:// base64 encoded URI."""
    try:
        b64 = uri[len("ssr://"):]
        padding = 4 - len(b64) % 4
        if padding != 4:
            b64 += "=" * padding
        decoded = base64.urlsafe_b64decode(b64).decode("utf-8")

        # ssr://server:port:protocol:method:obfs:base64pass/?params
        # Remove ssr:// prefix if still present after decode
        if decoded.startswith("ssr://"):
            decoded = decoded[len("ssr://"):]

        main_part, params_str = decoded.split("/?", 1) if "/?" in decoded else (decoded, "")
        parts = main_part.split(":")
        if len(parts) < 6:
            return None

        server, port, protocol, method, obfs, b64pass = parts[:6]

        try:
            padding = 4 - len(b64pass) % 4
            if padding != 4:
                b64pass += "=" * padding
            password = base64.urlsafe_b64decode(b64pass).decode("utf-8")
        except Exception:
            password = b64pass

        params = {}
        if params_str:
            for kv in params_str.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[k] = v

        # Decode base64 params
        for k in ("obfsparam", "protoparam", "remarks", "group"):
            if k in params:
                try:
                    v = params[k]
                    padding = 4 - len(v) % 4
                    if padding != 4:
                        v += "=" * padding
                    params[k] = base64.urlsafe_b64decode(v).decode("utf-8")
                except Exception:
                    pass

        return {
            "name": name or params.get("remarks", f"{server}:{port}"),
            "type": "ssr",
            "server": server,
            "port": int(port),
            "cipher": method,
            "password": password,
            "protocol": protocol,
            "obfs": obfs,
            "protocol-param": params.get("protoparam", ""),
            "obfs-param": params.get("obfsparam", ""),
            "udp": True,
            "_credit": 3,
        }
    except Exception:
        return None


def _parse_hysteria2_uri(uri: str, name: str) -> Optional[Dict]:
    """Parse hysteria2:// or hy2:// password@server:port?params#name."""
    try:
        if uri.startswith("hysteria2://"):
            rest = uri[len("hysteria2://"):]
        else:
            rest = uri[len("hy2://"):]

        password, rest = rest.split("@", 1)
        host_part, params_str = rest.split("?", 1) if "?" in rest else (rest, "")
        server, port_str = host_part.rsplit(":", 1) if ":" in host_part else (host_part, "443")

        params = {}
        if params_str:
            for kv in params_str.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[unquote(k)] = unquote(v)

        return {
            "name": name or f"{server}:{port_str}",
            "type": "hysteria2",
            "server": server.strip("[]"),
            "port": int(port_str),
            "password": unquote(password),
            "sni": params.get("sni", server),
            "skip-cert-verify": params.get("insecure") == "1",
            "udp": True,
            "_credit": 3,
        }
    except Exception:
        return None


def _parse_hysteria_uri(uri: str, name: str) -> Optional[Dict]:
    """Parse hysteria:// server:port?params#name."""
    try:
        rest = uri[len("hysteria://"):]
        host_part, params_str = rest.split("?", 1) if "?" in rest else (rest, "")
        server, port_str = host_part.rsplit(":", 1) if ":" in host_part else (host_part, "443")

        params = {}
        if params_str:
            for kv in params_str.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[unquote(k)] = unquote(v)

        return {
            "name": name or f"{server}:{port_str}",
            "type": "hysteria",
            "server": server.strip("[]"),
            "port": int(port_str),
            "password": params.get("auth", ""),
            "sni": params.get("peer", server),
            "skip-cert-verify": params.get("insecure") == "1",
            "udp": True,
            "_credit": 3,
        }
    except Exception:
        return None


def _parse_tuic_uri(uri: str, name: str) -> Optional[Dict]:
    """Parse tuic:// UUID:password@server:port?params."""
    try:
        rest = uri[len("tuic://"):]
        userinfo, rest = rest.split("@", 1)
        uuid, password = userinfo.split(":", 1) if ":" in userinfo else (userinfo, "")
        host_part, params_str = rest.split("?", 1) if "?" in rest else (rest, "")
        server, port_str = host_part.rsplit(":", 1) if ":" in host_part else (host_part, "443")

        params = {}
        if params_str:
            for kv in params_str.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    params[unquote(k)] = unquote(v)

        return {
            "name": name or f"{server}:{port_str}",
            "type": "tuic",
            "server": server.strip("[]"),
            "port": int(port_str),
            "uuid": uuid,
            "password": unquote(password),
            "sni": params.get("sni", server),
            "skip-cert-verify": params.get("allow_insecure") == "1",
            "udp": True,
            "_credit": 3,
        }
    except Exception:
        return None


def _parse_socks5_uri(uri: str, name: str) -> Optional[Dict]:
    """Parse socks5:// user:pass@server:port."""
    try:
        rest = uri[len("socks5://"):]
        host_part = rest
        user = ""
        password = ""
        if "@" in rest:
            userinfo, host_part = rest.split("@", 1)
            if ":" in userinfo:
                user, password = userinfo.split(":", 1)

        server, port_str = host_part.rsplit(":", 1) if ":" in host_part else (host_part, "1080")

        proxy = {
            "name": name or f"{server}:{port_str}",
            "type": "socks5",
            "server": server.strip("[]"),
            "port": int(port_str),
            "udp": True,
            "_credit": 3,
        }
        if user:
            proxy["username"] = user
        if password:
            proxy["password"] = password
        return proxy
    except Exception:
        return None


def _singbox_to_proxy(ob: Dict) -> Optional[Dict]:
    """Convert a SingBox outbound object to a standard proxy dict."""
    try:
        ob_type = ob.get("type", "")
        # Map sing-box types to standard types
        type_map = {
            "vmess": "vmess", "vless": "vless", "trojan": "trojan",
            "shadowsocks": "ss", "hysteria2": "hysteria2",
        }
        proxy_type = type_map.get(ob_type, ob_type)
        if proxy_type not in type_map:
            return None

        proxy = {
            "name": ob.get("tag", ""),
            "type": proxy_type,
            "server": ob.get("server", ""),
            "port": int(ob.get("server_port", 0)),
            "udp": True,
            "_credit": 3,
        }

        if proxy_type in ("vmess", "vless"):
            proxy["uuid"] = ob.get("uuid", "")
        elif proxy_type == "trojan":
            proxy["password"] = ob.get("password", "")
            if "tls" in ob:
                proxy["sni"] = ob["tls"].get("server_name", "")
        elif proxy_type == "ss":
            proxy["cipher"] = ob.get("method", "")
            proxy["password"] = ob.get("password", "")
        elif proxy_type == "hysteria2":
            proxy["password"] = ob.get("password", "")

        if "tls" in ob:
            proxy["tls"] = True
            if "server_name" in ob["tls"]:
                proxy["servername"] = ob["tls"]["server_name"]

        return proxy
    except Exception:
        return None
