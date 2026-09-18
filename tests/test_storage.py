"""
Unit tests for atomic CSV storage, date partitioning, and overwrite idempotency.
"""

import csv
from pathlib import Path
import pytest

from nse_downloader.models import StorageError
from nse_downloader.storage import save_csv


class TestStorage:
    """Storage test suite."""

    def test_csv_creation_and_headers(self, tmp_path):
        """Verify CSV is correctly created with expected headers and row values."""
        rows = [
            {"Symbol": "TCS", "LTP": 4180.0, "Direction": "gainer"},
            {"Symbol": "INFY", "LTP": 1840.0, "Direction": "gainer"},
        ]
        trading_date = "2026-09-18"
        file_path = save_csv(rows, tmp_path, "top_gainers_losers", trading_date)

        assert file_path.exists()
        assert file_path.parent.name == "2026-09-18"
        assert file_path.name == "top_gainers_losers_2026-09-18.csv"

        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = list(reader)

        assert len(records) == 2
        assert records[0]["Symbol"] == "TCS"
        assert records[0]["LTP"] == "4180.0"
        assert records[0]["Direction"] == "gainer"

    def test_idempotent_overwrite_no_duplicate_files(self, tmp_path):
        """
        Verify that re-running save_csv on the same day overwrites the deterministic
        filename and does not produce duplicate files like 'filename (1).csv'.
        """
        initial_rows = [{"Symbol": "TCS", "LTP": 4100.0}]
        updated_rows = [{"Symbol": "TCS", "LTP": 4200.0}, {"Symbol": "WIPRO", "LTP": 530.0}]
        trading_date = "2026-09-18"

        # First run
        path1 = save_csv(initial_rows, tmp_path, "test_dataset", trading_date)
        # Second run on same date
        path2 = save_csv(updated_rows, tmp_path, "test_dataset", trading_date)

        assert path1 == path2
        date_dir = tmp_path / trading_date
        csv_files = list(date_dir.glob("*.csv"))

        # Exactly 1 file should exist in the directory
        assert len(csv_files) == 1
        assert csv_files[0].name == "test_dataset_2026-09-18.csv"

        # Content must reflect updated rows
        with open(path2, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))
        assert len(reader) == 2
        assert reader[0]["LTP"] == "4200.0"

    def test_utf8_encoding(self, tmp_path):
        """Verify proper UTF-8 handling for special characters or currency symbols."""
        rows = [{"Symbol": "M&M", "Notes": "Special Char: ₹, %, ©"}]
        trading_date = "2026-09-18"
        file_path = save_csv(rows, tmp_path, "test_utf8", trading_date)

        content = file_path.read_text(encoding="utf-8")
        assert "₹" in content
        assert "©" in content

    def test_save_empty_rows_raises_error(self, tmp_path):
        """Verify attempting to save an empty rows list raises StorageError."""
        with pytest.raises(StorageError):
            save_csv([], tmp_path, "empty_dataset", "2026-09-18")
