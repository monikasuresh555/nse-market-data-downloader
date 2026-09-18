"""
Unit tests for data validation, schema enforcement, and deduplication.
"""

import pytest

from config.datasets import DATASET_REGISTRY
from nse_downloader.models import ValidationError
from nse_downloader.validation import (
    remove_duplicates,
    validate_and_filter_symbols,
    validate_dataset,
    validate_expected_collection,
    validate_records_are_dicts,
    validate_required_columns,
    validate_response_exists,
)


class TestValidation:
    """Validation test suite."""

    def test_validate_response_exists(self):
        """Verify None or empty response triggers ValidationError."""
        with pytest.raises(ValidationError):
            validate_response_exists(None)

        with pytest.raises(ValidationError):
            validate_response_exists([])

        with pytest.raises(ValidationError):
            validate_response_exists({})

    def test_validate_expected_collection(self):
        """Verify only non-empty lists are accepted."""
        with pytest.raises(ValidationError):
            validate_expected_collection("not a list")

        with pytest.raises(ValidationError):
            validate_expected_collection([])

        valid_list = [{"Symbol": "TCS"}]
        assert validate_expected_collection(valid_list) == valid_list

    def test_validate_records_are_dicts(self):
        """Verify lists with non-dict records raise ValidationError."""
        with pytest.raises(ValidationError):
            validate_records_are_dicts([{"Symbol": "TCS"}, "not-a-dict"])

    def test_validate_required_columns(self):
        """Verify missing required columns trigger ValidationError."""
        records = [
            {"Symbol": "TCS", "LTP": 4000.0},
            {"Symbol": "INFY", "LTP": 1800.0},
        ]
        # Missing 'Direction'
        with pytest.raises(ValidationError) as exc_info:
            validate_required_columns(records, ["Symbol", "LTP", "Direction"])
        assert "missing required columns" in str(exc_info.value).lower()

    def test_validate_and_filter_symbols(self):
        """Verify rows with missing or whitespace-only symbols are filtered."""
        records = [
            {"Symbol": "TCS", "LTP": 4000.0},
            {"Symbol": "   ", "LTP": 0.0},
            {"Symbol": None, "LTP": 0.0},
            {"Symbol": "TOTAL", "LTP": 99999.0},  # Filter total/summary row
            {"Symbol": "INFY", "LTP": 1800.0},
        ]
        filtered = validate_and_filter_symbols(records)
        assert len(filtered) == 2
        symbols = [r["Symbol"] for r in filtered]
        assert symbols == ["TCS", "INFY"]

    def test_all_invalid_symbols_raises_error(self):
        """Verify that when no valid symbol rows exist, ValidationError is raised."""
        records = [
            {"Symbol": "", "LTP": 0.0},
            {"Symbol": None, "LTP": 0.0},
        ]
        with pytest.raises(ValidationError):
            validate_and_filter_symbols(records)

    def test_duplicate_removal(self):
        """Verify duplicate records are pruned according to dedup keys."""
        records = [
            {"Symbol": "TCS", "Direction": "gainer", "LTP": 4100.0},
            {"Symbol": "TCS", "Direction": "gainer", "LTP": 4105.0},  # duplicate
            {"Symbol": "INFY", "Direction": "gainer", "LTP": 1850.0},
            {"Symbol": "tcs", "Direction": "GAINER", "LTP": 4110.0},  # case-insensitive dup
        ]
        deduped, removed_count = remove_duplicates(records, ["Symbol", "Direction"])
        assert len(deduped) == 2
        assert removed_count == 2
        assert [r["Symbol"] for r in deduped] == ["TCS", "INFY"]

    def test_full_dataset_validation_pipeline(self):
        """Verify end-to-end dataset validation using configuration rules."""
        config = DATASET_REGISTRY["top-gainers-losers"]
        records = [
            {"Symbol": "TCS", "LTP": 4100.0, "Direction": "gainer", "Open": 4050.0},
            {"Symbol": "TCS", "LTP": 4100.0, "Direction": "gainer", "Open": 4050.0},  # dup
            {"Symbol": "WIPRO", "LTP": 520.0, "Direction": "loser", "Open": 530.0},
        ]
        validated = validate_dataset(records, config)
        assert len(validated) == 2
        assert validated[0]["Symbol"] == "TCS"
        assert validated[1]["Symbol"] == "WIPRO"
