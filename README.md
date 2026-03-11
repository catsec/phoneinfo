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
     -p 5480:5480 \
     -v $(pwd)/db:/app/db \
     -e ME_API_URL=https://app.mobile.me.app/business-api/search \
     -e ME_API_SID=your_sid \
     -e ME_API_TOKEN=your_token \
     ghcr.io/catsec/phoneinfo:latest
   ```

3. Open http://localhost:5480 in your browser.

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

3. Open http://localhost:5480 in your browser.

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
| PORT | No | 5480 | Server port |
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
  server.py           Flask entry point (middleware, auth, blueprints)
  config.py           Configuration and rate limiter
  lookup.py           Core cache→API→DB pipeline
  db.py               SQLite operations
  scoring.py          Name matching engine
  transliteration.py  Hebrew/Arabic/Russian transliteration
  phone.py            Phone number utilities
  app_logger.py       CSV audit logging
  input_validator.py  Input sanitization
  providers/          API provider modules (ME, SYNC)
  routes/             Flask blueprints (api, web, nicknames)
  templates/          HTML templates
  db/                 SQLite database (must not be web-accessible)
  logs/               Audit logs (restrict filesystem read access)
  .env                Configuration (not in git)
  Dockerfile          Docker image definition
  docker-compose.yml  Docker Compose configuration
```

## Production Deployment

### Security checklist before going live

| Item | Setting | Notes |
|------|---------|-------|
| `DEBUG` | `false` | Never run debug mode in production |
| `TRUST_CF_IP` | `true` | Required when behind Cloudflare — enables correct IP-based rate limiting |
| `GUNICORN_WORKERS` | `1` (or set `RATE_LIMIT_STORAGE_URI=redis://...`) | In-memory rate limits are per-worker; with multiple workers use Redis |
| `db/` directory | Not web-accessible | Nginx/Caddy must not serve this path |
| `logs/` directory | OS permissions: readable only by the app user | Audit logs contain masked phone data |

### Shared folder permissions (Linux/Docker)

If you mount `db/` and `logs/` as Docker volumes or NFS shares, ensure only the app user can read them:

```bash
# On the host, after creating the directories:
chown -R 1000:1000 db/ logs/      # match the UID inside the container
chmod 750 db/ logs/               # owner rwx, group rx, others nothing
chmod 640 db/db.db                # owner rw, group r, others nothing
```

For NFS mounts, add `no_root_squash` only if your security policy requires it; otherwise keep default squash settings and map the app UID explicitly via `anonuid`/`anongid`.

### Log phone decryption

Phone numbers in `logs/app.log` are AES-256-ECB encrypted and base64-encoded using the `LOG_KEY` from `.env`. To recover a plaintext phone from a log entry:

```python
import base64, os
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

key = base64.b64decode(os.environ["LOG_KEY"])
ct  = base64.b64decode("<ciphertext column from log>")
phone = unpad(AES.new(key, AES.MODE_ECB).decrypt(ct), AES.block_size).decode()
print(phone)
```

- Encryption is **deterministic** — all log rows for the same phone number produce the same ciphertext, so you can `grep` for a specific number without decrypting the entire log.
- If `LOG_KEY` is not set, the phone is masked to `*****1234` (last 4 digits only).
- **Back up `LOG_KEY` securely** — if it is lost, the encrypted phones in existing logs cannot be recovered.

### Cloudflare Access

The app authenticates users via the `Cf-Access-Authenticated-User-Email` header injected by Cloudflare Access. **Do not expose port 5480 directly to the internet** — traffic must flow through the Cloudflare tunnel. Verify your tunnel policy allows only authenticated users with approved email domains.

## License

Proprietary - All rights reserved.
