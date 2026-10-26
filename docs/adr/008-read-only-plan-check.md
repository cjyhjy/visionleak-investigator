# ADR-008: Candidate manifest checks preserve the original audit

`plan-check` accepts a strict, complete image mapping bound to a previously verified input manifest. All registered images appear exactly once; image splits are immutable and test images remain included. The same checking function validates generated suggestions. This first interface supports exclusions in a proposed new experiment, not data movement or an alternative Core input format.

Only accepted, recomputed exact evidence and confirmed-goal entity metadata define known conflicts. Candidate relations and human same-source review are not promoted. The original audit coverage accompanies the result: removing known conflicts from a plan does not complete a partial audit or rerun image detection. An independent re-audit requires a separately authorized data view and run.

The checker binds source, original report/manifest, evidence and candidate digests; records local elapsed time and zero model/Core audit calls; and never edits the audit ledger or source files. Optional output is exclusive and outside the audit and registered sources. Hash checks detect ordinary drift, not malicious local administrators or atomic concurrent filesystem changes.

T17 acceptance uses a real Core process and then deliberately truncates its newly generated report before the host reads it. The original output, truncation parameters, hashes and process logs are retained. This is explicit fault injection, not a mock detector, observed production incident, or live Agent experiment. The host must reject the damaged report, charge the entire unknown reservation, retain finalization, and produce PARTIAL without claims.
