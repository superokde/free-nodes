"""Format proxy lists into output subscription files.

Generates three output formats matching Barabama/FreeNodes strategy:
  1. all.txt  — V2Ray subscription (one URI per line)
  2. all.yaml — Clash complete configuration
  3. provider.yaml — Clash proxy-provider format
"""

import base64
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Beijing timezone
TZ_BEIJING = timezone(timedelta(hours=8))


def generate_all_outputs(proxies: List[Dict], output_dir: Path) -> Dict[str, int]:
    """Generate all output files. Returns {filename: node_count}."""
    stats = {}

    # all.txt — V2Ray subscription format
    txt_path, txt_count = write_all_txt(proxies, output_dir)
    stats[txt_path.name] = txt_count

    # all.yaml — Clash complete config
    yaml_path, yaml_count = write_all_yaml(proxies, output_dir)
    stats[yaml_path.name] = yaml_count

    # provider.yaml — Clash proxy-provider format
    provider_path, provider_count = write_provider_yaml(proxies, output_dir)
    stats[provider_path.name] = provider_count

    # hiddify.yaml — Pure proxy list for Hiddify/OpenClash compatibility
    hiddify_path, hiddify_count = write_pure_proxies(proxies, output_dir)
    stats[hiddify_path.name] = hiddify_count

    return stats


def write_all_txt(proxies: List[Dict], output_dir: Path) -> tuple:
    """Write V2Ray subscription file (one URI per line, unencoded).

    This is the most universally compatible format — supported by:
    v2rayN, v2rayNG, Shadowrocket, Quantumult X, Surge, and more.
    """
    filepath = output_dir / "all.txt"
    uris = []

    for proxy in proxies:
        uri = proxy_to_uri(proxy)
        if uri:
            uris.append(uri)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(uris))
        f.write("\n")

    logger.info(f"Generated {filepath.name}: {len(uris)} URIs")
    return filepath, len(uris)


def write_all_yaml(proxies: List[Dict], output_dir: Path) -> tuple:
    """Write Clash complete configuration YAML file.

    Follows the clash-subscription-format-spec:
    - Inline YAML format for proxy entries
    - 4-space indentation
    - No Python repr strings for nested fields
    - Filters out types unsupported by Clash Premium kernel
    """
    filepath = output_dir / "all.yaml"
    now = datetime.now(TZ_BEIJING).strftime("%Y-%m-%d %H:%M:%S")

    # Filter: Premium-compatible types for max OpenClash compatibility
    # Clash Premium: ss, ssr, vmess, trojan
    # (vless/hysteria2/tuic are Meta-only, excluded for safety)
    premium_types = {"ss", "ssr", "vmess", "trojan"}
    valid = [p for p in proxies if p.get("type", "").lower() in premium_types]
    excluded = len(proxies) - len(valid)

    lines = []
    lines.append(f"# Free Node Aggregator | Updated: {now} Beijing Time")
    lines.append(f"# Total: {len(valid)} proxies" + (f" ({excluded} non-Clash types excluded)" if excluded else ""))
    lines.append("")

    # Clash config header
    lines.extend([
        "mixed-port: 7890",
        "allow-lan: false",
        "bind-address: '*'",
        "mode: rule",
        "log-level: info",
        "external-controller: '127.0.0.1:9090'",
        "unified-delay: true",
        "tcp-concurrent: true",
        "ipv6: false",
        "",
    ])

    # DNS config
    lines.extend([
        "dns:",
        "    enable: true",
        "    ipv6: false",
        "    default-nameserver: [223.5.5.5, 119.29.29.29, 114.114.114.114]",
        "    enhanced-mode: fake-ip",
        "    fake-ip-range: 198.18.0.1/16",
        "    use-hosts: true",
        "    respect-rules: true",
        "    proxy-server-nameserver: [223.5.5.5, 119.29.29.29, 114.114.114.114]",
        "    nameserver: [223.5.5.5, 119.29.29.29, 114.114.114.114]",
        "    fallback: [1.1.1.1, 8.8.8.8]",
        "    fallback-filter: { geoip: true, geoip-code: CN, geosite: [gfw], ipcidr: [240.0.0.0/4] }",
        "",
    ])

    # Proxies section — inline format per clash-subscription-format-spec
    lines.append("proxies:")
    node_names = []
    for proxy in valid:
        yaml_line = proxy_to_clash_yaml(proxy, clean_for_kernel=True)
        if yaml_line:
            lines.append(f"    - {yaml_line}")
            node_names.append(proxy.get("name", ""))

    lines.append("")

    # Proxy groups
    lines.extend(_generate_proxy_groups(node_names))
    lines.append("")

    # Rules
    lines.extend(_generate_rules())
    lines.append("")

    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Generated {filepath.name}: {len(node_names)} proxies (Premium+Meta compatible)")
    return filepath, len(node_names)


def write_provider_yaml(proxies: List[Dict], output_dir: Path) -> tuple:
    """Write Clash proxy-provider format YAML.

    Uses proxy-provider directive for dynamic loading.
    Groups by credit level and region detection.
    """
    filepath = output_dir / "provider.yaml"
    now = datetime.now(TZ_BEIJING).strftime("%Y-%m-%d %H:%M:%S")

    # Group proxies by credit level
    l1 = [p for p in proxies if p.get("_credit", 3) == 1]
    l2 = [p for p in proxies if p.get("_credit", 3) == 2]
    l3 = [p for p in proxies if p.get("_credit", 3) == 3]

    lines = []
    lines.append(f"# Free Node Aggregator — Provider Format | Updated: {now} Beijing Time")
    lines.append(f"# Proxies: L1={len(l1)}, L2={len(l2)}, L3={len(l3)}, Total={len(proxies)}")
    lines.append("")

    # Base config
    lines.extend([
        "mixed-port: 7890",
        "allow-lan: false",
        "bind-address: '*'",
        "mode: rule",
        "log-level: info",
        "external-controller: '127.0.0.1:9090'",
        "unified-delay: true",
        "tcp-concurrent: true",
        "",
    ])

    # DNS
    lines.extend([
        "dns:",
        "    enable: true",
        "    enhanced-mode: fake-ip",
        "    nameserver: [223.5.5.5, 119.29.29.29, 114.114.114.114]",
        "    fallback: [1.1.1.1, 8.8.8.8]",
        "",
    ])

    # Proxy provider definitions
    lines.extend([
        "proxy-providers:",
        "    all-nodes:",
        "        type: http",
        "        url: \"PLACEHOLDER_ALL_YAML_URL\"",
        "        path: ./all-nodes.yaml",
        "        interval: 86400",
        "        health-check:",
        "            enable: true",
        "            url: http://www.gstatic.com/generate_204",
        "            interval: 300",
        "",
    ])

    # Proxy groups
    group_names = ["🚀 自动选择", "🔄 故障转移", "🌍 手动选择"]
    all_node_names = [p.get("name", "") for p in proxies if _clean_name(p.get("name", ""))]

    lines.extend([
        "proxy-groups:",
        f"    - {{ name: 🚀 自动选择, type: url-test, proxies: {_yaml_list(all_node_names)}, url: 'http://www.gstatic.com/generate_204', interval: 300 }}",
        f"    - {{ name: 🔄 故障转移, type: fallback, proxies: {_yaml_list(all_node_names)}, url: 'http://www.gstatic.com/generate_204', interval: 600 }}",
        f"    - {{ name: 🌍 手动选择, type: select, proxies: {_yaml_list(group_names + all_node_names)} }}",
        "",
    ])

    # Rules
    lines.extend(_generate_rules())

    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Generated {filepath.name}: {len(proxies)} proxies (L1={len(l1)}, L2={len(l2)}, L3={len(l3)})")
    return filepath, len(proxies)


def write_pure_proxies(proxies: List[Dict], output_dir: Path) -> tuple:
    """Write a pure proxies: list without config wrapper.

    Compatible with Hiddify and OpenClash that need only the proxy list.
    Per the format spec: Hiddify parses JSON → V2Ray → Clash YAML.
    Pure proxy list ensures clean yaml.Unmarshal for broad compatibility.
    """
    filepath = output_dir / "hiddify.yaml"
    now = datetime.now(TZ_BEIJING).strftime("%Y-%m-%d %H:%M:%S")

    # Filter out proxy types not supported by Clash kernel
    clash_supported = {"vmess", "vless", "trojan", "ss", "ssr", "hysteria2", "hysteria", "tuic"}
    valid = [p for p in proxies if p.get("type", "").lower() in clash_supported]

    lines = [
        f"# Hiddify/Clash compatible proxy list | Updated: {now} BJT",
        f"# Total: {len(valid)} proxies",
        "proxies:",
    ]

    count = 0
    for proxy in valid:
        yaml_line = proxy_to_clash_yaml(proxy, clean_for_kernel=True)
        if yaml_line:
            lines.append(f"    - {yaml_line}")
            count += 1

    content = "\n".join(lines) + "\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Generated {filepath.name}: {count} proxies (Clash-kernel compatible)")
    return filepath, count


def proxy_to_uri(proxy: Dict) -> Optional[str]:
    """Convert a proxy dict to a standard proxy URI string."""
    ptype = str(proxy.get("type", "")).lower()
    name = proxy.get("name", "")
    server = str(proxy.get("server", ""))
    port = proxy.get("port", 0)

    if not server or not port:
        return None

    try:
        if ptype == "vmess":
            return _vmess_to_uri(proxy, name)
        elif ptype == "vless":
            return _vless_to_uri(proxy, name)
        elif ptype == "trojan":
            return _trojan_to_uri(proxy, name)
        elif ptype == "ss":
            return _ss_to_uri(proxy, name)
        elif ptype == "ssr":
            return _ssr_to_uri(proxy, name)
        elif ptype in ("hysteria2",):
            return _hysteria2_to_uri(proxy, name)
        elif ptype == "hysteria":
            return _hysteria_to_uri(proxy, name)
        elif ptype == "tuic":
            return _tuic_to_uri(proxy, name)
        elif ptype == "socks5":
            return _socks5_to_uri(proxy, name)
        else:
            logger.debug(f"Unsupported URI format for type: {ptype}")
            return None
    except Exception as e:
        logger.debug(f"Failed to generate URI for {name}: {e}")
        return None


def proxy_to_clash_yaml(proxy: Dict, clean_for_kernel: bool = False) -> Optional[str]:
    """Convert a proxy dict to Clash inline YAML format.

    Follows the clash-subscription-format-spec:
    - Inline format: { name: '...', server: '...', port: 443, type: ss, ... }
    - Nested fields as real YAML inline dicts (not Python repr strings)
    - If clean_for_kernel=True, strips fields that cause Clash kernel errors
    """
    ptype = str(proxy.get("type", ""))
    name = _clean_name(proxy.get("name", ""))
    server = str(proxy.get("server", ""))
    port = proxy.get("port", 0)

    if not server or not port:
        return None

    # Skip types not supported by Clash kernel
    if clean_for_kernel and ptype.lower() in ("socks5", "http", "socks"):
        return None

    parts = [
        f"name: '{name}'",
        f"server: '{server}'",
        f"port: {port}",
        f"type: '{ptype}'",
    ]

    if ptype in ("vmess", "vless"):
        parts.append(f"uuid: '{proxy.get('uuid', '')}'")
        alter_id = proxy.get("alterId", 0)
        parts.append(f"alterId: {alter_id}")
        if proxy.get("cipher") and ptype == "vmess":
            parts.append(f"cipher: '{proxy['cipher']}'")
        parts.append(f"tls: {str(proxy.get('tls', False)).lower()}")
        parts.append(f"skip-cert-verify: {str(proxy.get('skip-cert-verify', False)).lower()}")
        parts.append(f"udp: {str(proxy.get('udp', True)).lower()}")
        if proxy.get("servername"):
            parts.append(f"servername: '{proxy['servername']}'")
        if proxy.get("flow"):
            parts.append(f"flow: '{proxy['flow']}'")
        if proxy.get("client-fingerprint"):
            parts.append(f"client-fingerprint: '{proxy['client-fingerprint']}'")
        if proxy.get("public-key"):
            parts.append(f"reality-opts: {{ public-key: '{proxy['public-key']}'")
            if proxy.get("short-id"):
                parts[-1] += f", short-id: '{proxy['short-id']}'"
            parts[-1] += " }"

        network = proxy.get("network", "tcp")
        if network and network != "tcp":
            parts.append(f"network: '{network}'")

        # Transport opts — as real YAML inline dicts
        for opt_key in ("ws-opts", "http-opts", "grpc-opts"):
            if opt_key in proxy and proxy[opt_key]:
                parts.append(f"{opt_key}: {_dict_to_yaml(proxy[opt_key])}")

    elif ptype == "trojan":
        parts.append(f"password: '{proxy.get('password', '')}'")
        sni = proxy.get("sni", proxy.get("servername", ""))
        if sni:
            parts.append(f"sni: '{sni}'")
        # Trojan always uses TLS; some kernels reject explicit tls: true
        if not clean_for_kernel:
            parts.append(f"tls: {str(proxy.get('tls', True)).lower()}")
        parts.append(f"skip-cert-verify: {str(proxy.get('skip-cert-verify', False)).lower()}")
        parts.append(f"udp: {str(proxy.get('udp', True)).lower()}")
        network = proxy.get("network", "")
        if network and network != "tcp":
            parts.append(f"network: '{network}'")
        for opt_key in ("ws-opts", "grpc-opts"):
            if opt_key in proxy and proxy[opt_key]:
                parts.append(f"{opt_key}: {_dict_to_yaml(proxy[opt_key])}")

    elif ptype == "ss":
        parts.append(f"cipher: '{proxy.get('cipher', '')}'")
        parts.append(f"password: '{proxy.get('password', '')}'")
        parts.append(f"udp: {str(proxy.get('udp', True)).lower()}")

    elif ptype == "hysteria2":
        parts.append(f"password: '{proxy.get('password', '')}'")
        sni = proxy.get("sni", proxy.get("servername", ""))
        if sni:
            parts.append(f"sni: '{sni}'")
        parts.append(f"skip-cert-verify: {str(proxy.get('skip-cert-verify', False)).lower()}")
        parts.append(f"udp: {str(proxy.get('udp', True)).lower()}")
        if proxy.get("obfs"):
            parts.append(f"obfs: '{proxy['obfs']}'")
            if proxy.get("obfs-password"):
                parts.append(f"obfs-password: '{proxy['obfs-password']}'")

    elif ptype in ("socks5", "http", "socks"):
        if clean_for_kernel:
            return None  # Not supported by Clash kernel
        parts.append(f"skip-cert-verify: {str(proxy.get('skip-cert-verify', False)).lower()}")
        parts.append(f"udp: {str(proxy.get('udp', True)).lower()}")
        if proxy.get("username"):
            parts.append(f"username: '{proxy['username']}'")
        if proxy.get("password"):
            parts.append(f"password: '{proxy['password']}'")

    elif ptype == "ssr":
        parts.append(f"cipher: '{proxy.get('cipher', '')}'")
        parts.append(f"password: '{proxy.get('password', '')}'")
        if proxy.get("protocol"):
            parts.append(f"protocol: '{proxy['protocol']}'")
        if proxy.get("obfs"):
            parts.append(f"obfs: '{proxy['obfs']}'")

    elif ptype == "hysteria":
        parts.append(f"password: '{proxy.get('password', '')}'")
        sni = proxy.get("sni", "")
        if sni:
            parts.append(f"sni: '{sni}'")
        parts.append(f"skip-cert-verify: {str(proxy.get('skip-cert-verify', False)).lower()}")

    elif ptype == "tuic":
        parts.append(f"uuid: '{proxy.get('uuid', '')}'")
        parts.append(f"password: '{proxy.get('password', '')}'")
        sni = proxy.get("sni", "")
        if sni:
            parts.append(f"sni: '{sni}'")
        parts.append(f"skip-cert-verify: {str(proxy.get('skip-cert-verify', False)).lower()}")

    return "{ " + ", ".join(parts) + " }"


# ====== URI generators (private helpers) ======

def _vmess_to_uri(proxy: Dict, name: str) -> str:
    config = {
        "v": "2",
        "ps": name,
        "add": proxy["server"],
        "port": str(proxy["port"]),
        "id": proxy.get("uuid", ""),
        "aid": str(proxy.get("alterId", 0)),
        "scy": proxy.get("cipher", "auto"),
        "net": proxy.get("network", "tcp"),
        "type": "none",
        "tls": "tls" if proxy.get("tls") else "",
    }
    if proxy.get("servername"):
        config["sni"] = proxy["servername"]
        config["host"] = proxy["servername"]
    if "ws-opts" in proxy:
        ws = proxy["ws-opts"]
        config["net"] = "ws"
        config["path"] = ws.get("path", "/")
        if "headers" in ws and "Host" in ws["headers"]:
            config["host"] = ws["headers"]["Host"]

    b64 = base64.b64encode(json.dumps(config, ensure_ascii=False).encode()).decode()
    return f"vmess://{b64}"


def _vless_to_uri(proxy: Dict, name: str) -> str:
    uuid = proxy.get("uuid", "")
    server = proxy["server"]
    port = proxy["port"]
    params = []
    if proxy.get("network", "tcp") != "tcp":
        params.append(f"type={proxy['network']}")
    if proxy.get("tls"):
        params.append("security=tls")
    if proxy.get("servername"):
        params.append(f"sni={proxy['servername']}")
    if proxy.get("skip-cert-verify"):
        params.append("allowInsecure=1")
    if proxy.get("flow"):
        params.append(f"flow={proxy['flow']}")
    if "ws-opts" in proxy:
        ws = proxy["ws-opts"]
        if "path" in ws:
            params.append(f"path={ws['path']}")
        if "headers" in ws and "Host" in ws["headers"]:
            params.append(f"host={ws['headers']['Host']}")

    param_str = "&".join(params)
    uri = f"vless://{uuid}@{server}:{port}"
    if param_str:
        uri += f"?{param_str}"
    if name:
        uri += f"#{name}"
    return uri


def _trojan_to_uri(proxy: Dict, name: str) -> str:
    password = proxy.get("password", "")
    server = proxy["server"]
    port = proxy["port"]
    params = []
    if proxy.get("sni"):
        params.append(f"sni={proxy['sni']}")
    if proxy.get("skip-cert-verify"):
        params.append("allowInsecure=1")
    if proxy.get("network") == "ws" and "ws-opts" in proxy:
        ws = proxy["ws-opts"]
        params.append("type=ws")
        if "path" in ws:
            params.append(f"path={ws['path']}")
        if "headers" in ws and "Host" in ws["headers"]:
            params.append(f"host={ws['headers']['Host']}")

    param_str = "&".join(params)
    uri = f"trojan://{password}@{server}:{port}"
    if param_str:
        uri += f"?{param_str}"
    if name:
        uri += f"#{name}"
    return uri


def _ss_to_uri(proxy: Dict, name: str) -> str:
    cipher = proxy.get("cipher", "")
    password = proxy.get("password", "")
    server = proxy["server"]
    port = proxy["port"]
    # SIP002 format
    userinfo = base64.urlsafe_b64encode(f"{cipher}:{password}".encode()).decode().rstrip("=")
    uri = f"ss://{userinfo}@{server}:{port}"
    if name:
        uri += f"#{name}"
    return uri


def _ssr_to_uri(proxy: Dict, name: str) -> str:
    # SSR doesn't have a standard URI scheme; use base64 as many clients support it
    server = proxy["server"]
    port = proxy["port"]
    protocol = proxy.get("protocol", "origin")
    method = proxy.get("cipher", "")
    obfs = proxy.get("obfs", "plain")
    pass_b64 = base64.urlsafe_b64encode(proxy.get("password", "").encode()).decode().rstrip("=")
    main = f"{server}:{port}:{protocol}:{method}:{obfs}:{pass_b64}/?remarks={base64.urlsafe_b64encode(name.encode()).decode().rstrip('=')}"
    b64 = base64.urlsafe_b64encode(main.encode()).decode().rstrip("=")
    return f"ssr://{b64}"


def _hysteria2_to_uri(proxy: Dict, name: str) -> str:
    password = proxy.get("password", "")
    server = proxy["server"]
    port = proxy["port"]
    params = []
    if proxy.get("sni"):
        params.append(f"sni={proxy['sni']}")
    if proxy.get("skip-cert-verify"):
        params.append("insecure=1")
    param_str = "&".join(params)
    uri = f"hysteria2://{password}@{server}:{port}"
    if param_str:
        uri += f"?{param_str}"
    if name:
        uri += f"#{name}"
    return uri


def _hysteria_to_uri(proxy: Dict, name: str) -> str:
    server = proxy["server"]
    port = proxy["port"]
    params = []
    if proxy.get("password"):
        params.append(f"auth={proxy['password']}")
    if proxy.get("sni"):
        params.append(f"peer={proxy['sni']}")
    if proxy.get("skip-cert-verify"):
        params.append("insecure=1")
    param_str = "&".join(params)
    uri = f"hysteria://{server}:{port}"
    if param_str:
        uri += f"?{param_str}"
    if name:
        uri += f"#{name}"
    return uri


def _tuic_to_uri(proxy: Dict, name: str) -> str:
    uuid = proxy.get("uuid", "")
    password = proxy.get("password", "")
    server = proxy["server"]
    port = proxy["port"]
    params = []
    if proxy.get("sni"):
        params.append(f"sni={proxy['sni']}")
    if proxy.get("skip-cert-verify"):
        params.append("allow_insecure=1")
    param_str = "&".join(params)
    uri = f"tuic://{uuid}:{password}@{server}:{port}"
    if param_str:
        uri += f"?{param_str}"
    if name:
        uri += f"#{name}"
    return uri


def _socks5_to_uri(proxy: Dict, name: str) -> str:
    server = proxy["server"]
    port = proxy["port"]
    userinfo = ""
    if proxy.get("username"):
        userinfo = proxy["username"]
        if proxy.get("password"):
            userinfo += f":{proxy['password']}"
        userinfo += "@"
    uri = f"socks5://{userinfo}{server}:{port}"
    if name:
        uri += f"#{name}"
    return uri


# ====== YAML helpers ======

def _clean_name(name: str) -> str:
    """Clean a proxy name for YAML output, escaping special chars."""
    if not name:
        return "Unknown"
    return name.replace("'", "''")


def _dict_to_yaml(d: Dict) -> str:
    """Convert a dict to Clash-compatible inline YAML string.

    Example: {'path': '/', 'headers': {'Host': 'example.com'}}
    → { path: '/', headers: { Host: 'example.com' } }
    """
    parts = []
    for k, v in d.items():
        if isinstance(v, dict):
            parts.append(f"{k}: {_dict_to_yaml(v)}")
        elif isinstance(v, bool):
            parts.append(f"{k}: {str(v).lower()}")
        elif isinstance(v, (int, float)):
            parts.append(f"{k}: {v}")
        else:
            parts.append(f"{k}: '{v}'")
    return "{ " + ", ".join(parts) + " }"


def _yaml_list(items: List[str], max_items: int = 50) -> str:
    """Format a list of strings as Clash YAML inline list."""
    clean = [_clean_name(i) for i in items if i]
    limited = clean[:max_items]
    return "[" + ", ".join([f"'{n}'" for n in limited]) + "]"


def _generate_proxy_groups(node_names: List[str]) -> List[str]:
    """Generate Clash proxy-groups section with valid YAML syntax.

    Keeps groups limited for OpenClash compatibility (large groups crash kernel).
    """
    clean_names = [_clean_name(n) for n in node_names if n]

    # url-test: first 50 nodes — large enough for diversity, small enough for kernel
    auto_proxies = _yaml_list(clean_names, max_items=50)
    # fallback: first 50 nodes
    fb_proxies = _yaml_list(clean_names, max_items=50)
    # select: special groups + first 50 named nodes
    select_parts = ["'🚀 自动选择'", "'🔄 故障转移'", "'DIRECT'"]
    for n in clean_names[:50]:
        select_parts.append(f"'{n}'")
    select_proxies = "[" + ", ".join(select_parts) + "]"

    lines = [
        "proxy-groups:",
        f"    - {{ name: '🚀 自动选择', type: url-test, proxies: {auto_proxies}, url: 'http://www.gstatic.com/generate_204', interval: 300 }}",
        f"    - {{ name: '🔄 故障转移', type: fallback, proxies: {fb_proxies}, url: 'http://www.gstatic.com/generate_204', interval: 600 }}",
        f"    - {{ name: '🌍 手动选择', type: select, proxies: {select_proxies} }}",
    ]
    return lines


def _generate_rules() -> List[str]:
    """Generate Clash rules section with properly quoted values."""
    return [
        "rules:",
        "    - 'DOMAIN-KEYWORD,google,🚀 自动选择'",
        "    - 'DOMAIN-SUFFIX,google.com,🚀 自动选择'",
        "    - 'DOMAIN-SUFFIX,googleapis.com,🚀 自动选择'",
        "    - 'DOMAIN-KEYWORD,youtube,🚀 自动选择'",
        "    - 'DOMAIN-SUFFIX,youtube.com,🚀 自动选择'",
        "    - 'DOMAIN-SUFFIX,twitter.com,🚀 自动选择'",
        "    - 'DOMAIN-SUFFIX,facebook.com,🚀 自动选择'",
        "    - 'DOMAIN-SUFFIX,instagram.com,🚀 自动选择'",
        "    - 'DOMAIN-SUFFIX,github.com,🚀 自动选择'",
        "    - 'DOMAIN-SUFFIX,openai.com,🚀 自动选择'",
        "    - 'GEOIP,CN,DIRECT'",
        "    - 'MATCH,🚀 自动选择'",
    ]
