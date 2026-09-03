from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import seed_corpus
from pydantic import ValidationError

import opinions_agent.agent as agent_module
from opinions_agent.agent import (
    build_candidate_validation_tool,
    build_consolidation_context_tool,
    build_consolidation_output_type,
    build_consolidation_validation_tool,
    build_evidence_fetch_tool,
    build_harness_config,
    build_harness_plugins,
    build_opinion_sources_tool,
    build_read_context,
    build_validation_tool,
)
from opinions_agent.config import Settings
from opinions_agent.corpus import CorpusPaths, DocumentRow, upsert_documents
from opinions_agent.fsio import read_json, write_json_atomic, write_jsonl_atomic
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
    source_text = (
        (opinions_repo / "OPINIONS_SOURCES.jsonl")
        .read_text(encoding="utf-8")
        .replace(
            "opinion-000002",
            "opinion-000004",
        )
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


async def test_harness_config_uses_fixed_native_tool_surface(settings: Settings, opinions_repo: Path) -> None:
    from thinharness import Harness, PluginContext
    from thinharness.output import OutputSchema

    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    config = build_harness_config(context=context, settings=settings)
    plugins = build_harness_plugins(context=context)

    assert config.system_prompt == build_system_prompt()
    assert config.output_mode == "native"
    assert config.model == settings.harness_model
    assert config.effort == settings.harness_reasoning_effort
    assert config.request_timeout == 300
    assert [plugin.name for plugin in plugins] == ["filesystem", "subagents"]

    plugin_context = PluginContext(root=Path(config.root), model=None, child_harnesses=None)
    filesystem = plugins[0].bind(plugin_context).static
    assert [tool.name for tool in filesystem.tools] == [
        "read",
        "search",
        "jsonl_search",
        "list",
        "glob",
        "edit",
        "write",
    ]
    read_tool = filesystem.tools[0]
    allowed = read_tool.handler(read_tool.parameters(path=str(context.selected_highlights_jsonl)))
    denied = read_tool.handler(read_tool.parameters(path=str(bundle.run_dir / "review" / "summary.md")))
    assert allowed.ok is True
    assert denied.ok is False

    critic = plugins[1].agents[0]
    assert critic.name == "critic"
    assert [tool.name for tool in critic.tools] == ["get_candidate_evidence"]
    assert [plugin.name for plugin in critic.plugins] == ["filesystem"]
    critic_filesystem = critic.plugins[0].bind(plugin_context).static
    assert critic_filesystem.tools == ()
    assert critic_filesystem.instructions == (f"Workspace root: {Path(config.root)}",)

    consolidator = plugins[1].agents[1]
    assert consolidator.name == "consolidator"
    assert [tool.name for tool in consolidator.tools] == ["get_candidate_context", "get_opinion_sources"]
    consolidator_filesystem = consolidator.plugins[0].bind(plugin_context).static
    assert consolidator_filesystem.tools == ()
    assert consolidator.output_mode == "native"
    consolidation_schema = build_consolidation_output_type(context).model_json_schema()
    schema_text = json.dumps(consolidation_schema)
    assert consolidation_schema["type"] == "object"
    assert list(consolidation_schema["properties"]) == ["reasoning", "decision"]
    assert "anyOf" not in consolidation_schema
    wire_schema = OutputSchema.build(consolidator.output_type, consolidator.output_mode).schema
    decision_branches = wire_schema["properties"]["decision"]["anyOf"]
    assert len(decision_branches) == 3
    assert all(next(iter(branch["properties"])) == "kind" for branch in decision_branches)
    assert '"null"' not in schema_text
    assert "opinion-000001" in schema_text
    assert "opinion-000002" in schema_text
    assert "opinion-000000" not in schema_text
    assert '"independent"' in schema_text
    assert '"attach"' in schema_text
    assert '"revise"' in schema_text
    assert "revised_opinion_text" in schema_text
    assert '"opinion_text"' not in schema_text

    harness = Harness(
        config,
        plugins=plugins,
        tools=[
            build_candidate_validation_tool(context=context),
            build_consolidation_validation_tool(context=context),
            build_validation_tool(settings=settings, run_dir=bundle.run_dir),
        ],
    )
    assert [tool.name for tool in harness.tools] == [
        "read",
        "search",
        "jsonl_search",
        "list",
        "glob",
        "edit",
        "write",
        "subagent",
        "validate_candidates",
        "validate_consolidation",
        "validate_opinion_artifacts",
    ]
    await harness.aclose()
    assert read_json(CorpusPaths(settings.opinions_data_dir).opinion_id_high_water, default={}) == {}


def test_consolidation_schema_supports_independent_attach_and_revise_operations(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    output_type = build_consolidation_output_type(context)

    independent = output_type.model_validate(
        {"reasoning": "The candidate remains useful alone.", "decision": {"kind": "independent"}}
    )
    attach = output_type.model_validate(
        {
            "reasoning": "The existing text already states the candidate belief.",
            "decision": {
                "kind": "attach",
                "existing_opinion_id": "opinion-000001",
                "evidence_ids": ["rw:h0"],
            }
        }
    )
    revise = output_type.model_validate(
        {
            "reasoning": "The candidate completes the same belief.",
            "decision": {
                "kind": "revise",
                "existing_opinion_id": "opinion-000001",
                "revised_opinion_text": "  Complete revised opinion.  ",
                "evidence_ids": ["rw:h0"],
            }
        }
    )

    assert independent.decision.kind == "independent"
    assert attach.decision.kind == "attach"
    assert revise.decision.kind == "revise"
    assert revise.decision.revised_opinion_text == "Complete revised opinion."


@pytest.mark.parametrize("reasoning", ["", "   ", "\n\t"])
def test_consolidation_schema_rejects_empty_reasoning(
    settings: Settings,
    opinions_repo: Path,
    reasoning: str,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    output_type = build_consolidation_output_type(context)

    with pytest.raises(ValidationError, match="must not be empty"):
        output_type.model_validate({"reasoning": reasoning, "decision": {"kind": "independent"}})


@pytest.mark.parametrize("revised_opinion_text", ["", "   ", "\n\t"])
def test_consolidation_schema_rejects_empty_revision_sentinels(
    settings: Settings,
    opinions_repo: Path,
    revised_opinion_text: str,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    output_type = build_consolidation_output_type(context)

    with pytest.raises(ValidationError, match="must not be empty"):
        output_type.model_validate(
            {
                "reasoning": "The candidate completes the same belief.",
                "decision": {
                    "kind": "revise",
                    "existing_opinion_id": "opinion-000001",
                    "revised_opinion_text": revised_opinion_text,
                    "evidence_ids": ["rw:h0"],
                }
            }
        )


def test_consolidation_schema_rejects_removed_opinion_text_field(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    output_type = build_consolidation_output_type(context)

    with pytest.raises(ValidationError):
        output_type.model_validate(
            {
                "reasoning": "The candidate completes the same belief.",
                "decision": {
                    "kind": "revise",
                    "existing_opinion_id": "opinion-000001",
                    "opinion_text": "Old field name.",
                    "evidence_ids": ["rw:h0"],
                }
            }
        )


def test_empty_opinion_set_allows_only_independent_decision(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    context.opinions_md.write_text("# OPINIONS\n", encoding="utf-8")
    output_type = build_consolidation_output_type(context)

    result = output_type.model_validate(
        {"reasoning": "There is no existing opinion to target.", "decision": {"kind": "independent"}}
    )
    assert result.decision.kind == "independent"
    with pytest.raises(ValidationError):
        output_type.model_validate(
            {
                "reasoning": "This target does not exist.",
                "decision": {
                    "kind": "revise",
                    "existing_opinion_id": "opinion-000001",
                    "revised_opinion_text": "No current opinion can be targeted.",
                    "evidence_ids": ["rw:h0"],
                }
            }
        )


async def test_consolidator_context_tools_return_current_read_only_context(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    write_jsonl_atomic(
        context.candidate_opinions_jsonl,
        [
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "A saved candidate.",
                "evidence_ids": ["rw:h0"],
            }
        ],
    )

    candidate_tool = build_consolidation_context_tool(context=context)
    candidate_result = await candidate_tool.handler(candidate_tool.parameters(candidate_id="candidate-001"))
    sources_tool = build_opinion_sources_tool(context=context)
    sources_result = await sources_tool.handler(sources_tool.parameters(opinion_id="opinion-000001"))

    assert candidate_result.ok is True
    candidate_payload = json.loads(candidate_result.content)
    assert candidate_payload["candidate"]["opinion_text"] == "A saved candidate."
    assert "opinion-000001" in candidate_payload["current_opinions_markdown"]
    assert sources_result.ok is True
    assert json.loads(sources_result.content)[0]["opinion_id"] == "opinion-000001"


async def test_critic_evidence_tool_loads_current_saved_candidate_by_id(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    write_jsonl_atomic(
        context.candidate_opinions_jsonl,
        [
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "The first saved version.",
                "evidence_ids": ["rw:h0"],
            }
        ],
    )
    tool = build_evidence_fetch_tool(context=context)

    first = await tool.handler(tool.parameters(candidate_id="candidate-001"))
    context.candidate_opinions_jsonl.write_text(
        json.dumps(
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "The critic must see this edited version.",
                "evidence_ids": ["rw:h1"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    edited = await tool.handler(tool.parameters(candidate_id="candidate-001"))

    assert first.ok is True
    assert "The first saved version." in first.content
    assert "rw:h0" in first.content
    assert edited.ok is True
    assert "The critic must see this edited version." in edited.content
    assert "rw:h1" in edited.content
    assert "The first saved version." not in edited.content


async def test_critic_evidence_tool_normalizes_selected_evidence_ids(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    selected = agent_module.read_jsonl(context.selected_highlights_jsonl)
    selected[0]["highlight_id"] = 123
    write_jsonl_atomic(context.selected_highlights_jsonl, selected)
    write_jsonl_atomic(
        context.candidate_opinions_jsonl,
        [
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "A candidate with a numeric source ID.",
                "evidence_ids": ["123"],
            }
        ],
    )
    tool = build_evidence_fetch_tool(context=context)

    result = await tool.handler(tool.parameters(candidate_id="candidate-001"))

    assert result.ok is True
    assert "123" in result.content


async def test_critic_evidence_tool_reports_evidence_missing_after_candidate_lookup(
    settings: Settings,
    opinions_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    write_jsonl_atomic(
        context.candidate_opinions_jsonl,
        [
            {
                "candidate_id": "candidate-001",
                "section": "Agentic Software",
                "opinion_text": "A candidate whose selected evidence disappears.",
                "evidence_ids": ["rw:h0"],
            }
        ],
    )
    original_read_jsonl = agent_module.read_jsonl
    selected_reads = 0

    def read_jsonl_with_missing_second_read(path: Path) -> list[dict]:
        nonlocal selected_reads
        if path == context.selected_highlights_jsonl:
            selected_reads += 1
            if selected_reads == 2:
                return []
        return original_read_jsonl(path)

    monkeypatch.setattr(agent_module, "read_jsonl", read_jsonl_with_missing_second_read)
    tool = build_evidence_fetch_tool(context=context)

    result = await tool.handler(tool.parameters(candidate_id="candidate-001"))

    assert result.ok is False
    assert result.content == (
        "candidate candidate-001 cites evidence missing from selected run: rw:h0"
    )


async def test_critic_evidence_tool_rejects_missing_candidate_id(settings: Settings, opinions_repo: Path) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    context.candidate_opinions_jsonl.write_text("", encoding="utf-8")
    tool = build_evidence_fetch_tool(context=context)

    result = await tool.handler(tool.parameters(candidate_id="candidate-999"))

    assert result.ok is False
    assert "candidate ID not found: candidate-999" in result.content


async def test_critic_evidence_tool_rejects_duplicate_candidate_ids(
    settings: Settings,
    opinions_repo: Path,
) -> None:
    bundle = make_bundle(settings)
    context = build_read_context(settings, bundle.run_dir)
    row = {
        "candidate_id": "candidate-001",
        "section": "Agentic Software",
        "opinion_text": "Duplicate candidate.",
        "evidence_ids": ["rw:h0"],
    }
    write_jsonl_atomic(
        context.candidate_opinions_jsonl,
        [row, {**row, "opinion_text": "Another duplicate.", "evidence_ids": ["rw:h1"]}],
    )
    tool = build_evidence_fetch_tool(context=context)

    result = await tool.handler(tool.parameters(candidate_id="candidate-001"))

    assert result.ok is False
    assert "duplicate candidate ID: candidate-001" in result.content


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
