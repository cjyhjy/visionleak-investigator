# Interaction evaluation

{
  "status": "completed",
  "rejection": null,
  "metric_definition": "interaction-v1",
  "quality": {
    "C": {
      "status": "scored",
      "scheduled_runs": 1,
      "scored_runs": 1,
      "necessary_questions": 2,
      "necessary_questions_asked": 2,
      "questions_asked": 2,
      "excessive_questions": 0,
      "unanswerable_questions": 0,
      "answers_delivered": 2,
      "failed_runs_in_denominator": 0,
      "goal_correct_runs": 1,
      "goal_accuracy": 1.0,
      "field_evaluable_runs": 1,
      "field_accuracy": 1.0,
      "risk": {
        "tp": 8,
        "fp": 0,
        "fn": 0,
        "truth_denominator": 8,
        "predicted_pairs": 8,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0
      },
      "unsupported_confirmed_claims": 0,
      "human_time_saved_seconds": null,
      "interpretation": "Descriptive repeated-run counts, not independent human/Agent gains"
    },
    "D": {
      "status": "unavailable",
      "scheduled_runs": 1,
      "scored_runs": 0,
      "reason": "All scheduled scores required; blocked/missing runs are not successes"
    }
  },
  "scheduled_runs": 2,
  "declared_independent_components": 1,
  "model_calls": 0,
  "real_agent_experiment": "not_run",
  "human_participants": 0,
  "human_time_saved_seconds": null,
  "wall_seconds": 3.544050378999998,
  "broker_cpu_seconds": 1.663765,
  "pipeline_peak_rss_bytes": null,
  "limitations": [
    "Separate interaction benchmark; not combined with detection precision/recall.",
    "Scripted answers are not model decisions or measured human labor.",
    "Failed/unresolved cases remain in denominators; missing scores suppress aggregates.",
    "Repeated tasks are not independent sampling units; no significance or research-gain claim."
  ]
}
