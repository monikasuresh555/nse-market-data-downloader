"""
Data Acquisition module for NSE Market Data Downloader.

Coordinates retrieval of raw dataset responses using NSEClient,
handles multi-endpoint retrieval for combined datasets, and extracts
trading dates.
"""

from datetime import datetime, timezone, timedelta
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from config.datasets import DatasetConfig
from nse_downloader.client import NSEClient
from nse_downloader.logging_config import log_event
from nse_downloader.models import AcquisitionResult, EmptyResponseError, ValidationError

logger = logging.getLogger("nse_downloader")

# India Standard Time (IST) offset is UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))


def get_default_trading_date() -> str:
    """Return current date in IST formatted as YYYY-MM-DD."""
    return datetime.now(IST).strftime("%Y-%m-%d")


def extract_trading_date_from_payload(payload: Any) -> Optional[str]:
    """
    Attempt to extract a trading date string (YYYY-MM-DD) from typical NSE JSON headers.
    Examples of NSE timestamp formats:
    - "18-Sep-2026 15:30:00"
    - "2026-09-18"
    - "Sep 18, 2026 16:00:00"
    """
    if not isinstance(payload, dict):
        return None

    candidate_keys = ["timestamp", "marketStatus", "lastUpdateTime", "tradeDate", "asOn"]
    for key in candidate_keys:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            # Try to parse standard NSE date strings
            val_clean = val.strip().split()[0]  # Take date portion
            # Try formats
            for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    dt = datetime.strptime(val_clean, fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

    return None


class DataAcquirer:
    """
    Coordinates data acquisition from NSE endpoints according to dataset configuration.
    """

    def __init__(self, client: NSEClient, mock_data_dir: Optional[str] = None):
        self.client = client
        self.mock_data_dir = Path(mock_data_dir) if mock_data_dir else None

    def acquire(
        self,
        config: DatasetConfig,
        custom_date: Optional[str] = None,
    ) -> AcquisitionResult:
        """
        Acquires raw JSON payload for the specified dataset.

        Args:
            config: Dataset configuration instance.
            custom_date: Optional date override (YYYY-MM-DD).

        Returns:
            AcquisitionResult object containing raw data and metadata.
        """
        # 1. Check if offline/mock data directory is configured
        if self.mock_data_dir and self.mock_data_dir.exists():
            mock_json = self.mock_data_dir / f"{config.filename_prefix}.json"
            mock_csv = self.mock_data_dir / f"{config.filename_prefix}.csv"

            if mock_json.exists():
                log_event(
                    logger,
                    logging.INFO,
                    f"Loading dataset '{config.name}' from mock JSON: {mock_json}",
                    dataset=config.name,
                    endpoint=str(mock_json),
                    attempt_number=1,
                )
                import json
                with open(mock_json, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                trading_date = custom_date or extract_trading_date_from_payload(raw_data) or get_default_trading_date()
                return AcquisitionResult(
                    dataset_name=config.name,
                    endpoint=str(mock_json),
                    raw_data=raw_data,
                    status_code=200,
                    attempt_count=1,
                    trading_date=trading_date,
                )
            elif mock_csv.exists():
                log_event(
                    logger,
                    logging.INFO,
                    f"Loading dataset '{config.name}' from mock CSV: {mock_csv}",
                    dataset=config.name,
                    endpoint=str(mock_csv),
                    attempt_number=1,
                )
                with open(mock_csv, "r", encoding="utf-8") as f:
                    raw_data = f.read()
                trading_date = custom_date or get_default_trading_date()
                return AcquisitionResult(
                    dataset_name=config.name,
                    endpoint=str(mock_csv),
                    raw_data=raw_data,
                    status_code=200,
                    attempt_count=1,
                    trading_date=trading_date,
                )

        # 2. Live HTTP Acquisition
        trading_date = custom_date or get_default_trading_date()

        if config.name == "top-gainers-losers":
            return self._acquire_top_gainers_losers(config, trading_date)
        elif config.name == "52-week-high":
            return self._acquire_52_week_high(config, trading_date, custom_date)
        else:
            # Single endpoint acquisition
            endpoint = config.primary_endpoint
            log_event(
                logger,
                logging.INFO,
                f"Starting acquisition for '{config.name}' from {endpoint}",
                dataset=config.name,
                endpoint=endpoint,
                attempt_number=1,
            )
            raw_data = self.client.get_data(
                endpoint_path=endpoint,
                params=config.query_params,
                dataset_name=config.name,
                referer=config.webpage_url,
                page_url=config.webpage_url,
            )

            detected_date = extract_trading_date_from_payload(raw_data)
            if detected_date and not custom_date:
                trading_date = detected_date

            return AcquisitionResult(
                dataset_name=config.name,
                endpoint=endpoint,
                raw_data=raw_data,
                status_code=200,
                attempt_count=1,
                trading_date=trading_date,
            )

    def _acquire_top_gainers_losers(
        self,
        config: DatasetConfig,
        fallback_date: str,
    ) -> AcquisitionResult:
        """
        Specialized acquisition for top gainers and losers, combining both sides.
        """
        gainers_endpoint = config.secondary_endpoints.get(
            "gainers", "/api/live-analysis-variations?index=gainers"
        )
        losers_endpoint = config.secondary_endpoints.get(
            "losers", "/api/live-analysis-variations?index=loosers"
        )

        log_event(
            logger,
            logging.INFO,
            "Acquiring top gainers and losers endpoints...",
            dataset=config.name,
            endpoint=config.primary_endpoint,
            attempt_number=1,
        )

        gainers_payload = self.client.get_data(
            gainers_endpoint,
            dataset_name=f"{config.name} (gainers)",
            referer=config.webpage_url,
            page_url=config.webpage_url,
        )

        losers_payload = self.client.get_data(
            losers_endpoint,
            dataset_name=f"{config.name} (losers)",
            referer=config.webpage_url,
            page_url=config.webpage_url,
        )

        combined_raw = {
            "gainers": gainers_payload,
            "losers": losers_payload,
        }

        detected_date = (
            extract_trading_date_from_payload(gainers_payload)
            or extract_trading_date_from_payload(losers_payload)
            or fallback_date
        )

        return AcquisitionResult(
            dataset_name=config.name,
            endpoint=config.primary_endpoint,
            raw_data=combined_raw,
            status_code=200,
            attempt_count=1,
            trading_date=detected_date,
        )

    def _acquire_52_week_high(
        self,
        config: DatasetConfig,
        fallback_date: str,
        custom_date: Optional[str] = None,
    ) -> AcquisitionResult:
        """
        Acquisition for 52-Week High dataset.
        Prefers the live JSON API endpoint (/api/live-analysis-52week?index=high).
        If custom date is requested or live endpoint is unavailable, attempts archive CSV.
        """
        endpoint = config.primary_endpoint
        log_event(
            logger,
            logging.INFO,
            f"Starting acquisition for '{config.name}' from {endpoint}",
            dataset=config.name,
            endpoint=endpoint,
            attempt_number=1,
        )

        try:
            raw_data = self.client.get_data(
                endpoint_path=endpoint,
                params=config.query_params,
                dataset_name=config.name,
                referer=config.webpage_url,
                page_url=config.webpage_url,
            )
            detected_date = extract_trading_date_from_payload(raw_data) or fallback_date
            return AcquisitionResult(
                dataset_name=config.name,
                endpoint=endpoint,
                raw_data=raw_data,
                status_code=200,
                attempt_count=1,
                trading_date=detected_date,
            )
        except Exception as primary_err:
            # Check for archive CSV fallback
            date_to_use = custom_date or fallback_date
            dt_clean = date_to_use.replace("-", "")
            if len(date_to_use.split("-")) == 3:
                y, m, d = date_to_use.split("-")
                ddmmyyyy = f"{d}{m}{y}"
            else:
                ddmmyyyy = dt_clean

            csv_url = f"https://nsearchives.nseindia.com/content/CM_52_wk_High_low_{ddmmyyyy}.csv"
            log_event(
                logger,
                logging.WARNING,
                f"Primary 52-week endpoint failed ({primary_err}); attempting archive CSV fallback: {csv_url}",
                dataset=config.name,
                endpoint=csv_url,
            )
            try:
                csv_data = self.client.get_data(
                    endpoint_path=csv_url,
                    dataset_name=config.name,
                )
                return AcquisitionResult(
                    dataset_name=config.name,
                    endpoint=csv_url,
                    raw_data=csv_data,
                    status_code=200,
                    attempt_count=2,
                    trading_date=date_to_use,
                )
            except Exception:
                raise primary_err
