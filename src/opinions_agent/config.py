from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

OPINION_AGENT_MODEL = "openai:gpt-5.5"
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
        harness_model=OPINION_AGENT_MODEL,
        braintrust_api_key=_env("BRAINTRUST_API_KEY"),
        braintrust_project_id=_env("BRAINTRUST_PROJECT_ID"),
        environment=_env("OPINIONS_ENVIRONMENT") or ("prod" if _env("RAILWAY_VOLUME_MOUNT_PATH") else "dev"),
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
    )
