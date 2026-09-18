"""
Integration tests for DownloaderApplication.
Verifies full pipeline orchestration, failure isolation, and summary reporting.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from config.datasets import DATASET_REGISTRY
from nse_downloader.application import DownloaderApplication
from nse_downloader.models import DownloadResult, ServerError

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestApplication:
    """Application orchestration and failure isolation tests."""

    def test_full_pipeline_with_mock_fixtures(self, tmp_path):
        """Verify end-to-end download and storage of all 4 datasets using mock fixtures."""
        app = DownloaderApplication(
            output_dir=tmp_path,
            mock_data_dir=str(FIXTURES_DIR),
        )

        results = app.download_all(custom_date="2026-09-18")

        assert len(results) == 4
        for name, res in results.items():
            assert res.success is True, f"Dataset {name} failed: {res.error_message}"
            assert res.record_count > 0
            assert res.output_path is not None
            assert Path(res.output_path).exists()

        # Check saved files in directory
        saved_dir = tmp_path / "2026-09-18"
        assert saved_dir.exists()
        saved_files = {f.name for f in saved_dir.glob("*.csv")}

        expected_files = {
            "top_gainers_losers_2026-09-18.csv",
            "upper_band_hitters_2026-09-18.csv",
            "volume_gainers_spurts_2026-09-18.csv",
            "52_week_high_2026-09-18.csv",
        }
        assert expected_files.issubset(saved_files)

    def test_single_dataset_failure_does_not_halt_others(self, tmp_path):
        """
        Requirement 10: A failure in one dataset must NOT unnecessarily stop
        the remaining datasets.
        """
        app = DownloaderApplication(
            output_dir=tmp_path,
            mock_data_dir=str(FIXTURES_DIR),
        )

        # Simulate failure specifically for 'upper-band-hitters'
        orig_acquire = app.acquirer.acquire

        def selective_failing_acquire(config, custom_date=None):
            if config.name == "upper-band-hitters":
                raise ServerError("Simulated 500 Server Error on upper band hitters", 500, config.primary_endpoint)
            return orig_acquire(config, custom_date)

        app.acquirer.acquire = selective_failing_acquire

        results = app.download_all(custom_date="2026-09-18")

        # Verify failure in upper-band-hitters
        assert results["upper-band-hitters"].success is False
        assert "500" in results["upper-band-hitters"].error_message

        # Verify all other datasets succeeded
        assert results["top-gainers-losers"].success is True
        assert results["volume-gainers-spurts"].success is True
        assert results["52-week-high"].success is True

        # Verify corresponding CSVs were saved despite the one failure
        saved_dir = tmp_path / "2026-09-18"
        saved_files = {f.name for f in saved_dir.glob("*.csv")}
        assert "top_gainers_losers_2026-09-18.csv" in saved_files
        assert "volume_gainers_spurts_2026-09-18.csv" in saved_files
        assert "52_week_high_2026-09-18.csv" in saved_files
        assert "upper_band_hitters_2026-09-18.csv" not in saved_files

    def test_download_single_dataset(self, tmp_path):
        """Verify downloading just one specified dataset."""
        app = DownloaderApplication(
            output_dir=tmp_path,
            mock_data_dir=str(FIXTURES_DIR),
        )

        result = app.download_dataset("52-week-high", custom_date="2026-09-18")

        assert result.success is True
        assert result.dataset_name == "52-week-high"
        assert result.record_count == 3
        assert Path(result.output_path).exists()
