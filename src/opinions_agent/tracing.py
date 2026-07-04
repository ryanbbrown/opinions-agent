from __future__ import annotations

import atexit
import threading
from typing import Any

from opinions_agent.config import Settings

BRAINTRUST_OTEL_ENDPOINT = "https://api.braintrust.dev/otel/v1/traces"

_providers: dict[str, Any] = {}
_tracers: dict[str, Any] = {}
_tracing_lock = threading.Lock()


def braintrust_parent(settings: Settings) -> str:
    """The x-bt-parent slug spans attach to: an explicit parent (eval case span) or the project."""
    return settings.braintrust_parent or f"project_id:{settings.braintrust_project_id}"


def make_braintrust_tracing(settings: Settings):
    if not settings.braintrust_api_key or not settings.braintrust_project_id:
        return None
    from thinharness import TracingOptions

    return TracingOptions(
        tracer=_tracer_for_parent(settings, braintrust_parent(settings)),
        agent_name="opinions-agent",
        capture_messages=True,
        capture_tool_args=True,
        capture_tool_results=True,
    )


def flush_braintrust_tracing() -> None:
    with _tracing_lock:
        providers = list(_providers.values())
    for provider in providers:
        provider.force_flush()


def _tracer_for_parent(settings: Settings, parent: str):
    """One standalone OTLP provider per parent slug; never touches the global tracer provider."""
    with _tracing_lock:
        existing = _tracers.get(parent)
        if existing is not None:
            return existing
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": "opinions-agent"}))
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=BRAINTRUST_OTEL_ENDPOINT,
                    headers={
                        "Authorization": f"Bearer {settings.braintrust_api_key}",
                        "x-bt-parent": parent,
                    },
                )
            )
        )
        provider.add_span_processor(_environment_stamp_processor(settings.environment))
        tracer = provider.get_tracer("opinions-agent")
        _providers[parent] = provider
        _tracers[parent] = tracer
        atexit.register(provider.shutdown)
        return tracer


def _environment_stamp_processor(environment: str):
    from opentelemetry.sdk.trace import SpanProcessor

    class _EnvironmentStampProcessor(SpanProcessor):
        def on_start(self, span, parent_context=None) -> None:
            span.set_attribute("braintrust.metadata.environment", environment)

    return _EnvironmentStampProcessor()
