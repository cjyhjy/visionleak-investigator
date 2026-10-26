# Frozen catalog evaluation

`eval-run` executes the selected partition of a frozen, registered catalog. A uses one real Core `base` scan, B one real `all` scan, and C the production rules workflow. Every condition receives the same confirmed TaskSpec, source registry, total limits, Core/runtime and input identity. D is explicitly blocked because no authorized live provider adapter exists; no scripted callback is substituted. E remains second phase.

C now uses `rules-v2`: base precedes charged context/metadata interpretation, then registered Markdown/TXT excerpts and the request select a fixed supplemental profile under remaining coverage/budget gates. Selection records and the policy snapshot are saved with each run. Literal clues and limited local negation are not semantic understanding; missed synonyms or distant negation remain limitations. No profile is selected from evaluator truth, image filenames, CSV entity values or candidate counts. A/B and explicit profile requests do not inherit this routing. See [ADR-012](adr/012-rules-context-routing.md). New v2 results require a new freeze and must not be pooled as unchanged-policy repetitions of v1.

## Reproduce the synthetic acceptance

```sh
.venv/bin/python scripts/catalog_smoke.py --tasks 12 --out runs/catalog-acceptance
```

This creates 12 new procedural tasks (10 development, one validation, one test), freezes them and executes 36 real A/B/C tasks. The partition labels exercise the executor and separation gates; they do **not** establish independent natural-image validation/test results. The final test task has a comparison budget of one; another task contains a deliberately invalid image. All PARTIAL results stay in the score denominators. Source seed, truth, task inputs, process invocations, Core evidence, score receipts and expected repeat rejection are preserved.

## Run a registered catalog

Use `eval-validate` and `eval-freeze` as described in the README. For execution the frozen protocol must use `metric_definition: "catalog-pairs-v1"`. Earlier freezes with descriptive metric strings remain configuration-gate artifacts and cannot silently become experiments. The implementation digest is frozen, so code changes require a new, explicitly identified freeze.

```sh
vli eval-freeze --catalog /absolute/suite/catalog.json --root /absolute/suite \
  --protocol /absolute/suite/protocol.json --out /absolute/evaluation/frozen.json
vli eval-run --catalog /absolute/suite/catalog.json --root /absolute/suite \
  --protocol /absolute/suite/protocol.json --frozen /absolute/evaluation/frozen.json \
  --partition development --out /absolute/evaluation/development-001
```

Use a new output directory, disjoint from the entire suite, freeze and registered documents. Tasks must have a host-confirmed goal and local-only privacy settings. Interaction experiments with unanswered goals use a separate protocol; this command does not infer answers or measure human time savings.

All pre-registered A/B/C repetitions execute in fresh subprocesses, in fixed task/repetition/A/B/C order. OS caches are not flushed. Runs do not share fingerprints or learning state. Model declarations in a protocol do not authorize any call. Every D repetition is present as `blocked` with no score.

## Truth and metrics

Truth is evaluator-only JSON matching `contracts/evaluation-truth.schema.json`. It binds `task_id`, confirmed `goal`, and the complete dataset manifest digest. The catalog already freezes the truth file hash. `basis` records whether labels come from controlled generation or source annotations; that declaration is not an independent provenance audit.

The three axes are:

- `exact`: byte or normalized-pixel identity. Labels must be exhaustive because this set defines which pairs to exclude from approximate scoring.
- `related_excluding_exact`: same-source transformed pairs after excluding exact truth pairs. Predictions are validated perceptual/local candidate claims, not confirmed identity claims.
- `entity_goal_conflict`: cross-split pairs violating the confirmed new-entity goal. Predictions come only from validated metadata conflict claims. Other supported goals cannot have positive entity-overlap-conflict labels.

Each axis has `coverage`, `positive_pairs`, and `negative_pairs`. Each pair contains two registered relative image paths in different image splits; aliases are normalized using the actual input manifest. Duplicate, contradictory, unknown, within-split and exact-overlapping approximate labels are rejected.

- `exhaustive` is an explicit closed-world annotation: all eligible pairs outside `positive_pairs` are negatives, and `negative_pairs` must be empty.
- `partial` labels only the explicit positive/negative pairs. Unlisted predicted pairs remain unknown. Full precision, recall and F1 are null; the labeled subset and its denominators are separately visible. This mode is available for approximate and entity labels, not exact labels.

No predictions means precision N/A; no positive labels means recall N/A. Candidate burden counts the entire distinct accepted candidate set before exact-pair exclusion, alongside pending review pairs, known-invalid approximate candidates and unknown candidates. The scorer consumes validated published claims, never unverified raw exact evidence.

A failed worker has zero **usable published predictions**, not zero cost or zero risk. If the separate scorer can validate its truth, every positive remains an FN in the end-to-end denominator. If scoring itself fails, the condition aggregate is unavailable; scheduled known-positive counts remain visible. PARTIAL audits are scored against the whole truth, including unprocessed images. D has no predictions or score inferred from being blocked.

Pooled counts include repetitions and are descriptive. Per-repetition results and equal-task macro recall are also saved, with defined/undefined task counts. Independent source-component counts come from the catalog grouping gate. Pairs, repeated runs and task variants sharing sources are not independent samples; no confidence interval or significance claim is produced.

## Evidence and failure behavior

The audit worker receives only task path, registry path, new output and A/B/C condition. A different scoring subprocess receives truth and checks report/checkpoint/evidence identities, Core reports and deterministic claim support. No truth path or label is given to an audit tool or planner. This is an application boundary, not an OS filesystem sandbox against local administrators or modified code.

The runner checks the complete frozen catalog and runtime before/after every worker and scoring step. An input, truth, protocol, code, lock or environment change stops execution and suppresses quality aggregation. Already attempted work and its costs remain; unstarted tasks get `not_run`. Original logs, intermediate files and failures are retained.

Outputs include `evaluation_manifest.json` with the complete schedule, `frozen_config.json`, `source_split_manifest.json`, `per_run.jsonl`, `failures.jsonl`, `gate_checks.jsonl`, `comparison_checks.jsonl`, `metrics.json`, `costs.json`, `summary.md`, plus `runs/`, `processes/`, `scorers/` and `scores/`.

Each task retains whole-worker CPU/wall time and sampled process-tree RSS including Python and Core, with existing missing/partial-sample limitations. Scorer resources are separate. Runner CPU/wall accounting includes orchestration and waited children through pre-summary; whole-pipeline peak RSS is not measured. A missing measurement stays null. Resource differences are observations for this run, not hardware-independent performance claims.

## Test attempts and replay

The first test execution creates an exclusive claim next to the freeze (`frozen.json.executions/test.json`). A second unlabelled test run with that freeze is rejected. A deliberate replay must reference an existing attempt:

```sh
vli eval-run --catalog /absolute/suite/catalog.json --root /absolute/suite \
  --protocol /absolute/suite/protocol.json --frozen /absolute/evaluation/frozen.json \
  --partition test --out /absolute/evaluation/test-replay \
  --replay-of /absolute/evaluation/test-first
```

Replays are labelled and cannot be presented as new independent tests. The claim is a local guard; copying or editing a freeze is not cryptographically prevented. A process killed externally may leave a `running` schedule with partial artifacts: there is no automatic resumption or silent overwrite. Preserve that attempt and use a labelled replay to repeat it. Development/validation attempts also retain separate output directories.

Exit codes: 0 means the registered deterministic schedule completed (it may contain PARTIAL audits and blocked D); 2 means the schedule completed with worker/scorer failures; 1 means rejection or preflight failure. Inspect the per-run states rather than treating exit 0 as a fully complete scientific evaluation.


Interaction missingness uses a separate frozen C/D protocol and `eval-interaction`; it is not included in these detection metrics. See [INTERACTION_EVALUATION.md](INTERACTION_EVALUATION.md) for fixed answer permissions, independent scoring, failures and resource accounting.
