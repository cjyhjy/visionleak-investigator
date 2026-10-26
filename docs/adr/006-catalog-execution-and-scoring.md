# ADR-006: Frozen catalog execution and independent scoring

Status: implemented locally; real model D and independent natural-data experiments remain unrun.

The provenance gates previously froze source groups and file identities but did not execute registered catalogs. The existing engineering driver could only generate its own fixed synthetic inputs. Add `eval-run` around the same real A/B/C worker, with a strict evaluator-only truth contract and a separate scoring subprocess.

The audited task/registry/limits are identical for all conditions. Execution identities and the entire frozen catalog are checked before and after each worker/scorer. A failed worker is preserved with no usable predictions and full annotated-positive denominators. A missing scorer prevents a successful-only aggregate. Input/configuration drift rejects the comparison and marks the remaining schedule not_run; all attempted work and resource receipts remain.

Exhaustive labels explicitly treat unlisted eligible pairs as negative; partial annotations leave unknown predictions unknown and full-population metrics unavailable. Exact labels must be exhaustive to make the approximate denominator well-defined. Risk scoring is specifically confirmed new-entity overlap conflict, not a universal data-leakage score. Only published, deterministic, validated claims are predictions; raw unverified evidence is not silently promoted for higher scores.

First test execution is claimed next to its freeze. Subsequent runs need an explicit replay reference, and are not independent test results. This guards accidental reuse in the ordinary CLI flow, not copying manifests or local-administrator tampering. External termination can leave a running schedule and partial artifacts; automatic experiment resumption is not implemented.

The catalog runner does not unlock model requests, acquire datasets or authorize publication of user data. Its synthetic acceptance has three named benchmark partitions to exercise the execution machinery. Those names do not transform procedural fixtures into independent natural-scene data. Report real D as blocked and keep policy optimization/E deferred.

One integration boundary found during this work: a rules task requesting supplemental profiles with max_core_audit_runs=1 used to fail before its required base scan. The rules planner now performs the allowed base scan and reports omitted supplemental profiles as a PARTIAL coverage gap. Explicit caller-supplied invalid profile lists remain rejected; no budget or evidence guard is weakened.
