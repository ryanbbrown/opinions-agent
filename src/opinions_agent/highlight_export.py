from __future__ import annotations

import json
from pathlib import Path

from opinions_agent.models import ReadwiseHighlight, SummaryRun


def export_run_bundle(run: SummaryRun, highlights: list[ReadwiseHighlight], runs_dir: Path) -> dict[str, str]:
    run_dir = runs_dir / run.id
    run_dir.mkdir(parents=True, exist_ok=True)
    highlights_path = run_dir / "highlights.jsonl"
    brief_path = run_dir / "brief.md"

    with highlights_path.open("w", encoding="utf-8") as f:
        for highlight in highlights:
            payload = {
                "readwise_id": highlight.readwise_id,
                "document_title": highlight.document_title,
                "document_author": highlight.document_author,
                "text": highlight.text,
                "highlighted_at": highlight.highlighted_at.isoformat() if highlight.highlighted_at else None,
            }
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    titles = sorted({h.document_title or "Untitled" for h in highlights})
    brief_path.write_text(
        "\n".join(
            [
                f"# Summary run {run.id}",
                "",
                f"Highlights: {len(highlights)}",
                "",
                "Documents:",
                *[f"- {title}" for title in titles],
                "",
                "Create a concise summary from these recent Readwise highlights.",
            ]
        ),
        encoding="utf-8",
    )
    return {"dir": str(run_dir), "highlights_jsonl": str(highlights_path), "brief_md": str(brief_path)}
