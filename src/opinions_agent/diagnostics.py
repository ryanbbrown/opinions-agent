from __future__ import annotations

import logging
import os
import re

from opinions_agent.config import Settings
from opinions_agent.tools.git_ops import redact_git_error


def redact_operational_message(settings: Settings, message: str) -> str:
    for secret in (
        settings.opinions_git_token,
        settings.opinions_start_secret,
        settings.telegram_bot_token,
        settings.telegram_webhook_secret,
        settings.readwise_token,
        settings.braintrust_api_key,
        os.environ.get("OPENAI_API_KEY", ""),
        os.environ.get("BRAINTRUST_API_KEY", ""),
    ):
        if secret:
            message = message.replace(secret, "[REDACTED]")
    if settings.database_url:
        message = message.replace(settings.database_url, "[REDACTED_DATABASE_URL]")
    message = re.sub(r"(?i)(authorization\s*[:=]\s*)?bearer\s+[^\s,;]+", "Bearer [REDACTED]", message)
    message = re.sub(r"(?i)postgres(?:ql)?(?:\+\w+)?://[^@\s]+@", "postgresql://[REDACTED]@", message)
    return redact_git_error(message)


def log_operational_failure(
    logger: logging.Logger,
    settings: Settings,
    exc: Exception,
    *,
    phase: str,
    cycle_id: str = "none",
    batch: int = 0,
    run_id: str = "none",
) -> None:
    logger.error(
        "opinion workflow failure phase=%s exception=%s cycle_id=%s batch=%s run_id=%s message=%s",
        phase,
        type(exc).__name__,
        cycle_id,
        batch,
        run_id,
        redact_operational_message(settings, str(exc)),
    )
