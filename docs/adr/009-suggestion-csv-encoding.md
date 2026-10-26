# ADR-009: Suggestions remain read-only in JSON and CSV

`proposal-export` regenerates a suggestion from accepted witnesses after verifying the input and saved audit. It does not trust editable `proposal.json`, apply exclusions, write into registered sources or replace any existing file. JSON retains exact values and the full audit coverage. CSV includes every original image, original/proposed inclusion, split, reason, evidence references and source/report identity.

Every variable text cell uses `text:` followed by a JSON string, then standard CSV quoting/escaping. The fixed visible prefix prevents formula-starting characters from occupying the start of a cell; JSON escaping preserves control characters and Unicode reversibly. This deliberately changes the presentation, so the CSV is not accepted as a training/Core manifest. The JSON export remains the authoritative machine-readable suggestion.

This choice avoids relying solely on quotes or apostrophes, which some spreadsheet save/reopen paths remove. OWASP describes these limitations and the absence of a universal sanitizer across spreadsheet consumers: [CSV Injection](https://community.owasp.org/attacks/CSV_Injection). Tests cover ASCII/full-width formula prefixes, controls, separators, quotes, Unicode and a CSV parse/save cycle. No claim of GUI execution testing in every spreadsheet application is made.
