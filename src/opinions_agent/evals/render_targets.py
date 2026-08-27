"""Render the executable opinion targets as a human-readable Markdown twin."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render_targets_markdown(rows: list[dict]) -> str:
    lines = [
        "# Opinion Eval Targets",
        "",
        "## Judge rules",
        "",
        "- The conceptual judge checks required concepts and stance. Extra elaboration does not fail by itself.",
        "- Evidence precision separately penalizes citations outside the target's converted evidence.",
        "- Added same-source specificity is allowed when the draft carries the core concepts.",
        (
            "- One selected evidence row has one opinion home. "
            "Different highlights from the same article can support different opinions."
        ),
        "",
    ]
    for row in rows:
        lines.extend([f'## {row["week"]}', ""])
        for target in row["targets"]:
            lines.extend([f'### {target["target_id"]}', ""])
            if target["kind"] == "update":
                lines.append(f'**Operation:** update `{target["base_opinion_id"]}`')
            else:
                lines.append("**Operation:** add")
            lines.extend(
                [
                    "",
                    f'**Section:** {target["section"]}',
                    "",
                    target["ideal_opinion"],
                    "",
                    "**Core concepts**",
                    "",
                ]
            )
            lines.extend(f'- {concept}' for concept in target.get("required_concepts", []))
            lines.extend(["", "**Assigned evidence IDs**", ""])
            lines.extend(f'- `{source_id}`' for source_id in target["required_sources"])
            lines.extend(["", "**Source excerpts**", ""])
            for source in target.get("source_quotes", []):
                lines.append(f'- {source["title"]}: “{source["quote"]}”')
            lines.append("")
        lines.extend([f'### {row["week"]} not converted', ""])
        if row["not_converted"]:
            for item in row["not_converted"]:
                lines.append(f'- {item["title"]} (`{item["evidence_id"]}`, {item["evidence_kind"]})')
        else:
            lines.append("- None")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=Path("eval/opinion_targets.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("eval/opinion_targets.md"))
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.jsonl.read_text().splitlines() if line.strip()]
    args.output.write_text(render_targets_markdown(rows))


if __name__ == "__main__":
    main()
