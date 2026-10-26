# ADR-011: Review conclusions follow the active imported decision

Clause-level auditing reproduced three prior gaps in `reports/review-consistency-gap-v1`: human coverage remained `not_run` after a review; rejecting a previously confirmed witness retained the old affirmative claim; and a subsequent goal revision lost its review input file reference. The fixture uses real Core outputs and explicitly scripted reviews, not a human or model experiment.

New revisions derive record/pair coverage from current review rows. Pending, unsure or conflicting decisions on duplicate witnesses remain unresolved. Requested unresolved reviews keep the task in WAITING_USER; an already-charged request is not charged again when its first response is imported.

The latest imported decision for the same bound Core witness supersedes that witness's earlier human evidence in the new revision. Claims supported by superseded human evidence are removed from the active report; previous reports remain immutable. This is revision state, not a claim of reviewer consensus or physical truth. Core candidate kinds never change.

Each new revision materializes review payloads in `review-inputs/<payload-digest>.json`. A copy must match the evidence's original `params_digest`; validation binds every payload hash, its facts and the derived coverage. Legacy revisions may lack the old input file but retain the complete evidence-bound payload. Reinterpretation preserves that payload and removes stale confirmations inconsistent with the current review row. New verification checks these bindings; historical records are not rewritten.
