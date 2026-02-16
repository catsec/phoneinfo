# PhoneInfo

A phone number lookup tool that queries the ME API to retrieve user profile information. It provides a web interface for processing Excel/CSV files and single phone queries, with name matching and transliteration.

## Features

- Bulk processing of phone numbers from Excel/CSV files
- Single phone number lookup with detailed results
- Name matching with fuzzy comparison and nickname support
- Transliteration from Arabic, Russian, and English to Hebrew
- SQLite caching to reduce API calls
- Web interface and REST API

## Quick Start

### Using Pre-built Docker Image

**Multi-platform support:** Linux (AMD64, ARM64, ARM/v7), macOS (Intel, Apple Silicon), Windows

1. Pull the image from GitHub Container Registry:
   ```bash
   docker pull ghcr.io/catsec/phoneinfo:latest
   ```

2. Run with your ME API credentials:
   ```bash
   docker run -d \
     -p 5001:5001 \
     -v $(pwd)/db:/app/db \
     -e ME_API_URL=https://app.mobile.me.app/business-api/search \
     -e ME_API_SID=your_sid \
     -e ME_API_TOKEN=your_token \
     ghcr.io/catsec/phoneinfo:latest
   ```

3. Open http://localhost:5001 in your browser.

**Available tags:**
- `latest` - Latest build from master branch
- `master` - Master branch builds
- `v1.0.0` - Specific version tags
- `sha-<commit>` - Specific commit builds

### Using Docker Compose (Build Locally)

1. Copy `.env.example` to `.env` and fill in your ME API credentials:
   ```bash
   cp .env.example .env
   ```

2. Start the server:
   ```bash
   docker-compose up -d
   ```

3. Open http://localhost:5001 in your browser.

### Manual Installation

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill in your ME API credentials.

4. Start the server:
   ```bash
   python server.py
   ```

## Configuration

Environment variables (set in `.env` file):

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| ME_API_URL | Yes | - | ME API endpoint URL |
| ME_API_SID | Yes | - | ME API session ID |
| ME_API_TOKEN | Yes | - | ME API authentication token |
| DATABASE | No | db/db.db | SQLite database path |
| HOST | No | 0.0.0.0 | Server host |
| PORT | No | 5001 | Server port |
| DEBUG | No | true | Debug mode |

## Web Interface

### File Processing (/)

1. Upload an Excel (.xlsx) or CSV file with two columns:
   - Column 1: Phone number
   - Column 2: Contact name
2. Select APIs to use
3. Set refresh days (0 = cache only)
4. Download processed results

### Single Query (/web/query)

1. Enter a phone number
2. Optionally enter a contact name for matching score
3. View detailed results

### Nickname Management (/web/nicknames)

- Import/export nickname mappings
- Add/edit nicknames manually
- Nicknames improve matching accuracy (e.g., "Yossi" matches "Yosef")

## REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| /health | GET | Health check |
| /me | POST | Query ME API for a phone number |
| /translate | POST | Transliterate names to Hebrew |
| /nicknames | GET | Get nickname variants for a name |
| /compare | POST | Calculate name similarity score |

## Input File Format

Excel or CSV with two columns:

| Phone | Name |
|-------|------|
| 0501234567 | John Doe |
| +972521234567 | Jane Smith |

Phone numbers are automatically converted to international format (972...).

## Output File Format

The processed file includes:

- phone_number: International format
- cal_name: Original contact name
- me.common_name: Name from API
- me.matching: Match score (0-100%)
- me.first_name, me.last_name: Parsed names
- me.translated: Hebrew transliteration
- Additional profile data (email, gender, social links, etc.)

## Match Score Interpretation

| Score | Meaning |
|-------|---------|
| 90-100 | Excellent match - same person |
| 70-89 | Good match - likely same person |
| 50-69 | Partial match - needs verification |
| 0-49 | Low match - likely different person |

## Project Structure

```
phoneinfo/
  server.py           Flask web server
  functions.py        Core utility functions
  api_me.py           ME API client
  templates/          HTML templates
  db/                 SQLite database
  nicknames.xlsx      Nickname mappings
  .env                Configuration (not in git)
  Dockerfile          Docker image definition
  docker-compose.yml  Docker Compose configuration
```

## License

Proprietary - All rights reserved.
