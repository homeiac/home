-- Run from the repository root with DuckDB.
-- Project the SAME recorded remaining-work snapshot in both windows.
-- Checkpoints are diagnostic production progress, not verified publication.
WITH evidence AS (
    SELECT c.trial, c.trial_panel_id, c.completion_objective AS objective,
           c.cpu_timing, c.completion_assessment
    FROM read_json('scripts/knowledge-index/library-server-timing.json'),
         UNNEST(cpu_backfill_comparisons) AS rows(c)
), rates AS (
    SELECT *,
       objective.baseline.unique_production_completed * 60e9 /
          (objective.baseline.end_ns - objective.baseline.start_ns) AS before_per_min,
       objective.trial.unique_production_completed * 60e9 /
          (objective.trial.end_ns - objective.trial.start_ns) AS during_per_min
    FROM evidence
)
SELECT trial, objective.remaining.amount AS remaining_face_jobs,
       round(before_per_min, 3) AS before_faces_per_min,
       round(during_per_min, 3) AS during_faces_per_min,
       round(100 * (during_per_min / before_per_min - 1), 2) AS throughput_change_pct,
       round(objective.remaining.amount / before_per_min / 60, 3) AS before_remaining_hours,
       round(objective.remaining.amount / during_per_min / 60, 3) AS during_remaining_hours,
       round(objective.remaining.amount / before_per_min - objective.remaining.amount / during_per_min, 2) AS projected_minutes_saved,
       round(objective.baseline.backend_unique_production_completed['mac-metal'] * 60e9 /
           (objective.baseline.end_ns - objective.baseline.start_ns), 3) AS mac_gpu_before_faces_per_min,
       round(objective.trial.backend_unique_production_completed['mac-metal'] * 60e9 /
           (objective.trial.end_ns - objective.trial.start_ns), 3) AS mac_gpu_during_faces_per_min,
       round(objective.baseline.backend_unique_production_completed['rtx3070'] * 60e9 /
           (objective.baseline.end_ns - objective.baseline.start_ns), 3) AS rtx_gpu_before_faces_per_min,
       round(objective.trial.backend_unique_production_completed['rtx3070'] * 60e9 /
           (objective.trial.end_ns - objective.trial.start_ns), 3) AS rtx_gpu_during_faces_per_min,
       cpu_timing.measured_slow_stage,
       round(cpu_timing.prompt_share_pct, 1) AS cpu_prompt_time_pct,
       cpu_timing.resource_cause,
       objective.trial.verified_production_completed,
       objective.trial.readback_ref,
       completion_assessment.decision AS completion_gate,
       completion_assessment.reasons AS completion_gate_reasons
FROM rates ORDER BY trial_panel_id;
