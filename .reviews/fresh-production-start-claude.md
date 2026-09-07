# Review: fresh production start plan

Reviewer: Claude Code, Fable 5.1, medium effort. Target: `.plans/fresh-production-start.md` at `9341d46544211524a6d629b39e43a1a75c9cc589`. Planning-only review. No production, Railway, GitHub, Braintrust, Telegram, secret, or database state was read with write access or changed.

## Verified facts

- W13 maps to June 8–15, 2026 UTC. The main checkout corpus anchors on the first highlight (March 16, 2026, `sample_run.py:36`). W13 target evidence is dated June 10–14. No reviewed target evidence is dated at or after June 15, so the first fresh cycle cannot re-select seed evidence.
- June 15 to September 7 at 00:00 UTC is 12 complete weeks. Step 1 and step 9 agree.
- The two `reader-summary:` required sources (W04-03, W06-03) are absent from `highlights.jsonl` but present in `documents.jsonl` with `saved_at` and a summary. `_source_row_for_document_summary` (`sample_run.py:247`) can resolve them. All 66 other required rows are in the local corpus.
- The opinions repository remote `main` is still `a047383` (50 opinions, 119 source rows, max ID `opinion-000050`), matching the September 7 inspection. The local checkout at `/Users/ryanbrown/code/ryanbbrown` is stale at `c728764` (README-only difference). Do not use that checkout to judge "remote unchanged"; use `git ls-remote`.
- The repository already contains `OPINIONS_vOld.md` and `OPINIONS_SOURCES_vOld.jsonl` from an August 21 reset commit. This is the second reset of these artifacts.

## Findings

### F1. High: the opinion-ID guard has no mechanism in the plan

Step 5 says to preserve an ID floor at least as high as the old high-water mark, but nothing creates it. `init_data_dirs` (`corpus.py:117`) does not write `opinion-id-high-water.json`, and `read_opinion_id_high_water` (`validation.py:83`) returns 0 when the file is absent. Validation then uses `max(0, seed max ID 46)` (`validation.py:39`), so the first new opinion would take `opinion-000047`, which the git history of the opinions repository already used for a different opinion.

Correction: write `{"highest": 50}` to `/data/readwise/opinion-id-high-water.json` on the fresh volume before the first run, after confirming 50 is the old maximum from `a047383`. Add a verification bullet: `read_opinion_id_high_water` returns 50 and the first accepted new opinion is `opinion-000051`. Note the file is part of every run baseline (`recovery.py:36`), so it must exist before the first batch captures its baseline.

### F2. High: seed IDs 1–46 change meaning; the plan does not say so

`build_seed_opinions` allocates target IDs sequentially from 13 (`targets.py:102`, `opinions_doc.py:119`). Production history already assigned 13–50 to different text, and the checked-in seed text for 1–12 differs from production 1–12. README and OPINIONS-2 promise IDs are never reused. The plan calls this "a normal replacement commit" but never states the ID-meaning break.

Correction: pick one explicitly. Option A (simplest): accept reuse, tag `a047383` as the archive boundary, and add an archive-boundary exception to `docs/behavior.md` in step 3. Option B: renumber seed targets to start at 51 in the preparation script. User decision required; A is recommended because the old history is already retired and B makes production IDs diverge from every eval seed.

### F3. Medium: reviewed corpus stops before the launch boundary

The local corpus last synced on June 14 at 15:17 UTC with Reader watermark June 14 02:24 UTC (`state.json`). Any evidence created between that watermark and June 15 00:00 UTC lies inside W13 but was never reviewed. `_eligible_versions` (`cycles.py:366`) marks every fresh-synced row dated before the boundary as `baseline_ignored`, so those rows are never proposed.

Correction: in step 2 or step 7, after the fresh sync, list rows with `highlighted_at < 2026-06-15` that are not in the W04–W13 selections or the pre-W04 windows. Report the count to the user before launch. If nonzero, the user decides whether to accept the loss.

### F4. Medium: changing service variables can boot the old build on the fresh database

Railway redeploys the current build when variables or volumes change. Steps 4, 5, and 7 order "stop old worker", "attach fresh database and volume", then "deploy exactly 2526a50". If the old `d22ce27` build restarts after step 5, its `init-runtime` migrates the fresh database, clones the opinions repository, and starts the worker. Railway also allows one volume per service, so the old volume must be detached or deleted before the new one attaches.

Correction: state the exact stop mechanism (remove the active deployment or set the service to zero replicas) and confirm it survives variable edits. Confirm Railway keeps a detached volume; otherwise the `/data` archive is the only recovery copy, and step 4 must also verify a volume restore, not only a database restore. Verify the fresh database has zero migrations and the fresh volume is empty immediately before the pinned deploy.

### F5. Medium: Telegram pending-update handling is underspecified

With a webhook registered, `getUpdates` returns 409, so "inspect pending updates" needs `getWebhookInfo` (count only) or `deleteWebhook` followed by `getUpdates`. `_set_webhook` (`cli.py:453`) does not pass `drop_pending_updates`. Stale callbacks and replies are already harmless: the fresh database has no rows for messages 237–241, so callbacks answer "no longer pending" (`workflow.py:784`) and replies return `no_pending_run` (`workflow.py:879`). The one real hazard is a standalone `GO` or `SKIP` text queued during cutover; it resumes any run in `awaiting_user` (`workflow.py:865`).

Correction: replace "drain" with a direct `setWebhook` call using `drop_pending_updates=true` and the same URL and secret, then confirm `pending_update_count` is 0 before step 9. Telegram keeps undelivered updates for about 24 hours, so stopping the web service is enough to block delivery in step 4; no separate block is needed. Keyboard removal on messages 237–241 is cosmetic and can be skipped.

### F6. Medium: exact-revision deployment path and durable auto-deploy policy are open

GitHub `main` is at `d22ce27`; `2526a50` is a descendant, so `git push origin 2526a50:refs/heads/main` deploys it exactly. Step 3 then creates documentation and tooling commits that must also reach GitHub, and any push to `main` with auto-deploy on replaces the pinned build. Both `opinions-web` and `opinions-cron` build from `main`.

Correction: fix the order: push `2526a50` to `main`, confirm both services deployed that SHA, disable auto-deploy on both services, then push the documentation commits. If `railway up` is used instead, Railway shows no commit SHA, so add a build-time marker for verification. The plan needs a user decision for after catch-up: keep auto-deploy off and deploy manually, or accept that `main` tracks production again.

### F7. Low: rows without a source timestamp bypass the boundary

`_eligible_versions` treats `source_time is None` as eligible and never baseline-ignored (`cycles.py:380`). The local corpus has zero such rows, but the fresh sync covers more history.

Correction: add a check after the fresh sync that every evidence row and every tagged summary document has a timestamp.

### F8. Low: seed validation counts

Step 2 expects 94 distinct evidence rows. Check both the pair count `(opinion_id, evidence_id)` and the distinct evidence count equal 94, and that every one of the 46 opinions has at least one row. Run `validate_opinions_files` on the built artifacts; it enforces the required source fields (`opinions_doc.py:137`).

### F9. Low: archive approach conflicts with "touching no other files"

The prior reset added `*_vOld` files. Step 6 says the replacement commit touches only the two artifacts. A git tag on `a047383` satisfies "recoverable" without adding files. State which approach is used.

### F10. Info: Braintrust project value

`tracing.py:18` builds `project_id:<value>`, so `BRAINTRUST_PROJECT_ID` on production must be the new project's UUID, not its name. `validate_web_settings` rejects an empty value in prod. `docs/behavior.md` EVAL-6 currently says dev and production logs share the eval project; step 3 must change it.

## User questions

1. Accept opinion-ID reuse across the archive boundary, or renumber the seed from 51 (F2)?
2. After catch-up, keep Railway auto-deploy off permanently, or let `main` track production again (F6)?
3. If unreviewed evidence exists between June 14 02:24 and June 15 00:00 UTC, accept losing it (F3)?
4. Archive the old state by tag only, or continue the `*_vOld` file pattern (F9)?
