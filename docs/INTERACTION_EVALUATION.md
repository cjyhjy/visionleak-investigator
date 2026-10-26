# Independent interaction evaluation

`eval-interaction` evaluates initial goal/field missingness separately from image detection. It executes deterministic condition C using the real Core and saved revisions. D is present for every pre-registered repetition as `blocked`; no callback or replay is counted as a model. A/B belong to the detection benchmark and are not used as weaker interaction comparators.

The catalog and source grouping use the same `eval-validate`, `eval-freeze` and `eval-check` gates. The interaction protocol freezes `conditions: ["C", "D"]` and `metric_definition: "interaction-v1"`; other protocol fields retain their existing meanings. Detection still requires A/B/C/D and `catalog-pairs-v1`. Both runners refuse the other's metric definition.

```sh
.venv/bin/python scripts/interaction_smoke.py --out runs/interaction-acceptance
.venv/bin/vli eval-freeze --catalog catalog.json --root /absolute/suite --protocol interaction-protocol.json --out frozen.json
.venv/bin/vli eval-interaction --catalog catalog.json --root /absolute/suite --protocol interaction-protocol.json --frozen frozen.json --partition development --out runs/interaction-development
```

The smoke command creates twelve new synthetic tasks and freezes them before execution. Its development/validation/test names exercise the pipeline; they do not establish independent natural-data generalization. Known goals, missing goals, unknown field meaning, content-only and same-entity goals, zero/one-question budgets, unavailable answers, missing metadata rows, a malformed image and restricted comparisons all remain in the scheduled results. Source lineage and fixed task contracts determine entity-risk labels, not a model judge.

## Answer permissions and truth isolation

Each catalog `truth_path` uses `contracts/interaction-truth.schema.json`. It binds task/input identity, target goal and entity column, initial necessary questions, the fixed answerable question set, annotation basis and exhaustive positive entity-risk pairs. All other eligible cross-split pairs are negatives for this metric. The source gate keeps these evaluator files outside every registered dataset/document, including exact copies of another task's truth.

The broker reads the frozen answer contract and releases only answers to questions that appear in a verified report. It does not supply unrequested goal/field values. Initial workers receive only TaskSpec/registry/output/C; continuation workers receive the original run and the requested answer payload. Only the separate scorer receives the truth path. C and future D have the same fixed answer permissions; declarations of model settings do not authorize D. This is application data-flow isolation, not protection from an operating-system administrator.

Answers identify a fixed scripted broker, not a human. The transcript binds each observed question list to the saved report digest and each delivered answer to the frozen contract and actual continuation process result. No unsolicited human review is simulated: pending review pairs and actual question/review budget charges are retained. The current rules condition does not actively request candidate reviews, so these results cannot establish reduced human review work.

Before accepting predictions, the separate scorer verifies the real Core identities and follows the saved revision chain to the initial run. The initial TaskSpec and registry must equal the frozen inputs; every revision must retain the input digest, task ID, request, dataset/documents, limits, privacy and original confirmations. Only the goal/field confirmation fields may change. Parent report/manifest digests must match, and C must remain a deterministic run with unchanged source data. Scores retain the expected task/registry digests and accepted final/initial report identities. A valid report from another task is still unusable: it has no accepted predictions, all known positives remain false negatives, and unsupported-claim/cost fields are unknown. The runner marks a rejected score as a failed attempt and preserves the observed process records.

The transcript must cover that exact chain in order, including the initial and final observations. Every question list must match its report, and every delivered answer must match both the frozen contract and the next revision's input file. Foreign, missing or incomplete histories are rejected. `question_history_usable=false` means question/answer observations were withheld; their zero accepted counts do not mean no interaction actually occurred. Known necessary questions remain in the denominator. A failed continuation may retain a verified earlier question history, while its predictions still remain unusable.

## Metrics and denominators

- Goal accuracy includes every scheduled scored C run. A goal must be host-confirmed and match the target; failed or unresolved runs are incorrect.
- Field accuracy is applicable when the target needs entity interpretation and a target field exists. Content-only tasks use null, not an automatic correct score.
- Necessary questions follow initial missingness and the target goal. Necessary questions asked count unique required codes; excessive questions count all asks minus these unique required codes, including repetitions and fields unnecessary for the target. This definition can penalize asking a field together with an unknown goal that later proves to be content-only.
- Unanswerable questions, delivered answers and missed necessary questions are separate counts. Lack of an answer does not count as a successful resolution.
- Entity-risk precision/recall/F1 use the full predeclared cross-split positive population. No predictions gives null precision; no positives gives null recall. Failed attempts have no usable predictions and retain all positives as false negatives.
- Unsupported confirmed claims are zero only after report/claim verification. An unusable report records null. Missing scorer results suppress the condition aggregate; no successful-subset averaging.
- Question/review charges come from the cumulative final ledger. Source images are not rescanned for answers. Each initial/resume process retains its command, exit status, CPU and sampled process-tree RSS; worker CPU is summed and maximum sampled RSS reported. Broker CPU and total wall time are separate pipeline measurements; scoring resources are separate, and whole-pipeline peak RSS is null.

These are descriptive counts of task repetitions, not independent human observations, significance tests or measured efficiency gains. Human participants are zero and human time saved is null. Detection precision/recall is not pooled into these results.

## Attempts, failures and output

The freeze is checked before tasks/observations/scoring and after answers/tasks. Drift rejects the experiment and suppresses quality summaries while retaining attempted processes, reports and measured costs. The first frozen test attempt is exclusive; another attempt requires `--replay-of` pointing to an attempt of that same frozen partition. Replay is labelled and does not become a new independent test. A killed experiment has its existing artifacts and running manifest; automatic experiment continuation is not implemented.

Outputs include `evaluation_manifest.json`, `source_split_manifest.json`, `frozen_config.json`, `per_run.jsonl`, `metrics.json`, `failures.jsonl`, `costs.json`, `summary.md`, gate checks, per-task transcripts, answer payloads, original Core logs, revisions, process resources and separate scoring records. Exit 0 means the deterministic schedule finished and may include PARTIAL, WAITING_USER and blocked D; exit 2 means worker/scorer failures; exit 1 means rejection or preflight failure.

The first local engineering execution is retained in `reports/interaction-evaluation-v1-first`: 12 real C runs, 12 blocked D, 10 confirmed correct goals, 11 question requests, 1 excessive question, 2 missed required questions and 27 entity-risk false-negative pairs. The latter arise in deliberately missing/budget-limited cases. They remain visible and do not represent measured natural-data error rates or a C/D comparison.
