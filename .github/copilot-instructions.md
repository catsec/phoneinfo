# Project Guidelines

## Code Style
- Follow existing Python style: `snake_case` for functions/locals and UPPER_SNAKE for module-level config constants.
- Keep Flask route handlers in `server.py` focused on orchestration; place reusable logic in `functions.py` and API clients.
- Preserve response field conventions using API prefixes (`me.*`, `sync.*`) used in web/API outputs.
- Keep `None` normalization behavior (empty-string cleanup before persistence/response) consistent with current flow.
- Reference patterns: `server.py`, `functions.py`, `api_me.py`, `api_sync.py`.

## Architecture
- Main flow: template/browser request -> Flask route -> SQLite cache check -> external API (if needed) -> flatten/clean -> DB save -> optional transliteration/scoring -> response.
- `server.py` hosts web pages (`/`, `/web/query`) and REST endpoints (`/me`, `/sync`, `/translate`, `/compare`, `/nicknames`, `/health`).
- SQLite is request-scoped via `g.db`; initialization creates/uses `me_data`, `sync_data`, and `nicknames` tables.
- Bulk processing and single-query paths both route through shared utility functions and scoring config.
- Reference files: `server.py`, `functions.py`, `templates/index.html`, `templates/query.html`.

## Build and Test
- Install dependencies: `pip install -r requirements.txt`
- Run server locally: `python server.py`
- Alternate env setup (documented): activate `venv` first, then run/install commands.
- Docker is documented in project docs; verify compose/docker files are present before using docker commands.
- No automated Python test runner is currently discoverable; `test/` appears fixture-oriented.
- Reference files: `README.md`, `CLAUDE.md`, `requirements.txt`, `Makefile`, `test/`.

## Project Conventions
- Normalize and validate phone numbers in Israeli international format (`972...`) before lookup/storage.
- Preserve cache semantics in route logic: `refresh_days` and cache-only flags determine whether external APIs may be called.
- Keep Hebrew-facing UX/error text patterns aligned with existing templates and handlers.
- For bulk input processing, preserve implemented expectation of three columns: phone, first name, last name.
- Maintain nickname workflows via existing DB-backed routes/pages (`/nicknames`, upload/download/edit), not ad-hoc files.
- Reference files: `functions.py`, `server.py`, `templates/nicknames.html`, `templates/nickname_edit.html`.

## Integration Points
- Environment variables:
  - Required: `ME_API_URL`, `ME_API_SID`, `ME_API_TOKEN`
  - Optional: `SYNC_API_URL`, `SYNC_API_TOKEN`, `DATABASE`, `HOST`, `PORT`, `DEBUG`
- External APIs:
  - ME API client in `api_me.py` (GET + auth query parameters)
  - SYNC API client in `api_sync.py` (POST + bearer token)
- Persistence: SQLite cache and nickname tables; file-processing output exports generated as `.xlsx`.
- Web pages use client-side `fetch` to `/web/*` and API wrappers for processing/query.

## Security
- Treat phone/name/email/profile payloads as PII; avoid broad logging or accidental exposure in responses.
- Never hardcode credentials or tokens; use environment variables only.
- Avoid returning raw exception strings in new endpoints/handlers; prefer sanitized error responses.
- Keep debug mode controlled by env and default to non-debug behavior outside local development.
- Reference files: `server.py`, `api_me.py`, `README.md`, `.env.example`.
