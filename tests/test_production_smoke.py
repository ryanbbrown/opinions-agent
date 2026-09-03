from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from opinions_agent.evals.production_smoke import (
    GroundTruth,
    GroundTruthOperation,
    ProductionRun,
    SnapshotDiscovery,
    derive_ground_truth,
    discover_snapshot,
    extract_consolidations,
    reconstruct_input,
    score_routing,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=True).stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "OPINIONS.md", "OPINIONS_SOURCES.jsonl")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def test_ground_truth_comes_from_opinion_and_source_diffs(tmp_path: Path) -> None:
    repo = tmp_path / "opinions"
    _git(tmp_path, "init", "-b", "main", str(repo))
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    (repo / "OPINIONS.md").write_text(
        """# OPINIONS

## Software

- Old claim.
  <!-- opinion-id: opinion-000001 -->
  <!-- sources: evidence-old -->

- Stable claim.
  <!-- opinion-id: opinion-000002 -->
""",
        encoding="utf-8",
    )
    _write_jsonl(
        repo / "OPINIONS_SOURCES.jsonl",
        [{"opinion_id": "opinion-000001", "evidence_id": "evidence-old"}],
    )
    _commit(repo, "seed")

    (repo / "OPINIONS.md").write_text(
        """# OPINIONS

## Software

- Revised claim.
  <!-- opinion-id: opinion-000001 -->
  <!-- sources: evidence-new -->

- Stable claim.
  <!-- opinion-id: opinion-000002 -->
  <!-- sources: evidence-old -->

- Added claim.
  <!-- opinion-id: opinion-000003 -->
  <!-- sources: evidence-add -->
""",
        encoding="utf-8",
    )
    _write_jsonl(
        repo / "OPINIONS_SOURCES.jsonl",
        [
            {"opinion_id": "opinion-000001", "evidence_id": "evidence-new"},
            {"opinion_id": "opinion-000002", "evidence_id": "evidence-old"},
            {"opinion_id": "opinion-000003", "evidence_id": "evidence-add"},
        ],
    )
    run_id = "11111111-1111-1111-1111-111111111111"
    commit = _commit(repo, f"chore: complete opinion run {run_id}")

    truth = derive_ground_truth(repo, ProductionRun(commit, run_id))

    assert [(operation.opinion_id, operation.operation) for operation in truth.operations] == [
        ("opinion-000001", "revise"),
        ("opinion-000002", "attach"),
        ("opinion-000003", "add"),
    ]
    assert truth.operations[0].detached_evidence_ids == ("evidence-old",)
    assert truth.operations[1].moved_from_opinion_ids == {"evidence-old": ("opinion-000001",)}
    assert set(truth.accepted_evidence_ids) == {"evidence-new", "evidence-old", "evidence-add"}


def test_discovery_prefers_run_metadata_then_falls_back_to_diff(tmp_path: Path) -> None:
    run_id = "22222222-2222-2222-2222-222222222222"
    truth = GroundTruth(
        commit="commit",
        parent_commit="parent",
        run_id=run_id,
        operations=(GroundTruthOperation("add", "opinion-000003", ("evidence-1",), (), {}),),
    )
    archive = tmp_path / "archive"
    selected = archive / "completed" / "cycle" / "batches" / "1" / "selected-highlights.jsonl"
    _write_jsonl(selected, [{"highlight_id": "evidence-1"}, {"highlight_id": "unused"}])
    (selected.parent / "final.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

    discovered = discover_snapshot(archive, truth)

    assert discovered.provenance == "archive_run_id"
    assert discovered.evidence_ids == ("evidence-1", "unused")
    assert discovered.selected_path == selected

    (selected.parent / "final.json").unlink()
    evidence_match = discover_snapshot(archive, truth)
    assert evidence_match.provenance == "archive_evidence_match"
    assert evidence_match.evidence_ids == ("evidence-1", "unused")

    fallback = discover_snapshot(tmp_path / "missing", truth)
    assert fallback.provenance == "production_diff_fallback"
    assert fallback.evidence_ids == ("evidence-1",)


def test_discovery_rejects_different_archive_sets_for_same_run(tmp_path: Path) -> None:
    run_id = "33333333-3333-3333-3333-333333333333"
    truth = GroundTruth(
        commit="commit",
        parent_commit="parent",
        run_id=run_id,
        operations=(GroundTruthOperation("add", "opinion-000003", ("accepted",), (), {}),),
    )
    for name, rows in (("one", ["accepted"]), ("two", ["accepted", "other"])):
        selected = tmp_path / name / "selected-highlights.jsonl"
        _write_jsonl(selected, [{"highlight_id": evidence_id} for evidence_id in rows])
        (selected.parent / "final.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

    with pytest.raises(ValueError, match="ambiguous"):
        discover_snapshot(tmp_path, truth)


def test_reconstruction_uses_archive_ids_but_real_corpus_rows(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    _write_jsonl(
        corpus / "highlights.jsonl",
        [
            {
                "highlight_id": "rw:real",
                "document_id": "reader:doc-1",
                "text": "Real corpus text",
                "document_title": "Real title",
            }
        ],
    )
    _write_jsonl(
        corpus / "documents.jsonl",
        [
            {
                "document_id": "reader:doc-1",
                "reader_id": "doc-1",
                "title": "Real title",
                "summary": "Real summary",
                "saved_at": "2026-01-02T00:00:00+00:00",
                "content_path": "documents/reader_doc-1.md",
            },
            {
                "document_id": "reader:doc-2",
                "reader_id": "doc-2",
                "title": "Summary title",
                "summary": "Summary evidence",
                "saved_at": "2026-01-03T00:00:00+00:00",
                "content_path": "documents/reader_doc-2.md",
            },
        ],
    )
    archived = tmp_path / "archive" / "selected-highlights.jsonl"
    _write_jsonl(
        archived,
        [
            {"highlight_id": "rw:real", "text": "Old Telegram answer leak"},
            {"highlight_id": "reader-summary:doc-2", "text": "Old final opinion leak"},
        ],
    )
    snapshot = SnapshotDiscovery(
        evidence_ids=("rw:real", "reader-summary:doc-2"),
        provenance="archive_evidence_match",
        selected_path=archived,
    )

    reconstructed = reconstruct_input(corpus, snapshot)

    assert [row["text"] for row in reconstructed.selected_rows] == ["Real corpus text", "Summary evidence"]
    assert [row["document_id"] for row in reconstructed.selected_documents] == ["reader:doc-1", "reader:doc-2"]
    assert reconstructed.critic_context_rows == reconstructed.selected_rows


def test_reconstruction_fails_when_real_corpus_is_incomplete(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "highlights.jsonl", [])
    _write_jsonl(tmp_path / "documents.jsonl", [])
    snapshot = SnapshotDiscovery(("missing",), "production_diff_fallback", None)

    with pytest.raises(ValueError, match="missing production evidence"):
        reconstruct_input(tmp_path, snapshot)


def test_trace_report_exposes_reasoning_and_scores_routing(tmp_path: Path) -> None:
    trace = tmp_path / "trace.jsonl"
    arguments = {
        "candidate_id": "candidate-001",
        "result": {
            "reasoning": "It completes the same belief.",
            "decision": {
                "kind": "revise",
                "existing_opinion_id": "opinion-000001",
                "revised_opinion_text": "Generated revision.",
                "evidence_ids": ["evidence-new"],
            },
        },
    }
    _write_jsonl(
        trace,
        [
            {
                "attributes": {
                    "gen_ai.tool.name": "validate_consolidation",
                    "gen_ai.tool.call.arguments": json.dumps(arguments),
                }
            }
        ],
    )
    truth = GroundTruth(
        commit="commit",
        parent_commit="parent",
        run_id="run",
        operations=(GroundTruthOperation("revise", "opinion-000001", ("evidence-new",), (), {}),),
    )

    consolidations = extract_consolidations(tmp_path)
    metrics = score_routing(truth, consolidations)

    assert consolidations[0]["reasoning"] == "It completes the same belief."
    assert metrics["update_recall"] == {"numerator": 1, "denominator": 1}
    assert metrics["attach_vs_revise_exact"]["numerator"] == 1
    assert metrics["evidence_attachment_exact"]["numerator"] == 1
    assert metrics["false_positive_consolidations"] == []
