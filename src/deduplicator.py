"""Deduplicate proxies by server:port:type key."""

import hashlib
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def dedup_key(proxy: Dict) -> str:
    """Generate a deduplication key: server:port:type."""
    server = str(proxy.get("server", "")).strip().lower()
    port = proxy.get("port", 0)
    ptype = str(proxy.get("type", "")).strip().lower()
    return f"{server}:{port}:{ptype}"


def deduplicate(proxies: List[Dict]) -> List[Dict]:
    """Deduplicate proxy list by server:port:type.

    When duplicates are found, keeps the one with highest _credit (lowest number = L1).
    If credits are equal, keeps the first occurrence.
    """
    seen: Dict[str, Dict] = {}
    duplicates_removed = 0

    for proxy in proxies:
        key = dedup_key(proxy)
        if key in seen:
            existing = seen[key]
            # Keep the one with better credit (lower number = higher priority)
            new_credit = proxy.get("_credit", 3)
            old_credit = existing.get("_credit", 3)
            if new_credit < old_credit:
                seen[key] = proxy
                logger.debug(f"Replaced duplicate '{existing.get('name')}' with higher-credit '{proxy.get('name')}'")
            duplicates_removed += 1
        else:
            seen[key] = proxy

    if duplicates_removed > 0:
        logger.info(f"Deduplication: removed {duplicates_removed} duplicates, kept {len(seen)} unique nodes")
    else:
        logger.info(f"Deduplication: no duplicates found, {len(seen)} unique nodes")

    return list(seen.values())


def deduplicate_by_hash(uris: List[str]) -> List[str]:
    """Deduplicate proxy URIs by MD5 hash of the URI content."""
    seen = set()
    unique = []
    for uri in uris:
        uri_hash = hashlib.md5(uri.encode()).hexdigest()
        if uri_hash not in seen:
            seen.add(uri_hash)
            unique.append(uri)
    return unique
