"""Configuration loader for sources.yaml and blacklist.yaml."""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class SourceConfig:
    name: str
    url: str
    format: str  # clash, v2ray, base64, singbox
    credit: int  # 1=L1, 2=L2, 3=L3
    enabled: bool = True
    fallback_to_cdn: bool = False

    def __post_init__(self):
        valid_formats = {"clash", "v2ray", "base64", "singbox"}
        if self.format not in valid_formats:
            raise ValueError(f"Invalid format '{self.format}' for source '{self.name}'")
        if self.credit not in (1, 2, 3):
            raise ValueError(f"Invalid credit '{self.credit}' for source '{self.name}'")


@dataclass
class BlacklistConfig:
    ip_cidr: List[str] = field(default_factory=list)
    ip_patterns: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    ports: List[int] = field(default_factory=list)
    name_exclude_patterns: List[str] = field(default_factory=list)
    required_fields: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class SettingsConfig:
    request_timeout: int = 30
    max_retries: int = 3
    concurrency: int = 5
    gh_proxies: List[str] = field(default_factory=list)


@dataclass
class AppConfig:
    sources: List[SourceConfig] = field(default_factory=list)
    blacklist: BlacklistConfig = field(default_factory=BlacklistConfig)
    settings: SettingsConfig = field(default_factory=SettingsConfig)


def load_config(config_dir: str = None) -> AppConfig:
    """Load application configuration from YAML files."""
    if config_dir is None:
        config_dir = Path(__file__).parent.parent / "config"

    config_dir = Path(config_dir)

    # Load sources
    sources_path = config_dir / "sources.yaml"
    if not sources_path.exists():
        raise FileNotFoundError(f"Sources config not found: {sources_path}")

    with open(sources_path, "r", encoding="utf-8") as f:
        sources_raw = yaml.safe_load(f)

    sources = []
    for s in sources_raw.get("sources", []):
        if s.get("enabled", True):
            sources.append(SourceConfig(
                name=s["name"],
                url=s["url"],
                format=s["format"],
                credit=s.get("credit", 3),
                enabled=s.get("enabled", True),
                fallback_to_cdn=s.get("fallback_to_cdn", False),
            ))

    # Load settings
    settings_raw = sources_raw.get("settings", {})
    settings = SettingsConfig(
        request_timeout=settings_raw.get("request_timeout", 30),
        max_retries=settings_raw.get("max_retries", 3),
        concurrency=settings_raw.get("concurrency", 5),
        gh_proxies=settings_raw.get("gh_proxies", []),
    )

    # Load blacklist
    blacklist_path = config_dir / "blacklist.yaml"
    blacklist = BlacklistConfig()
    if blacklist_path.exists():
        with open(blacklist_path, "r", encoding="utf-8") as f:
            bl_raw = yaml.safe_load(f) or {}
        blacklist = BlacklistConfig(
            ip_cidr=bl_raw.get("ip_cidr") or [],
            ip_patterns=bl_raw.get("ip_patterns") or [],
            domains=bl_raw.get("domains") or [],
            ports=bl_raw.get("ports") or [],
            name_exclude_patterns=bl_raw.get("name_exclude_patterns") or [],
            required_fields=bl_raw.get("required_fields") or {},
        )

    return AppConfig(sources=sources, blacklist=blacklist, settings=settings)


def get_output_dir() -> Path:
    """Get the output directory for generated subscription files."""
    output_dir = Path(__file__).parent.parent / "nodes"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
