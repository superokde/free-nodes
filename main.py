#!/usr/bin/env python3
"""Free Nodes Aggregator — Entry Point.

Collects free proxy nodes from multiple subscription sources,
filters, deduplicates, and generates subscription files.

Usage:
    python main.py                 # Run full pipeline
    python main.py --config DIR    # Use custom config directory
    python main.py --verbose       # Enable debug logging
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent))

from src.config import load_config
from src.merger import Merger


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt)


def main():
    parser = argparse.ArgumentParser(
        description="Free Nodes Aggregator — Collect and aggregate free proxy nodes"
    )
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to config directory (default: ./config/)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("Free Nodes Aggregator v1.0.0")

    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    merger = Merger(config)
    success = merger.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
