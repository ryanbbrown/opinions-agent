from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import opinions_agent.app as app_module
from opinions_agent.cli import _cron_trigger
from opinions_agent.config import Settings, get_settings, validate_cron_settings, validate_web_settings
from opinions_agent.corpus import CorpusPaths, init_data_dirs
from opinions_agent.fsio import write_json_atomic
from opinions_agent.models import CycleStatus, GitPhase, OpinionCycle, OpinionRun, RunStatus
from opinions_agent.recovery import archive_and_restore_run, capture_run_baseline, reconcile_git_durability
from opinions_agent.telegram import FakeTelegramClient
from opinions_agent.tools.git_ops import commit_and_push_opinions_files, run_git
from opinions_agent.workflow import send_cycle_failure_notice


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
        opinions_target_file="TEST_OPINIONS.md" if environment == "staging" else "OPINIONS.md",
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
    with pytest.raises(ValueError, match="staging requires"):
        validate_web_settings(replace(web, opinions_target_file="OPINIONS.md"))
    with pytest.raises(ValueError, match="must not contain credentials"):
        validate_web_settings(replace(web, opinions_repo_url="https://token@github.com/example/repo.git"))


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
    (opinions_repo / "UNRELATED.md").write_text("user change\n", encoding="utf-8")

    archive = archive_and_restore_run(settings, run, run_dir)

    assert settings.opinions_target_path.read_text(encoding="utf-8") == original_opinions
    assert corpus.decisions_jsonl.read_text(encoding="utf-8") == ""
    assert (opinions_repo / "UNRELATED.md").read_text(encoding="utf-8") == "user change\n"
    assert (archive / "changes.patch").read_text(encoding="utf-8")


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

    assert len(telegram.sent) == 1
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
