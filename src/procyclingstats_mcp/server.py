"""
ProCyclingStats MCP Server

Exposes professional cycling data from ProCyclingStats via the
Model Context Protocol (MCP). Tools include race discovery, race/stage
results, rider profiles, startlists, and search.
"""

import json
import logging
import re
from typing import Any, Optional

from fastmcp import FastMCP

from . import pcs_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

mcp = FastMCP(
    "ProCyclingStats",
    instructions=(
        "This server provides professional cycling data from ProCyclingStats (PCS). "
        "Use it to look up race calendars, stage results, rider profiles, startlists, "
        "and to search for riders/races/teams. All URLs use the PCS slug format "
        "(e.g. 'race/tour-de-france/2025', 'rider/tadej-pogacar'). "
        "The server is rate-limited to be respectful to PCS."
    ),
)


def _format_result(data: Any) -> str:
    """Format a result as readable JSON."""
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


@mcp.tool
def discover_races(
    year: int,
    tiers: Optional[list[str]] = None,
) -> str:
    """Discover professional cycling races from the PCS calendar for a given year.

    Args:
        year: Calendar year (e.g. 2025).
        tiers: Optional list of race tier filters. Valid values:
               'worldtour', 'proseries', 'class1', 'class2'.
               Defaults to ['worldtour', 'proseries'] (top two tiers).

    Returns:
        JSON list of races with their base URL, tiers, and PCS link.
    """
    races = pcs_client.discover_races(year, tiers=tiers)
    return _format_result({
        "year": year,
        "tiers_searched": tiers or ["worldtour", "proseries"],
        "total_races": len(races),
        "races": races,
    })


@mcp.tool
def get_race_overview(race_url: str) -> str:
    """Get metadata and stage list for a race.

    Args:
        race_url: PCS race URL, e.g. 'race/tour-de-france/2025'.
                  Can also be a base URL like 'race/tour-de-france' for the latest edition.

    Returns:
        JSON with race name, dates, category, nationality, and list of stages.
    """
    data = pcs_client.get_race_overview(race_url)
    return _format_result(data)


@mcp.tool
def get_stage_results(stage_url: str) -> str:
    """Get results and metadata for a specific stage or one-day race.

    Args:
        stage_url: PCS stage URL, e.g. 'race/tour-de-france/2025/stage-1'.
                   For one-day races use 'race/milano-sanremo/2025/result'.

    Returns:
        JSON with stage metadata (distance, elevation, profile, climbs) and
        full classification results (rider, team, time, points).
    """
    data = pcs_client.get_stage_results(stage_url)
    return _format_result(data)


@mcp.tool
def get_rider_profile(rider_url: str) -> str:
    """Get a professional cyclist's profile from PCS.

    Args:
        rider_url: PCS rider URL, e.g. 'rider/tadej-pogacar'.

    Returns:
        JSON with rider name, nationality, birthdate, physical stats,
        specialty scores (GC, sprint, climber, etc.) and points history.
    """
    data = pcs_client.get_rider_profile(rider_url)
    return _format_result(data)


@mcp.tool
def get_rider_results(rider_url: str, season: Optional[int] = None) -> str:
    """Get a rider's race results for a specific season.

    Args:
        rider_url: PCS rider URL, e.g. 'rider/tadej-pogacar'.
        season: Year to fetch results for (e.g. 2025). Defaults to current year.

    Returns:
        JSON list of race results with date, race name, position, GC position,
        distance, and points.
    """
    data = pcs_client.get_rider_results(rider_url, season=season)
    return _format_result(data)


@mcp.tool
def get_race_startlist(race_url: str) -> str:
    """Get the startlist for a race.

    Args:
        race_url: PCS race URL, e.g. 'race/tour-de-france/2025'.
                  The '/startlist' suffix is added automatically.

    Returns:
        JSON with all riders, their teams, race numbers, and a teams summary.
    """
    data = pcs_client.get_race_startlist(race_url)
    return _format_result(data)


@mcp.tool
def search_pcs(query: str, max_results: int = 20) -> str:
    """Search ProCyclingStats for riders, races, or teams.

    Args:
        query: Search text (e.g. 'Pogacar', 'Tour de France', 'UAE').
        max_results: Maximum number of results (default 20).

    Returns:
        JSON list of search results with type (rider/race/team), name, and URL.
    """
    results = pcs_client.search_pcs(query, max_results=max_results)
    safe_query = re.sub(r"<[^>]+>", "", query).strip()
    return _format_result({
        "query": safe_query,
        "total_results": len(results),
        "results": results,
    })


def main():
    mcp.run()


if __name__ == "__main__":
    main()
