# Production deployment and catch-up

Inspected on 2026-09-07 at approximately 23:00 UTC. Deployment and catch-up are paused for a user decision about an existing Telegram conversation. No production state was changed during this inspection.

## Baseline and deployment

- Requested application commit: `2526a50c7187558776396698d162a40c09dfdacc`. Local main and this worktree both contained that commit at inspection.
- GitHub main still points to `d22ce271a65070f3a3faf6db9f92deb9dfe6e8cd`. The local fast-forward has not reached GitHub.
- Railway project: `opinions-agent`, ID `499ea088-a8fd-42cf-994a-fd8c73309545`.
- Railway environment: `production`, ID `56a08d8e-d05e-4a60-a95a-65cb7489bae0`. No separate staging environment was listed.
- `opinions-web` runs application commit `d22ce27`, deployment `df326f75-c115-49c3-985c-8cc6d4de03fa`, created August 21. One instance is running.
- `opinions-cron` uses the same old application commit and `/railway.cron.toml`. Its schedule is Monday at 00:00 UTC. The next scheduled run is September 14.
- Both services use the GitHub repository `ryanbbrown/opinions-agent`, branch main. Their deployed commands match the checked-in Railway files.
- The public hostname is `opinions-web-staging.up.railway.app`, but the app configuration is production and writes the real opinions repository on main. Do not treat the hostname as a staging boundary.
- Health returned HTTP 200 with `{"status":"ok"}`. The latest filtered application error-log request returned no entries. Health alone does not prove that model resume will succeed.
- No database migrations, Railway command changes, or default model changes exist between the deployed and requested commits. PostgreSQL is already at `0002_deployment_cycles`.

## State ownership and integrity

- Railway Postgres owns weekly progress, fixed evidence assignments, Telegram records, leases, and commit phases. It is not the local SQLite database.
- The web service alone mounts `/data`. Its durable paths are `/data/readwise`, `/data/runs`, and `/data/opinions-repo`.
- `/data/readwise` contains 720 document rows, 242 highlight/note rows, and 44 decision rows. The last successful sync was August 24 at 00:01:18 UTC; the Reader watermark is August 22 at 16:10:22.675787 UTC.
- Reader authentication returned HTTP 204. Sync was not started because an active cycle owns a frozen snapshot.
- The opinions repository is `ryanbbrown/ryanbbrown`, branch main, with `OPINIONS.md` and `OPINIONS_SOURCES.jsonl` as the configured artifacts.
- The volume checkout is clean at `44abd9399737a792cde3bb6838d4a9369eefcb9a`. Remote main is `a047383106512f468ebcfa0a8302536b58ae3cc3`. Both opinion artifacts are byte-identical at those two commits. No pull or reset was performed.
- Accepted production state has 50 opinion IDs and 119 source rows. All 119 `(opinion_id, evidence_id)` pairs are unique. There are 100 distinct evidence IDs: production already has evidence attached to more than one opinion. Preserve those accepted associations; do not replace them with eval's stricter one-home target partition.
- There are 89 cycle evidence assignments and 193 ignored-baseline assignments. The launch boundary remains June 15 at 00:00 UTC. Do not reset it or rebuild assignments from opinion text.
- There are no workflow leases. Two historical failed attempts belong to cycles that later completed; do not retry those attempts.
- The web volume has no backups or backup schedule. The database volume has one August 22 pre-security-patch backup, expiring September 21, and no schedule. PostgreSQL point-in-time recovery is disabled. A current database-and-volume recovery copy is needed before deployment or run replacement; backup policy remains a user decision.

## Telegram and catch-up boundary

Completed production windows form a continuous sequence from June 15 through August 17, with exclusive end dates. The August 10–17 run completed without an opinion commit; it is not missing work.

| UTC window, exclusive end | Production state |
|---|---|
| August 17–24 | Active; 12 evidence rows, one batch, awaiting Telegram input |
| August 24–31 | Not started |
| August 31–September 7 | Not started |
| September 7–14 | Incomplete week; do not start before September 14 at 00:00 UTC |

- Active cycle: `d37f431d-9cb2-430d-8d6f-67d472a93f89`.
- Active run: `a1503aa9-8eb9-4d77-8f2e-99fc928965c4`, turn 1, `awaiting_user`, git phase `agent_editing`, no result commit.
- The run has saved resume state and uses `/data/runs/active/d37f431d-9cb2-430d-8d6f-67d472a93f89/batches/1`. Its initial turn used the old single-stage runtime. It has no stored candidate-file input path.
- Five outbound messages, IDs 237–241, were sent for this run on August 24. No subsequent inbound response is recorded.
- Telegram's webhook points to the production web service and has zero pending updates. No polling, webhook change, synthetic approval, `GO`, or `SKIP` was sent.
- The latest cron log returns this existing active cycle. More start requests cannot bypass it and do not sync new evidence while it remains active.

## Braintrust and credentials

- Local and production configuration point to Braintrust project `opinions-agent`, ID `b3bd2c24-0c40-4d8b-adcb-b4ac57629bed`. Both configured keys could read the project.
- The project contains separate `opinion-targets` and `opinion-targets-v2` datasets. The inspected experiment list includes `concise90-i1-gpt-5.6-sol-full-20260907-w11-split-rescore` and its original full run.
- Production uses direct OpenAI access with `openai:gpt-5.6-sol`, medium effort. It does not use local cproxy. Braintrust tracing is configured with the `prod` environment tag and local plaintext tracing is disabled. This inspection verified configuration and API access, not receipt of a new production trace.
- `.env` key names, Railway variable names and safe configuration values, and Doppler `api-keys/dev_personal` key names were checked. Required deployed credentials are present. No secrets were requested, printed, copied into documentation, or changed.
- Do not run eval, sample-run, sample-session, or manual opinion-run against production. Do not copy the checked-in `OPINIONS.md`, target files, availability overrides, local corpus, or `.runs*` directories into `/data`.

## Decisions before mutation

1. Choose how to handle the pending August 17–24 conversation. Completing it in Telegram on the current deployment preserves its existing proposals. Alternatively, explicitly authorize archiving and abandoning that run, deploying the requested baseline, and retrying the same fixed batch to generate new proposals. The second option makes the pending week use the requested baseline but supersedes the old messages. Do not resume the old conversation under changed extraction tools without a decision.
2. Confirm the staging gate. README requires a complete staging cycle, repeated start, and stopped-batch retry before promotion. No isolated staging service/database/volume was found in this project. Do not repurpose production as staging. Either identify existing staging elsewhere or explicitly waive that gate; do not create new infrastructure without approval.
3. Choose backup protection. At minimum, capture both current database and web-volume state before deployment or run replacement. Confirm recurring backup policy separately. Do not restore the old database backup or change PostgreSQL topology.

## Deployment and catch-up procedure after those decisions

1. Re-read the active run, cycle, leases, repository status, remote refs, and webhook queue immediately before acting. User Telegram responses or cron may have changed state since this audit.
2. Resolve the old conversation according to the user's choice and verify the recovery copies. If replacing it, use the existing `abandon-run` operation only after approval; it archives/restores bounded artifacts and stops the cycle. Do not delete rows, assignments, or bundles.
3. Keep the deployed revision pinned to `2526a50c7187558776396698d162a40c09dfdacc`, not the later documentation commit. The existing GitHub deployment path can publish that exact commit with `git push origin 2526a50c7187558776396698d162a40c09dfdacc:refs/heads/main`, only if the remote remains its ancestor. Never force-push. Confirm both resulting Railway deployments use that exact application commit. If GitHub deployment does not start, inspect its settings before choosing another deployment route.
4. Verify runtime initialization, migration version, health, paths, real Telegram configuration, direct model configuration, repository state, and Braintrust access. Keep one web replica. Do not deploy the database or change the launch boundary.
5. If the pending run was replaced, run `uv run opinions-agent retry-cycle d37f431d-9cb2-430d-8d6f-67d472a93f89` inside the web container. Verify it uses the stored 12-row batch and preserves its evidence assignments. The worker generates replacement proposals; the user reviews them in Telegram.
6. Once that cycle is completed and any accepted commit is pushed, invoke the existing authenticated start endpoint from the web container using its configured start secret. Start exactly the next complete week, August 24–31. A repeated start while active must return the same cycle ID. Do not use manual date-window runs, which do not provide weekly assignment ownership.
7. Let the user answer all required proposal messages. Inspect the resulting commit, source-pair uniqueness, selected evidence ownership, cycle completion, and production Braintrust trace before starting August 31–September 7 the same way. A no-evidence cycle may complete immediately.
8. Stop at September 7 at 00:00 UTC. Batches advance automatically; later weekly cycles need separate starts. Do not send synthetic approvals to accelerate catch-up. Stop for any failure, changed repository artifact, unexpected evidence reassignment, or missing trace rather than resetting state.

## Inspection and validation performed

- Read the requested project contracts, eval status/performance, and deployment, configuration, sync, cycle, Telegram-routing, tracing, and recovery code.
- Used Railway status, variable inspection with redaction, read-only SQL transactions over Railway SSH, git read operations, backup queries, bounded logs, and read-only Telegram/Reader/Braintrust/GitHub API requests.
- Ran `uv run pytest -q`: 228 passed, 5 skipped. Optional model-backed tests were not enabled.
- Ran `uv run ruff check .`: passed.
- Ran `uv run pyright`: zero errors and warnings.
- No application code, product behavior, production service, database row, corpus file, opinion artifact, webhook, schedule, or credential was changed. No child threads or background jobs were started.
