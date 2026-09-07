# Fresh production start

Draft for review. This plan replaces the continuation procedure in `production-catch-up.md`; that file remains the historical inspection record. No production changes are authorized by writing or reviewing this plan.

## Agreed outcome

- Keep the Railway project `opinions-agent`, web service, cron service, hostname, Telegram bot, and existing credentials.
- Deploy application commit `2526a50c7187558776396698d162a40c09dfdacc` with a fresh PostgreSQL service and fresh web volume. Retain recovery copies of old state; do not restore it into the new runtime.
- Use one production environment. The user has waived a separate staging environment and accepts reviewing the first real run directly.
- Replace the live opinion artifacts with the checked-in seed plus every reviewed target through W13. Keep the opinions repository and main branch; preserve Git history with a normal replacement commit, never a force-push.
- Keep the existing Braintrust project for evals. Create `opinions-agent-runs` for production logs, not an experiment per run.
- Discard old pending conversations from the new workflow. All new proposals require fresh Telegram review.

## Steps and checks

1. **Freeze the inputs and dates.** Record the requested application SHA, seed and target file hashes, and the local reviewed corpus used to resolve source provenance. The current corpus maps W13 to June 8–15, 2026 UTC. Confirm that mapping against the reviewed evidence before changing production. The first fresh production window is therefore June 15–22, not August 24–31. Through September 7 at 00:00 UTC, catch-up contains 12 complete weeks. Freeze that upper bound for this catch-up; do not silently add more weeks if execution crosses another Monday.

2. **Build and validate the starting artifacts locally.** Apply all targets through W13, inclusive, to the checked-in seed. Reuse existing parsing, target application, and source-building helpers where suitable; `build_seed_opinions(..., "W13")` alone excludes W13 and is not sufficient. Expected result: 46 opinions, 94 distinct evidence rows, one opinion home per seed evidence row. Resolve complete provenance from the reviewed corpus, preserving original source dates rather than eval availability overrides. Fail on missing sources or count/partition mismatches. Do not copy eval databases, sample repositories, memory, decisions, assignments, or adjusted corpus timestamps. Check the fresh Reader corpus against this provenance before launch. Build any required preparation script with tests in a disposable repository; do not change the deployed agent baseline.

3. **Record the product contract after plan review.** Update `docs/behavior.md` and README to describe one production environment, the reviewed starting baseline, and separate Braintrust production logs. Document the exception to the prior staging gate and the archive boundary. Commit documentation and any preparation tooling separately from the pinned application revision. Run relevant tests, full pytest, Ruff, and Pyright for added code.

4. **Stop old work and make recoverable copies.** Inspect live state again. Disable cron starts and GitHub auto-deploys during the cutover; block Telegram delivery and stop the old web worker before snapshots. Do not let old and new workers overlap. Capture a consistent PostgreSQL dump, complete `/data` archive, opinion-repository refs, configuration key inventory, and deployed SHA. Keep secret values only in protected storage. Verify checksums, archive readability, and a database restore in isolation. Retain the old database and detached volume until the fresh first cycle succeeds and the user approves their deletion. Do not delete the Railway project.

5. **Prepare fresh infrastructure while stopped.** Add fresh PostgreSQL in the same project; create and attach a fresh volume to the existing web service. Keep the existing hostname. Point only the web service at the new database and volume. Use empty decisions and memory state, fresh sync watermarks, and fresh workflow tables. Set `OPINIONS_INITIAL_EVIDENCE_AFTER=2026-06-15T00:00:00Z`. Preserve an opinion-ID allocation floor at least as high as the old high-water mark and the seed maximum so future additions do not reuse retired IDs; this is an identifier guard, not old agent memory. Verify the seeded IDs as a new baseline, not as edits from an active old run.

6. **Separate tracing and publish the seed.** Create Braintrust project `opinions-agent-runs` with the existing account/key and set its project ID only on production. Leave the current eval project and local eval settings unchanged. Publish the two validated opinion artifacts as a normal commit on the opinions repository's main branch, touching no other files. Check remote main has not changed since preparation. Archive the prior commit so accepted old opinions remain recoverable. Fresh initialization must clone this seed commit, not the app repository's pre-W04 file.

7. **Deploy and initialize without starting a cycle.** Deploy exactly `2526a50` to the existing web service using a clean, pinned source snapshot and the existing Railway config. Do not upload the worktree's `.env`, `.runs*`, corpus, or local artifacts. Select the exact deployment mechanism after inspecting Railway's source controls; a plain push of a later documentation commit is not an exact-baseline deploy. Verify the deployed source, runtime initialization, migration head, mounted paths, clean seed checkout, real Telegram configuration, direct OpenAI model and medium effort, and new Braintrust project. Sync Readwise fresh on the new volume, using the normal sync command, with no simultaneous cycle start. Confirm there are no run, assignment, or Telegram rows before launch. Enable current recovery backups for the fresh database and volume.

8. **Reconnect Telegram safely.** Inspect pending Telegram updates from the cutover. Drain only stale callbacks/replies to archived runs while no new run exists; do not inject `GO`, `SKIP`, or approvals. Re-register the same webhook and secret against the existing hostname. Verify old message replies cannot reference new outbound rows and no old standalone command can approve a new conversation. Remove old keyboards if practical, without pretending the proposals were accepted. Confirm the webhook queue is clear before starting the first new run.

9. **Run one real week, then catch up in order.** Start June 15–22 through the normal authenticated weekly-cycle endpoint. Verify the first snapshot excludes all evidence dated before the launch boundary, records ignored baseline versions, and assigns each selected evidence version once. Inspect any selected evidence already in the seed before allowing a duplicate proposal. Verify a real trace reaches `opinions-agent-runs`. The user reviews the proposals in Telegram. After all batches finish, verify the push, accepted provenance, source-pair uniqueness, opinion-ID guard, and completed cycle. Repeat one week at a time through August 31–September 7. Repeated starts during an active cycle must return that cycle. Never use manual window runs, eval commands, or synthetic approvals for production catch-up. Changed Reader evidence is a new eligible version under the existing contract; do not suppress it by deleting assignments.

10. **Return to weekly operation.** Enable the existing Monday 00:00 UTC cron only after catch-up. Confirm its endpoint and secret still match the web service and its deployed command is pinned to the baseline. Recheck auto-deploy policy before reenabling it so a newer main commit cannot silently replace the pinned version. Record all new resource IDs, seed SHA, app deployment SHA, completed boundary, trace project, backup locations, and any retained old resources. Delete recovery infrastructure only with later user approval.

## Recovery and stop conditions

- Before any new accepted write, rollback means stopping the new worker, restoring the old configuration/database/volume and old opinion artifacts with a normal Git commit, then restoring the old webhook and schedule. Never enable both workers.
- After a new accepted write, stop and ask before rollback; restoring the old database alone would lose approvals and disagree with Git.
- Stop for an unverifiable backup, missing seed provenance, changed remote opinion files, mismatched deployed SHA, unexpected evidence overlap, failed validation/push, or missing production tracing. Preserve state rather than reset it.
- A stopped new batch uses existing recovery and retry commands against its fixed bundle. Failure is acceptable; evidence duplication or an unreviewed reset is not.

## User input

No further product choice is needed for the draft: the starting content, infrastructure reuse, fresh state, no staging split, and Braintrust separation are agreed. The user must review proposals during catch-up. Keep old recovery resources until explicit cleanup approval. If Railway requires an unexpected paid tier, cannot preserve the existing service with a fresh volume, or cannot pin the requested revision, ask before choosing a different arrangement.

## Review

Requested reviewer: Claude Code, Fable 5.1, medium effort. Review the reset boundary, seed construction, chronological coverage, cutover ordering, Telegram isolation, recovery, exact deployment revision, and required user decisions. Production remains unchanged during review.
