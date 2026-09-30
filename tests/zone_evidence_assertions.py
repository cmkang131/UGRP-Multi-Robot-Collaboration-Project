"""Always run evidence assertions; add real event readback when installed.

The offline CI jobs do not install TensorBoard. No fake writer or skipped
counterexample substitutes for semantic checks. The export CI job separately
requires TensorBoard and runs the same adversarial publication cases.
"""
from importlib.util import find_spec
import json

from scripts import zone_study_evidence_cohort as cohort


def checked_cohort(plan_path, pin, sources, output):
    plan = json.loads(plan_path.read_text())
    summary = cohort.collect(plan, pin, sources)
    cohort.verify_summary(summary, plan, pin, sources)
    if find_spec('tensorboard') is not None:
        from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
        published = cohort.publish(plan_path, pin, sources, output, allow_synthetic=True)
        assert published == summary
        event = EventAccumulator(str(output)).Reload()
        assert abs(event.Scalars('cohort/success_rate')[0].value - summary['success_rate']) < 1e-7
        assert event.Scalars('cohort/trials')[0].value == summary['admitted_trials']
    return summary
