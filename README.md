# opinions-agent

`opinions-agent` is a small Python app that syncs Readwise highlights, creates a summary proposal through a replaceable agent boundary, asks for Telegram approval, then appends the approved summary to a configured opinions repo file and commits only that file.

The first slice intentionally keeps side effects in the host app. The agent can read exported run inputs and the configured opinions target file, but approval, appending, Telegram sends, and git commits are app-owned.

## Local Setup

Install dependencies:

```bash
uv sync
```

ThinHarness is installed from a pinned git dependency so local and Railway installs use the same deployable package source.

Create local configuration:

```bash
cp .env.example .env
```

Required local variables:

- `DATABASE_URL`
- `READWISE_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOWED_CHAT_ID`
- `HARNESS_MODEL`
- `OPENAI_API_KEY` for the default `openai:gpt-5.2` model
- `OPINIONS_REPO_URL`
- `OPINIONS_REPO_BRANCH`
- `OPINIONS_REPO_DIR`
- `OPINIONS_TARGET_FILE`
- `OPINIONS_GIT_AUTHOR_NAME`
- `OPINIONS_GIT_AUTHOR_EMAIL`

Start Postgres:

```bash
docker compose up -d postgres
```

Apply migrations:

```bash
uv run alembic upgrade head
```

The development fallback command also creates tables directly, which is useful for SQLite test databases:

```bash
uv run opinions-agent init-db
```

## Commands

Run the web service:

```bash
uv run opinions-agent serve
```

Healthcheck:

```bash
curl http://localhost:8000/healthz
```

Manual local workflow:

```bash
uv run opinions-agent readwise-sync
uv run opinions-agent summarize-recent --limit 10
uv run opinions-agent telegram-poll
```

Daily cron entry point:

```bash
uv run opinions-agent daily-run
```

For deterministic local smoke runs without Telegram API sends:

```bash
OPINIONS_FAKE_TELEGRAM=1 uv run opinions-agent summarize-recent --limit 10 --deterministic-agent
```

## Telegram

Railway should expose `POST /telegram/webhook`. Configure it with:

```bash
uv run opinions-agent set-telegram-webhook https://your-service.up.railway.app/telegram/webhook
```

If `TELEGRAM_WEBHOOK_SECRET` is set, webhook requests must include Telegram's `X-Telegram-Bot-Api-Secret-Token` header.

## Opinions Repo

Local defaults point at:

```text
/Users/ryanbrown/code/ryanbbrown/TEST_OPINIONS.md
```

Railway should set `OPINIONS_REPO_DIR` to a writable app-owned directory or mounted volume. The app clones `OPINIONS_REPO_URL` when that directory is not already a git checkout, otherwise it fetches the configured branch. Push authentication should be configured in the repo URL or the Railway environment; for example, use a token-backed HTTPS URL stored as a Railway secret.

The commit helper stages and commits only `OPINIONS_TARGET_FILE`, then pushes `origin OPINIONS_REPO_BRANCH`.

## Testing

Run the automated checks:

```bash
uv run pytest
uv run ruff check .
uv run pyright
```

The normal e2e test uses a disposable local git remote and simulated Telegram updates. To run the real ThinHarness/OpenAI e2e path:

```bash
OPINIONS_RUN_REAL_E2E=1 uv run pytest tests/test_real_e2e_optional.py
```

That test still uses fake Telegram and a disposable git remote; it only makes the agent proposal call through the configured model.

## Artifacts

Run bundles are written under `.runs/<summary_run_id>/` as JSONL and Markdown. They may contain Readwise highlight content, so `.runs/` is gitignored. Local traces are also gitignored under `.traces/`; disable plaintext local traces in deployed environments with `THINHARNESS_DISABLE_LOCAL_TRACING=1`.
