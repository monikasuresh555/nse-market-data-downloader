"""
Unit tests for dataset parsers.
Verifies structure inspection, field extraction, normalizations, and error handling.
"""

import json
from pathlib import Path
import pytest

from nse_downloader.models import ParserError, ValidationError
from nse_downloader.parsers import (
    parse_52_week_high,
    parse_top_gainers_losers,
    parse_upper_band_hitters,
    parse_volume_gainers_spurts,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestParsers:
    """Tests for dataset-specific parsing functions."""

    def test_parse_top_gainers_losers_combined(self):
        """Verify top gainers & losers parsed with 'Direction' column."""
        with open(FIXTURES_DIR / "top_gainers_losers.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        records = parse_top_gainers_losers(raw_data)

        assert len(records) == 5  # 3 gainers + 2 losers

        # Check gainers
        gainers = [r for r in records if r["Direction"] == "gainer"]
        assert len(gainers) == 3
        reliance = next(r for r in gainers if r["Symbol"] == "RELIANCE")
        assert reliance["Open"] == 2950.00
        assert reliance["High"] == 3020.50
        assert reliance["Low"] == 2940.00
        assert reliance["Prev. Close"] == 2930.00
        assert reliance["LTP"] == 3010.25
        assert reliance["%change"] == 2.74
        assert reliance["Volume"] == 4521000
        assert reliance["Value"] == 135400.50

        # Check losers
        losers = [r for r in records if r["Direction"] == "loser"]
        assert len(losers) == 2
        hdfc = next(r for r in losers if r["Symbol"] == "HDFCBANK")
        assert hdfc["LTP"] == 1620.00
        assert hdfc["Direction"] == "loser"

    def test_parse_upper_band_hitters(self):
        """Verify upper band hitters parsing."""
        with open(FIXTURES_DIR / "upper_band_hitters.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        records = parse_upper_band_hitters(raw_data)

        assert len(records) == 3
        zomato = records[0]
        assert zomato["Symbol"] == "ZOMATO"
        assert zomato["Series"] == "EQ"
        assert zomato["Prev. Close"] == 265.40
        assert zomato["LTP"] == 291.94
        assert zomato["%change"] == 10.00
        assert zomato["Upper Band"] == 291.94
        assert zomato["Volume"] == 45120000
        assert zomato["Value"] == 131750.40

    def test_parse_volume_gainers_spurts(self):
        """Verify volume gainers spurts parsing."""
        with open(FIXTURES_DIR / "volume_gainers_spurts.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        records = parse_volume_gainers_spurts(raw_data)

        assert len(records) == 3
        yesbank = records[0]
        assert yesbank["Symbol"] == "YESBANK"
        assert yesbank["Series"] == "EQ"
        assert yesbank["LTP"] == 24.50
        assert yesbank["%change"] == 6.52
        assert yesbank["Prev Week Avg Vol"] == 25000000
        assert yesbank["Week Avg Vol"] == 110000000
        assert yesbank["Volume Spurt %"] == 340.00
        assert yesbank["Volume"] == 150000000
        assert yesbank["Value"] == 36750.00

    def test_parse_52_week_high(self):
        """Verify 52 week high parsing."""
        with open(FIXTURES_DIR / "52_week_high.json", "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        records = parse_52_week_high(raw_data)

        assert len(records) == 3
        airtel = records[0]
        assert airtel["Symbol"] == "BHARTIARTL"
        assert airtel["Series"] == "EQ"
        assert airtel["LTP"] == 1685.00
        assert airtel["%change"] == 3.42
        assert airtel["52W High"] == 1698.80
        assert airtel["Prev 52W High"] == 1650.00
        assert airtel["52W High Date"] == "18-Sep-2026"
        assert airtel["Volume"] == 6800000
        assert airtel["Value"] == 114580.00

    def test_unexpected_json_structure_raises_error(self):
        """Verify that unexpected JSON structure raises ParserError."""
        invalid_payload = {"status": "ok", "unexpectedKey": "no data array here"}

        with pytest.raises(ParserError):
            parse_upper_band_hitters(invalid_payload)

        with pytest.raises(ParserError):
            parse_52_week_high(invalid_payload)

        with pytest.raises(ParserError):
            parse_top_gainers_losers(invalid_payload)

    def test_empty_records_list_raises_error(self):
        """Verify that payload with empty data array raises ParserError."""
        empty_payload = {"data": []}

        with pytest.raises(ParserError):
            parse_upper_band_hitters(empty_payload)

    def test_parse_52_week_high_live_split_schema(self):
        """Verify parsing 52-week-high payload using dataLtpGreater20 and dataLtpLess20."""
        live_payload = {
            "timestamp": "18-Sep-2026 15:30:00",
            "dataLtpGreater20": [
                {
                    "symbol": "INFY",
                    "series": "EQ",
                    "ltp": 1950.0,
                    "pChange": 1.45,
                    "new52WHL": 1960.0,
                    "prev52WHL": 1920.0,
                    "prevHLDate": "17-Sep-2026",
                    "volume": 3500000,
                    "turnover": 68000.0,
                }
            ],
            "dataLtpLess20": [
                {
                    "symbol": "PENNYSTK",
                    "series": "EQ",
                    "ltp": 14.5,
                    "pChange": 4.9,
                    "new52WHL": 14.5,
                    "prev52WHL": 13.8,
                    "prevHLDate": "15-Sep-2026",
                    "volume": 1200000,
                    "turnover": 1740.0,
                }
            ],
        }
        records = parse_52_week_high(live_payload)
        assert len(records) == 2
        symbols = [r["Symbol"] for r in records]
        assert "INFY" in symbols
        assert "PENNYSTK" in symbols
        infy = next(r for r in records if r["Symbol"] == "INFY")
        assert infy["52W High"] == 1960.0
        assert infy["Prev 52W High"] == 1920.0

    def test_parse_upper_band_hitters_live_nested_schema(self):
        """Verify parsing upper-band-hitters from nested upper.AllSec.data structure."""
        nested_payload = {
            "upper": {
                "AllSec": {
                    "data": [
                        {
                            "symbol": "TATASTEEL",
                            "series": "EQ",
                            "ltp": 160.0,
                            "change": 8.0,
                            "pChange": 5.26,
                            "priceBand": 160.0,
                            "totalTradedVol": 45000000,
                            "turnover": 72000.0,
                        }
                    ]
                }
            }
        }
        records = parse_upper_band_hitters(nested_payload)
        assert len(records) == 1
        record = records[0]
        assert record["Symbol"] == "TATASTEEL"
        assert record["LTP"] == 160.0
        assert record["Prev. Close"] == 152.0  # Computed from ltp - change
        assert record["Upper Band"] == 160.0

    def test_parse_csv_string_payload(self):
        """Verify parsing CSV formatted response for 52-week-high archives."""
        csv_text = (
            "SYMBOL,SERIES,Adjusted_52_Week_High,52_Week_High_Date\n"
            "WIPRO,EQ,580.00,18-SEP-2026\n"
            "TCS,EQ,4400.00,18-SEP-2026\n"
        )
        records = parse_52_week_high(csv_text)
        assert len(records) == 2
        assert records[0]["Symbol"] == "WIPRO"
        assert records[0]["52W High"] == "580.00"
        assert records[1]["Symbol"] == "TCS"

