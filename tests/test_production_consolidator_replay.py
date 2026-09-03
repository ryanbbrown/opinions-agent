from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from opinions_agent.config import Settings
from opinions_agent.evals.consolidator_replay import _case_settings, _selected_candidates, _summarize


def test_replay_settings_read_smoke_case_opinion_artifacts(tmp_path: Path, settings: Settings) -> None:
    configured = _case_settings(
        replace(settings, opinions_target_file="TEST_OPINIONS.md"),
        tmp_path / "case",
        tmp_path / "traces",
    )

    assert configured.opinions_target_file == "OPINIONS.md"
    assert configured.opinions_sources_file == "OPINIONS_SOURCES.jsonl"
    assert configured.opinions_target_path == (tmp_path / "case/opinions-repo/OPINIONS.md").resolve()


def test_candidate_selector_accepts_short_commit_and_rejects_unknown_case() -> None:
    source = {
        "runs": [
            {
                "commit": "abcdef0123456789",
                "generated": {"candidates": [{"candidate_id": "candidate-001"}]},
            }
        ]
    }

    selected = _selected_candidates(source, [("abcdef0", "candidate-001")])

    assert len(selected) == 1
    with pytest.raises(ValueError, match="unknown replay cases"):
        _selected_candidates(source, [("abcdef0", "candidate-999")])


def test_summary_distinguishes_false_add_consolidation_from_correct_revision() -> None:
    results = [
        {
            "expected_operations": [{"operation": "add", "opinion_id": "opinion-000002"}],
            "result": {"decision": {"kind": "independent"}},
        },
        {
            "expected_operations": [{"operation": "add", "opinion_id": "opinion-000003"}],
            "result": {"decision": {"kind": "revise", "existing_opinion_id": "opinion-000001"}},
        },
        {
            "expected_operations": [{"operation": "revise", "opinion_id": "opinion-000001"}],
            "result": {"decision": {"kind": "revise", "existing_opinion_id": "opinion-000001"}},
        },
    ]

    assert _summarize(results) == {
        "cases": 3,
        "exact_candidate_routes": 2,
        "correct_update_associations": 1,
        "false_consolidations_of_adds": 1,
    }
