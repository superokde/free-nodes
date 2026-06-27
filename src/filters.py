"""Filter proxies by blacklist, port patterns, and validity checks."""

import ipaddress
import logging
import re
from typing import List, Dict, Set

from .config import BlacklistConfig

logger = logging.getLogger(__name__)


class ProxyFilter:
    """Filters out proxies based on blacklist rules and validity checks."""

    def __init__(self, config: BlacklistConfig):
        self.config = config
        self.blocked_ports: Set[int] = set(config.ports)
        self.name_patterns = [re.compile(p, re.IGNORECASE) for p in config.name_exclude_patterns]
        self.blocked_ips = set(config.ip_patterns)
        self.blocked_cidrs = self._parse_cidrs(config.ip_cidr)
        self.blocked_domains = set(d.lower() for d in config.domains)

    @staticmethod
    def _parse_cidrs(cidrs: List[str]) -> List[ipaddress.IPv4Network]:
        """Parse CIDR strings into IPv4Network objects."""
        result = []
        for cidr in cidrs:
            try:
                result.append(ipaddress.IPv4Network(cidr, strict=False))
            except ValueError as e:
                logger.warning(f"Invalid CIDR '{cidr}': {e}")
        return result

    def filter(self, proxies: List[Dict]) -> List[Dict]:
        """Filter proxies, returning only valid and allowed ones."""
        filtered = []
        stats = {
            "total": len(proxies),
            "invalid": 0,
            "blacklisted_port": 0,
            "blacklisted_ip": 0,
            "blacklisted_domain": 0,
            "blacklisted_name": 0,
            "passed": 0,
        }

        for proxy in proxies:
            if not self._is_valid(proxy):
                stats["invalid"] += 1
                continue
            if self._is_port_blocked(proxy):
                stats["blacklisted_port"] += 1
                continue
            if self._is_ip_blocked(proxy):
                stats["blacklisted_ip"] += 1
                continue
            if self._is_domain_blocked(proxy):
                stats["blacklisted_domain"] += 1
                continue
            if self._is_name_blocked(proxy):
                stats["blacklisted_name"] += 1
                continue
            filtered.append(proxy)
            stats["passed"] += 1

        logger.info(
            f"Filter: {stats['total']} total → {stats['passed']} passed "
            f"(invalid={stats['invalid']}, port={stats['blacklisted_port']}, "
            f"ip={stats['blacklisted_ip']}, domain={stats['blacklisted_domain']}, "
            f"name={stats['blacklisted_name']})"
        )
        return filtered

    def _is_valid(self, proxy: Dict) -> bool:
        """Check if proxy has the minimum required fields for its type."""
        ptype = str(proxy.get("type", "")).lower()
        required = self.config.required_fields.get(ptype, ["server", "port"])

        for field in required:
            value = proxy.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                return False

        # Port must be a valid number
        port = proxy.get("port")
        if not isinstance(port, (int, float)) or port < 1 or port > 65535:
            return False

        # Server must be non-empty
        server = str(proxy.get("server", "")).strip()
        if not server:
            return False

        return True

    def _is_port_blocked(self, proxy: Dict) -> bool:
        """Check if the proxy uses a blocked port."""
        port = proxy.get("port", 0)
        return int(port) in self.blocked_ports

    def _is_ip_blocked(self, proxy: Dict) -> bool:
        """Check if the proxy's server IP is blacklisted."""
        server = str(proxy.get("server", "")).strip()

        # Check exact IP matches
        if server in self.blocked_ips:
            return True

        # Check CIDR matches
        try:
            addr = ipaddress.IPv4Address(server)
            for cidr in self.blocked_cidrs:
                if addr in cidr:
                    return True
        except (ipaddress.AddressValueError, ValueError):
            # Server is a hostname, not an IP
            pass

        return False

    def _is_domain_blocked(self, proxy: Dict) -> bool:
        """Check if the proxy's server domain is blacklisted."""
        server = str(proxy.get("server", "")).strip().lower()
        for blocked_domain in self.blocked_domains:
            if blocked_domain in server:
                return True
        return False

    def _is_name_blocked(self, proxy: Dict) -> bool:
        """Check if the proxy's name matches exclusion patterns."""
        name = str(proxy.get("name", ""))

        # Check compiled regex patterns
        for pattern in self.name_patterns:
            if pattern.search(name):
                return True

        # Check if name contains blocked domains
        for blocked_domain in self.blocked_domains:
            if blocked_domain in name.lower():
                return True

        return False
