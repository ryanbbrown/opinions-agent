"""Flag test-set text leaking into the prompt levers.

Usage: uv run python eval/check_leakage.py [worktree-dir]

Compares the worktree's prompts.py and RULES.md against eval/opinion_targets.jsonl
(ideal opinions, source quotes, and titles): any word 5-gram that appears in both a
lever file and the test set — and is not already in main's version of that lever file —
is reported as a hit. Exits 1 on hits. This is a tripwire for verbatim and near-verbatim
leaks; it does not replace the anti-leakage judgment rules in eval/GOAL.md.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

NGRAM = 5
LEVER_FILES = ("src/opinions_agent/prompts.py", "RULES.md")
TARGETS_PATH = Path(__file__).resolve().parent / "opinion_targets.jsonl"


def ngrams(text: str) -> set[tuple[str, ...]]:
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    return {tuple(words[i : i + NGRAM]) for i in range(len(words) - NGRAM + 1)}


def target_ngrams() -> dict[tuple[str, ...], str]:
    """Map each test-set n-gram to a label saying where it came from."""
    out: dict[tuple[str, ...], str] = {}
    for line in TARGETS_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        for target in row["targets"]:
            label = f"{row['week']}/{target['target_id']}"
            for gram in ngrams(target["ideal_opinion"]):
                out.setdefault(gram, f"{label} ideal_opinion")
            for quote in target.get("source_quotes", []):
                for gram in ngrams(f"{quote.get('title', '')} {quote.get('quote', '')}"):
                    out.setdefault(gram, f"{label} source_quote")
        for evidence in row.get("not_converted", []):
            for gram in ngrams(evidence.get("title", "")):
                out.setdefault(gram, f"{row['week']} not_converted title")
    return out


def main() -> None:
    worktree = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    targets = target_ngrams()
    hits: list[tuple[str, str, str]] = []
    for lever in LEVER_FILES:
        path = worktree / lever
        if not path.exists():
            raise SystemExit(f"lever file not found: {path}")
        baseline = subprocess.run(
            ["git", "-C", str(worktree), "show", f"main:{lever}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        added = ngrams(path.read_text(encoding="utf-8")) - ngrams(baseline)
        for gram in added & set(targets):
            hits.append((lever, " ".join(gram), targets[gram]))
    if not hits:
        print(f"no leakage hits ({', '.join(LEVER_FILES)} vs {TARGETS_PATH.name})")
        return
    print(f"{len(hits)} leakage hit(s) — n-grams added since main that also appear in the test set:")
    for lever, gram, source in sorted(hits):
        print(f'  {lever}: "{gram}"  <- {source}')
    print("review each hit; generalize any real leak before running the eval (see eval/GOAL.md)")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
