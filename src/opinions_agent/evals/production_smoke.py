"""Disposable replay of accepted production runs through the current initial proposal path."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from opinions_agent.agent import ThinHarnessOpinionAgent, build_read_context
from opinions_agent.config import Settings, get_settings
from opinions_agent.fsio import read_jsonl, write_jsonl_atomic
from opinions_agent.opinions_doc import Opinion, parse_opinions
from opinions_agent.reader import iso_week, parse_iso


@dataclass(frozen=True)
class ProductionRun:
    commit: str
    run_id: str


PRODUCTION_RUNS = (
    ProductionRun("4f2827a", "745e736b-acb3-46d1-8709-f8a9e551dc9d"),
    ProductionRun("ac0046f", "fe479d9e-7e33-429e-ba62-8f8ef28472c7"),
    ProductionRun("a5e4a1e", "7fc94877-c615-489f-b896-637abbdab5d4"),
    ProductionRun("26f7bfe", "0b933d39-06b1-4760-8c36-2c80920e7418"),
    ProductionRun("12bcc1c", "1f0ded61-791c-49e0-8d8d-dc5831e794ed"),
    ProductionRun("a3c1618", "08b2a03c-9834-4a90-bbb5-b197d9047e61"),
    ProductionRun("ba3dd2b", "2200ec9f-abb7-4945-b74c-9e514b7c247b"),
)

OperationKind = Literal["add", "attach", "revise"]


@dataclass(frozen=True)
class GroundTruthOperation:
    operation: OperationKind
    opinion_id: str
    attached_evidence_ids: tuple[str, ...]
    detached_evidence_ids: tuple[str, ...]
    moved_from_opinion_ids: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class GroundTruth:
    commit: str
    parent_commit: str
    run_id: str
    operations: tuple[GroundTruthOperation, ...]

    @property
    def accepted_evidence_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                evidence_id for operation in self.operations for evidence_id in operation.attached_evidence_ids
            )
        )


@dataclass(frozen=True)
class SnapshotDiscovery:
    evidence_ids: tuple[str, ...]
    provenance: Literal["archive_run_id", "archive_evidence_match", "production_diff_fallback"]
    selected_path: Path | None
    equivalent_paths: tuple[Path, ...] = ()


@dataclass(frozen=True)
class ReconstructedInput:
    selected_rows: tuple[dict[str, Any], ...]
    selected_documents: tuple[dict[str, Any], ...]
    critic_context_rows: tuple[dict[str, Any], ...]
    provenance: SnapshotDiscovery


def derive_ground_truth(repo: Path, production_run: ProductionRun) -> GroundTruth:
    commit = _git(repo, "rev-parse", production_run.commit).strip()
    parents = _git(repo, "show", "-s", "--format=%P", commit).split()
    if len(parents) != 1:
        raise ValueError(f"production commit must have one parent: {production_run.commit}")
    parent = parents[0]
    subject = _git(repo, "show", "-s", "--format=%s", commit)
    if production_run.run_id not in subject:
        raise ValueError(f"commit {production_run.commit} does not name run {production_run.run_id}")

    before_doc = parse_opinions(_git_file(repo, parent, "OPINIONS.md"))
    after_doc = parse_opinions(_git_file(repo, commit, "OPINIONS.md"))
    before_by_id = {opinion.opinion_id: opinion for opinion in before_doc.opinions}
    after_by_id = {opinion.opinion_id: opinion for opinion in after_doc.opinions}
    removed_opinions = sorted(before_by_id.keys() - after_by_id.keys())
    if removed_opinions:
        raise ValueError(f"production smoke does not support removed opinions: {removed_opinions}")

    before_pairs = _source_pairs(_git_file(repo, parent, "OPINIONS_SOURCES.jsonl"))
    after_pairs = _source_pairs(_git_file(repo, commit, "OPINIONS_SOURCES.jsonl"))
    added_pairs = after_pairs - before_pairs
    removed_pairs = before_pairs - after_pairs
    changed_ids = {
        opinion_id
        for opinion_id, opinion in after_by_id.items()
        if opinion_id not in before_by_id
        or _opinion_claim(opinion) != _opinion_claim(before_by_id[opinion_id])
        or any(pair[0] == opinion_id for pair in added_pairs | removed_pairs)
    }

    operations: list[GroundTruthOperation] = []
    after_order = [opinion.opinion_id for opinion in after_doc.opinions]
    for opinion_id in after_order:
        if opinion_id not in changed_ids:
            continue
        added = tuple(sorted(evidence_id for pair_opinion, evidence_id in added_pairs if pair_opinion == opinion_id))
        removed = tuple(
            sorted(evidence_id for pair_opinion, evidence_id in removed_pairs if pair_opinion == opinion_id)
        )
        moved_from = {
            evidence_id: tuple(sorted(old_id for old_id, old_evidence in removed_pairs if old_evidence == evidence_id))
            for evidence_id in added
            if any(old_evidence == evidence_id for _, old_evidence in removed_pairs)
        }
        if opinion_id not in before_by_id:
            operation: OperationKind = "add"
        elif _opinion_claim(after_by_id[opinion_id]) != _opinion_claim(before_by_id[opinion_id]):
            operation = "revise"
        else:
            operation = "attach"
        operations.append(
            GroundTruthOperation(
                operation=operation,
                opinion_id=opinion_id,
                attached_evidence_ids=added,
                detached_evidence_ids=removed,
                moved_from_opinion_ids=moved_from,
            )
        )
    return GroundTruth(
        commit=commit,
        parent_commit=parent,
        run_id=production_run.run_id,
        operations=tuple(operations),
    )


def discover_snapshot(archive_root: Path, ground_truth: GroundTruth) -> SnapshotDiscovery:
    accepted = set(ground_truth.accepted_evidence_ids)
    candidates: list[tuple[Path, tuple[str, ...], bool]] = []
    if archive_root.exists():
        for selected_path in sorted(archive_root.rglob("selected-highlights.jsonl")):
            try:
                evidence_ids = tuple(str(row["highlight_id"]) for row in read_jsonl(selected_path))
            except (KeyError, OSError, ValueError, json.JSONDecodeError):
                continue
            direct = ground_truth.run_id in selected_path.parts or _bundle_names_run(selected_path, ground_truth.run_id)
            candidates.append((selected_path, evidence_ids, direct))

    direct = [(path, ids) for path, ids, is_direct in candidates if is_direct]
    if direct:
        return _equivalent_snapshot(direct, "archive_run_id")

    matching = [(path, ids) for path, ids, _ in candidates if accepted and accepted.issubset(ids)]
    if matching:
        non_eval = [(path, ids) for path, ids in matching if not any("-eval" in part for part in path.parts)]
        return _equivalent_snapshot(non_eval or matching, "archive_evidence_match")

    if not ground_truth.accepted_evidence_ids:
        raise ValueError(f"cannot reconstruct run {ground_truth.run_id}: production diff added no evidence")
    return SnapshotDiscovery(
        evidence_ids=ground_truth.accepted_evidence_ids,
        provenance="production_diff_fallback",
        selected_path=None,
    )


def reconstruct_input(corpus_root: Path, snapshot: SnapshotDiscovery) -> ReconstructedInput:
    highlights = read_jsonl(corpus_root / "highlights.jsonl")
    documents = read_jsonl(corpus_root / "documents.jsonl")
    highlights_by_id = {str(row["highlight_id"]): row for row in highlights}
    documents_by_id = {str(row["document_id"]): row for row in documents}
    summary_by_id = {
        f"reader-summary:{row['reader_id']}": _summary_evidence(row)
        for row in documents
        if str(row.get("summary") or "").strip()
    }
    evidence_by_id = {**highlights_by_id, **summary_by_id}
    missing = [evidence_id for evidence_id in snapshot.evidence_ids if evidence_id not in evidence_by_id]
    if missing:
        raise ValueError(
            "real Readwise corpus is missing production evidence required for replay: " + ", ".join(missing)
        )
    selected = tuple(dict(evidence_by_id[evidence_id]) for evidence_id in snapshot.evidence_ids)
    selected_documents = tuple(
        documents_by_id[document_id]
        for document_id in dict.fromkeys(str(row["document_id"]) for row in selected)
        if document_id in documents_by_id
    )

    critic_ids = snapshot.evidence_ids
    if snapshot.selected_path is not None:
        critic_path = snapshot.selected_path.with_name("critic-context.jsonl")
        if critic_path.exists():
            critic_ids = tuple(str(row["highlight_id"]) for row in read_jsonl(critic_path))
    missing_critic = [evidence_id for evidence_id in critic_ids if evidence_id not in evidence_by_id]
    if missing_critic:
        raise ValueError("real Readwise corpus is missing archived critic context: " + ", ".join(missing_critic))
    critic_rows = tuple(dict(evidence_by_id[evidence_id]) for evidence_id in critic_ids)
    return ReconstructedInput(
        selected_rows=selected,
        selected_documents=selected_documents,
        critic_context_rows=critic_rows,
        provenance=snapshot,
    )


def extract_consolidations(trace_dir: Path) -> list[dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for trace_path in sorted(trace_dir.rglob("*.jsonl")):
        for line in trace_path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            attributes = event.get("attributes") or {}
            if attributes.get("gen_ai.tool.name") != "validate_consolidation":
                continue
            raw = attributes.get("gen_ai.tool.call.arguments")
            arguments = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(arguments, dict) or not isinstance(arguments.get("result"), dict):
                continue
            results[str(arguments["candidate_id"])] = {
                "candidate_id": str(arguments["candidate_id"]),
                **arguments["result"],
            }
    return [results[candidate_id] for candidate_id in sorted(results)]


def score_routing(ground_truth: GroundTruth, consolidations: list[dict[str, Any]]) -> dict[str, Any]:
    expected_updates = {
        operation.opinion_id: operation
        for operation in ground_truth.operations
        if operation.operation in {"attach", "revise"}
    }
    generated_by_target: dict[str, list[dict[str, Any]]] = {}
    false_positives: list[dict[str, Any]] = []
    for result in consolidations:
        decision = result.get("decision") or {}
        if decision.get("kind") not in {"attach", "revise"}:
            continue
        target = str(decision.get("existing_opinion_id"))
        generated_by_target.setdefault(target, []).append(result)
        expected = expected_updates.get(target)
        moved = set(decision.get("evidence_ids") or [])
        if expected is None or not moved.issubset(expected.attached_evidence_ids):
            false_positives.append(result)

    recalled_targets = sorted(set(expected_updates) & set(generated_by_target))
    operation_exact_targets = sorted(
        target
        for target in recalled_targets
        if {result["decision"]["kind"] for result in generated_by_target[target]}
        == {expected_updates[target].operation}
    )
    evidence_exact_targets = sorted(
        target
        for target in recalled_targets
        if {
            evidence_id
            for result in generated_by_target[target]
            for evidence_id in result["decision"].get("evidence_ids", [])
        }
        == set(expected_updates[target].attached_evidence_ids)
    )
    return {
        "expected_update_targets": sorted(expected_updates),
        "recalled_update_targets": recalled_targets,
        "update_recall": {"numerator": len(recalled_targets), "denominator": len(expected_updates)},
        "false_positive_consolidations": false_positives,
        "attach_vs_revise_exact": {
            "targets": operation_exact_targets,
            "numerator": len(operation_exact_targets),
            "denominator": len(expected_updates),
        },
        "evidence_attachment_exact": {
            "targets": evidence_exact_targets,
            "numerator": len(evidence_exact_targets),
            "denominator": len(expected_updates),
        },
    }


async def run_smoke(
    *,
    settings: Settings,
    opinions_repo: Path,
    corpus_root: Path,
    archive_root: Path,
    output_dir: Path,
) -> Path:
    _require_disposable_output(output_dir, [opinions_repo, corpus_root, archive_root])
    output_dir.mkdir(parents=True)
    run_reports: list[dict[str, Any]] = []
    for production_run in PRODUCTION_RUNS:
        ground_truth = derive_ground_truth(opinions_repo, production_run)
        snapshot = discover_snapshot(archive_root, ground_truth)
        reconstructed = reconstruct_input(corpus_root, snapshot)
        case_dir = output_dir / f"{production_run.commit}-{production_run.run_id}"
        case_dir.mkdir()
        case_settings, run_dir = _prepare_case(
            settings=settings,
            opinions_repo=opinions_repo,
            corpus_root=corpus_root,
            case_dir=case_dir,
            ground_truth=ground_truth,
            reconstructed=reconstructed,
        )
        context = build_read_context(case_settings, run_dir)
        output, _ = await ThinHarnessOpinionAgent().run_turn(
            run_id=f"production-replay-{production_run.run_id}",
            context=context,
            settings=case_settings,
            prompt_fragment=None,
            resume_state=None,
        )
        consolidations = extract_consolidations(case_settings.local_trace_dir)
        candidates = read_jsonl(run_dir / "candidate-opinions.jsonl")
        case_report = {
            "commit": ground_truth.commit,
            "parent_commit": ground_truth.parent_commit,
            "production_run_id": ground_truth.run_id,
            "input_provenance": _snapshot_json(snapshot, archive_root),
            "ground_truth": [_ground_truth_json(operation) for operation in ground_truth.operations],
            "generated": {
                "candidates": candidates,
                "consolidations": consolidations,
                "agent_output": output.model_dump(mode="json"),
            },
            "metrics": score_routing(ground_truth, consolidations),
            "run_dir": str(run_dir),
            "trace_dir": str(case_settings.local_trace_dir),
        }
        _write_json(case_dir / "report.json", case_report)
        run_reports.append(case_report)
        _write_json(output_dir / "report.json", _aggregate_report(run_reports))
    return output_dir / "report.json"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opinions-repo", type=Path, default=Path("/Users/ryanbrown/code/ryanbbrown"))
    parser.add_argument("--corpus", type=Path, default=Path("/Users/ryanbrown/code/opinions-agent/.readwise"))
    parser.add_argument("--archive-root", type=Path, default=Path("/Users/ryanbrown/code/opinions-agent/.runs/active"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = asyncio.run(
        run_smoke(
            settings=get_settings(),
            opinions_repo=args.opinions_repo.expanduser().resolve(),
            corpus_root=args.corpus.expanduser().resolve(),
            archive_root=args.archive_root.expanduser().resolve(),
            output_dir=args.output_dir.expanduser().resolve(),
        )
    )
    print(report)


def _prepare_case(
    *,
    settings: Settings,
    opinions_repo: Path,
    corpus_root: Path,
    case_dir: Path,
    ground_truth: GroundTruth,
    reconstructed: ReconstructedInput,
) -> tuple[Settings, Path]:
    data_dir = case_dir / "data"
    _copy_corpus(corpus_root, data_dir)
    repo_dir = case_dir / "opinions-repo"
    repo_dir.mkdir()
    (repo_dir / "OPINIONS.md").write_text(
        _git_file(opinions_repo, ground_truth.parent_commit, "OPINIONS.md"), encoding="utf-8"
    )
    (repo_dir / "OPINIONS_SOURCES.jsonl").write_text(
        _git_file(opinions_repo, ground_truth.parent_commit, "OPINIONS_SOURCES.jsonl"), encoding="utf-8"
    )

    run_dir = case_dir / "run"
    (run_dir / "review").mkdir(parents=True)
    write_jsonl_atomic(run_dir / "selected-highlights.jsonl", list(reconstructed.selected_rows))
    write_jsonl_atomic(run_dir / "selected-documents.jsonl", list(reconstructed.selected_documents))
    write_jsonl_atomic(run_dir / "critic-context.jsonl", list(reconstructed.critic_context_rows))
    titles = [str(row.get("document_title") or "Untitled") for row in reconstructed.selected_rows]
    (run_dir / "review" / "summary.md").write_text(
        "# Historical production replay\n\n"
        f"Selected evidence: {len(reconstructed.selected_rows)}\n\n"
        + "\n".join(f"- {title}" for title in dict.fromkeys(titles))
        + "\n",
        encoding="utf-8",
    )
    case_settings = replace(
        settings,
        database_url=f"sqlite+pysqlite:///{case_dir / 'unused.db'}",
        telegram_allowed_chat_id=settings.telegram_allowed_chat_id or 1,
        braintrust_api_key="",
        braintrust_project_id="",
        braintrust_parent="",
        environment="dev",
        opinions_repo_url=str(repo_dir),
        opinions_repo_dir=repo_dir,
        opinions_target_file="OPINIONS.md",
        opinions_sources_file="OPINIONS_SOURCES.jsonl",
        opinions_data_dir=data_dir,
        runs_dir=case_dir,
        local_trace_dir=run_dir / ".traces",
        local_tracing_enabled=True,
        use_fake_telegram=True,
    )
    return case_settings, run_dir


def _copy_corpus(source: Path, target: Path) -> None:
    target.mkdir()
    for name in ("documents.jsonl", "highlights.jsonl"):
        shutil.copy2(source / name, target / name)
    for name in ("documents", "memory"):
        source_dir = source / name
        if source_dir.exists():
            shutil.copytree(source_dir, target / name)
        else:
            (target / name).mkdir()
    (target / "opinion-decisions.jsonl").write_text("", encoding="utf-8")


def _summary_evidence(document: dict[str, Any]) -> dict[str, Any]:
    saved_at = str(document.get("saved_at") or "")
    saved_datetime = parse_iso(saved_at)
    return {
        "highlight_id": f"reader-summary:{document['reader_id']}",
        "evidence_kind": "document_summary",
        "document_id": document["document_id"],
        "reader_id": document["reader_id"],
        "document_title": document.get("title"),
        "document_author": document.get("author"),
        "document_summary": document.get("summary"),
        "source_url": document.get("source_url"),
        "text": str(document.get("summary") or "").strip(),
        "highlighted_at": saved_at,
        "highlighted_date": saved_at[:10],
        "highlighted_week": iso_week(saved_datetime) if saved_datetime is not None else None,
        "updated_at": document.get("updated_at"),
        "content_path": document.get("content_path"),
        "note": None,
        "color": None,
    }


def _equivalent_snapshot(
    candidates: list[tuple[Path, tuple[str, ...]]],
    provenance: Literal["archive_run_id", "archive_evidence_match"],
) -> SnapshotDiscovery:
    grouped: dict[tuple[str, ...], list[Path]] = {}
    for path, evidence_ids in candidates:
        grouped.setdefault(evidence_ids, []).append(path)
    if len(grouped) != 1:
        paths = [str(path) for path, _ in candidates]
        raise ValueError(f"archive discovery is ambiguous across different selected evidence sets: {paths}")
    evidence_ids, paths = next(iter(grouped.items()))
    return SnapshotDiscovery(
        evidence_ids=evidence_ids,
        provenance=provenance,
        selected_path=paths[0],
        equivalent_paths=tuple(paths[1:]),
    )


def _bundle_names_run(selected_path: Path, run_id: str) -> bool:
    for parent in (selected_path.parent, *selected_path.parents[:3]):
        final_path = parent / "final.json"
        if final_path.exists():
            try:
                if json.loads(final_path.read_text(encoding="utf-8")).get("run_id") == run_id:
                    return True
            except (OSError, ValueError):
                pass
        summary_path = parent / "review" / "summary.md"
        if summary_path.exists() and f"Opinion run {run_id}" in summary_path.read_text(encoding="utf-8"):
            return True
    return False


def _opinion_claim(opinion: Opinion) -> tuple[str, str]:
    return opinion.section, opinion.text


def _source_pairs(text: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        evidence_id = row.get("evidence_id") or row.get("highlight_id")
        if not isinstance(row.get("opinion_id"), str) or not isinstance(evidence_id, str):
            raise ValueError("source rows must contain opinion_id and evidence_id")
        pairs.add((row["opinion_id"], evidence_id))
    return pairs


def _git_file(repo: Path, revision: str, path: str) -> str:
    return _git(repo, "show", f"{revision}:{path}")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError((result.stderr or result.stdout).strip())
    return result.stdout


def _require_disposable_output(output_dir: Path, protected: list[Path]) -> None:
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    for path in protected:
        resolved = path.resolve()
        if output_dir == resolved or resolved in output_dir.parents:
            raise ValueError(f"output directory must not be inside protected input: {resolved}")


def _ground_truth_json(operation: GroundTruthOperation) -> dict[str, Any]:
    return asdict(operation)


def _snapshot_json(snapshot: SnapshotDiscovery, archive_root: Path) -> dict[str, Any]:
    def display(path: Path | None) -> str | None:
        if path is None:
            return None
        try:
            return str(path.relative_to(archive_root))
        except ValueError:
            return str(path)

    return {
        "kind": snapshot.provenance,
        "selected_path": display(snapshot.selected_path),
        "equivalent_paths": [display(path) for path in snapshot.equivalent_paths],
        "evidence_ids": list(snapshot.evidence_ids),
        "rows_materialized_from": "read_only_real_readwise_corpus",
        "old_telegram_or_proposal_input_used": False,
    }


def _aggregate_report(run_reports: list[dict[str, Any]]) -> dict[str, Any]:
    update_numerator = sum(report["metrics"]["update_recall"]["numerator"] for report in run_reports)
    update_denominator = sum(report["metrics"]["update_recall"]["denominator"] for report in run_reports)
    operation_numerator = sum(report["metrics"]["attach_vs_revise_exact"]["numerator"] for report in run_reports)
    false_positives = sum(len(report["metrics"]["false_positive_consolidations"]) for report in run_reports)
    return {
        "created_at": datetime.now(UTC).isoformat(),
        "completed_runs": len(run_reports),
        "intended_runs": len(PRODUCTION_RUNS),
        "aggregate": {
            "update_recall": {"numerator": update_numerator, "denominator": update_denominator},
            "false_positive_consolidations": false_positives,
            "attach_vs_revise_exact": {"numerator": operation_numerator, "denominator": update_denominator},
        },
        "runs": run_reports,
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
