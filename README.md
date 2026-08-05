# CopyMint

CopyMint is an invite-only, multi-user NFT mint intelligence and paper-copy system for Ethereum. It discovers repeated minters across NFT collections, watches selected wallets, recognizes supported public mint routes, and prepares safe paper execution plans for isolated user wallets.

Release 1 cannot sign or broadcast transactions.

## Documentation

- Product and delivery plan: [`implementation.md`](implementation.md)
- Architecture decisions: [`docs/adr/`](docs/adr/)
- Append-only workspace memory: [`.memory/MEMORY_LOG.md`](.memory/MEMORY_LOG.md)
- Original specification: `NFT_Mint_Intelligence_Copy_Mint_Technical_Specification.docx`

## Local setup

Prerequisites:

- Python 3.13.13
- uv 0.11.6
- Docker with Compose

```bash
cp .env.example .env
docker compose up -d postgres queue
uv sync --frozen --group dev
uv run alembic upgrade head
uv run uvicorn app.api.main:app --reload
```

The example environment values are local-only placeholders. Never commit real Telegram, Chainstack, AWS, database, queue, or signer secrets.

## Quality commands

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest
uv run python scripts/secret_scan.py
```

## Service commands

```bash
uv run uvicorn app.api.main:app --host 0.0.0.0 --port 10000
uv run celery -A app.workers.celery_app:celery_app worker --queues indexer --loglevel INFO
uv run celery -A app.workers.celery_app:celery_app worker --queues live --loglevel INFO
uv run celery -A app.workers.celery_app:celery_app worker --queues analytics --loglevel INFO
uv run celery -A app.workers.celery_app:celery_app worker --queues opportunities --loglevel INFO
uv run uvicorn app.signer.api:app --host 0.0.0.0 --port 10000
```

## Current phase

Phase 0 foundation. See the checklist in `implementation.md` for authoritative status and release gates.
