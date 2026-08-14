from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

OPINION_AGENT_MODEL = "openai:gpt-5.6-sol"
OPINION_AGENT_REASONING_EFFORT = "medium"


def load_dotenv(path: Path | str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    database_url: str
    telegram_bot_token: str
    telegram_allowed_chat_id: int | None
    telegram_webhook_secret: str
    readwise_token: str
    harness_model: str
    braintrust_api_key: str
    braintrust_project_id: str
    environment: str
    opinions_repo_url: str
    opinions_repo_branch: str
    opinions_repo_dir: Path
    opinions_target_file: str
    opinions_sources_file: str
    opinions_git_author_name: str
    opinions_git_author_email: str
    opinions_data_dir: Path
    runs_dir: Path
    completed_run_retention_days: int
    local_trace_dir: Path
    local_tracing_enabled: bool
    use_fake_telegram: bool
    braintrust_parent: str = ""
    harness_reasoning_effort: str = OPINION_AGENT_REASONING_EFFORT
    opinions_start_secret: str = ""
    opinions_start_url: str = ""
    opinions_git_token: str = ""
    initial_evidence_after: str = ""
    volume_mount_path: Path | None = None

    @property
    def opinions_target_path(self) -> Path:
        return (self.opinions_repo_dir / self.opinions_target_file).resolve()

    @property
    def opinions_sources_path(self) -> Path:
        return (self.opinions_repo_dir / self.opinions_sources_file).resolve()


def _default_path(env_name: str, local_default: str, railway_subdir: str) -> Path:
    """Default a durable path env var locally, or under the Railway volume mount when present."""
    explicit = _env(env_name)
    if explicit:
        return Path(explicit).expanduser()
    mount = _env("RAILWAY_VOLUME_MOUNT_PATH")
    if mount:
        return Path(mount) / railway_subdir
    return Path(local_default).expanduser()


def get_settings() -> Settings:
    load_dotenv()
    allowed_chat = _env("TELEGRAM_ALLOWED_CHAT_ID")
    return Settings(
        database_url=_env("DATABASE_URL", "sqlite+pysqlite:///./opinions-agent.db"),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_chat_id=int(allowed_chat) if allowed_chat else None,
        telegram_webhook_secret=_env("TELEGRAM_WEBHOOK_SECRET"),
        readwise_token=_env("READWISE_TOKEN"),
        harness_model=_env("OPINION_AGENT_MODEL", OPINION_AGENT_MODEL),
        braintrust_api_key=_env("BRAINTRUST_API_KEY"),
        braintrust_project_id=_env("BRAINTRUST_PROJECT_ID"),
        environment=_env("OPINIONS_ENVIRONMENT", "dev"),
        opinions_repo_url=_env("OPINIONS_REPO_URL", "https://github.com/ryanbbrown/ryanbbrown.git"),
        opinions_repo_branch=_env("OPINIONS_REPO_BRANCH", "main"),
        opinions_repo_dir=_default_path("OPINIONS_REPO_DIR", "/Users/ryanbrown/code/ryanbbrown", "opinions-repo"),
        opinions_target_file=_env("OPINIONS_TARGET_FILE", "TEST_OPINIONS.md"),
        opinions_sources_file=_env("OPINIONS_SOURCES_FILE", "OPINIONS_SOURCES.jsonl"),
        opinions_git_author_name=_env("OPINIONS_GIT_AUTHOR_NAME", "opinions-agent"),
        opinions_git_author_email=_env("OPINIONS_GIT_AUTHOR_EMAIL", "opinions-agent@example.com"),
        opinions_data_dir=_default_path("OPINIONS_DATA_DIR", ".readwise", "readwise"),
        runs_dir=_default_path("RUNS_DIR", ".runs", "runs"),
        completed_run_retention_days=int(_env("OPINIONS_COMPLETED_RUN_RETENTION_DAYS", "30")),
        local_trace_dir=Path(_env("THINHARNESS_LOCAL_TRACE_DIR", ".traces")),
        local_tracing_enabled=_env("THINHARNESS_DISABLE_LOCAL_TRACING", "").lower() not in {"1", "true", "yes"},
        use_fake_telegram=_env("OPINIONS_FAKE_TELEGRAM", "").lower() in {"1", "true", "yes"},
        harness_reasoning_effort=_env("OPINION_AGENT_REASONING_EFFORT", OPINION_AGENT_REASONING_EFFORT),
        opinions_start_secret=_env("OPINIONS_START_SECRET"),
        opinions_start_url=_env("OPINIONS_START_URL"),
        opinions_git_token=_env("OPINIONS_GIT_TOKEN"),
        initial_evidence_after=_env("OPINIONS_INITIAL_EVIDENCE_AFTER"),
        volume_mount_path=Path(_env("RAILWAY_VOLUME_MOUNT_PATH")) if _env("RAILWAY_VOLUME_MOUNT_PATH") else None,
    )


def validate_web_settings(settings: Settings) -> None:
    """Reject incomplete or unsafe Railway web configuration."""
    if settings.environment not in {"staging", "prod"}:
        raise ValueError("OPINIONS_ENVIRONMENT must be staging or prod")
    required = {
        "DATABASE_URL": settings.database_url,
        "RAILWAY_VOLUME_MOUNT_PATH": str(settings.volume_mount_path or ""),
        "READWISE_TOKEN": settings.readwise_token,
        "TELEGRAM_BOT_TOKEN": settings.telegram_bot_token,
        "TELEGRAM_ALLOWED_CHAT_ID": str(settings.telegram_allowed_chat_id or ""),
        "TELEGRAM_WEBHOOK_SECRET": settings.telegram_webhook_secret,
        "OPINIONS_START_SECRET": settings.opinions_start_secret,
        "OPENAI_API_KEY": _env("OPENAI_API_KEY"),
        "OPINIONS_REPO_URL": settings.opinions_repo_url,
        "OPINIONS_GIT_TOKEN": settings.opinions_git_token,
        "OPINIONS_REPO_BRANCH": settings.opinions_repo_branch,
        "OPINIONS_TARGET_FILE": settings.opinions_target_file,
        "OPINIONS_SOURCES_FILE": settings.opinions_sources_file,
        "OPINIONS_INITIAL_EVIDENCE_AFTER": settings.initial_evidence_after,
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        raise ValueError("missing Railway web settings: " + ", ".join(missing))
    try:
        database = make_url(settings.database_url)
    except Exception as exc:
        raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from exc
    if database.get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL must use PostgreSQL")
    if "@" in settings.opinions_repo_url.partition("://")[2].partition("/")[0]:
        raise ValueError("OPINIONS_REPO_URL must not contain credentials")
    if settings.use_fake_telegram or settings.local_tracing_enabled:
        raise ValueError("Railway web cannot use fake Telegram or local plaintext tracing")
    if settings.opinions_target_file != "OPINIONS.md":
        raise ValueError(f"{settings.environment} requires OPINIONS_TARGET_FILE=OPINIONS.md")
    if settings.opinions_sources_file != "OPINIONS_SOURCES.jsonl":
        raise ValueError("Railway web requires OPINIONS_SOURCES_FILE=OPINIONS_SOURCES.jsonl")
    expected_branch = "staging" if settings.environment == "staging" else "main"
    if settings.opinions_repo_branch != expected_branch:
        raise ValueError(f"{settings.environment} requires OPINIONS_REPO_BRANCH={expected_branch}")
    if settings.environment == "prod" and not (settings.braintrust_api_key and settings.braintrust_project_id):
        raise ValueError("production requires BRAINTRUST_API_KEY and BRAINTRUST_PROJECT_ID")


def validate_cron_settings(settings: Settings) -> None:
    if not settings.opinions_start_url or not settings.opinions_start_secret:
        raise ValueError("OPINIONS_START_URL and OPINIONS_START_SECRET are required")


def is_railway_runtime() -> bool:
    return any(_env(name) for name in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_SERVICE_ID"))
