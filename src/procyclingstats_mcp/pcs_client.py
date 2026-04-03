"""
ProCyclingStats client — fetches and parses data from PCS.

Adapted from cycling-predictor/data/scraper.py. Stateless: no SQLite caching,
just fetch → parse → return dicts. Rate-limited and retries on server errors.
"""

import html
import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import Any, Optional

import cloudscraper
from procyclingstats import Race, RaceStartlist, Rider, Stage

log = logging.getLogger(__name__)

PCS_BASE = "https://www.procyclingstats.com"

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
_last_request_time = 0.0
_rate_limit_lock = threading.Lock()
REQUEST_DELAY = 0.5  # seconds between PCS requests
MAX_RETRIES = 3

RACE_CALENDAR_URLS = {
    "worldtour": "races.php?year={year}&circuit=1&class=&filter=Filter",
    "proseries": "races.php?year={year}&circuit=2&class=&filter=Filter",
    "class1": "races.php?year={year}&circuit=&class=1.1&filter=Filter",
    "class2": "races.php?year={year}&circuit=&class=1.2&filter=Filter",
}

# Shared HTTP session — reused across requests to avoid resource leaks
_scraper = cloudscraper.create_scraper()


def _validate_url(url: str, prefix: str, label: str):
    """Raise ValueError if url is empty or doesn't start with the expected prefix."""
    if not url or not url.strip():
        raise ValueError(f"{label} URL cannot be empty.")
    if not url.startswith(prefix):
        raise ValueError(f"{label} URL must start with '{prefix}'. Got: '{url}'")


def _validate_race_url_has_year(url: str):
    """Raise ValueError if a race URL is missing the year component."""
    parts = url.strip("/").split("/")
    # Expected: race/<name>/<year> — at least 3 parts with a numeric year
    if len(parts) < 3 or not parts[2].isdigit():
        raise ValueError(
            f"Race URL must include a year (e.g. 'race/tour-de-france/2025'). Got: '{url}'"
        )




def _rate_limit():
    global _last_request_time
    with _rate_limit_lock:
        elapsed = time.time() - _last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)
        _last_request_time = time.time()


def _pcs_fetch(pcs_class, url: str, retries: int = MAX_RETRIES):
    """Fetch and parse a PCS page with automatic retry on server errors."""
    for attempt in range(retries):
        _rate_limit()
        try:
            return pcs_class(url)
        except Exception as e:
            err_str = str(e)
            if any(code in err_str for code in ["500", "502", "503", "429", "Cloudflare"]):
                backoff = REQUEST_DELAY * (attempt + 2)
                log.warning(
                    f"Server error ({err_str[:60]}) on {url}, "
                    f"retrying in {backoff:.1f}s (attempt {attempt + 1}/{retries})"
                )
                time.sleep(backoff)
                continue
            raise
    _rate_limit()
    return pcs_class(url)


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def discover_races(year: int, tiers: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Discover races from PCS calendar pages for a given year.

    Returns list of dicts with race base URLs and the tier they were found in.
    """
    max_year = datetime.now().year + 1
    if year > max_year:
        raise ValueError(
            f"Year {year} is too far in the future. Maximum allowed: {max_year}."
        )

    if tiers is not None:
        if len(tiers) == 0:
            return []
        invalid = set(tiers) - set(RACE_CALENDAR_URLS.keys())
        if invalid:
            raise ValueError(
                f"Invalid tier(s): {sorted(invalid)}. "
                f"Valid tiers: {sorted(RACE_CALENDAR_URLS.keys())}"
            )

    if tiers is None:
        tiers = ["worldtour", "proseries"]

    all_races: dict[str, set[str]] = {}  # base_url -> set of tiers

    for tier in tiers:
        url_template = RACE_CALENDAR_URLS.get(tier)
        if not url_template:
            continue

        url = f"{PCS_BASE}/{url_template.format(year=year)}"
        _rate_limit()
        try:
            resp = _scraper.get(url, timeout=30)
            if resp.status_code != 200:
                log.warning(f"Failed to fetch {tier} calendar for {year}: HTTP {resp.status_code}")
                continue

            links = re.findall(r'href="(race/[^"]+)"', resp.text)
            for link in links:
                parts = link.split("/")
                if len(parts) >= 2:
                    base = "/".join(parts[:2])
                    if base not in all_races:
                        all_races[base] = set()
                    all_races[base].add(tier)
        except Exception as e:
            log.warning(f"Error fetching {tier} calendar for {year}: {e}")

    result = []
    for race_url, race_tiers in sorted(all_races.items()):
        result.append({
            "race_url": race_url,
            "tiers": sorted(race_tiers),
            "pcs_link": f"{PCS_BASE}/{race_url}/{year}",
        })

    return result


def get_race_overview(race_url: str) -> dict[str, Any]:
    """Fetch race overview metadata.

    Args:
        race_url: Full race URL like 'race/tour-de-france/2025' or base URL
                  like 'race/tour-de-france' (year defaults to latest).
    """
    _validate_url(race_url, "race/", "Race")
    _validate_race_url_has_year(race_url)

    try:
        race = _pcs_fetch(Race, race_url)
        data = race.parse()
    except Exception as e:
        return {"error": f"Failed to fetch race '{race_url}': {e}", "url": race_url}

    stages_list = []
    try:
        for s in race.stages():
            stages_list.append({
                "stage_url": s.get("stage_url"),
                "date": s.get("date"),
                "departure": s.get("departure"),
                "arrival": s.get("arrival"),
            })
    except Exception:
        pass

    return {
        "url": race_url,
        "name": data.get("name"),
        "year": data.get("year"),
        "nationality": data.get("nationality"),
        "is_one_day_race": data.get("is_one_day_race"),
        "category": data.get("category"),
        "uci_tour": data.get("uci_tour"),
        "startdate": data.get("startdate"),
        "enddate": data.get("enddate"),
        "stages": stages_list,
        "pcs_link": f"{PCS_BASE}/{race_url}",
    }


def get_stage_results(stage_url: str) -> dict[str, Any]:
    """Fetch stage/one-day race results + metadata.

    Args:
        stage_url: PCS stage URL like 'race/tour-de-france/2025/stage-1'
                   or one-day race result like 'race/milano-sanremo/2025/result'.
    """
    _validate_url(stage_url, "race/", "Stage")

    try:
        stage = _pcs_fetch(Stage, stage_url)
        data = stage.parse()
    except Exception as e:
        return {"error": f"Failed to fetch stage '{stage_url}': {e}", "url": stage_url}

    climbs = data.get("climbs", [])

    results = []
    for r in data.get("results", []):
        results.append({
            "rank": r.get("rank"),
            "rider_name": r.get("rider_name"),
            "rider_url": r.get("rider_url"),
            "team_name": r.get("team_name"),
            "nationality": r.get("nationality"),
            "age": r.get("age"),
            "time": r.get("time"),
            "bonus": r.get("bonus"),
            "pcs_points": _safe_float(r.get("pcs_points")),
            "uci_points": _safe_float(r.get("uci_points")),
        })

    return {
        "url": stage_url,
        "stage_name": f"{data.get('departure', '')} → {data.get('arrival', '')}",
        "date": data.get("date"),
        "distance": _safe_float(data.get("distance")),
        "vertical_meters": _safe_float(data.get("vertical_meters")),
        "profile_score": _safe_float(data.get("profile_score")),
        "profile_icon": data.get("profile_icon"),
        "stage_type": data.get("stage_type"),
        "avg_speed_winner": _safe_float(data.get("avg_speed_winner")),
        "avg_temperature": _safe_float(data.get("avg_temperature")),
        "departure": data.get("departure"),
        "arrival": data.get("arrival"),
        "is_one_day_race": data.get("is_one_day_race"),
        "race_category": data.get("race_category"),
        "startlist_quality_score": data.get("race_startlist_quality_score"),
        "num_climbs": len(climbs) if climbs else 0,
        "climbs": climbs,
        "results": results,
        "pcs_link": f"{PCS_BASE}/{stage_url}",
    }


def get_rider_profile(rider_url: str) -> dict[str, Any]:
    """Fetch a rider profile.

    Args:
        rider_url: PCS rider URL like 'rider/tadej-pogacar'.
    """
    _validate_url(rider_url, "rider/", "Rider")

    try:
        rider = _pcs_fetch(Rider, rider_url)
        data = rider.parse()
    except Exception as e:
        return {"error": f"Failed to fetch rider '{rider_url}': {e}", "url": rider_url}

    spec = data.get("points_per_speciality", {}) or {}
    pts_history = data.get("points_per_season_history", [])

    return {
        "url": rider_url,
        "name": data.get("name"),
        "nationality": data.get("nationality"),
        "birthdate": data.get("birthdate"),
        "weight": data.get("weight"),
        "height": data.get("height"),
        "specialties": {
            "one_day_races": spec.get("one_day_races"),
            "gc": spec.get("gc"),
            "time_trial": spec.get("time_trial"),
            "sprint": spec.get("sprint"),
            "climber": spec.get("climber"),
            "hills": spec.get("hills"),
        },
        "points_per_season": pts_history,
        "pcs_link": f"{PCS_BASE}/{rider_url}",
    }


def get_race_startlist(race_url: str) -> dict[str, Any]:
    """Fetch race startlist.

    Args:
        race_url: Race URL like 'race/tour-de-france/2025'. The /startlist
                  suffix is appended automatically if not present.
    """
    _validate_url(race_url, "race/", "Race")

    startlist_url = race_url.rstrip("/")
    if not startlist_url.endswith("/startlist"):
        startlist_url = f"{startlist_url}/startlist"

    try:
        sl = _pcs_fetch(RaceStartlist, startlist_url)
        data = sl.parse()
    except Exception as e:
        return {"error": f"Failed to fetch startlist '{startlist_url}': {e}", "url": startlist_url}

    riders = []
    for r in data.get("startlist", []):
        riders.append({
            "rider_name": r.get("rider_name"),
            "rider_url": r.get("rider_url"),
            "nationality": r.get("nationality"),
            "rider_number": r.get("rider_number"),
            "team_name": r.get("team_name"),
            "team_url": r.get("team_url"),
        })

    # Group by team for a convenient view
    teams: dict[str, list] = {}
    for r in riders:
        team = r.get("team_name", "Unknown")
        if team not in teams:
            teams[team] = []
        teams[team].append(r["rider_name"])

    return {
        "url": startlist_url,
        "total_riders": len(riders),
        "total_teams": len(teams),
        "riders": riders,
        "teams_summary": teams,
        "pcs_link": f"{PCS_BASE}/{startlist_url}",
    }


def search_pcs(query: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Search PCS for riders, races, and teams.

    Args:
        query: Free-text search query (e.g. 'Pogacar', 'Tour de France').
        max_results: Maximum number of results to return.
    """
    if not query or not query.strip():
        return []

    scraper = _scraper
    url = f"{PCS_BASE}/search.php"
    _rate_limit()

    try:
        resp = scraper.get(url, params={"term": query}, timeout=30)
        if resp.status_code != 200:
            return [{"error": f"Search returned HTTP {resp.status_code}"}]
    except Exception as e:
        return [{"error": f"Search request failed: {e}"}]

    results = []

    # PCS search results are in <a> tags with specific patterns
    # Rider links: rider/slug, Race links: race/slug, Team links: team/slug
    patterns = [
        (r'<a[^>]*href="(rider/[^"]+)"[^>]*>(.*?)</a>', "rider"),
        (r'<a[^>]*href="(race/[^"]+)"[^>]*>(.*?)</a>', "race"),
        (r'<a[^>]*href="(team/[^"]+)"[^>]*>(.*?)</a>', "team"),
    ]

    seen_urls = set()
    for pattern, result_type in patterns:
        matches = re.findall(pattern, resp.text, re.DOTALL)
        for match_url, match_name in matches:
            if match_url in seen_urls:
                continue
            seen_urls.add(match_url)
            # Strip HTML tags and their content for script/style, then remaining tags
            clean_name = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", match_name, flags=re.DOTALL | re.IGNORECASE)
            clean_name = re.sub(r"<[^>]+>", "", clean_name)
            clean_name = html.unescape(clean_name)
            clean_name = re.sub(r"\s+", " ", clean_name).strip()
            if clean_name:
                results.append({
                    "type": result_type,
                    "name": clean_name,
                    "url": match_url,
                    "pcs_link": f"{PCS_BASE}/{match_url}",
                })

    return results[:max_results]
