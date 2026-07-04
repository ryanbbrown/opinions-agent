"""Inspect eval experiments: pooled score means, per-run spread, and per-target pass counts.

Usage: uv run python eval/inspect_experiment.py <run> [<run2> ...] [--vs <baseline-run> ...]

Positional experiments are replicate runs of the same variant and are pooled together;
--vs pools one or more baseline runs and diffs the variant against them. Reads the scores
and judge verdicts already stored on the runs, so it never re-runs the judge.
"""

from __future__ import annotations

import argparse
import gzip
import json
from statistics import mean

import httpx

from opinions_agent.config import get_settings

SCORE_KEYS = ("opinion_quality", "opinion_attempted", "evidence_recall", "evidence_precision")


def _headers(settings) -> dict:
    return {"Authorization": f"Bearer {settings.braintrust_api_key}"}


def _experiment_ids(settings) -> dict[str, str]:
    r = httpx.get(
        "https://api.braintrust.dev/v1/experiment",
        params={"project_id": settings.braintrust_project_id, "limit": 100},
        headers=_headers(settings),
        timeout=30,
    )
    r.raise_for_status()
    return {obj["name"]: obj["id"] for obj in r.json()["objects"]}


def _fetch_events(settings, experiment_id: str) -> list[dict]:
    r = httpx.post(
        f"https://api.braintrust.dev/v1/experiment/{experiment_id}/fetch",
        headers=_headers(settings),
        json={"limit": 1000},
        timeout=120,
        follow_redirects=True,
    )
    r.raise_for_status()
    try:
        return json.loads(r.content)["events"]
    except ValueError:
        return json.loads(gzip.decompress(r.content))["events"]


def load(settings, ids: dict[str, str], name: str) -> tuple[dict, dict]:
    """Return (score values by key, verdicts by (week, target_id)) for one experiment."""
    if name not in ids:
        raise SystemExit(f"experiment not found: {name} (have: {sorted(ids)})")
    events = _fetch_events(settings, ids[name])
    scores: dict[str, list[float]] = {}
    for event in events:
        if (event.get("span_attributes") or {}).get("type") == "score":
            for key, value in (event.get("scores") or {}).items():
                if value is not None:
                    scores.setdefault(key, []).append(value)
    week_of_root = {
        event.get("root_span_id"): (event.get("input") or {}).get("week")
        for event in events
        if (event.get("span_attributes") or {}).get("type") == "eval"
    }
    verdicts: dict[tuple, tuple] = {}
    for event in events:
        metadata = event.get("metadata")
        if (event.get("scores") or {}).get("opinion_quality") is None or not isinstance(metadata, dict):
            continue
        week = week_of_root.get(event.get("root_span_id"), "?")
        for target in metadata.get("targets") or []:
            verdicts[(week, target["target_id"])] = (target.get("verdict"), target.get("missing"))
    return scores, verdicts


def pool(settings, ids: dict[str, str], names: list[str]) -> tuple[dict, dict, dict]:
    """Pool replicate runs: (pooled means, per-run means, per-target pass stats).

    Pass stats map (week, target_id) -> {"passes": int, "runs": int, "missing": last fail's missing note}.
    """
    pooled_scores: dict[str, list[float]] = {}
    run_means: dict[str, dict[str, float]] = {}
    passes: dict[tuple, dict] = {}
    for name in names:
        scores, verdicts = load(settings, ids, name)
        for key, values in scores.items():
            pooled_scores.setdefault(key, []).extend(values)
        run_means[name] = {key: round(mean(values), 4) for key, values in scores.items()}
        for target_key, (verdict, missing) in verdicts.items():
            stats = passes.setdefault(target_key, {"passes": 0, "runs": 0, "missing": None})
            stats["runs"] += 1
            if verdict == "pass":
                stats["passes"] += 1
            else:
                stats["missing"] = f"[{verdict}] {missing}"
    means = {key: round(mean(values), 4) for key, values in pooled_scores.items()}
    return means, run_means, passes


def _print_group(label: str, means: dict, run_means: dict, passes: dict) -> None:
    print(f"== {label} ({len(run_means)} run{'s' if len(run_means) != 1 else ''}) ==")
    for key in SCORE_KEYS:
        per_run = [m.get(key) for m in run_means.values() if m.get(key) is not None]
        detail = ""
        if len(per_run) > 1:
            detail = f"  (runs: {', '.join(f'{v:.3f}' for v in per_run)}; spread {max(per_run) - min(per_run):.3f})"
        print(f"  {key}: {means.get(key)}{detail}")
    flaky = {k: v for k, v in passes.items() if v["passes"] < v["runs"]}
    print("  targets not passing every run:" if flaky else "  targets not passing every run: none")
    for (week, target_id), stats in sorted(flaky.items()):
        note = f" missing: {str(stats['missing'])[:140]}" if stats["missing"] else ""
        print(f"    {week}/{target_id}  {stats['passes']}/{stats['runs']} pass{note}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("experiments", nargs="+", help="replicate runs of one variant, pooled together")
    parser.add_argument("--vs", nargs="+", default=[], help="baseline run(s) to pool and diff against")
    args = parser.parse_args()

    settings = get_settings()
    ids = _experiment_ids(settings)
    means, run_means, passes = pool(settings, ids, args.experiments)
    _print_group(" + ".join(args.experiments), means, run_means, passes)
    if not args.vs:
        return
    base_means, base_run_means, base_passes = pool(settings, ids, args.vs)
    print()
    _print_group(" + ".join(args.vs), base_means, base_run_means, base_passes)

    print(f"\n== {' + '.join(args.experiments)} vs {' + '.join(args.vs)} ==")
    for key in SCORE_KEYS:
        delta = (means.get(key) or 0) - (base_means.get(key) or 0)
        print(f"  {key}: {means.get(key)} vs {base_means.get(key)}  ({delta:+.3f})")

    def rate(stats: dict | None) -> float:
        return stats["passes"] / stats["runs"] if stats and stats["runs"] else 0.0

    keys = set(passes) | set(base_passes)
    gained = sorted(k for k in keys if rate(passes.get(k)) > rate(base_passes.get(k)))
    lost = sorted(k for k in keys if rate(passes.get(k)) < rate(base_passes.get(k)))

    def fmt(k: tuple) -> str:
        v, b = passes.get(k), base_passes.get(k)
        if not v or not b:
            return f"{k[0]}/{k[1]}"
        return f"{k[0]}/{k[1]} ({v['passes']}/{v['runs']} vs {b['passes']}/{b['runs']})"

    print(f"  pass rate up:   {', '.join(fmt(k) for k in gained) or 'none'}")
    print(f"  pass rate down: {', '.join(fmt(k) for k in lost) or 'none'}")


if __name__ == "__main__":
    main()
