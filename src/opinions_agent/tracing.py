from __future__ import annotations

import base64

from opinions_agent.config import Settings


def langfuse_headers(settings: Settings) -> dict[str, str]:
    token = base64.b64encode(f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def langfuse_endpoint(settings: Settings) -> str:
    return f"{settings.langfuse_base_url.rstrip('/')}/api/public/otel/v1/traces"


def make_langfuse_tracing(settings: Settings):
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    from thinharness import TracingOptions, create_otlp_tracing

    tracing = create_otlp_tracing(
        service_name="opinions-agent",
        endpoint=langfuse_endpoint(settings),
        headers=langfuse_headers(settings),
    )
    return TracingOptions(
        tracer=tracing.tracer,
        agent_name="opinions-agent",
        capture_messages=False,
        capture_tool_args=False,
        capture_tool_results=False,
    )
