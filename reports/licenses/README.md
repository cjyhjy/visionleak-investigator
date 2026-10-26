# Installed dependency notice inventory

2026-10-26. Current inventories: `base-dev-v2.json` and `optional-sdk-v2.json`. Actual commands and stdout are indexed in `reports/commands.jsonl` (license-base-v2 / license-sdk-v2). `collect.py` records installed package versions, declared license metadata, project URLs and bundled notice file SHA-256 values without changing or republishing third-party source.

- Base/dev environment: 13 Python distributions including Investigator; SDK environment: 162 including Investigator. Node inventory: Core plus six installed dependencies (7 entries), specific to this macOS arm64 installation.
- The installed openJiuwen 0.1.19.post2 wheel has no structured License field/classifier, but its `.dist-info/LICENSE` begins **Apache License, Version 2.0**. SHA-256: `58d1e17ffe5109a7ae296caafcadfdbe6a7d176f0bc4ab01e12a689b0499d8bd`.
- The installed docx2txt 0.9 wheel likewise lacks structured license metadata; its bundled `licenses/LICENSE.txt` begins **The MIT License (MIT)**. SHA-256: `c89b2a2423d1ecebcdc19d1a9b0c594b1b8f51a11732889110e02d9280d0f81b`.
- Investigator has no assigned project license. This inventory does not choose one on the owner's behalf.
- The installed openJiuwen metadata names `https://gitcode.com/openJiuwen/agent-core.git` as Repository; retain that pinned-package provenance alongside the earlier design references.

The v1 inventory is retained with `collect-v1.py`: its filename prefix filter included a Python module named notice.py. v2 excludes source-code suffixes. Neither version treats a filename alone as a license determination.

Scope: installed dependency metadata and bundled notice files. The native libvips notice bundle is recorded by hash; this is not a complete, individually classified SBOM of every embedded native component. No wheel, npm/Mooncakes package, native dependency bundle or new Investigator license was published by this step.
