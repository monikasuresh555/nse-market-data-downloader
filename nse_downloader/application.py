"""
Application orchestration layer for NSE Market Data Downloader.

Coordinates acquisition, parsing, validation, and storage across single or multiple
datasets with failure isolation and comprehensive structured logging.
"""

from datetime import datetime
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union

from config.datasets import DATASET_REGISTRY, DatasetConfig, get_dataset_config
from nse_downloader.acquisition import DataAcquirer
from nse_downloader.client import NSEClient
from nse_downloader.logging_config import log_event
from nse_downloader.models import DownloadResult, NSEDownloaderError
from nse_downloader.parsers import get_parser
from nse_downloader.storage import save_csv
from nse_downloader.validation import validate_dataset

logger = logging.getLogger("nse_downloader")


class DownloaderApplication:
    """
    Orchestrates downloading, parsing, validating, and saving NSE datasets.
    """

    def __init__(
        self,
        client: Optional[NSEClient] = None,
        output_dir: Union[str, Path] = "data",
        mock_data_dir: Optional[str] = None,
    ):
        self.client = client if client is not None else NSEClient()
        self.output_dir = Path(output_dir)
        self.mock_data_dir = mock_data_dir
        self.acquirer = DataAcquirer(self.client, mock_data_dir=mock_data_dir)

    def download_dataset(
        self,
        dataset_name: str,
        custom_date: Optional[str] = None,
    ) -> DownloadResult:
        """
        Download, parse, validate, and store a single dataset.

        Args:
            dataset_name: Name of the dataset (e.g., 'top-gainers-losers').
            custom_date: Optional trading date override (YYYY-MM-DD).

        Returns:
            DownloadResult containing status, record count, path, or error.
        """
        config = get_dataset_config(dataset_name)
        start_time = datetime.utcnow()

        log_event(
            logger,
            logging.INFO,
            f"Starting processing for dataset '{config.display_name}'",
            dataset=config.name,
            endpoint=config.primary_endpoint,
            attempt_number=1,
        )

        try:
            # 1. Acquire raw data
            acquisition = self.acquirer.acquire(config, custom_date=custom_date)
            trading_date = acquisition.trading_date or custom_date or datetime.utcnow().strftime("%Y-%m-%d")

            # 2. Parse payload using dataset-specific parser
            parser_fn = get_parser(config.parser_name)
            raw_records = parser_fn(acquisition.raw_data)

            # 3. Validate and deduplicate
            validated_records = validate_dataset(raw_records, config)

            # 4. Save atomic CSV
            csv_path = save_csv(
                rows=validated_records,
                output_dir=self.output_dir,
                filename_prefix=config.filename_prefix,
                trading_date=trading_date,
            )

            result = DownloadResult(
                dataset_name=config.name,
                endpoint=config.primary_endpoint,
                success=True,
                attempt_count=acquisition.attempt_count,
                record_count=len(validated_records),
                output_path=str(csv_path),
                trading_date=trading_date,
                timestamp=start_time,
            )

            log_event(
                logger,
                logging.INFO,
                f"Successfully saved {len(validated_records)} records to {csv_path}",
                dataset=config.name,
                endpoint=config.primary_endpoint,
                attempt_number=acquisition.attempt_count,
                success=True,
                record_count=len(validated_records),
                output_path=str(csv_path),
            )
            return result

        except Exception as exc:
            error_msg = str(exc)
            result = DownloadResult(
                dataset_name=config.name,
                endpoint=config.primary_endpoint,
                success=False,
                attempt_count=1,
                record_count=0,
                output_path=None,
                trading_date=custom_date,
                error_message=error_msg,
                timestamp=start_time,
            )

            log_event(
                logger,
                logging.ERROR,
                f"Failed processing dataset '{config.name}': {error_msg}",
                dataset=config.name,
                endpoint=config.primary_endpoint,
                attempt_number=1,
                success=False,
                record_count=0,
                error_message=error_msg,
            )
            return result

    def download_all(
        self,
        dataset_names: Optional[List[str]] = None,
        custom_date: Optional[str] = None,
    ) -> Dict[str, DownloadResult]:
        """
        Downloads all specified datasets, ensuring failure in one dataset
        does not halt processing for the others.

        Args:
            dataset_names: Optional list of datasets to process (defaults to all).
            custom_date: Optional trading date override (YYYY-MM-DD).

        Returns:
            Dictionary mapping dataset names to their DownloadResult.
        """
        targets = dataset_names or list(DATASET_REGISTRY.keys())
        results: Dict[str, DownloadResult] = {}

        log_event(
            logger,
            logging.INFO,
            f"Beginning batch execution for {len(targets)} dataset(s): {', '.join(targets)}",
        )

        for name in targets:
            try:
                res = self.download_dataset(name, custom_date=custom_date)
                results[name] = res
            except Exception as unhandled:
                # Catch-all safety guard to enforce isolation guarantee
                log_event(
                    logger,
                    logging.CRITICAL,
                    f"Unexpected unhandled failure during '{name}': {unhandled}",
                    dataset=name,
                    success=False,
                    error_message=str(unhandled),
                )
                results[name] = DownloadResult(
                    dataset_name=name,
                    endpoint=DATASET_REGISTRY.get(name, DatasetConfig(name, name, "", "")).primary_endpoint,
                    success=False,
                    attempt_count=1,
                    error_message=str(unhandled),
                )

        return results

    def close(self) -> None:
        """Close client resources."""
        self.client.close()
