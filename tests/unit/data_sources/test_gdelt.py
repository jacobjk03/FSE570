"""Unit tests for GDELT datasource connector retry behavior."""

from unittest.mock import MagicMock, patch

import pytest

from osint_swarm.data_sources.gdelt import GdeltError, fetch_news_for_entity


def _mock_response(status_code: int, payload=None, headers=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.headers = headers or {}
    mock.json.return_value = payload if payload is not None else {"articles": []}
    if status_code >= 400:
        mock.raise_for_status.side_effect = __import__("requests").HTTPError(f"{status_code} error")
    else:
        mock.raise_for_status.return_value = None
    return mock


def test_fetch_news_retries_on_429_then_succeeds():
    responses = [
        _mock_response(429, headers={"Retry-After": "0"}),
        _mock_response(200, payload={"articles": [{"title": "t", "url": "u"}]}),
    ]
    with patch("osint_swarm.data_sources.gdelt.requests.get", side_effect=responses) as mock_get, patch(
        "osint_swarm.data_sources.gdelt.time.sleep"
    ) as mock_sleep:
        result = fetch_news_for_entity("Microsoft Corp")

    assert mock_get.call_count == 2
    assert mock_sleep.call_count == 1
    assert result["total_returned"] == 1


def test_fetch_news_raises_after_repeated_429():
    responses = [_mock_response(429), _mock_response(429), _mock_response(429)]
    with patch("osint_swarm.data_sources.gdelt.requests.get", side_effect=responses), patch(
        "osint_swarm.data_sources.gdelt.time.sleep"
    ):
        with pytest.raises(GdeltError, match="429 Too Many Requests"):
            fetch_news_for_entity("Microsoft Corp")

