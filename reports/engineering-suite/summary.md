# 本地工程评测

{
  "status": "engineering_only",
  "tasks": 12,
  "independent_photographic_sources": 0,
  "synthetic_source_groups": 12,
  "runs": {
    "A": {
      "COMPLETED": 10,
      "PARTIAL": 2,
      "WAITING_USER": 0,
      "FAILED": 0,
      "blocked": 0
    },
    "B": {
      "COMPLETED": 10,
      "PARTIAL": 2,
      "WAITING_USER": 0,
      "FAILED": 0,
      "blocked": 0
    },
    "C": {
      "COMPLETED": 10,
      "PARTIAL": 2,
      "WAITING_USER": 0,
      "FAILED": 0,
      "blocked": 0
    },
    "D": {
      "COMPLETED": 0,
      "PARTIAL": 0,
      "WAITING_USER": 0,
      "FAILED": 0,
      "blocked": 12
    }
  },
  "real_agent_experiment": "not_run",
  "research_gain": "not_established",
  "cpu_seconds": "not_measured",
  "peak_rss": "not_measured; no parent-only RSS claim",
  "limitations": [
    "Controlled procedural images only.",
    "No independent validation/test partition collected.",
    "No statistical significance or natural leakage claim.",
    "D/E not run, so no Agent-vs-rule comparison."
  ]
}

逐任务原始分母、失败与成本见 per_run.jsonl。A=base 一次；B=all 一次；C=规则；D 因未授权不运行。
