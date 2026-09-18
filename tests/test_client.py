"""
Unit tests for NSEClient HTTP requests, sessions, retries, and error handling.
Does NOT perform live network requests; strictly uses mocked sessions.
"""

from unittest.mock import MagicMock, patch
import pytest
import requests

from nse_downloader.client import NSEClient
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


def create_mock_response(
    status_code: int = 200,
    text: str = '{"status": "ok"}',
    json_data: dict = None,
):
    """Utility to build mock requests.Response objects."""
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = status_code
    mock_resp.text = text
    if json_data is not None:
        mock_resp.json.return_value = json_data
    else:
        import json
        try:
            mock_resp.json.return_value = json.loads(text)
        except Exception:
            mock_resp.json.side_effect = ValueError("Invalid JSON")
    return mock_resp


class TestNSEClient:
    """Tests for NSEClient behavior under various conditions."""

    def test_successful_request_and_session_init(self):
        """Verify successful session initialization and subsequent JSON retrieval."""
        mock_session = MagicMock(spec=requests.Session)
        # Session init response
        mock_session.get.side_effect = [
            create_mock_response(200, "<html>NSE Home</html>"),
            create_mock_response(200, '{"data": [{"symbol": "INFY"}]}', {"data": [{"symbol": "INFY"}]}),
        ]

        client = NSEClient(session=mock_session, max_retries=2, initial_backoff=0.01)
        data = client.get_json("/api/test-endpoint", dataset_name="test")

        assert client.session_initialized is True
        assert data == {"data": [{"symbol": "INFY"}]}
        assert mock_session.get.call_count == 2

    def test_request_timeout_with_retries(self):
        """Verify that timeouts trigger retries and ultimately raise TimeoutError."""
        mock_session = MagicMock(spec=requests.Session)
        # 1 call for session init (success), then timeouts on API calls
        mock_session.get.side_effect = [
            create_mock_response(200, "<html>NSE Home</html>"),
            requests.exceptions.Timeout("Connection timed out"),
            requests.exceptions.Timeout("Connection timed out again"),
        ]

        client = NSEClient(session=mock_session, max_retries=2, initial_backoff=0.01)

        with pytest.raises(TimeoutError) as exc_info:
            client.get_json("/api/test-endpoint")

        assert "timed out" in str(exc_info.value).lower()
        # 1 session init + 2 retries
        assert mock_session.get.call_count == 3

    def test_connection_error_with_retries(self):
        """Verify connection errors trigger retry and raise NetworkError."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.side_effect = [
            create_mock_response(200, "<html>NSE Home</html>"),
            requests.exceptions.ConnectionError("Name resolution failed"),
            requests.exceptions.ConnectionError("Connection refused"),
        ]

        client = NSEClient(session=mock_session, max_retries=2, initial_backoff=0.01)

        with pytest.raises(NetworkError):
            client.get_json("/api/test-endpoint")

        assert mock_session.get.call_count == 3

    def test_http_429_rate_limiting(self):
        """Verify HTTP 429 raises RateLimitError after retries."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.side_effect = [
            create_mock_response(200, "<html>NSE Home</html>"),
            create_mock_response(429, "Too Many Requests"),
            create_mock_response(429, "Too Many Requests"),
        ]

        client = NSEClient(session=mock_session, max_retries=2, initial_backoff=0.01)

        with pytest.raises(RateLimitError) as exc_info:
            client.get_json("/api/test-endpoint")

        assert exc_info.value.status_code == 429
        assert mock_session.get.call_count == 3

    def test_http_500_server_error(self):
        """Verify HTTP 500 server error triggers retry and raises ServerError."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.side_effect = [
            create_mock_response(200, "<html>NSE Home</html>"),
            create_mock_response(500, "Internal Server Error"),
            create_mock_response(503, "Service Unavailable"),
        ]

        client = NSEClient(session=mock_session, max_retries=2, initial_backoff=0.01)

        with pytest.raises(ServerError) as exc_info:
            client.get_json("/api/test-endpoint")

        assert exc_info.value.status_code == 503
        assert mock_session.get.call_count == 3

    def test_empty_response_body(self):
        """Verify empty or whitespace-only response body raises EmptyResponseError."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.side_effect = [
            create_mock_response(200, "<html>NSE Home</html>"),
            create_mock_response(200, "   \n\t  "),
        ]

        client = NSEClient(session=mock_session, max_retries=1)

        with pytest.raises(EmptyResponseError):
            client.get_json("/api/test-endpoint")

    def test_invalid_json_response(self):
        """Verify non-JSON response payload raises InvalidJSONError."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.side_effect = [
            create_mock_response(200, "<html>NSE Home</html>"),
            create_mock_response(200, "<!DOCTYPE html><html><body>Error</body></html>"),
        ]

        client = NSEClient(session=mock_session, max_retries=1)

        with pytest.raises(InvalidJSONError):
            client.get_json("/api/test-endpoint")

    def test_session_init_forbidden_403(self):
        """Verify that HTTP 403 on session initialization raises AuthenticationError."""
        mock_session = MagicMock(spec=requests.Session)
        mock_session.get.return_value = create_mock_response(403, "Forbidden by Akamai")

        client = NSEClient(session=mock_session)

        with pytest.raises(AuthenticationError) as exc_info:
            client.initialize_session()

        assert exc_info.value.status_code == 403
