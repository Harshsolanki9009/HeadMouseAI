"""Tests for safe Groq API diagnostics reporting."""

import os
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from ai_provider.diagnostics import run_groq_diagnostic


def test_diagnostic_missing_key():
    """Verify diagnostic correctly identifies missing key without throwing exceptions."""
    with patch("ai_provider.diagnostics.resolve_groq_api_key", return_value=""), \
         patch.dict(os.environ, {}, clear=True):

        report = run_groq_diagnostic(api_key="")
        assert report["client_initialized"] is False
        assert report["auth_success"] is False
        assert report["failure_category"] == "MISSING_KEY"
        assert report["key_length"] == 0


def test_diagnostic_valid_auth():
    """Verify diagnostic reports successful authentication when API returns 200."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"data": [{"id": "whisper-large-v3-turbo"}]}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp), \
         patch("ai_provider.diagnostics.resolve_groq_api_key", return_value="gsk_" + "x" * 52):

        report = run_groq_diagnostic(api_key="gsk_" + "x" * 52)
        assert report["client_initialized"] is True
        assert report["auth_success"] is True
        assert report["failure_category"] == "NONE"
        assert report["model_available"] is True
        assert report["key_length"] == 56


def test_diagnostic_http_401():
    """Verify diagnostic classifies HTTP 401 as INVALID_KEY_401."""
    err = HTTPError(url="https://api.groq.com", code=401, msg="Unauthorized", hdrs=None, fp=None)

    with patch("urllib.request.urlopen", side_effect=err), \
         patch("ai_provider.diagnostics.resolve_groq_api_key", return_value="gsk_invalid"):

        report = run_groq_diagnostic(api_key="gsk_invalid")
        assert report["client_initialized"] is True
        assert report["auth_success"] is False
        assert report["failure_category"] == "INVALID_KEY_401"


def test_diagnostic_network_error():
    """Verify diagnostic classifies connection drop as NETWORK_ERROR."""
    err = URLError(reason="Name or service not known")

    with patch("urllib.request.urlopen", side_effect=err), \
         patch("ai_provider.diagnostics.resolve_groq_api_key", return_value="gsk_valid"):

        report = run_groq_diagnostic(api_key="gsk_valid")
        assert report["client_initialized"] is True
        assert report["auth_success"] is False
        assert report["failure_category"] == "NETWORK_ERROR"
