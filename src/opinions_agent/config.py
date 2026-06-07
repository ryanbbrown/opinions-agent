from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_base_url: str
    opinions_repo_url: str
    opinions_repo_branch: str
    opinions_repo_dir: Path
    opinions_target_file: str
    opinions_git_author_name: str
    opinions_git_author_email: str
    runs_dir: Path
    local_trace_dir: Path
    local_tracing_enabled: bool
    use_fake_telegram: bool

    @property
    def opinions_target_path(self) -> Path:
        return (self.opinions_repo_dir / self.opinions_target_file).resolve()


def get_settings() -> Settings:
    load_dotenv()
    allowed_chat = _env("TELEGRAM_ALLOWED_CHAT_ID")
    return Settings(
        database_url=_env("DATABASE_URL", "sqlite+pysqlite:///./opinions-agent.db"),
        telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
        telegram_allowed_chat_id=int(allowed_chat) if allowed_chat else None,
        telegram_webhook_secret=_env("TELEGRAM_WEBHOOK_SECRET"),
        readwise_token=_env("READWISE_TOKEN"),
        harness_model=_env("HARNESS_MODEL", "openai:gpt-5.2"),
        langfuse_public_key=_env("LANGFUSE_PUBLIC_KEY"),
        langfuse_secret_key=_env("LANGFUSE_SECRET_KEY"),
        langfuse_base_url=_env("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com"),
        opinions_repo_url=_env("OPINIONS_REPO_URL", "https://github.com/ryanbbrown/ryanbbrown.git"),
        opinions_repo_branch=_env("OPINIONS_REPO_BRANCH", "main"),
        opinions_repo_dir=Path(_env("OPINIONS_REPO_DIR", "/Users/ryanbrown/code/ryanbbrown")).expanduser(),
        opinions_target_file=_env("OPINIONS_TARGET_FILE", "TEST_OPINIONS.md"),
        opinions_git_author_name=_env("OPINIONS_GIT_AUTHOR_NAME", "opinions-agent"),
        opinions_git_author_email=_env("OPINIONS_GIT_AUTHOR_EMAIL", "opinions-agent@example.com"),
        runs_dir=Path(_env("RUNS_DIR", ".runs")),
        local_trace_dir=Path(_env("THINHARNESS_LOCAL_TRACE_DIR", ".traces")),
        local_tracing_enabled=_env("THINHARNESS_DISABLE_LOCAL_TRACING", "").lower() not in {"1", "true", "yes"},
        use_fake_telegram=_env("OPINIONS_FAKE_TELEGRAM", "").lower() in {"1", "true", "yes"},
    )
