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
- Catch-up is not complete. Later weeks must wait for the current cycle's user review and successful completion.
- A detailed retry trace check confirmed eight critic calls, eight consolidator calls, eight candidates of 34–61 words, and 10 unique candidate evidence links. Telegram recorded all eight proposal messages as sent, IDs 245–252.
- The detailed trace check found three document-search failures in the first image because it lacked `rg`. The web runtime package setting is `RAILPACK_DEPLOY_APT_PACKAGES="git ripgrep"`; the application source remains pinned. One selected highlight has empty text and note fields, which appears as a title/ID without a quote in the first proposal. These issues were not detected by the initial delivery/trace-receipt checks. The scheduled catch-up monitor is paused pending review; the current run remains awaiting user input.

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

## Verification

`uv run pytest -q`: 228 passed, 5 skipped. `uv run ruff check .`: passed. `uv run pyright`: zero errors and warnings. The ripgrep deployment passed health and the 107-file source comparison. Ripgrep 14.1.1 successfully executed all three previously failing document searches. The existing retry remains awaiting user input; no proposals were regenerated. No application code was changed. Product-contract and operational documentation changes are committed separately from the pinned deployment.
