# Project Instructions

## Project Context
- This is a greenfield side project.
- Unless the user explicitly says otherwise, there are no backwards-compatibility requirements.

## Workflow
- Plans live in `.plans/` and should be committed.
- Multi-agent reviews live in `.reviews/` and should be committed when they capture useful decision context.
- Generated HTML artifacts live in `.html/` and should be committed when they capture useful design, planning, or review context.
- Keep `README.md` current with the minimum context needed to run and understand the project.

## Behavior Contracts
Update `docs/behavior.md` after the plan review cycle and before implementation for any nontrivial change that affects durable product behavior. Treat it as a scanable product contract, not an implementation checklist. A good bullet usually still matters if the implementation changes.

Document externally meaningful behavior, invariants, ownership boundaries, and durable artifact contracts. Organize by durable workflow boundaries. Define operations by product meaning, not by schema fields. Avoid file inventories, status inventories, API/CLI command lists, standalone deployment/runtime/recovery/rules sections, prompt wording, verification commands, and agent judgment rubrics unless they define ownership, durability, read/write boundaries, recovery, or user-visible behavior.

Do not update `docs/behavior.md` for pure refactors, internal cleanup, renames, file moves, dependency updates, or implementation-only API changes unless they change the product behavior described there. If intended behavior cannot be stated clearly, stop and clarify before implementation.

## Development
- Prefer the simplest implementation that satisfies the current product intent.
- Every implementation step must end with passing verification.
- Write tests for behavior that would be expensive or risky to verify manually.
- Run the relevant tests, typecheck, and lint before declaring work complete.
