# Multi-review round manifest

- Feature: deployment readiness
- Mode: implementation
- Round: v2
- Captured at: 2026-08-12T00:17:10Z
- Base SHA: cb147864053c4417fd0df23e905e11891cb1b7f3
- Snapshot SHA: cac0a65f497dde083fed65f773cfb0055468ce52
- Diff SHA-256: 0e5b8cc551d70f48676bb84cc86f498bf6b60efb12f07d7c08f5852ccfa94fdf
- Plan: .plans/deployment-readiness.md
- Plan SHA-256: 419bf053e7e35d41aacae666be3363f7dc88676493bdfff6f87ef54ca74d6f2b
- Prompt version: 2
- Prompt SHA-256: 6a242431e5899b8661c9da0f3da6906ab836456f8501b73cee2beca5c76145a4
- Launcher SHA-256: 6215b5d5ccac7437676a78968d91086e30d0eb2fc3d23fde80d79e066892377e

## Reviewers

- Codex: model gpt-5.6-sol; harness codex-cli 0.147.0
- Claude: model claude-opus-5; harness 2.1.224 (Claude Code)
- GLM: model accounts/fireworks/models/glm-5p2; harness 2.1.224 (Claude Code) (Claude Code via Fireworks)

## Git status at capture

~~~text
 M .env.example
 M .plans/deployment-readiness.md
 M README.md
 M docs/behavior.md
 M eval/STATUS.md
 M eval/brevity_report.py
 M eval/experiments.md
 M pyproject.toml
 M railway.toml
 M src/opinions_agent/agent.py
 M src/opinions_agent/app.py
 M src/opinions_agent/cli.py
 M src/opinions_agent/config.py
 M src/opinions_agent/corpus.py
 M src/opinions_agent/evals/runner.py
 M src/opinions_agent/models.py
 M src/opinions_agent/prompts.py
 M src/opinions_agent/repo_checkout.py
 M src/opinions_agent/tools/git_ops.py
 M src/opinions_agent/workflow.py
 M tests/test_corpus.py
 M tests/test_e2e.py
 M tests/test_validation.py
 M tests/test_workflow.py
 M uv.lock
?? alembic/versions/0002_deployment_cycles.py
?? railway.cron.toml
?? src/opinions_agent/cycles.py
?? src/opinions_agent/git_askpass.py
?? src/opinions_agent/recovery.py
?? src/opinions_agent/worker.py
?? tests/test_cycles.py
?? tests/test_deployment.py
~~~

## Changed files in frozen diff

~~~text
M	.env.example
M	.plans/deployment-readiness.md
M	README.md
A	alembic/versions/0002_deployment_cycles.py
M	docs/behavior.md
M	eval/STATUS.md
M	eval/brevity_report.py
M	eval/experiments.md
M	pyproject.toml
A	railway.cron.toml
M	railway.toml
M	src/opinions_agent/agent.py
M	src/opinions_agent/app.py
M	src/opinions_agent/cli.py
M	src/opinions_agent/config.py
M	src/opinions_agent/corpus.py
A	src/opinions_agent/cycles.py
M	src/opinions_agent/evals/runner.py
A	src/opinions_agent/git_askpass.py
M	src/opinions_agent/models.py
M	src/opinions_agent/prompts.py
A	src/opinions_agent/recovery.py
M	src/opinions_agent/repo_checkout.py
M	src/opinions_agent/tools/git_ops.py
A	src/opinions_agent/worker.py
M	src/opinions_agent/workflow.py
M	tests/test_corpus.py
A	tests/test_cycles.py
A	tests/test_deployment.py
M	tests/test_e2e.py
M	tests/test_validation.py
M	tests/test_workflow.py
M	uv.lock
~~~

## Untracked files at capture

~~~text
alembic/versions/0002_deployment_cycles.py
railway.cron.toml
src/opinions_agent/cycles.py
src/opinions_agent/git_askpass.py
src/opinions_agent/recovery.py
src/opinions_agent/worker.py
tests/test_cycles.py
tests/test_deployment.py
~~~
