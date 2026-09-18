"""
HTTP Client implementation for communicating with NSE India API endpoints.

Handles browser session initialization, cookie management, exponential backoff
retries, and status code error handling.
"""

import json
import logging
import random
import time
from typing import Any, Dict, List, Optional, Union

import requests

from config.datasets import (
    DEFAULT_API_HEADERS,
    DEFAULT_BACKOFF_MULTIPLIER,
    DEFAULT_INITIAL_BACKOFF_SECONDS,
    DEFAULT_JITTER,
    DEFAULT_MAX_RETRIES,
    DEFAULT_NSE_HEADERS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    NSE_BASE_URL,
    NSE_REFERER_URL,
)
from nse_downloader.logging_config import log_event
from nse_downloader.models import (
    AuthenticationError,
    EmptyResponseError,
    HTTPStatusError,
    InvalidJSONError,
    NetworkError,
    RateLimitError,
    ServerError,
    TimeoutError,
)

logger = logging.getLogger("nse_downloader")


class NSEClient:
    """
    Session-aware HTTP client specialized for interacting with NSE India endpoints.
    """

    def __init__(
        self,
        base_url: str = NSE_BASE_URL,
        timeout: int = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        backoff_multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
        enable_jitter: bool = DEFAULT_JITTER,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.backoff_multiplier = backoff_multiplier
        self.enable_jitter = enable_jitter

        self.session = session if session is not None else requests.Session()
        self.session_initialized = False

    def initialize_session(self, page_url: Optional[str] = None, force: bool = False) -> None:
        """
        Visits an NSE India page to initialize cookies and headers.
        Prefers visiting an actual market-data page (or specified page_url), which passes
        Akamai WAF verification, before falling back to the root home page.
        """
        if self.session_initialized and not force:
            return

        target_pages: List[str] = []
        if page_url:
            target_pages.append(page_url)
        target_pages.extend([
            f"{self.base_url}/market-data/top-gainers-losers",
            f"{self.base_url}/",
        ])

        last_auth_error: Optional[AuthenticationError] = None

        for candidate_url in target_pages:
            log_event(
                logger,
                logging.DEBUG,
                f"Initializing NSE browser session against {candidate_url}",
                endpoint=candidate_url,
                attempt_number=1,
            )

            try:
                response = self.session.get(
                    candidate_url,
                    headers=DEFAULT_NSE_HEADERS,
                    timeout=self.timeout,
                )
                if response.status_code in (401, 403):
                    last_auth_error = AuthenticationError(
                        f"Access forbidden by NSE WAF/gateway (HTTP {response.status_code}) at {candidate_url}. "
                        "Note that NSE restricts certain cloud/datacenter IP addresses.",
                        status_code=response.status_code,
                        endpoint=candidate_url,
                    )
                    continue

                response.raise_for_status()
                self.session_initialized = True
                log_event(
                    logger,
                    logging.DEBUG,
                    f"NSE browser session initialized successfully with cookies via {candidate_url}",
                    endpoint=candidate_url,
                    attempt_number=1,
                    success=True,
                )
                return
            except requests.exceptions.Timeout as exc:
                raise TimeoutError(f"Session initialization timed out: {exc}") from exc
            except requests.exceptions.ConnectionError as exc:
                raise NetworkError(f"Session initialization connection error: {exc}") from exc
            except AuthenticationError:
                raise
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                raise HTTPStatusError(
                    f"HTTP error during session initialization: {exc}",
                    status_code=status,
                    endpoint=candidate_url,
                ) from exc
            except Exception as exc:
                raise NetworkError(f"Unexpected error initializing session: {exc}") from exc

        if last_auth_error:
            raise last_auth_error

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff duration with optional random jitter."""
        delay = self.initial_backoff * (self.backoff_multiplier ** (attempt - 1))
        if self.enable_jitter:
            delay += random.uniform(0.1, 0.5)
        return delay

    def get_data(
        self,
        endpoint_path: str,
        params: Optional[Dict[str, Any]] = None,
        dataset_name: str = "N/A",
        referer: Optional[str] = None,
        page_url: Optional[str] = None,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]], str]:
        """
        Execute an HTTP GET request to an NSE endpoint with automatic retries,
        exponential backoff, status code translation, and auto-detection of JSON or CSV.

        Args:
            endpoint_path: Relative or absolute path (e.g., '/api/live-analysis-variations')
            params: Optional query parameters dictionary.
            dataset_name: Dataset name for contextual logging.
            referer: Optional HTTP Referer header to include with the request.
            page_url: Optional page URL to use for session initialization if needed.

        Returns:
            Parsed JSON object (dict or list) or raw CSV text.
        """
        full_url = (
            endpoint_path
            if endpoint_path.startswith("http")
            else f"{self.base_url}{endpoint_path}"
        )

        # Ensure session cookies are established first
        if not self.session_initialized:
            self.initialize_session(page_url=page_url or referer)

        headers = DEFAULT_API_HEADERS.copy()
        if referer:
            headers["Referer"] = referer

        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            log_event(
                logger,
                logging.INFO,
                f"Requesting endpoint (attempt {attempt}/{self.max_retries})",
                dataset=dataset_name,
                endpoint=full_url,
                attempt_number=attempt,
            )

            try:
                response = self.session.get(
                    full_url,
                    headers=headers,
                    params=params,
                    timeout=self.timeout,
                )

                status_code = response.status_code

                # Handle Rate Limiting (429)
                if status_code == 429:
                    raise RateLimitError(
                        "NSE rate limit encountered (HTTP 429)",
                        status_code=429,
                        endpoint=full_url,
                    )

                # Handle Authentication / Forbidden (401/403)
                if status_code in (401, 403):
                    # Try re-initializing session once if token or cookie expired
                    if attempt < self.max_retries:
                        log_event(
                            logger,
                            logging.WARNING,
                            f"Encountered HTTP {status_code}; refreshing session cookies",
                            dataset=dataset_name,
                            endpoint=full_url,
                            attempt_number=attempt,
                        )
                        self.initialize_session(page_url=page_url or referer, force=True)
                    raise AuthenticationError(
                        f"Access forbidden by NSE WAF/gateway (HTTP {status_code}) for endpoint '{full_url}'. "
                        "NSE India enforces Akamai bot detection that often restricts datacenter and cloud IP addresses. "
                        "To resolve this: (1) Run this CLI from a local workstation, home, or office network; "
                        "(2) Route requests through an HTTP/HTTPS residential proxy via HTTP_PROXY/HTTPS_PROXY; "
                        "(3) For offline testing and verification, run with mock fixtures: python main.py --mock-dir tests/fixtures",
                        status_code=status_code,
                        endpoint=full_url,
                    )

                # Handle Server Errors (5xx)
                if 500 <= status_code < 600:
                    raise ServerError(
                        f"NSE server error (HTTP {status_code})",
                        status_code=status_code,
                        endpoint=full_url,
                    )

                # Handle Other HTTP errors
                if status_code >= 400:
                    raise HTTPStatusError(
                        f"HTTP client error (HTTP {status_code})",
                        status_code=status_code,
                        endpoint=full_url,
                    )

                # Validate non-empty response body
                text = response.text.strip()
                if not text:
                    raise EmptyResponseError(
                        f"Empty response body received from {full_url}",
                        {"status_code": status_code, "endpoint": full_url},
                    )

                # Check if response is CSV
                headers_dict = getattr(response, "headers", None)
                content_type = (
                    headers_dict.get("Content-Type", "").lower()
                    if headers_dict is not None and hasattr(headers_dict, "get")
                    else ""
                )
                is_csv = (
                    "text/csv" in content_type
                    or "application/csv" in content_type
                    or full_url.endswith(".csv")
                    or ("," in text.split("\n")[0] and not text.startswith(("{", "[")))
                )

                if is_csv:
                    log_event(
                        logger,
                        logging.DEBUG,
                        "Successfully received CSV payload",
                        dataset=dataset_name,
                        endpoint=full_url,
                        attempt_number=attempt,
                        success=True,
                    )
                    return text

                # Parse JSON
                try:
                    data = response.json()
                except Exception as json_err:
                    raise InvalidJSONError(
                        f"Failed to parse JSON from {full_url}: {json_err}",
                        {"endpoint": full_url, "preview": text[:200]},
                    ) from json_err

                log_event(
                    logger,
                    logging.DEBUG,
                    "Successfully received and parsed JSON payload",
                    dataset=dataset_name,
                    endpoint=full_url,
                    attempt_number=attempt,
                    success=True,
                )
                return data

            except (TimeoutError, requests.exceptions.Timeout) as exc:
                err = TimeoutError(f"Request timeout connecting to {full_url}: {exc}")
                last_error = err
                is_transient = True
            except (NetworkError, requests.exceptions.ConnectionError) as exc:
                err = NetworkError(f"Connection failed for {full_url}: {exc}")
                last_error = err
                is_transient = True
            except RateLimitError as exc:
                last_error = exc
                is_transient = True
            except ServerError as exc:
                last_error = exc
                is_transient = True
            except AuthenticationError as exc:
                last_error = exc
                is_transient = attempt < self.max_retries
            except (EmptyResponseError, InvalidJSONError, HTTPStatusError) as exc:
                last_error = exc
                is_transient = False
            except Exception as exc:
                err = NetworkError(f"Unexpected error requesting {full_url}: {exc}")
                last_error = err
                is_transient = False

            # Decide whether to retry
            if is_transient and attempt < self.max_retries:
                backoff = self._calculate_backoff(attempt)
                log_event(
                    logger,
                    logging.WARNING,
                    f"Transient error: {last_error}. Backing off for {backoff:.2f}s before retry...",
                    dataset=dataset_name,
                    endpoint=full_url,
                    attempt_number=attempt,
                    success=False,
                    error_message=str(last_error),
                )
                time.sleep(backoff)
            else:
                break

        log_event(
            logger,
            logging.ERROR,
            f"Failed all {self.max_retries} attempts: {last_error}",
            dataset=dataset_name,
            endpoint=full_url,
            attempt_number=self.max_retries,
            success=False,
            error_message=str(last_error),
        )
        raise last_error or NetworkError(f"Unknown failure requesting {full_url}")

    def get_json(
        self,
        endpoint_path: str,
        params: Optional[Dict[str, Any]] = None,
        dataset_name: str = "N/A",
        referer: Optional[str] = None,
        page_url: Optional[str] = None,
    ) -> Any:
        """
        Execute an HTTP GET request to an NSE endpoint expecting JSON.
        """
        data = self.get_data(
            endpoint_path=endpoint_path,
            params=params,
            dataset_name=dataset_name,
            referer=referer,
            page_url=page_url,
        )
        if isinstance(data, (dict, list)):
            return data
        # If data is a string (e.g. CSV returned), return as is or convert
        return data

    def close(self) -> None:
        """Close the underlying requests Session."""
        self.session.close()
