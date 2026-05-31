# Project Instructions

## Project Context
- This is a greenfield side project.
- Unless the user explicitly says otherwise, there are no backwards-compatibility requirements.

## Workflow
- Plans live in `.plans/` and should be committed.
- Multi-agent reviews live in `.reviews/` and should be committed when they capture useful decision context.
- Generated HTML artifacts live in `.html/` and should be committed when they capture useful design, planning, or review context.
- Keep `README.md` current with the minimum context needed to run and understand the project.

## Development
- Prefer the simplest implementation that satisfies the current product intent.
- Every implementation step must end with passing verification.
- Write tests for behavior that would be expensive or risky to verify manually.
- Run the relevant tests, typecheck, and lint before declaring work complete.
