#!/usr/bin/env python3
"""
NSE Market Data Downloader CLI.

Production-grade command-line interface to acquire, validate, and store
market datasets from the National Stock Exchange of India (NSE).
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List

from config.datasets import DATASET_REGISTRY, get_all_dataset_names
from nse_downloader.application import DownloaderApplication
from nse_downloader.client import NSEClient
from nse_downloader.logging_config import setup_logger


def parse_arguments(args: List[str] = None) -> argparse.Namespace:
    """Parse command-line arguments for NSE Market Data Downloader."""
    parser = argparse.ArgumentParser(
        prog="nse-downloader",
        description="Download and store CSV data from NSE India market data pages.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all datasets into default 'data' directory
  python main.py

  # Download only top gainers and losers
  python main.py --dataset top-gainers-losers

  # Download upper band hitters to custom directory
  python main.py --dataset upper-band-hitters --output-dir /var/market_data

  # Download 52-week high with debug logging
  python main.py --dataset 52-week-high --log-level DEBUG

  # Run with mock fixtures for testing/demonstration
  python main.py --mock-dir tests/fixtures
""",
    )

    available_datasets = get_all_dataset_names()

    parser.add_argument(
        "--dataset",
        "-d",
        type=str,
        choices=available_datasets,
        default=None,
        help=(
            "Download an individual dataset. If omitted, all datasets are downloaded. "
            f"Choices: {', '.join(available_datasets)}"
        ),
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="data",
        help="Base output directory for saved CSV files (default: 'data')",
    )

    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Explicit trading date override in YYYY-MM-DD format (default: auto-detected or current IST date)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity level (default: INFO)",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Optional file path to persist structured log outputs",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP request timeout in seconds (default: 15)",
    )

    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Maximum HTTP retry attempts for transient errors (default: 3)",
    )

    parser.add_argument(
        "--mock-dir",
        type=str,
        default=None,
        help="Directory containing mock JSON responses for offline demonstration or testing",
    )

    return parser.parse_args(args)


def format_summary_table(results: dict) -> str:
    """Formats a clear, human-readable summary table of dataset download results."""
    lines = []
    lines.append("\n" + "=" * 80)
    lines.append(f"{'DATASET':<25} | {'STATUS':<8} | {'RECORDS':<8} | {'OUTPUT PATH / ERROR'}")
    lines.append("-" * 80)

    for name, res in results.items():
        status = "SUCCESS" if res.success else "FAILED"
        rec_str = str(res.record_count) if res.success else "0"
        detail = res.output_path if res.success else f"Error: {res.error_message}"
        lines.append(f"{name:<25} | {status:<8} | {rec_str:<8} | {detail}")

    lines.append("=" * 80 + "\n")
    return "\n".join(lines)


def main() -> int:
    """Main CLI execution entry point."""
    args = parse_arguments()

    # Configure structured logging
    logger = setup_logger(level=args.log_level, log_file=args.log_file)

    # Instantiate HTTP client
    client = NSEClient(
        timeout=args.timeout,
        max_retries=args.retries,
    )

    # Instantiate application orchestrator
    app = DownloaderApplication(
        client=client,
        output_dir=args.output_dir,
        mock_data_dir=args.mock_dir,
    )

    try:
        if args.dataset:
            # Single dataset requested
            result = app.download_dataset(args.dataset, custom_date=args.date)
            results = {args.dataset: result}
        else:
            # All datasets requested
            results = app.download_all(custom_date=args.date)

        summary = format_summary_table(results)
        print(summary)

        # Check if all completed successfully
        all_succeeded = all(r.success for r in results.values())
        if all_succeeded:
            logger.info("All requested datasets were processed and saved successfully.")
            return 0
        else:
            failed_count = sum(1 for r in results.values() if not r.success)
            logger.error(f"{failed_count} dataset(s) failed during execution.")
            return 1

    finally:
        app.close()


if __name__ == "__main__":
    sys.exit(main())
