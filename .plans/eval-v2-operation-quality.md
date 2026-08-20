# Eval v2: operation-gated opinion quality

## Decision

Keep the current eval and `opinion_quality` scorer unchanged as v1. Add an explicit v2 command that runs the same weekly proposal cases and reports the same scores plus deterministic operation correctness and operation-gated opinion quality.

For each target:

- conceptual quality uses the existing match and coverage judge;
- an add target requires an `add` proposal;
- an update target requires a `revise` or `update` proposal whose stated current opinion matches the target's canonical base opinion;
- `opinion_quality_v2` passes only when conceptual quality and operation correctness both pass.

The first v2 keeps the existing one-to-one matcher. Matching changes would confound the first operation baseline.

## Durable contracts

- V1 commands, targets, scorers, scoring version, and Braintrust dataset remain available and unchanged.
- V2 uses a separate Braintrust dataset and scoring version.
- V2 stores per-target operation reasons in score metadata and reports `operation_accuracy` separately from `opinion_quality_v2`.
- Existing Braintrust outputs can be rescored through v2 without rerunning the opinion agent.
- The v2 target payload derives an update target's canonical base text from the same canonical seed builder used by the weekly eval.

## Implementation

1. Parse the optional current-opinion block from revision proposal messages. Accept the current `<b>Current</b>` and `<b>Current Opinion</b>` labels.
2. Add v2 scorers that share the existing match and conceptual judge result.
3. Add `opinions-agent eval v2 run` and `opinions-agent eval v2 rescore` commands.
4. Keep v1 runner defaults and output unchanged.
5. Add focused parser, operation, v2-quality, summary, and runner tests.
6. Update the behavior contract and README.

## Experiment round

Use the six clean `explicit-critic-docscope` full runs as the stored-output baseline. Then run three full nine-week prompt experiments with `openai:gpt-5.6-sol` through cproxy on port 8113.

For each round:

1. Change only the smallest prompt or rule block needed for one routing hypothesis.
2. Run leakage checks and local verification.
3. Run all nine weeks under eval v2.
4. Inspect conceptual quality, operation accuracy, v2 quality, and per-target failures.
5. Base the next round on the best result and the observed failure mechanism.

Do not improve v2 quality by weakening conceptual coverage or changing targets.
