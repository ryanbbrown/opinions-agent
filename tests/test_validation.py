from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import seed_corpus

from opinions_agent.agent import build_harness_config, build_read_context, build_validation_tool
from opinions_agent.config import OPINION_AGENT_MODEL, OPINION_AGENT_REASONING_EFFORT, Settings
from opinions_agent.corpus import CorpusPaths, DocumentRow, upsert_documents
from opinions_agent.fsio import read_json, write_json_atomic
from opinions_agent.opinions_doc import OpinionsDocError
from opinions_agent.prompts import build_system_prompt
from opinions_agent.selection import RunPaths, select_run_highlights, write_run_bundle
from opinions_agent.validation import run_artifact_validation


def make_bundle(settings: Settings):
    seed_corpus(settings)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    end = datetime(2026, 6, 12, tzinfo=UTC)
    highlights, documents = select_run_highlights(CorpusPaths(settings.opinions_data_dir), start, end)
    return write_run_bundle(
        run_id="validation-test",
        run_paths=RunPaths(settings.runs_dir),
        window_start=start,
        window_end=end,
        highlights=highlights,
        documents=documents,
    )


def test_validator_accepts_seed_artifacts(settings: Settings, opinions_repo: Path) -> None:
    bundle = make_bundle(settings)

    result = run_artifact_validation(settings=settings, run_dir=bundle.run_dir)

    assert result.opinion_count == 2
    assert result.source_count == 2
    assert result.max_opinion_id == 2


def test_validator_rejects_new_source_rows_outside_current_run(settings: Settings, opinions_repo: Path) -> None:
    bundle = make_bundle(settings)
    with (opinions_repo / "OPINIONS_SOURCES.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "opinion_id": "opinion-000001",
                    "evidence_id": "rw:not-selected",
                    "document_id": "reader:doc1",
                    "document_title": "Example Article",
                    "source_url": "https://example.com/article",
                    "evidence_text": "Nope.",
                    "added_at": "2026-06-01T00:00:00+00:00",
                }
            )
            + "\n"
        )

    with pytest.raises(OpinionsDocError, match="outside current run"):
        run_artifact_validation(settings=settings, run_dir=bundle.run_dir)


def test_validator_rejects_high_water_reuse(settings: Settings, opinions_repo: Path) -> None:
    bundle = make_bundle(settings)
    write_json_atomic(CorpusPaths(settings.opinions_data_dir).opinion_id_high_water, {"highest": 3})
    with (opinions_repo / "OPINIONS.md").open("a", encoding="utf-8") as handle:
        handle.write(
            """
## Strategy

- Reused IDs are invalid.
  <!-- opinion-id: opinion-000003 -->
"""
        )

    with pytest.raises(OpinionsDocError, match="high-water 3"):
        run_artifact_validation(settings=settings, run_dir=bundle.run_dir)


def test_validator_rejects_new_opinion_without_source_row(settings: Settings, opinions_repo: Path) -> None:
    bundle = make_bundle(settings)
    with (opinions_repo / "OPINIONS.md").open("a", encoding="utf-8") as handle:
        handle.write(
            """
## Strategy

- Unsupported new opinions are invalid.
  <!-- opinion-id: opinion-000003 -->
"""
        )

    with pytest.raises(OpinionsDocError, match="missing machine-readable source rows"):
        run_artifact_validation(settings=settings, run_dir=bundle.run_dir)


def test_validator_uses_baseline_max_as_effective_high_water(settings: Settings, opinions_repo: Path) -> None:
    bundle = make_bundle(settings)
    text = (opinions_repo / "OPINIONS.md").read_text(encoding="utf-8").replace("opinion-000002", "opinion-000004")
    (opinions_repo / "OPINIONS.md").write_text(text, encoding="utf-8")
    source_text = (opinions_repo / "OPINIONS_SOURCES.jsonl").read_text(encoding="utf-8").replace(
        "opinion-000002",
        "opinion-000004",
    )
    (opinions_repo / "OPINIONS_SOURCES.jsonl").write_text(source_text, encoding="utf-8")
    high_water = read_json(CorpusPaths(settings.opinions_data_dir).opinion_id_high_water, default={})
    assert high_water == {}

    subprocess.run(["git", "-C", str(opinions_repo), "add", "OPINIONS.md", "OPINIONS_SOURCES.jsonl"], check=True)
    subprocess.run(["git", "-C", str(opinions_repo), "commit", "-m", "test: create id gap"], check=True)
    with (opinions_repo / "OPINIONS.md").open("a", encoding="utf-8") as handle:
        handle.write(
            """
## Strategy

- Reusing an ID below the baseline max is invalid.
  <!-- opinion-id: opinion-000003 -->
  <!-- sources: rw:h0 -->
"""
        )
    with (opinions_repo / "OPINIONS_SOURCES.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(selected_source_row(bundle.run_dir, "opinion-000003", "rw:h0")) + "\n")

    with pytest.raises(OpinionsDocError, match="high-water 4"):
        run_artifact_validation(settings=settings, run_dir=bundle.run_dir)


def test_validator_rejects_incomplete_source_rows(settings: Settings, opinions_repo: Path) -> None:
    bundle = make_bundle(settings)
    with (opinions_repo / "OPINIONS_SOURCES.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"opinion_id": "opinion-000001", "evidence_id": "rw:h0"}) + "\n")

    with pytest.raises(OpinionsDocError, match="missing required fields"):
        run_artifact_validation(settings=settings, run_dir=bundle.run_dir)


def test_validator_rejects_new_source_rows_that_do_not_match_selected_evidence(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    bundle = make_bundle(settings)
    row = selected_source_row(bundle.run_dir, "opinion-000001", "rw:h0")
    row["evidence_text"] = "Fabricated text."
    with (opinions_repo / "OPINIONS_SOURCES.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")

    with pytest.raises(OpinionsDocError, match="metadata does not match selected evidence"):
        run_artifact_validation(settings=settings, run_dir=bundle.run_dir)


def test_validator_accepts_new_source_row_from_document_summary_evidence(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    seed_corpus(settings, highlight_count=0)
    paths = CorpusPaths(settings.opinions_data_dir)
    upsert_documents(
        paths,
        [
            DocumentRow(
                document_id="reader:summary-doc",
                reader_id="summary-doc",
                title="Summary Only",
                source_url="https://example.com/summary",
                summary="A tagged document summary can support an opinion.",
                tags=["ai direction"],
                saved_at="2026-06-02T00:00:00+00:00",
            )
        ],
    )
    highlights, documents = select_run_highlights(
        paths,
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 6, 12, tzinfo=UTC),
    )
    bundle = write_run_bundle(
        run_id="summary-validation-test",
        run_paths=RunPaths(settings.runs_dir),
        window_start=datetime(2026, 6, 1, tzinfo=UTC),
        window_end=datetime(2026, 6, 12, tzinfo=UTC),
        highlights=highlights,
        documents=documents,
    )
    with (opinions_repo / "OPINIONS.md").open("a", encoding="utf-8") as handle:
        handle.write(
            """
## AI Leverage

- Tagged document summaries can be accepted as selected evidence when they carry a deliberate context tag.
  <!-- opinion-id: opinion-000003 -->
  <!-- sources: reader-summary:summary-doc -->
"""
        )
    with (opinions_repo / "OPINIONS_SOURCES.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(selected_source_row(bundle.run_dir, "opinion-000003", "reader-summary:summary-doc")) + "\n"
        )

    result = run_artifact_validation(settings=settings, run_dir=bundle.run_dir)

    assert result.opinion_count == 3


async def test_validation_tool_uses_shared_validator(settings: Settings, opinions_repo: Path) -> None:
    bundle = make_bundle(settings)
    tool = build_validation_tool(settings=settings, run_dir=bundle.run_dir)

    result = await tool.handler(tool.parameters())

    assert tool.name == "validate_opinion_artifacts"
    assert result.ok is True
    assert "validated 2 opinions" in result.content


def test_harness_config_uses_fixed_native_tool_surface(settings: Settings, opinions_repo: Path) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    config = build_harness_config(context=context, settings=settings)

    assert config.builtin_tools == ["read", "search", "jsonl_search", "list", "glob", "edit", "write"]
    assert str(settings.opinions_target_path) in config.write_paths
    assert str(settings.opinions_sources_path) in config.write_paths
    assert str(CorpusPaths(settings.opinions_data_dir).decisions_jsonl) in config.write_paths
    assert str((bundle.run_dir / "selected-highlights.jsonl").resolve()) in config.read_paths
    assert str((bundle.run_dir / "selected-documents.jsonl").resolve()) in config.read_paths
    assert str((bundle.run_dir / "review").resolve()) not in config.read_paths
    assert config.system_prompt == build_system_prompt()
    assert config.output_mode == "auto"
    assert config.model == OPINION_AGENT_MODEL
    assert config.extra_body == {
        "output_config": {"effort": OPINION_AGENT_REASONING_EFFORT},
        "thinking": {"type": "adaptive"},
        "max_tokens": 64000,
    }
    assert read_json(CorpusPaths(settings.opinions_data_dir).opinion_id_high_water, default={}) == {}


def selected_source_row(run_dir: Path, opinion_id: str, evidence_id: str) -> dict:
    from opinions_agent.fsio import read_jsonl

    evidence = {row["highlight_id"]: row for row in read_jsonl(run_dir / "selected-highlights.jsonl")}[evidence_id]
    return {
        "opinion_id": opinion_id,
        "evidence_id": evidence_id,
        "document_id": evidence["document_id"],
        "document_title": evidence["document_title"],
        "source_url": evidence["source_url"],
        "evidence_text": evidence["text"],
        "added_at": evidence["highlighted_at"],
    }
