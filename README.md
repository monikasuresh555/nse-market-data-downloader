# NSE Market Data Downloader

A production-minded, resilient Python CLI application engineered to automatically download, validate, and store end-of-day and live market datasets from the National Stock Exchange of India (NSE).

Designed specifically for automated execution, cron jobs, and financial data pipelines.

---

## Table of Contents

1. [Overview](#overview)
2. [Supported Datasets](#supported-datasets)
3. [Architecture & Design Principles](#architecture--design-principles)
4. [Requirements & Installation](#requirements--installation)
5. [CLI Usage & Options](#cli-usage--options)
6. [Data Storage & Directory Organization](#data-storage--directory-organization)
7. [NSE Acquisition & Session Management](#nse-acquisition--session-management)
8. [Validation Pipeline](#validation-pipeline)
9. [Error Handling & Retry Strategy](#error-handling--retry-strategy)
10. [Duplicate Pruning & Idempotency](#duplicate-pruning--idempotency)
11. [Running Tests](#running-tests)
12. [Automation (Linux Cron & Windows Task Scheduler)](#automation)
13. [Extensibility: Adding New Datasets](#extensibility-adding-new-datasets)
14. [Limitations & Assumptions](#limitations--assumptions)

---

## Overview

The NSE Market Data Downloader automates the acquisition of official equity market data feeds from NSE India without requiring browser automation (Selenium/Playwright) or manual scraping. It issues clean HTTP calls directly to NSE's internal JSON endpoints, verifies response schemas, removes duplicate items, and writes clean, normalized CSV files atomically to disk.

### Key Capabilities

- **Zero Manual Intervention**: Interacts directly with official REST endpoints using realistic browser session negotiation.
- **Unified Top Gainers & Losers**: Automatically acquires both gainers and losers and merges them into a single consolidated dataset with a `Direction` column (`gainer` / `loser`).
- **Atomic File Persistence**: Writes to a temporary buffer and executes an `os.replace()` atomic swap, ensuring zero file corruption or incomplete reads by downstream consumers.
- **Idempotent Overwrites**: Re-running the downloader on the same trading day updates existing files cleanly without creating confusing duplicates like `file (1).csv`.
- **Fault Isolation**: If any single dataset fails (e.g., due to an unexpected upstream schema change or transient endpoint outage), processing continues for the remaining datasets.
- **Structured Audit Logs**: Every execution records timestamp, dataset, endpoint, attempt count, record count, output path, and error diagnostics.

---

## Supported Datasets

The application natively supports four core NSE market-data feeds:

| Dataset CLI Identifier | Official Webpage | Primary Endpoint | Output Prefix |
| :--- | :--- | :--- | :--- |
| `top-gainers-losers` | [Top Gainers & Losers](https://www.nseindia.com/market-data/top-gainers-losers) | `/api/live-analysis-variations` | `top_gainers_losers` |
| `upper-band-hitters` | [Upper Band Hitters](https://www.nseindia.com/market-data/upper-band-hitters) | `/api/live-analysis-price-band-hitter` | `upper_band_hitters` |
| `volume-gainers-spurts` | [Volume Gainers & Spurts](https://www.nseindia.com/market-data/volume-gainers-spurts) | `/api/live-analysis-volume-gainers` | `volume_gainers_spurts` |
| `52-week-high` | [52 Week High Equity](https://www.nseindia.com/market-data/52-week-high-equity-market) | `/api/live-analysis-52week?index=high` | `52_week_high` |

---

## Architecture & Design Principles

The codebase follows a strict separation of concerns:

```text
main.py (CLI Interface & Argument Dispatcher)
  |
  v
DownloaderApplication (Orchestrator & Fault Boundary)
  |
  +--> NSEClient (Session lifecycle, cookies, retry with backoff, HTTP errors)
  |
  +--> DataAcquirer (Coordinates single/multi-endpoint payloads & trading date detection)
  |
  +--> Dataset Parser (Inspects JSON tree, extracts and normalizes fields)
  |
  +--> Validator (Verifies non-empty payload, required columns, symbol rules, deduplication)
  |
  +--> CSV Storage (Atomic writes, directory partitioning, UTF-8 formatting)
```

### Project Layout

```text
NSE-Market-Data-Downloader/
|-- main.py                     # CLI entry point
|-- requirements.txt            # Python dependencies
|-- README.md                   # Complete architectural documentation
|-- Dockerfile                  # Containerized deployment specification
|-- .gitignore                  # Git exclusion rules
|-- config/
|   |-- __init__.py
|   `-- datasets.py             # Central registry of endpoints, headers, schema rules
|-- nse_downloader/
|   |-- __init__.py
|   |-- client.py               # Session-aware HTTP client with backoff
|   |-- acquisition.py          # Multi-endpoint acquisition & date resolution
|   |-- parsers.py              # Dataset-specific structural parsers
|   |-- validation.py           # Reusable validation & deduplication logic
|   |-- storage.py              # Atomic CSV persistence & date partitioning
|   |-- application.py          # High-level pipeline coordinator
|   |-- logging_config.py       # 8-attribute structured logging formatter
|   `-- models.py               # Domain models and typed exception hierarchy
|-- tests/
|   |-- __init__.py
|   |-- fixtures/               # Offline JSON mock responses for test suite
|   |-- test_client.py          # HTTP, timeout, 429, 500, and backoff tests
|   |-- test_parsers.py         # JSON inspection, extraction, and error tests
|   |-- test_validation.py      # Schema enforcement, column checks, dedup tests
|   |-- test_storage.py         # Atomic write, idempotency, UTF-8 tests
|   `-- test_application.py     # Fault isolation & end-to-end pipeline tests
`-- sample_output/
    `-- 2026-09-18/             # Deterministic daily folder with sample CSVs
```

---

## Requirements & Installation

### Prerequisites

- Python 3.10 or higher
- `pip` package manager

### Setup

1. **Clone or navigate to the repository**:
   ```bash
   cd NSE-Market-Data-Downloader
   ```

2. **Create and activate a virtual environment**:

   **Windows (PowerShell)**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

   **Linux / macOS**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

---

## CLI Usage & Options

### 1. Download All Four Datasets

```bash
python main.py
```

### 2. Download an Individual Dataset

```bash
# Top gainers and losers
python main.py --dataset top-gainers-losers

# Upper band circuit hitters
python main.py --dataset upper-band-hitters

# Volume gainers & spurts
python main.py --dataset volume-gainers-spurts

# 52-week high equities
python main.py --dataset 52-week-high
```

### 3. Custom Output Directory

```bash
python main.py --output-dir /path/to/my_data
```

### 4. Explicit Trading Date Override

Explicit output/trading date override (`YYYY-MM-DD`). Historical data availability depends on the dataset and NSE endpoint/archive support.

```bash
python main.py --date 2026-09-18
```

### 5. Offline Demonstration / Mock Execution

When testing in environments where cloud IP ranges are geoblocked by NSE:

```bash
python main.py --mock-dir tests/fixtures
```

### 6. Command-Line Options Reference

| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--dataset` | `-d` | `None` (All) | Specific dataset to process (`top-gainers-losers`, `upper-band-hitters`, `volume-gainers-spurts`, `52-week-high`). |
| `--output-dir` | `-o` | `data` | Base output directory for saved CSV files. |
| `--date` | | `None` | Explicit output/trading date override (`YYYY-MM-DD`). Historical data availability depends on the dataset and NSE endpoint/archive support. |
| `--log-level` | | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `--log-file` | | `None` | Path to save structured log outputs to disk. |
| `--timeout` | | `15` | Request timeout in seconds. |
| `--retries` | | `3` | Maximum retry attempts for transient HTTP errors. |
| `--mock-dir` | | `None` | Directory containing JSON fixtures for offline execution. |

---

## Data Storage & Directory Organization

Output files are partitioned deterministically by trading date in `YYYY-MM-DD` format:

```text
data/
`-- 2026-09-18/
    |-- top_gainers_losers_2026-09-18.csv
    |-- upper_band_hitters_2026-09-18.csv
    |-- volume_gainers_spurts_2026-09-18.csv
    `-- 52_week_high_2026-09-18.csv
```

### Atomic File Writes

To prevent incomplete CSV files if a job is terminated mid-write:
1. Rows are written to a hidden temporary file in the target directory (e.g. `.top_gainers_losers_xyz.tmp`).
2. Buffers are flushed and `os.fsync(fileno)` is called to ensure data is committed to disk.
3. `os.replace()` atomically moves the temporary file to the final destination.
4. If an exception occurs, the temporary file is unlinked, leaving existing files intact.

---

## NSE Acquisition & Session Management

NSE India employs Akamai Web Application Firewall (WAF) and bot-detection heuristics that reject direct API calls unless preceded by a valid browser handshake:

1. **Market-Page Session Handshake**: `NSEClient` initializes a `requests.Session` and performs a `GET` to the relevant market-data page (e.g. `https://www.nseindia.com/market-data/top-gainers-losers`) with browser-identical headers (`User-Agent`, `sec-ch-ua`, `Accept-Language`, `Referer`). Visiting an actual content page establishes valid Akamai challenge tokens (`AKA_A2`, `bm_sv`, `_abck`) that are required by live endpoints.
2. **Dynamic Referer Context**: Every API request dynamically sets the `Referer` header matching its corresponding market-data webpage URL.
3. **Session Re-negotiation**: If an API request returns HTTP 401 or 403 (indicating cookie expiry or session timeout), `NSEClient` automatically re-initializes the session and retries.
4. **Dual-Format Fallback**: For datasets such as `52-week-high`, the application preferentially queries the real-time JSON API and seamlessly falls back to the official NSE historical archive CSV (`nsearchives.nseindia.com`) if requested dates or network changes necessitate.

---

## Validation Pipeline

Every dataset passes through `validate_dataset()` before persistence:

1. **Payload Existence**: Ensures response payload is neither `None` nor empty.
2. **Collection Type**: Confirms the parsed records collection is a non-empty list of dictionaries.
3. **Required Columns**: Confirms all critical columns defined in `DatasetConfig.required_columns` exist and are not entirely empty.
4. **Symbol Sanity**: Strips whitespace, excludes header/summary rows (e.g., `TOTAL`, `NONE`), and verifies that non-empty `Symbol` entries exist.
5. **Deduplication**: Removes duplicate records based on dataset-specific deduplication keys.

---

## Error Handling & Retry Strategy

| Condition | Internal Exception | Behavior |
| :--- | :--- | :--- |
| **Connection Timeout** | `TimeoutError` | Exponential backoff retry ($1.5s \times 2^{attempt-1} + \text{jitter}$) up to `max_retries`. |
| **Connection Dropped** | `NetworkError` | Exponential backoff retry up to `max_retries`. |
| **HTTP 429 Too Many Requests** | `RateLimitError` | Exponential backoff retry with jitter. |
| **HTTP 5xx Server Error** | `ServerError` | Exponential backoff retry up to `max_retries`. |
| **HTTP 401 / 403 Forbidden** | `AuthenticationError` | Re-initializes session cookies against market-data page; emits clear troubleshooting guide for cloud/datacenter IPs. |
| **Empty Body** | `EmptyResponseError` | Non-transient; fails immediately with audit log. |
| **Invalid JSON** | `InvalidJSONError` | Non-transient; falls back to CSV reader if applicable or logs snippet. |
| **Missing Fields / Schema Mismatch** | `ParserError` / `ValidationError` | Fails dataset validation cleanly without crashing other datasets. |

---

## Duplicate Pruning & Idempotency

- **Record Deduplication**:
  - `top-gainers-losers`: Deduplicated on `(Symbol, Direction)`.
  - `upper-band-hitters`, `volume-gainers-spurts`, `52-week-high`: Deduplicated on `Symbol`.
  - First-seen order is preserved.
- **File-Level Idempotency**:
  - File naming uses the deterministic pattern `{filename_prefix}_{YYYY-MM-DD}.csv`.
  - Re-running the application multiple times on the same date cleanly replaces the day's file rather than appending numbers like `file (1).csv`.

---

## Running Tests

The test suite contains 32 comprehensive unit and integration tests using `pytest`. **Tests do NOT depend on live NSE connectivity** and use fully isolated fixtures and mocks.

Run the test suite:

**Windows (PowerShell)**:
```powershell
python -m pytest -v
```

**Linux / macOS**:
```bash
python -m pytest -v
# Or directly:
pytest -v
```

### Tested Scenarios

- Successful requests and session initialization
- Request timeouts with exponential backoff
- Connection drops with retries
- HTTP 429 Rate Limiting
- HTTP 500 & 503 Server Errors
- Empty response bodies & invalid HTML/JSON
- Parser inspection for all 4 datasets
- Top gainers and losers direction consolidation
- Missing required columns & empty symbol handling
- Duplicate record removal
- Atomic file replacement & directory partitioning
- **Failure isolation: one dataset failing while the remaining three succeed**

---

## Automation

### 1. Linux / macOS Cron

To download market data automatically after market close every weekday (e.g. at 16:30 IST / 11:00 UTC Monday through Friday):

Edit your crontab:
```bash
crontab -e
```

Add the following entry (adjust paths to your environment):
```cron
# Run at 16:30 IST (11:00 UTC) every Monday-Friday
0 11 * * 1-5 /home/ubuntu/NSE-Market-Data-Downloader/venv/bin/python /home/ubuntu/NSE-Market-Data-Downloader/main.py --output-dir /var/data/nse >> /var/log/nse_downloader.log 2>&1
```

### 2. Windows Task Scheduler

1. Open **Task Scheduler** (`taskschd.msc`).
2. Click **Create Basic Task...** and name it `NSE Market Data Downloader`.
3. Set **Trigger** to **Daily** -> Select Weekdays at `16:30:00`.
4. Set **Action** to **Start a program**:
   - **Program/script**: `C:\path\to\NSE-Market-Data-Downloader\venv\Scripts\python.exe`
   - **Add arguments**: `main.py --output-dir C:\market_data\nse --log-file C:\market_data\nse\downloader.log`
   - **Start in**: `C:\path\to\NSE-Market-Data-Downloader`
5. Check **Run whether user is logged on or not** and save.

---

## Extensibility: Adding New Datasets

The application is designed for open-closed extensibility. Adding a 5th NSE dataset requires zero changes to the core engine:

1. **Add Configuration in `config/datasets.py`**:
   ```python
   DATASET_REGISTRY["advances-declines"] = DatasetConfig(
       name="advances-declines",
       display_name="Advances and Declines",
       webpage_url="https://www.nseindia.com/market-data/advances-declines",
       primary_endpoint="/api/equity-stockIndices?index=NIFTY%2050",
       filename_prefix="advances_declines",
       parser_name="advances_declines",
       expected_fields=["Symbol", "LTP", "Advances", "Declines"],
       required_columns=["Symbol", "LTP"],
       dedup_keys=["Symbol"],
   )
   ```

2. **Add Parser in `nse_downloader/parsers.py`**:
   ```python
   def parse_advances_declines(raw_payload: Any) -> List[Dict[str, Any]]:
       items = _find_data_array(raw_payload)
       # Transform and return standardized dictionaries
       ...

   PARSER_REGISTRY["advances_declines"] = parse_advances_declines
   ```

The new dataset is automatically available in CLI choices (`--dataset advances-declines`) and the `download_all` execution loop!

---

## Limitations & Assumptions

1. **NSE WAF / Geoblocking**:
   - NSE India blocks or challenges cloud provider IP blocks (AWS EC2, GCP Compute Engine, DigitalOcean) with HTTP 403 Forbidden.
   - The application must be run from an Indian residential, corporate, or proxy network, or tested using the included `--mock-dir tests/fixtures` option.
2. **Trading Hours & Data Updates**:
   - NSE endpoints update in real time during market hours (09:15 to 15:30 IST) and provide finalized end-of-day numbers after 16:00 IST.
3. **No CAPTCHA Bypassing**:
   - In adherence with ethical engineering practices, this application does not attempt to break CAPTCHAs or bypass anti-bot mechanisms. It operates strictly within normal HTTP session protocols.
