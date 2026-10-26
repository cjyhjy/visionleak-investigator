# ADR-007: Distinguish processing provenance and quarantine interrupted evidence

Status: implemented and locally verified, 2026-10-26.

A revision used to inherit its parent's code_digest, even when a different host version generated the new interpretation. New revision manifests record the current processor code and a stable image_evidence_origin containing the original Investigator code, manifest and Core/runtime locks. Parent manifest and report digests bind the immediate predecessor. Core image audits are not repeated.

Report integrity now verifies the checkpoint-bound manifest and the standalone ledger against the report's ledger. This improves accidental-change detection; it is not a signature or protection from an administrator who can rewrite all records.

Conservative recovery used to retain pre-crash evidence and proposal files in the active output locations while publishing no claims. A later host revision could then consume those retained witnesses. Recovery now moves pre-crash derived artifacts into a unique archive, publishes an empty evidence set and unavailable proposal, and records the archive hashes and actual processing version. Subsequent revisions accept only witnesses belonging to an accepted profile; legacy recovered evidence cannot silently re-enter a proposal.

Recovery and host revisions share one file lock. This serializes duplicate recovery/answer imports; it does not stop an original worker. Operators must confirm that worker has stopped before invoking recovery. Recovery remains conservative close-out, not scan continuation, automatic retry or a model decision.

Acceptance includes real Core runs, explicit controlled final-report removal, actual historical synthetic report reuse across two recorded code versions, and unit metadata-version injection labelled as a fixture. No fixture is presented as a production failure rate or real model experiment.
