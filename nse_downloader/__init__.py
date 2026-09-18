"""
NSE Market Data Downloader Package.
"""

from nse_downloader.application import DownloaderApplication
from nse_downloader.client import NSEClient
from nse_downloader.models import (
    AcquisitionResult,
    AuthenticationError,
    DownloadResult,
    EmptyResponseError,
    HTTPStatusError,
    InvalidJSONError,
    NetworkError,
    NSEDownloaderError,
    ParserError,
    RateLimitError,
    ServerError,
    StorageError,
    TimeoutError,
    ValidationError,
)

__version__ = "1.0.0"

__all__ = [
    "DownloaderApplication",
    "NSEClient",
    "NSEDownloaderError",
    "NetworkError",
    "TimeoutError",
    "HTTPStatusError",
    "RateLimitError",
    "ServerError",
    "AuthenticationError",
    "EmptyResponseError",
    "InvalidJSONError",
    "ValidationError",
    "ParserError",
    "StorageError",
    "AcquisitionResult",
    "DownloadResult",
]
