"""Report quality and length together for one or more eval experiments.

Usage: uv run python eval/brevity_report.py <experiment> [<experiment> ...]

Prints, per experiment: target-weighted quality (x/N), mean generated length as a
multiple of the golden opinion length, and how many proposals fit in a tweet.
Reads stored generations and verdicts from Braintrust; never re-judges.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent))

from inspect_experiment import _experiment_ids, _fetch_events  # noqa: E402

from opinions_agent.config import get_settings  # noqa: E402

TWEET_CHARS = 280


def golden_opinions() -> dict[str, str]:
    path = Path(__file__).resolve().parent / "opinion_targets.jsonl"
    golden = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            for target in json.loads(line)["targets"]:
                golden[target["target_id"]] = target["ideal_opinion"]
    return golden


def report(settings, ids: dict[str, str], name: str, golden: dict[str, str]) -> None:
    targets = {}
    for event in _fetch_events(settings, ids[name]):
        metadata = event.get("metadata")
        if (event.get("scores") or {}).get("opinion_quality") is None or not isinstance(metadata, dict):
            continue
        for target in metadata.get("targets") or []:
            targets[target["target_id"]] = target

    passes = sum(1 for t in targets.values() if t.get("verdict") == "pass")
    written = {tid: t.get("generated") or "" for tid, t in targets.items()}
    written = {tid: text for tid, text in written.items() if text}
    ratios = [len(text.split()) / len(golden[tid].split()) for tid, text in written.items()]
    tweetable = sum(1 for text in written.values() if len(text) <= TWEET_CHARS)
    golden_tweetable = sum(1 for tid in written if len(golden[tid]) <= TWEET_CHARS)

    print(f"{name}")
    print(f"  quality        {passes}/{len(targets)} = {passes / len(targets):.3f}")
    written_words = mean(len(text.split()) for text in written.values())
    golden_words = mean(len(golden[target_id].split()) for target_id in written)
    print(f"  length         {mean(ratios):.2f}x golden   ({written_words:.0f}w vs {golden_words:.0f}w)")
    print(f"  fits in tweet  {tweetable}/{len(written)}   (golden: {golden_tweetable}/{len(written)})")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    settings = get_settings()
    ids = _experiment_ids(settings)
    golden = golden_opinions()
    for name in sys.argv[1:]:
        if name not in ids:
            raise SystemExit(f"experiment not found: {name}")
        report(settings, ids, name, golden)


if __name__ == "__main__":
    main()
