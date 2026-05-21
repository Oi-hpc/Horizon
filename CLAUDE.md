# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Horizon is an AI-powered news aggregation system that fetches content from multiple sources (Hacker News, RSS, Reddit, Telegram, Twitter, GitHub, OpenBB, OSS Insight), scores items with AI, deduplicates, enriches with background context, and generates bilingual daily briefings delivered via GitHub Pages, email, webhooks, or MCP.

## Common Commands

```bash
# Install dependencies (recommended)
uv sync

# Install dev dependencies for testing
uv sync --extra dev

# Install optional OpenBB financial news dependency
uv sync --extra openbb

# Run the main pipeline (default 24h window)
uv run horizon

# Run with custom time window
uv run horizon --hours 48

# Interactive setup wizard
uv run horizon-wizard

# Run MCP server
uv run horizon-mcp

# Run webhook CLI
uv run horizon-webhook

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/test_analyzer.py
```

## Architecture

### Pipeline Flow

The main pipeline (`src/orchestrator.py:HorizonOrchestrator.run`) executes in this order:

1. **Fetch** - Concurrent fetch from all configured sources via scrapers
2. **URL Deduplicate** - Merge items pointing to same URL across different sources
3. **AI Score** - Rate each item 0-10 for importance
4. **Filter** - Keep items above `filtering.ai_score_threshold`
5. **Topic Deduplicate** - Semantic dedup via AI to merge items covering same story
6. **Enrich** - Add background knowledge for important items
7. **Summarize** - Generate Markdown briefing per configured language
8. **Deliver** - Publish to GitHub Pages, email subscribers, webhooks

### Core Components

- **`src/main.py`** - CLI entry point, loads config and runs orchestrator
- **`src/orchestrator.py`** - Coordinates the full pipeline
- **`src/models.py`** - Pydantic models for `Config`, `ContentItem`, all source configs
- **`src/storage/manager.py`** - Config loading with `${VAR}` interpolation, summary saving, subscriber management

### Scrapers (`src/scrapers/`)

Each scraper extends `BaseScraper` with:
- `__init__(config, http_client)` - receives source-specific config and shared async HTTP client
- `async fetch(since: datetime) -> List[ContentItem]` - returns items published after `since`

The ID format is `{source}:{subtype}:{native_id}` (e.g., `hackernews:story:12345`).

### AI Layer (`src/ai/`)

- **`client.py`** - Factory `create_ai_client(config)` returns provider-specific client (Anthropic, OpenAI, Azure, Gemini, Ali, DeepSeek, Doubao, MiniMax, Ollama)
- **`analyzer.py`** - Scores items and assigns tags
- **`enricher.py`** - Adds background context via web search
- **`summarizer.py`** - Generates the daily Markdown report
- **`prompts.py`** - All system/user prompts for AI calls

### MCP Server (`src/mcp/`)

Exposes pipeline stages as MCP tools for AI assistants:
- `server.py` - FastMCP entry point with metrics tracking
- `service.py` - Pipeline operations exposed as tools
- `horizon_adapter.py` - Adapts orchestrator methods for MCP

### Services (`src/services/`)

- **`email.py`** - SMTP/IMAP for newsletter delivery and subscription handling
- **`webhook.py`** - Push notifications to Feishu, DingTalk, Slack, Discord, generic endpoints

### Setup Wizard (`src/setup/`)

- **`wizard.py`** - Interactive CLI that generates `data/config.json` from user interests
- **`presets.py`** - Predefined source templates organized by topic

## Configuration

- **`data/config.json`** - Main config (sources, AI provider, thresholds, delivery channels)
- **`.env`** - API keys and secrets (referenced via `${VAR_NAME}` in config)

Config values can use `${VAR_NAME}` syntax for environment variable interpolation. This keeps secrets out of the JSON file. Unset variables are left as-is (will surface as downstream errors).

See `data/config.example.json` for a complete template and `docs/configuration.md` for detailed reference.

## Key Patterns

### Adding a New Source Type

1. Add source config model to `src/models.py`
2. Create scraper in `src/scrapers/<source>.py` extending `BaseScraper`
3. Register scraper in `src/orchestrator.py:fetch_all_sources`
4. Add source type to `SourceType` enum in `src/models.py`

### Adding a New AI Provider

1. Add provider to `AIProvider` enum in `src/models.py`
2. Create client class in `src/ai/client.py` extending `AIClient`
3. Add factory logic to `create_ai_client()`
4. Handle provider-specific quirks (temperature clamping, token limits, response format)

### ContentItem Metadata

The `metadata` dict carries source-specific fields. Common ones:
- `subreddit`, `feed_name`, `channel` - for per-sub-source breakdowns
- `score`, `comments`, `engagement` - for filtering decisions
- `merged_sources` - set when URL dedup merges multiple sources

## Testing

Tests are in `tests/` using pytest. Run with `uv run pytest`. Key test files:
- `test_analyzer.py` - AI scoring logic
- `test_storage.py` - Config loading and env var interpolation
- `test_mcp_*.py` - MCP server behavior
- `test_webhook.py` - Webhook formatting per platform