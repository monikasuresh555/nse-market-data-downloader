"""
Domain models and exception hierarchy for NSE Market Data Downloader.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# ==============================================================================
# Exceptions
# ==============================================================================


class NSEDownloaderError(Exception):
    """Base exception for all NSE Downloader errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class NetworkError(NSEDownloaderError):
    """Raised when an underlying network or connection error occurs."""
    pass


class TimeoutError(NetworkError):
    """Raised when an HTTP request exceeds the configured timeout."""
    pass


class HTTPStatusError(NSEDownloaderError):
    """Raised when an HTTP response returns an error status code."""

    def __init__(self, message: str, status_code: int, endpoint: str):
        super().__init__(message, {"status_code": status_code, "endpoint": endpoint})
        self.status_code = status_code
        self.endpoint = endpoint


class RateLimitError(HTTPStatusError):
    """Raised when HTTP 429 Too Many Requests is returned."""
    pass


class ServerError(HTTPStatusError):
    """Raised when HTTP 5xx Server Error is returned."""
    pass


class AuthenticationError(HTTPStatusError):
    """Raised when HTTP 401 or 403 Forbidden is returned."""
    pass


class EmptyResponseError(NSEDownloaderError):
    """Raised when the server returns an empty or whitespace-only response."""
    pass


class InvalidJSONError(NSEDownloaderError):
    """Raised when the response body cannot be parsed as valid JSON."""
    pass


class ValidationError(NSEDownloaderError):
    """Raised when downloaded data fails schema or content validation rules."""
    pass


class ParserError(ValidationError):
    """Raised when a dataset parser cannot extract records from payload."""
    pass


class StorageError(NSEDownloaderError):
    """Raised when atomic CSV persistence or directory operations fail."""
    pass


# ==============================================================================
# Data Transfer Models
# ==============================================================================


@dataclass
class AcquisitionResult:
    """Represents raw data acquired from an NSE endpoint."""

    dataset_name: str
    endpoint: str
    raw_data: Any
    status_code: int
    attempt_count: int
    trading_date: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DownloadResult:
    """Represents the final result of processing and persisting a dataset."""

    dataset_name: str
    endpoint: str
    success: bool
    attempt_count: int
    record_count: int = 0
    output_path: Optional[str] = None
    trading_date: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_log_dict(self) -> Dict[str, Any]:
        """Convert result into standard structured log dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "dataset": self.dataset_name,
            "endpoint": self.endpoint,
            "attempt_number": self.attempt_count,
            "success": self.success,
            "record_count": self.record_count,
            "output_path": self.output_path or "",
            "error_message": self.error_message or "",
        }
