# ProCyclingStats MCP Server

An MCP (Model Context Protocol) server that provides professional cycling data from [ProCyclingStats](https://www.procyclingstats.com).

## Tools

| Tool | Description |
|------|-------------|
| `discover_races` | Find races from the PCS calendar for a given year and tier |
| `get_race_overview` | Get race metadata — name, dates, category, stages list |
| `get_stage_results` | Get full stage/one-day race results with metadata |
| `get_rider_profile` | Get rider bio, physical stats, specialty scores, palmares |
| `get_rider_results` | Get a rider's race results for a specific season |
| `get_race_startlist` | Get the startlist for a race grouped by team |
| `search_pcs` | Free-text search for riders, races, and teams |

## Installation

```bash
pip install git+https://github.com/lewis-mcgillion/procyclingstats-mcp-server.git
```

Or clone and install locally:

```bash
git clone https://github.com/lewis-mcgillion/procyclingstats-mcp-server.git
cd procyclingstats-mcp-server
pip install -e .
```

## Usage

### Run the server directly

```bash
procyclingstats-mcp
```

### Configure in your MCP client

Add to your MCP client config (e.g. Claude Desktop, VS Code GitHub Copilot).

**Recommended — using `uvx`** (no manual install needed):

```json
{
  "mcpServers": {
    "procyclingstats": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lewis-mcgillion/procyclingstats-mcp-server.git", "procyclingstats-mcp"]
    }
  }
}
```

**Using a local clone with `uv`:**

```json
{
  "mcpServers": {
    "procyclingstats": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/procyclingstats-mcp-server", "procyclingstats-mcp"]
    }
  }
}
```

**Using a global install:**

```json
{
  "mcpServers": {
    "procyclingstats": {
      "command": "procyclingstats-mcp",
      "args": []
    }
  }
}
```

## Example Queries

- "What WorldTour races are happening in 2025?"
- "Show me the results of Tour de France 2025 Stage 1"
- "What's Tadej Pogačar's rider profile?"
- "Who's on the startlist for the Giro d'Italia 2025?"
- "Search for Remco Evenepoel"

## URL Format

All PCS URLs use the slug format:

- Races: `race/tour-de-france/2025`
- Stages: `race/tour-de-france/2025/stage-1`
- One-day results: `race/milano-sanremo/2025/result`
- Riders: `rider/tadej-pogacar`

## Rate Limiting

The server enforces a 0.5s delay between requests to PCS and retries automatically on server errors (500/502/503/429).

## Credits

Built on top of the [procyclingstats](https://pypi.org/project/procyclingstats/) Python library.
