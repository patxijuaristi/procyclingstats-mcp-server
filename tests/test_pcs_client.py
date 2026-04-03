"""Tests for pcs_client input validation and error handling.

All network calls are mocked — these tests verify our code logic,
not PCS availability.
"""

import html
import re
from unittest.mock import MagicMock, patch

import pytest

from procyclingstats_mcp import pcs_client


VALID_TIERS = {"worldtour", "proseries", "class1", "class2"}


# ---------------------------------------------------------------------------
# discover_races
# ---------------------------------------------------------------------------

class TestDiscoverRaces:
    """Tests for discover_races input validation."""

    @patch.object(pcs_client, "_scraper")
    def test_invalid_tier_raises_error(self, mock_scraper):
        """Invalid tier names should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tier"):
            pcs_client.discover_races(2025, tiers=["invalid_tier"])

    @patch.object(pcs_client, "_scraper")
    def test_mixed_valid_invalid_tiers_raises(self, mock_scraper):
        """Even one invalid tier in the list should raise."""
        with pytest.raises(ValueError, match="Invalid tier"):
            pcs_client.discover_races(2025, tiers=["worldtour", "fake"])

    @patch.object(pcs_client, "_scraper")
    def test_empty_tiers_returns_empty(self, mock_scraper):
        """Empty tiers list should return no races, not fall back to defaults."""
        result = pcs_client.discover_races(2025, tiers=[])
        assert result == []

    @patch.object(pcs_client, "_scraper")
    def test_future_year_raises_error(self, mock_scraper):
        """Years too far in the future should be rejected."""
        current_year = 2026  # approximate
        with pytest.raises(ValueError, match="[Yy]ear"):
            pcs_client.discover_races(current_year + 2)

    @patch.object(pcs_client, "_scraper")
    def test_none_tiers_uses_defaults(self, mock_scraper):
        """None tiers should use defaults without error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        mock_scraper.get.return_value = mock_resp
        # Should not raise
        result = pcs_client.discover_races(2025, tiers=None)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_race_overview
# ---------------------------------------------------------------------------

class TestGetRaceOverview:
    """Tests for get_race_overview input validation and error handling."""

    def test_base_url_without_year_raises(self):
        """Base URL without a year should raise ValueError."""
        with pytest.raises(ValueError, match="[Yy]ear"):
            pcs_client.get_race_overview("race/tour-de-france")

    def test_empty_url_raises(self):
        """Empty URL should raise ValueError."""
        with pytest.raises(ValueError):
            pcs_client.get_race_overview("")

    @patch.object(pcs_client, "_pcs_fetch")
    def test_nonexistent_race_returns_error(self, mock_fetch):
        """Non-existent race should return an error dict."""
        mock_fetch.side_effect = Exception("list index out of range")
        result = pcs_client.get_race_overview("race/fake-race/2025")
        assert "error" in result

    @patch.object(pcs_client, "_pcs_fetch")
    def test_valid_race_returns_data(self, mock_fetch):
        """Valid race URL should return structured data."""
        mock_race = MagicMock()
        mock_race.parse.return_value = {
            "name": "Tour de France",
            "year": 2025,
            "nationality": "France",
            "is_one_day_race": False,
            "category": "Men Elite",
            "uci_tour": "WorldTour",
            "startdate": "2025-07-05",
            "enddate": "2025-07-27",
        }
        mock_race.stages.return_value = []
        mock_fetch.return_value = mock_race

        result = pcs_client.get_race_overview("race/tour-de-france/2025")
        assert result["name"] == "Tour de France"
        assert "error" not in result


# ---------------------------------------------------------------------------
# get_stage_results
# ---------------------------------------------------------------------------

class TestGetStageResults:
    """Tests for get_stage_results error handling."""

    def test_empty_url_raises(self):
        """Empty URL should raise ValueError."""
        with pytest.raises(ValueError):
            pcs_client.get_stage_results("")

    @patch.object(pcs_client, "_pcs_fetch")
    def test_nonexistent_stage_returns_error(self, mock_fetch):
        """Non-existent stage should return an error dict."""
        mock_fetch.side_effect = AttributeError("'NoneType' object has no attribute 'css'")
        result = pcs_client.get_stage_results("race/tour-de-france/2025/stage-99")
        assert "error" in result


# ---------------------------------------------------------------------------
# get_rider_profile
# ---------------------------------------------------------------------------

class TestGetRiderProfile:
    """Tests for get_rider_profile input validation."""

    def test_empty_url_raises(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError):
            pcs_client.get_rider_profile("")

    def test_invalid_url_format_raises(self):
        """URL not starting with 'rider/' should raise."""
        with pytest.raises(ValueError, match="[Rr]ider"):
            pcs_client.get_rider_profile("not/a/rider")

    @patch.object(pcs_client, "_pcs_fetch")
    def test_nonexistent_rider_returns_error(self, mock_fetch):
        """Non-existent rider should return an error dict."""
        mock_fetch.side_effect = Exception("HTML from given URL is invalid")
        result = pcs_client.get_rider_profile("rider/fake-rider-doesnt-exist")
        assert "error" in result


# ---------------------------------------------------------------------------
# get_race_startlist
# ---------------------------------------------------------------------------

class TestGetRaceStartlist:
    """Tests for get_race_startlist error handling."""

    def test_empty_url_raises(self):
        """Empty URL should raise ValueError."""
        with pytest.raises(ValueError):
            pcs_client.get_race_startlist("")

    @patch.object(pcs_client, "_pcs_fetch")
    def test_nonexistent_race_returns_error(self, mock_fetch):
        """Non-existent race should return an error dict."""
        mock_fetch.side_effect = AttributeError("'NoneType' object has no attribute 'css'")
        result = pcs_client.get_race_startlist("race/fake-race/2025")
        assert "error" in result


# ---------------------------------------------------------------------------
# search_pcs
# ---------------------------------------------------------------------------

class TestSearchPcs:
    """Tests for search_pcs input validation and sanitization."""

    def test_empty_query_returns_empty(self):
        """Empty query should return an empty list."""
        result = pcs_client.search_pcs("")
        assert result == []

    def test_whitespace_query_returns_empty(self):
        """Whitespace-only query should be treated as empty."""
        result = pcs_client.search_pcs("   ")
        assert result == []

    @patch.object(pcs_client, "_scraper")
    def test_xss_payload_is_sanitized(self, mock_scraper):
        """Script tags in query should not cause errors."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<a href="rider/test">Test Rider</a>'
        mock_scraper.get.return_value = mock_resp

        result = pcs_client.search_pcs('<script>alert(1)</script>')
        # The query should not contain raw script tags
        # (search_pcs returns a list, not the wrapper — the server.py adds the query field)
        # But internally, the function should not crash
        assert isinstance(result, list)

    @patch.object(pcs_client, "_scraper")
    def test_search_results_have_consistent_format(self, mock_scraper):
        """Every result should have type, name, url, and pcs_link."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '''
            <a href="rider/tadej-pogacar">Tadej Pogačar</a>
            <a href="race/tour-de-france/2025">Tour de France</a>
            <a href="team/uae-team-emirates-xrg-2025">UAE Team Emirates</a>
        '''
        mock_scraper.get.return_value = mock_resp

        results = pcs_client.search_pcs("test")
        for r in results:
            assert "type" in r
            assert "name" in r
            assert "url" in r
            assert "pcs_link" in r
            assert r["type"] in ("rider", "race", "team")


# ---------------------------------------------------------------------------
# server.py — search query sanitization
# ---------------------------------------------------------------------------

class TestServerSearchSanitization:
    """Test that server.py sanitizes the query field in search responses."""

    @patch.object(pcs_client, "search_pcs", return_value=[])
    def test_xss_query_sanitized_in_response(self, mock_search):
        """The query echoed in the response must not contain HTML tags."""
        from procyclingstats_mcp.server import search_pcs as server_search_pcs
        import json

        result_json = server_search_pcs('<script>alert("xss")</script>')
        result = json.loads(result_json)

        assert "<script>" not in result.get("query", "")
        assert "</script>" not in result.get("query", "")
