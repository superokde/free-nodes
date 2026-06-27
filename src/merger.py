"""Orchestrate the full pipeline: collect → filter → deduplicate → output."""

import concurrent.futures
import logging
from typing import List, Dict
from pathlib import Path

from .config import AppConfig, load_config, get_output_dir
from .collector import fetch_source, parse_proxies
from .deduplicator import deduplicate
from .filters import ProxyFilter
from .formatter import generate_all_outputs

logger = logging.getLogger(__name__)


class Merger:
    """Orchestrates the full collection, filtering, and output pipeline."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.filter = ProxyFilter(config.blacklist)
        self.stats: Dict = {}

    def run(self) -> bool:
        """Run the full pipeline. Returns True on success."""
        logger.info("=" * 60)
        logger.info("Free Nodes Aggregator — Starting collection pipeline")
        logger.info(f"Sources: {len(self.config.sources)} configured")
        logger.info(f"Concurrency: {self.config.settings.concurrency}")
        logger.info("=" * 60)

        # Phase 1: Fetch and parse all sources
        logger.info("\n>>> Phase 1: Fetching sources")
        all_proxies = self._collect_all()

        if not all_proxies:
            logger.error("No proxies collected from any source. Aborting.")
            return False

        logger.info(f"\nTotal proxies collected: {len(all_proxies)}")

        # Phase 2: Filter
        logger.info("\n>>> Phase 2: Filtering")
        filtered = self.filter.filter(all_proxies)

        if not filtered:
            logger.error("All proxies filtered out. Aborting.")
            return False

        # Phase 3: Deduplicate
        logger.info("\n>>> Phase 3: Deduplicating")
        unique = deduplicate(filtered)
        logger.info(f"Unique proxies after dedup: {len(unique)}")

        # Phase 4: Generate output files
        logger.info("\n>>> Phase 4: Generating output files")
        output_dir = get_output_dir()
        output_stats = generate_all_outputs(unique, output_dir)

        # Print final summary
        self._print_summary(output_stats, len(unique))
        return True

    def _collect_all(self) -> List[Dict]:
        """Fetch and parse all enabled sources in parallel."""
        all_proxies = []
        sources = [s for s in self.config.sources if s.enabled]
        settings = self.config.settings

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(settings.concurrency, len(sources))
        ) as executor:
            futures = {}
            for source in sources:
                future = executor.submit(_collect_source, source, settings)
                futures[future] = source

            for future in concurrent.futures.as_completed(futures):
                source = futures[future]
                try:
                    proxies = future.result()
                    # Tag each proxy with source credit level
                    for p in proxies:
                        p["_credit"] = min(p.get("_credit", 3), source.credit)
                    all_proxies.extend(proxies)
                    logger.info(f"[{source.name}] Collected {len(proxies)} proxies (credit=L{source.credit})")
                except Exception as e:
                    logger.error(f"[{source.name}] Error: {e}")

        return all_proxies

    def _print_summary(self, output_stats: Dict[str, int], total: int) -> None:
        """Print a formatted summary of results."""
        logger.info("\n" + "=" * 60)
        logger.info("Pipeline Complete!")
        logger.info(f"  Total unique nodes: {total}")
        logger.info("  Output files:")
        for filename, count in output_stats.items():
            logger.info(f"    nodes/{filename}: {count} entries")
        logger.info("=" * 60)


def _collect_source(source, settings) -> List[Dict]:
    """Helper: fetch and parse a single source."""
    content = fetch_source(source, settings)
    if content is None:
        return []
    return parse_proxies(content, source.format)
