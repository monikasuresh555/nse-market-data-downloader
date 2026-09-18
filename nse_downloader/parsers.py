"""
Dataset-specific parser implementations for NSE Market Data Downloader.

Each parser inspects the real payload structure, normalizes field names,
and returns structured dictionaries ready for validation and storage.
Supports both JSON responses and CSV string downloads.
"""

import csv
import io
from typing import Any, Callable, Dict, List, Optional, Union

from nse_downloader.models import ParserError, ValidationError


def _parse_if_csv(payload: Any) -> Optional[List[Dict[str, Any]]]:
    """Check if payload is a CSV string and return parsed rows if so."""
    if not isinstance(payload, str):
        return None
    text = payload.strip()
    if not text:
        return None
    lines = text.splitlines()
    if len(lines) >= 1 and ("," in lines[0] or "\t" in lines[0]):
        try:
            reader = csv.DictReader(io.StringIO(text))
            rows = [dict(r) for r in reader if r]
            if rows:
                return rows
        except Exception:
            return None
    return None


def _find_data_array(payload: Any, search_keys: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Locate and return a list of dictionary records from nested JSON structures or CSV text.
    Tolerates common NSE variations such as `{"data": [...]}`, root list `[...]`,
    `{"upper": {"AllSec": {"data": [...]}}}`, `{"dataLtpGreater20": [...]}`,
    `{"allSec": {"data": [...]}}`, or CSV strings.
    """
    csv_rows = _parse_if_csv(payload)
    if csv_rows is not None:
        return csv_rows

    if isinstance(payload, list):
        if all(isinstance(x, dict) for x in payload):
            return payload
        raise ParserError(f"Expected list of dictionary records, but found non-dict items: {payload[:2]}")

    if not isinstance(payload, dict):
        raise ParserError(f"Expected dictionary or list root payload, got {type(payload).__name__}")

    # Check for 52-week-high keys: dataLtpGreater20 + dataLtpLess20
    if "dataLtpGreater20" in payload or "dataLtpLess20" in payload:
        combined: List[Dict[str, Any]] = []
        if isinstance(payload.get("dataLtpGreater20"), list):
            combined.extend(payload["dataLtpGreater20"])
        if isinstance(payload.get("dataLtpLess20"), list):
            combined.extend(payload["dataLtpLess20"])
        if combined:
            return combined

    # Check for upper band hitters: payload["upper"]["AllSec"]["data"] or payload["upper"]["data"]
    if "upper" in payload and isinstance(payload["upper"], dict):
        upper_obj = payload["upper"]
        if "AllSec" in upper_obj and isinstance(upper_obj["AllSec"], dict):
            sec_data = upper_obj["AllSec"].get("data")
            if isinstance(sec_data, list):
                return sec_data
        if "data" in upper_obj and isinstance(upper_obj["data"], list):
            return upper_obj["data"]

    # Check for variation payload keys: allSec, AllSec, NIFTY
    for sec_key in ["allSec", "AllSec", "allsec", "NIFTY"]:
        if sec_key in payload and isinstance(payload[sec_key], dict):
            sec_data = payload[sec_key].get("data")
            if isinstance(sec_data, list):
                return sec_data

    # Standard data keys
    keys_to_check = search_keys or ["data", "records", "items", "dataList", "list"]
    for key in keys_to_check:
        if key in payload:
            nested = payload[key]
            if isinstance(nested, list) and all(isinstance(x, dict) for x in nested):
                return nested
            if isinstance(nested, dict):
                for sub_key in ["data", "records", "items", "AllSec", "allSec"]:
                    if sub_key in nested:
                        val = nested[sub_key]
                        if isinstance(val, list):
                            return val
                        if isinstance(val, dict) and "data" in val and isinstance(val["data"], list):
                            return val["data"]

    # Any top-level key that maps to a list of dicts
    for k, v in payload.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
        if isinstance(v, dict) and "data" in v and isinstance(v["data"], list):
            return v["data"]

    raise ParserError(
        f"Could not locate a records list in payload. Available root keys: {list(payload.keys())}"
    )


def _get_val(record: Dict[str, Any], candidate_keys: List[str], default: Any = "") -> Any:
    """Retrieve first present value from candidate keys in a case-insensitive manner."""
    rec_lower = {k.lower().strip(): v for k, v in record.items()}
    for key in candidate_keys:
        if key in record:
            return record[key]
        cleaned_key = key.lower().strip()
        if cleaned_key in rec_lower:
            return rec_lower[cleaned_key]
    return default


def parse_top_gainers_losers(raw_payload: Any) -> List[Dict[str, Any]]:
    """
    Parses top gainers and losers. Supports:
    1. Combined payload with 'gainers' and 'losers' keys:
       {"gainers": {"allSec": {"data": [...]}, ...}, "losers": {"allSec": {"data": [...]}, ...}}
    2. Single structure containing 'gainers' and 'loosers' sections
    3. Flat list with already tagged directions
    4. CSV string format
    """
    csv_rows = _parse_if_csv(raw_payload)
    if csv_rows is not None:
        records: List[Dict[str, Any]] = []
        for r in csv_rows:
            sym = _get_val(r, ["symbol", "SYMBOL", "secName", "identifier", "Symbol"])
            if not sym or not str(sym).strip():
                continue
            pct_val = _get_val(r, ["perChange", "pChange", "%change", "change", "net_price"])
            direction = str(_get_val(r, ["direction", "Direction"], "gainer")).lower()
            try:
                if float(str(pct_val).replace(",", "")) < 0:
                    direction = "loser"
            except (ValueError, TypeError):
                pass
            records.append({
                "Symbol": str(sym).strip(),
                "Series": _get_val(r, ["series", "SERIES", "Series"], "EQ"),
                "Open": _get_val(r, ["open_price", "open", "openPrice", "Open"]),
                "High": _get_val(r, ["high_price", "high", "dayHigh", "High"]),
                "Low": _get_val(r, ["low_price", "low", "dayLow", "Low"]),
                "Prev. Close": _get_val(r, ["prev_price", "previousClose", "prevClose", "Prev. Close"]),
                "LTP": _get_val(r, ["ltp", "lastPrice", "LTP"]),
                "%change": pct_val,
                "Volume": _get_val(r, ["trade_quantity", "totalTradedVolume", "volume", "Volume"]),
                "Value": _get_val(r, ["turnover", "turnover_lakhs", "totalTradedValue", "value", "Value"]),
                "Direction": direction,
            })
        if records:
            return records

    records = []

    if not isinstance(raw_payload, dict):
        if isinstance(raw_payload, list):
            raw_gainers = raw_payload
            raw_losers = []
        else:
            raise ParserError(f"Expected dict, list, or CSV for top_gainers_losers, got {type(raw_payload).__name__}")
    else:
        raw_gainers = (
            raw_payload.get("gainers")
            or raw_payload.get("gainer")
            or raw_payload.get("GL_GAINERS")
        )
        raw_losers = (
            raw_payload.get("losers")
            or raw_payload.get("loser")
            or raw_payload.get("loosers")
            or raw_payload.get("GL_LOOSERS")
        )

        if raw_gainers is None and raw_losers is None:
            if "data" in raw_payload and isinstance(raw_payload["data"], dict):
                data_obj = raw_payload["data"]
                raw_gainers = data_obj.get("gainers") or data_obj.get("GL_GAINERS")
                raw_losers = data_obj.get("loosers") or data_obj.get("losers") or data_obj.get("GL_LOOSERS")

    def _extract_side(data_src: Any, direction: str) -> List[Dict[str, Any]]:
        if data_src is None:
            return []
        try:
            arr = _find_data_array(data_src)
        except ParserError:
            return []

        parsed_side: List[Dict[str, Any]] = []
        for r in arr:
            sym = _get_val(r, ["symbol", "secName", "identifier", "Symbol"])
            if not sym or not str(sym).strip():
                continue

            parsed_side.append({
                "Symbol": str(sym).strip(),
                "Series": _get_val(r, ["series", "Series"], "EQ"),
                "Open": _get_val(r, ["open_price", "open", "openPrice", "Open"]),
                "High": _get_val(r, ["high_price", "high", "dayHigh", "High"]),
                "Low": _get_val(r, ["low_price", "low", "dayLow", "Low"]),
                "Prev. Close": _get_val(r, ["prev_price", "previousClose", "prevClose", "Prev. Close"]),
                "LTP": _get_val(r, ["ltp", "lastPrice", "LTP"]),
                "%change": _get_val(r, ["perChange", "pChange", "net_price", "netPrice", "%change", "change"]),
                "Volume": _get_val(r, ["trade_quantity", "totalTradedVolume", "volume", "Volume"]),
                "Value": _get_val(r, ["turnover", "turnover_lakhs", "totalTradedValue", "value", "Value"]),
                "Direction": direction,
            })
        return parsed_side

    gainers_list = _extract_side(raw_gainers, "gainer")
    losers_list = _extract_side(raw_losers, "loser")

    if not gainers_list and not losers_list:
        try:
            general_arr = _find_data_array(raw_payload)
            for r in general_arr:
                sym = _get_val(r, ["symbol", "secName", "identifier", "Symbol"])
                if not sym:
                    continue
                pct_val = _get_val(r, ["perChange", "pChange", "net_price", "netPrice", "%change"])
                direction = "gainer"
                try:
                    if float(str(pct_val).replace(",", "")) < 0:
                        direction = "loser"
                except (ValueError, TypeError):
                    pass

                records.append({
                    "Symbol": str(sym).strip(),
                    "Series": _get_val(r, ["series", "Series"], "EQ"),
                    "Open": _get_val(r, ["open_price", "open", "openPrice", "Open"]),
                    "High": _get_val(r, ["high_price", "high", "dayHigh", "High"]),
                    "Low": _get_val(r, ["low_price", "low", "dayLow", "Low"]),
                    "Prev. Close": _get_val(r, ["prev_price", "previousClose", "prevClose", "Prev. Close"]),
                    "LTP": _get_val(r, ["ltp", "lastPrice", "LTP"]),
                    "%change": pct_val,
                    "Volume": _get_val(r, ["trade_quantity", "totalTradedVolume", "volume", "Volume"]),
                    "Value": _get_val(r, ["turnover", "turnover_lakhs", "totalTradedValue", "value", "Value"]),
                    "Direction": direction,
                })
        except ParserError as exc:
            raise ParserError(f"Failed to parse top gainers/losers payload: {exc}") from exc
    else:
        records.extend(gainers_list)
        records.extend(losers_list)

    if not records:
        raise ParserError("No valid records found in top-gainers-losers payload")

    return records


def parse_upper_band_hitters(raw_payload: Any) -> List[Dict[str, Any]]:
    """
    Parses Upper Band Hitters payload.
    Supports real NSE structure `{"upper": {"AllSec": {"data": [...]}}}`,
    flat list of dicts, or CSV strings.
    Fields: Symbol, Series, Prev. Close, LTP, %change, Upper Band, Volume, Value
    """
    items = _find_data_array(raw_payload)
    records: List[Dict[str, Any]] = []

    for r in items:
        sym = _get_val(r, ["symbol", "secName", "Symbol", "identifier", "SYMBOL"])
        if not sym or not str(sym).strip():
            continue

        # Compute previous close if not directly provided
        prev_close = _get_val(r, ["previousClose", "prevClose", "prev_price", "Prev. Close"])
        if not prev_close:
            ltp_val = _get_val(r, ["ltp", "lastPrice", "LTP"])
            chg_val = _get_val(r, ["change", "netPrice", "net_price"])
            try:
                prev_close = round(float(str(ltp_val).replace(",", "")) - float(str(chg_val).replace(",", "")), 2)
            except (ValueError, TypeError):
                prev_close = ""

        records.append({
            "Symbol": str(sym).strip(),
            "Series": _get_val(r, ["series", "Series", "SERIES"], "EQ"),
            "Prev. Close": prev_close,
            "LTP": _get_val(r, ["ltp", "lastPrice", "LTP"]),
            "%change": _get_val(r, ["pChange", "perChange", "%change", "change"]),
            "Upper Band": _get_val(r, ["priceBand", "upperBand", "bandLimit", "upper_band", "Upper Band", "band"]),
            "Volume": _get_val(r, ["totalTradedVol", "totalTradedVolume", "tradedQuantity", "volume", "Volume"]),
            "Value": _get_val(r, ["turnover", "totalTradedValue", "tradedValue", "value", "Value", "totalValue"]),
        })

    if not records:
        raise ParserError("No records could be parsed from upper-band-hitters payload")

    return records


def parse_volume_gainers_spurts(raw_payload: Any) -> List[Dict[str, Any]]:
    """
    Parses Volume Gainers and Spurts payload.
    Supports real NSE structure `{"data": [{"symbol": ..., "volume": ..., "week1AvgVolume": ...}]}`.
    Fields: Symbol, Series, LTP, %change, Prev Week Avg Vol, Week Avg Vol, Volume Spurt %, Volume, Value
    """
    items = _find_data_array(raw_payload)
    records: List[Dict[str, Any]] = []

    for r in items:
        sym = _get_val(r, ["symbol", "secName", "Symbol", "identifier", "SYMBOL"])
        if not sym or not str(sym).strip():
            continue

        records.append({
            "Symbol": str(sym).strip(),
            "Series": _get_val(r, ["series", "Series", "SERIES"], "EQ"),
            "LTP": _get_val(r, ["ltp", "lastPrice", "LTP"]),
            "%change": _get_val(r, ["pChange", "perChange", "%change", "change"]),
            "Prev Week Avg Vol": _get_val(
                r,
                ["week1AvgVolume", "prevWeekAvgVol", "weekAvgVolPrev", "previousWeekAvgVol", "prevAvgVol", "Prev Week Avg Vol"],
            ),
            "Week Avg Vol": _get_val(
                r,
                ["week2AvgVolume", "weekAvgVol", "avgVolume", "currentWeekAvgVol", "Week Avg Vol"],
            ),
            "Volume Spurt %": _get_val(
                r,
                ["week1volChange", "volumeSpurt", "volumeSpurtPercent", "spurtPercentage", "spurt", "Volume Spurt %"],
            ),
            "Volume": _get_val(r, ["volume", "totalTradedVolume", "tradedQuantity", "Volume"]),
            "Value": _get_val(r, ["turnover", "totalTradedValue", "tradedValue", "value", "Value", "totalValue"]),
        })

    if not records:
        raise ParserError("No records could be parsed from volume-gainers-spurts payload")

    return records


def parse_52_week_high(raw_payload: Any) -> List[Dict[str, Any]]:
    """
    Parses 52-Week High Equity Market payload.
    Supports real live NSE structure `{"dataLtpGreater20": [...], "dataLtpLess20": [...]}`,
    standard dicts with `data`, or NSE archives CSV (`Adjusted_52_Week_High`).
    Fields: Symbol, Series, LTP, %change, 52W High, Prev 52W High, 52W High Date, Volume, Value
    """
    items = _find_data_array(raw_payload)
    records: List[Dict[str, Any]] = []

    for r in items:
        sym = _get_val(r, ["symbol", "SYMBOL", "secName", "Symbol", "identifier"])
        if not sym or not str(sym).strip():
            continue

        high_val = _get_val(
            r,
            ["new52WHL", "Adjusted_52_Week_High", "high52", "yearHigh", "high52Price", "52W High"],
        )
        ltp_val = _get_val(r, ["ltp", "lastPrice", "LTP", "Adjusted_52_Week_High"])

        records.append({
            "Symbol": str(sym).strip(),
            "Series": _get_val(r, ["series", "SERIES", "Series"], "EQ"),
            "LTP": ltp_val,
            "%change": _get_val(r, ["pChange", "perChange", "%change", "change", "net_price"]),
            "52W High": high_val,
            "Prev 52W High": _get_val(r, ["prev52WHL", "prevHigh52", "previous52High", "prevYearHigh", "Prev 52W High"]),
            "52W High Date": _get_val(r, ["prevHLDate", "52_Week_High_Date", "high52Date", "dtYearHigh", "52W_date", "52W High Date", "date"]),
            "Volume": _get_val(r, ["volume", "totalTradedVol", "totalTradedVolume", "tradedQuantity", "Volume"]),
            "Value": _get_val(r, ["turnover", "totalTradedValue", "tradedValue", "value", "Value", "totalValue"]),
        })

    if not records:
        raise ParserError("No records could be parsed from 52-week-high payload")

    return records


# Registry of available parser functions
PARSER_REGISTRY: Dict[str, Callable[[Any], List[Dict[str, Any]]]] = {
    "top_gainers_losers": parse_top_gainers_losers,
    "upper_band_hitters": parse_upper_band_hitters,
    "volume_gainers_spurts": parse_volume_gainers_spurts,
    "52_week_high": parse_52_week_high,
}


def get_parser(parser_name: str) -> Callable[[Any], List[Dict[str, Any]]]:
    """Retrieve parser function by registered name."""
    if parser_name not in PARSER_REGISTRY:
        raise KeyError(
            f"Parser '{parser_name}' not found. Available parsers: {list(PARSER_REGISTRY.keys())}"
        )
    return PARSER_REGISTRY[parser_name]
