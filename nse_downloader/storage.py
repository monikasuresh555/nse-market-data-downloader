"""
Storage module for NSE Market Data Downloader.

Implements atomic CSV serialization, deterministic daily directory partitioning,
and idempotent overwrite semantics.
"""

import csv
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Union

from nse_downloader.models import StorageError

logger = logging.getLogger("nse_downloader")


def save_csv(
    rows: List[Dict[str, Any]],
    output_dir: Union[str, Path],
    filename_prefix: str,
    trading_date: str,
) -> Path:
    """
    Atomically writes rows to a CSV file partitioned by trading date.

    Directory structure:
        output_dir/YYYY-MM-DD/

    Target filename:
        dataset_prefix_YYYY-MM-DD.csv

    Atomic write mechanism:
        1. Writes to a temporary file (.tmp) located inside the target directory.
        2. Flushes and fsyncs buffers to ensure on-disk persistence.
        3. Calls os.replace() to atomically swap the temp file into the target filename.
        4. Overwrites existing files cleanly without creating 'file (1).csv' duplicates.

    Args:
        rows: List of dictionary records to write.
        output_dir: Base directory path for outputs.
        filename_prefix: Dataset prefix (e.g., 'top_gainers_losers').
        trading_date: Trading date string in YYYY-MM-DD format.

    Returns:
        Path to the saved CSV file.

    Raises:
        StorageError: If directory creation, CSV writing, or atomic swap fails.
    """
    if not rows:
        raise StorageError(f"Cannot save empty rows for '{filename_prefix}'")

    if not trading_date or not trading_date.strip():
        raise StorageError("Trading date must be provided in YYYY-MM-DD format")

    try:
        base_path = Path(output_dir)
        date_dir = base_path / trading_date.strip()
        date_dir.mkdir(parents=True, exist_ok=True)

        target_filename = f"{filename_prefix}_{trading_date.strip()}.csv"
        target_path = date_dir / target_filename

        # Extract fieldnames preserving key order from first record
        fieldnames = list(rows[0].keys())

        temp_file_path: Union[Path, None] = None

        # Write to temporary file in the same directory to ensure same filesystem for os.replace()
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=date_dir,
                prefix=f".{filename_prefix}_",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                temp_file_path = Path(tmp_file.name)
                writer = csv.DictWriter(
                    tmp_file,
                    fieldnames=fieldnames,
                    extrasaction="ignore",
                )
                writer.writeheader()
                writer.writerows(rows)

                # Ensure all contents are flushed to physical disk
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            # Atomically replace target file
            os.replace(temp_file_path, target_path)
            try:
                os.chmod(target_path, 0o644)
            except OSError:
                pass
            temp_file_path = None  # Replaced successfully

            return target_path

        finally:
            # Clean up temporary file if an error occurred prior to os.replace()
            if temp_file_path and temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                except OSError:
                    pass

    except Exception as exc:
        raise StorageError(
            f"Failed to atomically save CSV for '{filename_prefix}' on {trading_date}: {exc}"
        ) from exc
