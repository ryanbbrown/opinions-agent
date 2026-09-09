# Production reset — September 8, 2026

The fresh production deployment is live. Catch-up starts June 15 and ends September 7, 2026 at 00:00 UTC. No old production run history or opinion-ID limits were imported.

## Deployment and state

- Application source: `2526a50c7187558776396698d162a40c09dfdacc`.
- Railway web deployment: `89ff52f0-5861-4d3d-a6aa-03cb668d48f5`, using the existing project and web service. It uses the same pinned application source with `git ripgrep` as runtime packages.
- Deployment input was a clean `git archive` of that SHA, uploaded with `railway up --path-as-root`. All 107 tracked source files were verified by SHA-256 against the live container. This upload has no Git commit metadata in Railway; the source comparison is the revision check.
- GitHub deployment triggers were removed from both app services. Weekly cron is paused until catch-up completes. The cron service still has its old build; deploy the pinned archive with its existing cron config before reenabling the schedule.
- Fresh PostgreSQL service: `Postgres-I2d7`, ID `5cf436f8-633d-4bd2-9879-e48b20a037f5`; database volume `0e81312b-50d5-4e6c-a41f-ad719d6bdadb`.
- Fresh web volume: `2d05024f-b1f1-41f0-9cb7-7a48a69462cf`, mounted at `/data` on the existing web service.
- Database binding was checked against the new PostgreSQL service. Before the first cycle, runs, cycles, evidence assignments, and Telegram tables were empty. Migration head was `0002_deployment_cycles`.
- Direct OpenAI model: `openai:gpt-5.6-sol`, medium effort. Real Telegram is enabled; local plaintext tracing is disabled.
- Health returned HTTP 200 with `{"status":"ok"}`.

## Starting opinions

- Seed commit in `ryanbbrown/ryanbbrown` main: `36fc0bc15cfa26defa8f177d6de020930ab34a2f`.
- Starting content is the checked-in pre-W04 seed plus every reviewed target through W13, inclusive. Assembly used the existing target application and source-building helpers, without model calls.
- Validation confirmed 46 opinions, 94 source pairs, 94 distinct evidence IDs, source coverage for every opinion, and every target's reviewed text and required evidence. The source validator passed.
- Internal IDs are unchanged from that assembly. The fresh high-water file contains `{"highest":46}`. No archived ID limit was read or copied.
- Only `OPINIONS.md` and `OPINIONS_SOURCES.jsonl` changed in the opinions repository. The checked-in app eval seed remains unchanged. Existing Git history preserves old opinion content; no archive tag was added.
- Live seed hashes before proposals: `OPINIONS.md` = `b89f367a7c889eed9774f3a9619d63a085a977c980126b710db6529704e9e454`; sources = `d022a34e6aa3102d99b42dca982f29d7380a7232e45be6377fefd1240aa8f5fe`.

## Reader, Telegram, and Braintrust

- Fresh Readwise sync fetched 1,451 rows and wrote 767 documents and 259 highlight/note rows. No eval availability overrides were applied. No historical completeness audit was performed.
- The same Telegram bot and webhook are in use. The queue was empty; registration explicitly dropped pending updates before any new cycle existed. No old proposals were approved or resumed.
- New Braintrust production project: `opinions-agent-runs`, UUID `29c09a04-5546-4952-9b88-cbfc9b6dfb16`. Production-key access and real `prod` agent/model/tool traces were verified.
- The existing eval Braintrust project and local eval configuration are unchanged.

## First cycle

- Cycle `378193e2-1790-4c4c-81af-26d108e037d5` owns June 15–22, with 10 evidence rows in one batch. The same-window second start returned the same active cycle.
- The database recorded 193 ignored baseline versions and 10 cycle assignments. These are fresh assignments, not copied old progress.
- First attempt `fd03979c-4935-4c10-b849-a41c06041de2` generated eight candidates and reached native Telegram proposal output, but sending the first proposal failed with a connection-establishment error (`ConnectError`). Start/failure notices were recorded; no opinion changes were committed. Both opinion artifact hashes still matched the seed.
- A read-only Telegram connectivity check then succeeded. The existing `retry-cycle` command queued the same stored batch once. Retry `723fea2e-0515-485b-b411-35fab2d7e458` reached `awaiting_user`, with all eight proposal messages sent. No new evidence selection, database reset, code change, or synthetic approval was used.
- June 15–22 completed at commit `ae3505d26b73175552182ab44eeb9b7dfbcbd7fd`, present at both the clean volume checkout and the opinions repository's remote main. Approvals were #1, #2, #6, and #8; rejections were #3, #4, #5, and #7. All 46 starting opinions remain unchanged, with four additions and six new evidence rows: 50 opinions and 100 unique source pairs/evidence IDs. Only the two configured opinion artifacts changed, and the final Telegram success message was sent after completion.
- Catch-up is not complete. Cycles through July 6 are completed; July 6–13 is active. The user requests later starts explicitly, without scheduled monitoring or routine post-run inspection.
- A detailed retry trace check confirmed eight critic calls, eight consolidator calls, eight candidates of 34–61 words, and 10 unique candidate evidence links. Telegram recorded all eight proposal messages as sent, IDs 245–252.
- The detailed trace check found three document-search failures in the first image because it lacked `rg`. The web runtime package setting is `RAILPACK_DEPLOY_APT_PACKAGES="git ripgrep"`; the application source remains pinned. One selected highlight has empty text and note fields, which appears as a title/ID without a quote in the first proposal. These issues were not detected by the initial delivery/trace-receipt checks. The scheduled catch-up monitor remains paused. The first cycle has completed through normal Telegram approval.

## Second cycle: June 22–29

- Cycle `b2248a4d-b439-454c-981e-9fb475359b4f`, run `6d51e612-1c45-454e-b11b-aae29965e185`, completed through three agent turns. Seven evidence rows produced four candidates, each 49–74 words, with unique evidence ownership.
- Inspection covered 100 Braintrust spans across the initial proposal, feedback, and final approval turns. No model/tool errors or failed tool outputs were present. Four critic calls and four consolidator calls completed; document search worked.
- Four initial Telegram proposals and two revised proposals matched the traced message text and buttons exactly and had real sent message IDs. The final success message matched the agent text with the app's durability suffix.
- The user approved the first two proposals, requested a separate opinion instead of one revision, and requested that another revision retain simplification as models improve. The agent preserved those pending opinions until the revised proposals were explicitly approved. Earlier artifact edits covered only the already-approved proposals.
- Commit `cd2c3f2ad404be262e51785a03f5093247120e64` added two opinions, revised two, and attached seven evidence rows. Validation passed: 52 opinions, 107 source rows, and high-water mark 52. There are no duplicate evidence assignments. Only the two configured opinion artifacts changed; the clean checkout HEAD matches remote main.
- No further week was started by this inspection. Ten complete weeks remain through September 7 at 00:00 UTC. No follow-up approval monitor is queued.

## Third cycle: June 29–July 6

- Cycle `29f79d4c-67f8-4b25-bc7b-ce052f9c9690`, run `3db47879-b93f-403d-8849-fd5badef1d69`, completed after user review. Its technical inspection covered the first two turns, before final approval. Thirteen evidence rows produced ten candidates of 41–63 words, with unique selected-evidence ownership.
- Inspection covered 147 Braintrust spans across generation and feedback. No model/tool errors or failed tool outputs were present. All ten critic and ten consolidator calls completed; document search worked.
- All ten initial proposals (Telegram IDs 265–274) and the requested standalone replacement for proposal #5 (ID 276) were sent with text and buttons matching traced output. At inspection, the other nine proposals had recorded approve/reject responses and #5 awaited its revised decision. A later start-boundary check confirmed the cycle completed.
- No opinion artifacts were edited before this inspection. The volume checkout is clean at `cd2c3f2ad404be262e51785a03f5093247120e64`, matching remote main. There are no duplicate evidence assignments.
- July 6–13 was then started at the user's request as cycle `64601029-f1fe-4fb4-a0ef-aa7b0b0aecc2`, with one batch. No timer or post-run inspection was scheduled.

## Comparison with the original first production week

The archived June 15–22 batch (`557acb0f-1c08-4c60-93e0-f610bcab53fd`, successful run `232d4519-bed4-4faa-af43-e646b482e57c`) contains exactly the same 10 selected evidence rows as the fresh batch, with no changed fields. The difference is proposal generation and routing, not evidence selection.

- Both runs proposed frontier-model training limits, trainable taste, downstream review costs from AI output, and distribution-market fit. These are fresh proposals #1, #3, #6, and #8.
- The fresh run also proposed greenfield software-factory setup (#2), research limitations (#4), failure clustering (#5), and founders using competing products (#7). The old initial transcript had no proposals for these four topics.
- The old run routed downstream review costs as a revision to its existing ownership/comprehension opinion. The fresh run proposed a separate addition. The starting opinion files and agent workflow differ, so this comparison does not isolate which change caused that routing choice.
- The old first run wrote `TEST_OPINIONS.md`; fresh production writes `OPINIONS.md`. The archived first-run transcript and its final Git diff were inspected, not imported into the new runtime.

## Recovery and cleanup

Private local copies live at `~/code/opinions-agent-backups/2026-09-08/`:

- `postgres.dump`: PostgreSQL custom-format archive, 801,570 bytes; SHA-256 `2566524881aeaa07ef0c45dea6023f400d75326735cda7f988f3bef8e2707779`. `pg_restore --list` succeeded.
- `data.tar.gz`: complete old `/data` archive, 8,536,208 bytes and 2,505 archive entries; SHA-256 `3693803d88291004ada65efd8b6e2c1a3058928697d7a5a69d1dc64081bb043e`. The member listing was checked.
- `manifest.json`: archived revision references, checksums, and configuration key names, without credential values.
- `seed/`: assembled starting opinion artifacts. `opinions-checkout/` is the local checkout used to publish the seed.

The directory is private. No full restore rehearsal was performed. The old PostgreSQL service was deleted. Both old Railway volumes are detached and pending Railway's deletion on September 10. They are not connected to production.

## Operational issues

- Railway file download requires a running deployment. A temporary source/start-command maintenance configuration did not take effect as expected: Railway rebuilt the old application instead. Old run timestamps remained unchanged, and the fresh database was still empty. The configuration was removed. Source-API deploy calls also reused the old revision despite an explicit commit argument, so deployment used a clean pinned archive instead. Live source hashes were verified before starting any fresh cycle.
- The Railway volume-add CLI panicked; the documented GraphQL create operation succeeded. CLI deletion timed out; explicit GraphQL deletes succeeded and their resulting state was verified.
- Daily backup scheduling for the fresh volumes returned `Not Authorized`. Neither fresh volume has a confirmed automatic backup schedule. This remains an operational blocker for automatic backups; no credential or account-tier changes were made to bypass it.

## Next-week start blocked by Railway API reads

After July 6–13 was started, subsequent next-week requests could not retrieve the start credential from Railway. The start endpoint was never called by those failed attempts.

- `railway whoami` and project listing succeed; the project still appears accessible. No `RAILWAY_*` environment variables override authentication.
- Project, service, deployment, and variable reads fail with `Problem processing request`, including direct GraphQL calls with explicit IDs. This is not limited to CLI name resolution. Example Railway trace IDs: `2595427158258200897` (minimal project read) and `2192832016895126309` (variables read).
- The deployed app's health endpoint still returns HTTP 200 and `{"status":"ok"}`, which includes its database connectivity check. Railway's public status page reports operational service; no wider outage is confirmed.
- The cause remains unresolved in Railway's resource-read path. No service restart, code change, credential rotation, new cycle, or timer was used in this investigation.

## July 20–27 stopped conversation

- Cycle `6650f71b-8ae0-4c40-a56d-2ebe52a417db`, run `672c2edc-4a4c-4454-950e-37eac2faeefd`, stopped after the agent refused a user-requested change from revision to standalone opinion and selected `blocked`. The subsequent user correction reached Telegram storage but did not resume the terminal run.
- Read-only inspection confirmed all four writable files match this run's saved baseline: opinions, sources, decisions, and the opinion-ID counter. The opinions checkout is clean at `78fbbe094db3da83f6c5fffed24e6ddef4ebdb84`. No artifact restoration is needed before retrying this batch.
- The conversation-control fix permits user-requested changes to initial consolidation and removes agent-selected `blocked`. Replies to plain help messages can resume the conversation without buttons. Revised proposals still require approval; application errors still preserve recovery state.
- Fix verification: 228 tests passed, 5 skipped; Ruff and Pyright passed. Revision `7583e7f` was deployed from a clean archive to web deployment `3c09fd13-3217-42b8-86ee-ffec48452498`. All 113 uploaded file hashes match the live container and `/healthz` passed. Cron and GitHub auto-deploy settings were not changed.
- Immediately before retry, all four writable files still matched the stopped attempt's baseline and the opinions checkout was clean. `retry-cycle 6650f71b-8ae0-4c40-a56d-2ebe52a417db` queued the same fixed batch once. Fresh attempt `08cfa634-1b4e-4fc9-a0bb-fe2cc6cab117` is running with turn sequence zero, no saved conversation, and base commit `78fbbe094db3da83f6c5fffed24e6ddef4ebdb84`. The old blocked attempt remains as history. No files were restored, no approvals were carried forward, and no later week was started. No follow-up timer was scheduled.

## July 27–August 2 attachment display retry

- Both prompt restrictions against showing existing opinion text were replaced: attachment proposals show the target opinion ID and its existing text unchanged under “Opinion”. Revision `095cba2` passed 228 tests (5 skipped), Ruff, and Pyright, and was pushed to main.
- Cycle `8b4d9e0f-0180-4bc8-8992-a3caa00a9ecf` covers July 27 through exclusive August 3 UTC. Awaiting attempt `c44ae1e1-dfb6-40c9-8db5-a4dbbb98cab2` had no changes to any of the four writable files. The authorized `abandon-run` command preserved its history and recovery archive and stopped the batch.
- Web deployment `c7bdef32-693f-4981-bb20-57643a21f10c` uses a clean archive of `095cba2`. All 113 uploaded file hashes match the live container; health passed. All four writable files still matched the baseline and the opinions checkout was clean before retry.
- The stored batch was queued once with `retry-cycle`. Fresh attempt `b2d2eec0-b592-48a5-a2b1-728d2489fe50` started at turn zero with no saved conversation and base commit `f6300c3f81c492817caf256c93cc83328a114d65`. Use its new Telegram proposals; the old attempt's responses do not carry forward. No later week, timer, cron change, or auto-deploy change was made.

## Verification

`uv run pytest -q`: 228 passed, 5 skipped. `uv run ruff check .`: passed. `uv run pyright`: zero errors and warnings. The ripgrep deployment passed health and the 107-file source comparison. Ripgrep 14.1.1 successfully executed all three previously failing document searches. The dependency deployment preserved the awaiting retry without regenerating proposals; that retry subsequently completed through user approval. No application code was changed. Product-contract and operational documentation changes are committed separately from the pinned deployment.
