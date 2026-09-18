"""
Validation module for NSE Market Data Downloader.

Provides modular, reusable validation checks for payload integrity,
record schemas, symbol validity, required columns, and duplicate pruning.
"""

from typing import Any, Dict, List, Optional, Set, Tuple
from config.datasets import DatasetConfig
from nse_downloader.models import ValidationError


def validate_response_exists(data: Any) -> None:
    """Verify that response data is not None or empty."""
    if data is None:
        raise ValidationError("Response payload is None")
    if isinstance(data, (str, list, dict)) and len(data) == 0:
        raise ValidationError("Response payload is empty")


def validate_expected_collection(data: Any) -> List[Dict[str, Any]]:
    """
    Ensure the records object is a non-empty list of dictionaries.
    """
    if not isinstance(data, list):
        raise ValidationError(f"Expected records collection to be a list, but got {type(data).__name__}")
    if not data:
        raise ValidationError("Records collection is empty (0 items)")
    return data


def validate_records_are_dicts(records: List[Any]) -> None:
    """Verify that every record in the collection is a dictionary."""
    for idx, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValidationError(
                f"Record at index {idx} is not a dictionary (type={type(item).__name__}): {item}"
            )


def validate_required_columns(
    records: List[Dict[str, Any]],
    required_columns: List[str],
) -> None:
    """
    Verify that all required columns are present and non-empty in the dataset.
    """
    if not required_columns or not records:
        return

    # Check first record has keys
    sample_keys = set(records[0].keys())
    missing_cols = [col for col in required_columns if col not in sample_keys]
    if missing_cols:
        raise ValidationError(
            f"Dataset is missing required columns: {missing_cols}. Present keys: {list(sample_keys)}"
        )

    # Verify that not all values in a required column are empty
    for col in required_columns:
        has_any_val = any(
            str(rec.get(col, "")).strip() != ""
            for rec in records
        )
        if not has_any_val:
            raise ValidationError(f"Required column '{col}' contains only empty values across all records")


def validate_and_filter_symbols(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validates that records possess a non-empty 'Symbol' column.
    Discards invalid/header/footer rows and raises ValidationError if no valid symbols remain.
    """
    valid_records: List[Dict[str, Any]] = []

    for idx, rec in enumerate(records):
        raw_symbol = rec.get("Symbol")
        if raw_symbol is None:
            continue

        symbol_str = str(raw_symbol).strip()
        # Filter out obvious non-symbol rows or headers
        if not symbol_str or symbol_str.upper() in ("TOTAL", "N/A", "NONE", "SYMBOL"):
            continue

        # Clean symbol in record
        rec["Symbol"] = symbol_str
        valid_records.append(rec)

    if not valid_records:
        raise ValidationError("All records lacked a valid non-empty 'Symbol'")

    return valid_records


def remove_duplicates(
    records: List[Dict[str, Any]],
    dedup_keys: List[str],
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Remove duplicate records based on dataset-specific deduplication keys.
    Preserves first-seen order.

    Returns:
        Tuple of (deduplicated_records, number_of_duplicates_removed)
    """
    if not dedup_keys:
        dedup_keys = ["Symbol"]

    seen: Set[Tuple[str, ...]] = set()
    deduped: List[Dict[str, Any]] = []
    removed_count = 0

    for rec in records:
        key_tuple = tuple(str(rec.get(k, "")).strip().upper() for k in dedup_keys)
        if key_tuple in seen:
            removed_count += 1
            continue
        seen.add(key_tuple)
        deduped.append(rec)

    return deduped, removed_count


def validate_dataset(
    records: List[Dict[str, Any]],
    config: DatasetConfig,
) -> List[Dict[str, Any]]:
    """
    Executes full validation pipeline for a parsed dataset.

    Steps:
    1. Response exists & is non-empty list
    2. Records are dictionaries
    3. Required columns exist
    4. Non-empty symbol validation
    5. Duplicate removal based on dataset-specific keys

    Returns:
        Sanitized, validated, and deduplicated record list.
    """
    validate_response_exists(records)
    validate_expected_collection(records)
    validate_records_are_dicts(records)
    validate_required_columns(records, config.required_columns)
    valid_symbols = validate_and_filter_symbols(records)
    deduped_records, _ = remove_duplicates(valid_symbols, config.dedup_keys)

    if not deduped_records:
        raise ValidationError(f"Dataset '{config.name}' has 0 valid records after validation pipeline")

    return deduped_records
