"""
Configuration module for NSE Market Data Downloader.

Contains all endpoint definitions, query parameters, expected fields,
parser mapping, and filename conventions for the four target datasets.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class DatasetConfig:
    """Configuration definition for an NSE market dataset."""

    name: str
    display_name: str
    webpage_url: str
    primary_endpoint: str
    secondary_endpoints: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, Any] = field(default_factory=dict)
    filename_prefix: str = ""
    parser_name: str = ""
    expected_fields: List[str] = field(default_factory=list)
    required_columns: List[str] = field(default_factory=list)
    dedup_keys: List[str] = field(default_factory=lambda: ["Symbol"])
    description: str = ""


# Standard NSE India Base URLs and API Endpoints
NSE_BASE_URL = "https://www.nseindia.com"
NSE_REFERER_URL = "https://www.nseindia.com/"

# Standard browser headers required for NSE session handshake
DEFAULT_NSE_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": NSE_REFERER_URL,
    "Connection": "keep-alive",
}

DEFAULT_API_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": NSE_REFERER_URL,
    "Connection": "keep-alive",
}

# Client timeout and retry configuration
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF_SECONDS = 1.5
DEFAULT_BACKOFF_MULTIPLIER = 2.0
DEFAULT_JITTER = True

# Registry of supported datasets
DATASET_REGISTRY: Dict[str, DatasetConfig] = {
    "top-gainers-losers": DatasetConfig(
        name="top-gainers-losers",
        display_name="Top Gainers and Losers",
        webpage_url="https://www.nseindia.com/market-data/top-gainers-losers",
        primary_endpoint="/api/live-analysis-variations",
        secondary_endpoints={
            "gainers": "/api/live-analysis-variations?index=gainers",
            "losers": "/api/live-analysis-variations?index=loosers",
            "csv_gainers": "/api/live-analysis-variations?index=gainers&csv=true",
            "csv_losers": "/api/live-analysis-variations?index=loosers&csv=true",
        },
        query_params={"index": "gainers"},
        filename_prefix="top_gainers_losers",
        parser_name="top_gainers_losers",
        expected_fields=[
            "Symbol",
            "Series",
            "Open",
            "High",
            "Low",
            "Prev. Close",
            "LTP",
            "%change",
            "Volume",
            "Value",
            "Direction",
        ],
        required_columns=["Symbol", "LTP", "Direction"],
        dedup_keys=["Symbol", "Direction"],
        description="Top gainers and losers from NSE India equity variation analysis.",
    ),
    "upper-band-hitters": DatasetConfig(
        name="upper-band-hitters",
        display_name="Upper Band Hitters",
        webpage_url="https://www.nseindia.com/market-data/upper-band-hitters",
        primary_endpoint="/api/live-analysis-price-band-hitter",
        secondary_endpoints={
            "csv": "/api/live-analysis-price-band-hitter?csv=true",
        },
        query_params={},
        filename_prefix="upper_band_hitters",
        parser_name="upper_band_hitters",
        expected_fields=[
            "Symbol",
            "Series",
            "Prev. Close",
            "LTP",
            "%change",
            "Upper Band",
            "Volume",
            "Value",
        ],
        required_columns=["Symbol", "LTP", "Upper Band"],
        dedup_keys=["Symbol"],
        description="Equities hitting the daily upper circuit band on NSE India.",
    ),
    "volume-gainers-spurts": DatasetConfig(
        name="volume-gainers-spurts",
        display_name="Volume Gainers and Spurts",
        webpage_url="https://www.nseindia.com/market-data/volume-gainers-spurts",
        primary_endpoint="/api/live-analysis-volume-gainers",
        secondary_endpoints={
            "csv": "/api/live-analysis-volume-gainers?csv=true",
        },
        query_params={},
        filename_prefix="volume_gainers_spurts",
        parser_name="volume_gainers_spurts",
        expected_fields=[
            "Symbol",
            "Series",
            "LTP",
            "%change",
            "Prev Week Avg Vol",
            "Week Avg Vol",
            "Volume Spurt %",
            "Volume",
            "Value",
        ],
        required_columns=["Symbol", "LTP", "Volume"],
        dedup_keys=["Symbol"],
        description="Securities displaying significant trading volume spurts compared to averages.",
    ),
    "52-week-high": DatasetConfig(
        name="52-week-high",
        display_name="52 Week High Equity Market",
        webpage_url="https://www.nseindia.com/market-data/52-week-high-equity-market",
        primary_endpoint="/api/live-analysis-52week",
        secondary_endpoints={
            "live_high": "/api/live-analysis-52week?index=high",
            "archive_csv": "https://nsearchives.nseindia.com/content/CM_52_wk_High_low_{date}.csv",
            "latest_csv": "https://archives.nseindia.com/content/CM_52_wk_High_low.csv",
        },
        query_params={"index": "high"},
        filename_prefix="52_week_high",
        parser_name="52_week_high",
        expected_fields=[
            "Symbol",
            "Series",
            "LTP",
            "%change",
            "52W High",
            "Prev 52W High",
            "52W High Date",
            "Volume",
            "Value",
        ],
        required_columns=["Symbol", "52W High"],
        dedup_keys=["Symbol"],
        description="Stocks touching new 52-week highs in the NSE equity market.",
    ),
}


def get_dataset_config(name: str) -> DatasetConfig:
    """Retrieve configuration for a dataset by its CLI name."""
    if name not in DATASET_REGISTRY:
        supported = ", ".join(DATASET_REGISTRY.keys())
        raise KeyError(
            f"Unknown dataset '{name}'. Supported datasets are: {supported}"
        )
    return DATASET_REGISTRY[name]


def get_all_dataset_names() -> List[str]:
    """Retrieve all supported dataset names."""
    return list(DATASET_REGISTRY.keys())
