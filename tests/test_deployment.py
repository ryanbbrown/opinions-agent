from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import opinions_agent.app as app_module
import opinions_agent.worker as worker_module
from opinions_agent.cli import _cron_trigger
from opinions_agent.config import Settings, get_settings, validate_cron_settings, validate_web_settings
from opinions_agent.corpus import CorpusPaths, init_data_dirs
from opinions_agent.db import make_engine, normalize_database_url
from opinions_agent.diagnostics import log_operational_failure
from opinions_agent.fsio import write_json_atomic
from opinions_agent.models import CycleStatus, GitPhase, OpinionCycle, OpinionRun, RunStatus
from opinions_agent.recovery import archive_and_restore_run, capture_run_baseline, reconcile_git_durability
from opinions_agent.repo_checkout import ensure_opinions_repo
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.tools.git_ops import commit_and_push_opinions_files, run_git
from opinions_agent.workflow import abandon_run, send_cycle_failure_notice


@pytest.mark.parametrize("database_url", ["postgresql://db/service", "postgres://db/service"])
def test_make_engine_uses_installed_psycopg_driver_for_railway_urls(database_url: str) -> None:
    assert normalize_database_url(database_url).startswith("postgresql+psycopg://")
    engine = make_engine(database_url)

    assert engine.url.drivername == "postgresql+psycopg"
    engine.dispose()


def railway_settings(settings: Settings, tmp_path: Path, *, environment: str) -> Settings:
    return replace(
        settings,
        environment=environment,
        database_url="postgresql+psycopg://db/service",
        volume_mount_path=tmp_path,
        opinions_start_secret="start-secret",
        opinions_start_url="https://web.example/internal/opinion-cycle/start",
        opinions_git_token="git-token",
        initial_evidence_after="2026-06-01T00:00:00+00:00",
        opinions_repo_url="https://github.com/example/opinions.git",
        opinions_repo_branch="staging" if environment == "staging" else "main",
        opinions_target_file="OPINIONS.md",
        local_tracing_enabled=False,
        use_fake_telegram=False,
    )


def test_web_and_cron_validation_are_independent(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    web = railway_settings(settings, tmp_path, environment="staging")
    validate_web_settings(web)

    cron = replace(settings, opinions_start_url=web.opinions_start_url, opinions_start_secret="start-secret")
    validate_cron_settings(cron)
    with pytest.raises(ValueError, match="OPINIONS_START_URL"):
        validate_cron_settings(replace(cron, opinions_start_url=""))
    with pytest.raises(ValueError, match="staging requires OPINIONS_REPO_BRANCH=staging"):
        validate_web_settings(replace(web, opinions_repo_branch="main"))
    with pytest.raises(ValueError, match="requires OPINIONS_TARGET_FILE=OPINIONS.md"):
        validate_web_settings(replace(web, opinions_target_file="TEST_OPINIONS.md"))
    with pytest.raises(ValueError, match="must not contain credentials"):
        validate_web_settings(replace(web, opinions_repo_url="https://token@github.com/example/repo.git"))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"environment": "dev"}, "must be staging or prod"),
        ({"volume_mount_path": None}, "RAILWAY_VOLUME_MOUNT_PATH"),
        ({"database_url": "sqlite+pysqlite:///unsafe.db"}, "must use PostgreSQL"),
        ({"database_url": "not a database url"}, "valid PostgreSQL URL"),
        ({"local_tracing_enabled": True}, "local plaintext tracing"),
        ({"use_fake_telegram": True}, "fake Telegram"),
    ],
)
def test_web_validation_rejects_unsafe_railway_settings(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    change: dict,
    message: str,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    configured = railway_settings(settings, tmp_path, environment="staging")

    with pytest.raises(ValueError, match=message):
        validate_web_settings(replace(configured, **change))


def test_production_validation_requires_tracing_credentials(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    configured = railway_settings(settings, tmp_path, environment="prod")

    with pytest.raises(ValueError, match="production requires"):
        validate_web_settings(configured)


def test_production_validation_requires_main_branch(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    configured = replace(
        railway_settings(settings, tmp_path, environment="prod"),
        braintrust_api_key="braintrust-key",
        braintrust_project_id="project-id",
        opinions_repo_branch="staging",
    )

    with pytest.raises(ValueError, match="prod requires OPINIONS_REPO_BRANCH=main"):
        validate_web_settings(configured)


@pytest.mark.parametrize("environment", ["staging", "prod"])
def test_explicit_deployed_environment_validates_without_railway_markers(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    for name in ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_SERVICE_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(app_module, "settings", replace(settings, environment=environment))

    with pytest.raises(ValueError, match="missing Railway web settings"):
        with TestClient(app_module.app):
            pass


def test_model_overrides_load_from_dotenv_after_file_is_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPINION_AGENT_MODEL", raising=False)
    monkeypatch.delenv("OPINION_AGENT_REASONING_EFFORT", raising=False)
    (tmp_path / ".env").write_text(
        "OPINION_AGENT_MODEL=openai:test-model\nOPINION_AGENT_REASONING_EFFORT=high\n",
        encoding="utf-8",
    )

    loaded = get_settings()

    assert loaded.harness_model == "openai:test-model"
    assert loaded.harness_reasoning_effort == "high"


async def test_cron_trigger_posts_once_and_accepts_202(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict]] = []

    class Response:
        status_code = 202

        def json(self):
            return {"cycle_id": "cycle-1", "status": "active", "batch_count": 2, "result_code": "created"}

    class Client:
        def __init__(self, *, timeout):
            assert timeout == 600

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, headers):
            calls.append((url, headers))
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    configured = replace(
        settings,
        opinions_start_url="https://web.example/internal/opinion-cycle/start",
        opinions_start_secret="start-secret",
    )

    await _cron_trigger(configured)

    assert calls == [
        (
            "https://web.example/internal/opinion-cycle/start",
            {"Authorization": "Bearer start-secret"},
        )
    ]


@pytest.mark.parametrize("status_code", [200, 202])
async def test_cron_trigger_accepts_success_responses(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    class Response:
        def json(self):
            return {"cycle_id": "cycle-1", "status": "active", "batch_count": 1, "result_code": "existing"}

    response = Response()
    response.status_code = status_code

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return response

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: Client())
    configured = replace(settings, opinions_start_url="https://web.example/start", opinions_start_secret="secret")
    await _cron_trigger(configured)


@pytest.mark.parametrize("status_code", [401, 409, 500])
async def test_cron_trigger_rejects_http_failures(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return SimpleNamespace(status_code=status_code)

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: Client())
    configured = replace(settings, opinions_start_url="https://web.example/start", opinions_start_secret="secret")
    with pytest.raises(SystemExit, match=str(status_code)):
        await _cron_trigger(configured)


async def test_cron_trigger_propagates_network_failure(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            raise OSError("network unavailable")

    monkeypatch.setattr("httpx.AsyncClient", lambda **kwargs: Client())
    configured = replace(settings, opinions_start_url="https://web.example/start", opinions_start_secret="secret")
    with pytest.raises(OSError, match="network unavailable"):
        await _cron_trigger(configured)


def test_start_endpoint_is_authenticated_and_returns_small_contract(
    session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = replace(settings, opinions_start_secret="start-secret")
    monkeypatch.setattr(app_module, "settings", configured)

    async def _fake_cycle(**kwargs):
        return SimpleNamespace(
            cycle_id="cycle-1",
            status="active",
            batch_count=2,
            result_code="created",
            created=True,
        )

    monkeypatch.setattr(
        app_module,
        "create_opinion_cycle",
        _fake_cycle,
    )
    app_module.app.dependency_overrides[app_module.get_session] = lambda: session
    client = TestClient(app_module.app)
    try:
        assert client.post("/internal/opinion-cycle/start").status_code == 401
        response = client.post(
            "/internal/opinion-cycle/start",
            headers={"Authorization": "Bearer start-secret"},
        )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json() == {
        "cycle_id": "cycle-1",
        "status": "active",
        "batch_count": 2,
        "result_code": "created",
    }


@pytest.mark.parametrize(
    ("created", "result_code", "status", "expected"),
    [
        (False, "existing", "active", 200),
        (True, "no_evidence", "completed", 200),
        (False, "stopped", "stopped", 409),
    ],
)
def test_start_endpoint_status_contract(
    session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    created: bool,
    result_code: str,
    status: str,
    expected: int,
) -> None:
    monkeypatch.setattr(app_module, "settings", replace(settings, opinions_start_secret="start-secret"))

    async def fake_cycle(**kwargs):
        return SimpleNamespace(
            cycle_id="cycle-1", status=status, batch_count=0, result_code=result_code, created=created
        )

    monkeypatch.setattr(app_module, "create_opinion_cycle", fake_cycle)
    app_module.app.dependency_overrides[app_module.get_session] = lambda: session
    try:
        response = TestClient(app_module.app).post(
            "/internal/opinion-cycle/start", headers={"Authorization": "Bearer start-secret"}
        )
    finally:
        app_module.app.dependency_overrides.clear()

    assert response.status_code == expected


def test_non_ascii_authorization_headers_return_unauthorized_without_logging_values(
    session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configured = replace(
        settings,
        opinions_start_secret="start-secret",
        telegram_webhook_secret="webhook-secret",
    )
    monkeypatch.setattr(app_module, "settings", configured)
    app_module.app.dependency_overrides[app_module.get_session] = lambda: session
    client = TestClient(app_module.app)
    malformed = "Bearer sécřet"
    malformed_bytes = malformed.encode()
    try:
        start = client.post("/internal/opinion-cycle/start", headers={"Authorization": malformed_bytes})
        webhook = client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": malformed_bytes},
            json={"update_id": 1},
        )
    finally:
        app_module.app.dependency_overrides.clear()

    assert start.status_code == 401
    assert webhook.status_code == 401
    assert malformed not in caplog.text


def test_health_requires_startup_database_and_volume(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_module, "startup_ready", False)
    with pytest.raises(app_module.HTTPException, match="startup reconciliation"):
        app_module.healthz()


def test_lifespan_serves_unhealthy_until_reconciliation_recovers(
    session,
    settings: Settings,
    opinions_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configured = replace(settings, opinions_git_token="operator-secret")
    run = OpinionRun(
        status=RunStatus.FAILED.value,
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 8, tzinfo=UTC),
        git_phase=GitPhase.PUSHED.value,
        baseline_complete=True,
    )
    session.add(run)
    session.commit()

    @contextmanager
    def session_scope():
        yield session

    async def idle_worker(*args, **kwargs):
        stop = args[4]
        await stop.wait()

    def fail_completion(*args, **kwargs):
        raise RuntimeError("artifact validation failed with operator-secret")

    def recover_completion(db_session, _settings, stored_run):
        stored_run.status = RunStatus.COMPLETED.value
        stored_run.git_phase = GitPhase.COMPLETED.value
        stored_run.failure_reason = None
        db_session.commit()

    monkeypatch.setattr(worker_module, "complete_reconciled_run", fail_completion)
    monkeypatch.setattr(app_module, "settings", configured)
    monkeypatch.setattr(app_module, "engine", session.get_bind())
    monkeypatch.setattr(app_module, "SessionLocal", session_scope)
    monkeypatch.setattr(app_module, "worker_loop", idle_worker)

    with caplog.at_level(logging.ERROR), TestClient(app_module.app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/healthz").status_code == 503
        assert "artifact validation failed" in caplog.text
        assert "operator-secret" not in caplog.text

        monkeypatch.setattr(worker_module, "complete_reconciled_run", recover_completion)
        run.reconcile_after = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        result = worker_module.reconcile_startup(session, configured)
        app_module._set_startup_ready(result.healthy)
        assert client.get("/healthz").status_code == 200

    class BrokenEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, RuntimeError("database unavailable"))

    monkeypatch.setattr(app_module, "startup_ready", True)
    monkeypatch.setattr(app_module, "engine", BrokenEngine())
    with pytest.raises(OperationalError):
        app_module.healthz()

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement):
            return None

    monkeypatch.setattr(app_module, "engine", SimpleNamespace(connect=lambda: Connection()))
    monkeypatch.setattr(app_module, "settings", replace(settings, opinions_repo_dir=tmp_path / "missing"))
    with pytest.raises(app_module.HTTPException, match="required volume path"):
        app_module.healthz()


def test_failed_edits_archive_and_restore_only_writable_artifacts(
    session,
    settings: Settings,
    opinions_repo: Path,
) -> None:
    corpus = CorpusPaths(settings.opinions_data_dir)
    init_data_dirs(corpus)
    write_json_atomic(corpus.opinion_id_high_water, {"highest": 2})
    run = OpinionRun(
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 8, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    run_dir = settings.runs_dir / "active" / run.id
    capture_run_baseline(settings, run, run_dir)
    original_opinions = settings.opinions_target_path.read_text(encoding="utf-8")
    settings.opinions_target_path.write_text("failed edit\n", encoding="utf-8")
    corpus.decisions_jsonl.write_text('{"failed": true}\n', encoding="utf-8")
    write_json_atomic(corpus.opinion_id_high_water, {"highest": 99})
    run_git(opinions_repo, "add", settings.opinions_target_file)
    (opinions_repo / "UNRELATED.md").write_text("user change\n", encoding="utf-8")

    archive = archive_and_restore_run(settings, run, run_dir)

    assert settings.opinions_target_path.read_text(encoding="utf-8") == original_opinions
    assert corpus.decisions_jsonl.read_text(encoding="utf-8") == ""
    assert (opinions_repo / "UNRELATED.md").read_text(encoding="utf-8") == "user change\n"
    assert (archive / "changes.patch").read_text(encoding="utf-8")
    assert run_git(opinions_repo, "diff", "--cached", "--name-only") == ""


def test_incomplete_baseline_never_deletes_current_artifacts(
    session,
    settings: Settings,
    opinions_repo: Path,
) -> None:
    cycle = OpinionCycle(
        week_key="2026-W24",
        status=CycleStatus.STOPPED.value,
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 8, tzinfo=UTC),
    )
    session.add(cycle)
    session.flush()
    run = OpinionRun(
        status=RunStatus.RUNNING_AGENT.value,
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 8, tzinfo=UTC),
        cycle_id=cycle.id,
        baseline_complete=False,
    )
    session.add(run)
    session.commit()
    original = settings.opinions_target_path.read_bytes()
    partial = settings.runs_dir / "active" / run.id / "recovery" / run.id / "baseline"
    partial.mkdir(parents=True)
    (partial / "opinions.md").write_text("partial copy", encoding="utf-8")

    with pytest.raises(RuntimeError, match="baseline is incomplete"):
        archive_and_restore_run(settings, run, settings.runs_dir / "active" / run.id)
    assert settings.opinions_target_path.read_bytes() == original

    with pytest.raises(RuntimeError, match="baseline is incomplete"):
        abandon_run(session, settings, run)
    assert run.status == RunStatus.RUNNING_AGENT.value
    assert settings.opinions_target_path.read_bytes() == original


async def test_stopped_cycle_notification_is_generic_and_idempotent(
    session,
    settings: Settings,
) -> None:
    cycle = OpinionCycle(
        week_key="2026-W24",
        status=CycleStatus.STOPPED.value,
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 8, tzinfo=UTC),
        failure_code="interrupted_agent",
    )
    session.add(cycle)
    session.flush()
    run = OpinionRun(
        status=RunStatus.FAILED.value,
        cycle_id=cycle.id,
        batch=2,
        window_start=cycle.window_start,
        window_end=cycle.window_end,
        failure_reason="secret-token raw exception",
    )
    session.add(run)
    session.commit()
    telegram = FakeTelegramClient()

    await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)
    await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=run)

    retry_run = OpinionRun(
        status=RunStatus.FAILED.value,
        cycle_id=cycle.id,
        batch=2,
        window_start=cycle.window_start,
        window_end=cycle.window_end,
        failure_reason="same failure on retry",
    )
    session.add(retry_run)
    session.commit()
    await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=retry_run)
    await send_cycle_failure_notice(session=session, settings=settings, telegram=telegram, run=retry_run)

    assert len(telegram.sent) == 2
    text = telegram.sent[0][1].text
    assert cycle.id in text and "batch 2" in text and "retry-cycle" in text
    assert "secret-token" not in text and "exception" not in text


def test_recovery_pushes_a_recorded_local_commit_without_rerunning_agent(
    session,
    settings: Settings,
    opinions_repo: Path,
) -> None:
    run = OpinionRun(
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 8, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    settings.opinions_target_path.write_text(
        settings.opinions_target_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    commit = commit_and_push_opinions_files(
        repo_dir=settings.opinions_repo_dir,
        target_files=[settings.opinions_target_file, settings.opinions_sources_file],
        branch=settings.opinions_repo_branch,
        author_name=settings.opinions_git_author_name,
        author_email=settings.opinions_git_author_email,
        message=f"chore: complete opinion run {run.id}",
        push=False,
    )
    run.git_phase = GitPhase.COMMITTED.value
    run.git_result_sha = commit.commit_sha

    assert reconcile_git_durability(settings, run) is True
    remote_head = run_git(settings.opinions_repo_dir, "ls-remote", "origin", "refs/heads/main").split()[0]
    assert remote_head == commit.commit_sha
    assert run.git_phase == GitPhase.PUSHED.value


def test_recovery_accepts_a_remote_descendant_of_the_recorded_commit(
    session,
    settings: Settings,
    opinions_repo: Path,
) -> None:
    run = OpinionRun(
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 8, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    settings.opinions_target_path.write_text(
        settings.opinions_target_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    first = commit_and_push_opinions_files(
        repo_dir=settings.opinions_repo_dir,
        target_files=[settings.opinions_target_file, settings.opinions_sources_file],
        branch=settings.opinions_repo_branch,
        author_name=settings.opinions_git_author_name,
        author_email=settings.opinions_git_author_email,
        message=f"chore: complete opinion run {run.id}",
        push=False,
    )
    (opinions_repo / "UNRELATED.md").write_text("remote descendant\n", encoding="utf-8")
    run_git(opinions_repo, "add", "UNRELATED.md")
    run_git(opinions_repo, "commit", "-m", "chore: later commit")
    run_git(opinions_repo, "push", "origin", "main")
    run.git_phase = GitPhase.COMMITTED.value
    run.git_result_sha = first.commit_sha

    assert reconcile_git_durability(settings, run) is True
    assert run.git_phase == GitPhase.PUSHED.value


def test_repo_refresh_fast_forwards_a_checkout_behind_remote(
    settings: Settings,
    opinions_repo: Path,
    tmp_path: Path,
) -> None:
    clone = tmp_path / "writer"
    run_git(tmp_path, "clone", "--branch", "main", str(tmp_path / "remote.git"), str(clone))
    run_git(clone, "config", "user.name", "Test User")
    run_git(clone, "config", "user.email", "test@example.com")
    (clone / "UNRELATED.md").write_text("remote update\n", encoding="utf-8")
    run_git(clone, "add", "UNRELATED.md")
    run_git(clone, "commit", "-m", "chore: remote update")
    run_git(clone, "push", "origin", "main")

    ensure_opinions_repo(settings)

    assert run_git(opinions_repo, "rev-parse", "HEAD") == run_git(opinions_repo, "rev-parse", "origin/main")


def test_baseline_rejects_a_local_commit_ahead_of_remote(
    session,
    settings: Settings,
    opinions_repo: Path,
) -> None:
    run = OpinionRun(
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 8, tzinfo=UTC),
    )
    session.add(run)
    session.flush()
    (opinions_repo / "UNRELATED.md").write_text("local update\n", encoding="utf-8")
    run_git(opinions_repo, "add", "UNRELATED.md")
    run_git(opinions_repo, "commit", "-m", "chore: local update")

    with pytest.raises(RuntimeError, match="does not match"):
        capture_run_baseline(settings, run, settings.runs_dir / "active" / run.id)


def test_repo_refresh_rejects_a_diverged_checkout(
    settings: Settings,
    opinions_repo: Path,
    tmp_path: Path,
) -> None:
    clone = tmp_path / "writer"
    run_git(tmp_path, "clone", "--branch", "main", str(tmp_path / "remote.git"), str(clone))
    run_git(clone, "config", "user.name", "Test User")
    run_git(clone, "config", "user.email", "test@example.com")
    (clone / "UNRELATED.md").write_text("remote update\n", encoding="utf-8")
    run_git(clone, "add", "UNRELATED.md")
    run_git(clone, "commit", "-m", "chore: remote update")
    run_git(clone, "push", "origin", "main")
    (opinions_repo / "UNRELATED.md").write_text("local update\n", encoding="utf-8")
    run_git(opinions_repo, "add", "UNRELATED.md")
    run_git(opinions_repo, "commit", "-m", "chore: local update")

    with pytest.raises(RuntimeError):
        ensure_opinions_repo(settings)


def test_operational_failure_log_redacts_credentials_and_keeps_context(
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    configured = replace(
        settings,
        opinions_git_token="git-secret",
        opinions_start_secret="start-secret",
        telegram_bot_token="telegram-secret",
        telegram_webhook_secret="webhook-secret",
        readwise_token="reader-secret",
        braintrust_api_key="braintrust-secret",
        database_url="postgresql+psycopg://db-user:db-secret@db.example/service",
    )
    error = RuntimeError(
        "git-secret start-secret telegram-secret webhook-secret reader-secret braintrust-secret "
        "https://user:password@example.com/repo Authorization: Bearer other-secret "
        "postgresql://another:database-secret@db.example/other failed"
    )

    with caplog.at_level(logging.ERROR):
        log_operational_failure(
            logging.getLogger("test.operational"),
            configured,
            error,
            phase="agent_turn",
            cycle_id="cycle-1",
            batch=2,
            run_id="run-1",
        )

    assert "phase=agent_turn" in caplog.text
    assert "exception=RuntimeError" in caplog.text
    assert "cycle_id=cycle-1 batch=2 run_id=run-1" in caplog.text
    for secret in (
        "git-secret",
        "start-secret",
        "telegram-secret",
        "webhook-secret",
        "reader-secret",
        "braintrust-secret",
        "other-secret",
        "database-secret",
        "password",
    ):
        assert secret not in caplog.text
