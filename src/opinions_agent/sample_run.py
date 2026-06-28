from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from opinions_agent.config import Settings
from opinions_agent.corpus import (
    CorpusPaths,
    DocumentRow,
    HighlightRow,
    init_data_dirs,
    read_documents,
    read_highlights,
)
from opinions_agent.fsio import write_jsonl_atomic
from opinions_agent.opinions_doc import load_opinions
from opinions_agent.reader import parse_iso
from opinions_agent.tools.git_ops import run_git


def parse_week_label(label: str) -> int:
    normalized = label.strip().upper()
    if len(normalized) < 2 or not normalized.startswith("W") or not normalized[1:].isdigit():
        raise ValueError("week must look like W04")
    index = int(normalized[1:])
    if index < 1:
        raise ValueError("week must be W01 or later")
    return index


def week_window_for_label(paths: CorpusPaths, label: str) -> tuple[datetime, datetime]:
    week_index = parse_week_label(label)
    dated = [_highlight_datetime(highlight) for highlight in read_highlights(paths)]
    starts = [value for value in dated if value is not None]
    if not starts:
        raise ValueError(f"no dated highlights found in {paths.highlights_jsonl}")
    first = min(starts)
    anchor = datetime(first.year, first.month, first.day, tzinfo=UTC) - timedelta(days=first.weekday())
    start = anchor + timedelta(days=(week_index - 1) * 7)
    return start, start + timedelta(days=7)


def sample_run_id(label: str, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{label.strip().upper()}"


def sample_session_dir(settings: Settings, name: str) -> Path:
    normalized = name.strip()
    if not normalized:
        raise ValueError("sample session name is required")
    if any(part in {".", ".."} for part in Path(normalized).parts):
        raise ValueError("sample session name must not contain . or .. path components")
    return (settings.runs_dir / "sessions" / normalized).resolve()


def prepare_sample_session_settings(
    *,
    settings: Settings,
    name: str,
    opinions_file: Path,
    sources_file: Path | None = None,
) -> Settings:
    session_dir = sample_session_dir(settings, name)
    if session_dir.exists():
        raise FileExistsError(f"sample session already exists: {session_dir}")
    session_dir.mkdir(parents=True)
    sample_data = session_dir / "data"
    _copy_sample_corpus(CorpusPaths(settings.opinions_data_dir), CorpusPaths(sample_data))
    _init_sample_repo(
        repo_dir=session_dir / "opinions-repo",
        remote_dir=session_dir / "remote.git",
        branch=settings.opinions_repo_branch,
        author_name=settings.opinions_git_author_name,
        author_email=settings.opinions_git_author_email,
        opinions_file=opinions_file,
        sources_file=sources_file,
        corpus=CorpusPaths(sample_data),
    )
    return sample_session_settings(settings=settings, name=name)


def sample_session_settings(*, settings: Settings, name: str) -> Settings:
    session_dir = sample_session_dir(settings, name)
    if not session_dir.exists():
        raise FileNotFoundError(f"sample session not found: {session_dir}")
    return replace(
        settings,
        database_url=f"sqlite+pysqlite:///{session_dir / 'sample-session.db'}",
        opinions_repo_url=str(session_dir / "remote.git"),
        opinions_repo_dir=session_dir / "opinions-repo",
        opinions_target_file="OPINIONS.md",
        opinions_sources_file="OPINIONS_SOURCES.jsonl",
        opinions_data_dir=session_dir / "data",
        runs_dir=session_dir / "runs",
        local_trace_dir=session_dir / ".traces",
        use_fake_telegram=True,
    )


def prepare_sample_settings(
    *,
    settings: Settings,
    run_id: str,
    opinions_file: Path,
    sources_file: Path | None = None,
) -> Settings:
    run_dir = (settings.runs_dir / "active" / run_id).resolve()
    if run_dir.exists():
        raise FileExistsError(f"sample run already exists: {run_dir}")
    run_dir.mkdir(parents=True)

    sample_data = run_dir / "data"
    _copy_sample_corpus(CorpusPaths(settings.opinions_data_dir), CorpusPaths(sample_data))

    sample_repo = run_dir / "opinions-repo"
    _init_sample_repo(
        repo_dir=sample_repo,
        remote_dir=run_dir / "remote.git",
        branch=settings.opinions_repo_branch,
        author_name=settings.opinions_git_author_name,
        author_email=settings.opinions_git_author_email,
        opinions_file=opinions_file,
        sources_file=sources_file,
        corpus=CorpusPaths(sample_data),
    )

    return replace(
        settings,
        database_url=f"sqlite+pysqlite:///{run_dir / 'sample-run.db'}",
        opinions_repo_url=str(run_dir / "remote.git"),
        opinions_repo_dir=sample_repo,
        opinions_target_file="OPINIONS.md",
        opinions_sources_file="OPINIONS_SOURCES.jsonl",
        opinions_data_dir=sample_data,
        local_trace_dir=run_dir / ".traces",
        use_fake_telegram=True,
    )


def _highlight_datetime(highlight: HighlightRow) -> datetime | None:
    parsed = parse_iso(highlight.highlighted_at)
    return parsed.astimezone(UTC) if parsed else None


def _copy_sample_corpus(source: CorpusPaths, target: CorpusPaths) -> None:
    init_data_dirs(target)
    for source_file, target_file in [
        (source.documents_jsonl, target.documents_jsonl),
        (source.highlights_jsonl, target.highlights_jsonl),
        (source.decisions_jsonl, target.decisions_jsonl),
        (source.opinion_id_high_water, target.opinion_id_high_water),
    ]:
        if source_file.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)
    for source_dir, target_dir in [
        (source.documents_dir, target.documents_dir),
        (source.memory_dir, target.memory_dir),
    ]:
        if source_dir.exists():
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)


def _init_sample_repo(
    *,
    repo_dir: Path,
    remote_dir: Path,
    branch: str,
    author_name: str,
    author_email: str,
    opinions_file: Path,
    sources_file: Path | None,
    corpus: CorpusPaths,
) -> None:
    if not opinions_file.exists():
        raise FileNotFoundError(f"opinions file not found: {opinions_file}")
    _run("git", "init", "--bare", str(remote_dir))
    _run("git", "init", "-b", branch, str(repo_dir))
    run_git(repo_dir, "config", "user.name", author_name)
    run_git(repo_dir, "config", "user.email", author_email)
    shutil.copy2(opinions_file, repo_dir / "OPINIONS.md")
    if sources_file is not None and sources_file.exists():
        shutil.copy2(sources_file, repo_dir / "OPINIONS_SOURCES.jsonl")
    else:
        write_jsonl_atomic(repo_dir / "OPINIONS_SOURCES.jsonl", _source_rows_from_inline(opinions_file, corpus))
    run_git(repo_dir, "add", "OPINIONS.md", "OPINIONS_SOURCES.jsonl")
    run_git(repo_dir, "commit", "-m", "chore: seed sample opinion artifacts")
    run_git(repo_dir, "remote", "add", "origin", str(remote_dir))
    run_git(repo_dir, "push", "-u", "origin", branch)


def _source_rows_from_inline(opinions_file: Path, corpus: CorpusPaths) -> list[dict]:
    doc = load_opinions(opinions_file)
    highlights = {highlight.highlight_id: highlight for highlight in read_highlights(corpus)}
    summary_documents = {f"reader-summary:{document.reader_id}": document for document in read_documents(corpus)}
    rows: list[dict] = []
    missing: list[str] = []
    for opinion in doc.opinions:
        for evidence_id in opinion.sources:
            highlight = highlights.get(evidence_id)
            if highlight is not None:
                rows.append(_source_row_for_highlight(opinion.opinion_id, evidence_id, highlight))
                continue
            document = summary_documents.get(evidence_id)
            if document is not None and (document.summary or "").strip():
                rows.append(_source_row_for_document_summary(opinion.opinion_id, evidence_id, document))
                continue
            missing.append(f"{opinion.opinion_id}:{evidence_id}")
    if missing:
        raise ValueError(f"inline opinion sources are missing from the copied corpus: {missing}")
    return rows


def _source_row_for_highlight(opinion_id: str, evidence_id: str, highlight: HighlightRow) -> dict:
    return {
        "opinion_id": opinion_id,
        "evidence_id": evidence_id,
        "document_id": highlight.document_id,
        "document_title": highlight.document_title,
        "source_url": highlight.source_url,
        "evidence_text": highlight.text,
        "added_at": highlight.highlighted_at or "",
    }


def _source_row_for_document_summary(opinion_id: str, evidence_id: str, document: DocumentRow) -> dict:
    return {
        "opinion_id": opinion_id,
        "evidence_id": evidence_id,
        "document_id": document.document_id,
        "document_title": document.title,
        "source_url": document.source_url,
        "evidence_text": (document.summary or "").strip(),
        "added_at": document.saved_at or "",
    }


def _run(*args: str) -> None:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
