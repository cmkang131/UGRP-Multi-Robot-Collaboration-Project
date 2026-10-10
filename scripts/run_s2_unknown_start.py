"""s2v54 full DEV with no start-area prior, unchanged v133 plant and goals."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

from harness import zone_s2_unknown_start_contract as contract
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_unknown_start import Runtime as UnknownStart
from harness.zone_solo_cyan_best_cluster import runtime_class as best_runtime
from harness.zone_solo_cyan_amcl_sensor import runtime_class as sensor_runtime
from harness.zone_solo_cyan_landmarks import runtime_class as landmark_runtime
from harness.zone_solo_cyan_path_heading import runtime_class as heading_runtime
from harness.path_heading_policy import mode_for_bundle
from scripts import run_s2_landmarks_dev as previous
from scripts.run_final_environment_checks import check_source, write


def runtime_factory(b):
    Runtime = landmark_runtime(sensor_runtime(best_runtime(heading_runtime(UnknownStart))))
    omit = ('drive_profile', 'stagnation_watch', 'idle_robot_contacts', 'dev_grasp_policy', 'eval_camera_trace')
    options = {k: v for k, v in b['options'].items() if k not in omit}
    options['heading_mode'] = mode_for_bundle(b)
    keys = ('motion_model', 'pulse_calibration', 'extrinsic_calibration', 'floor_appearance',
            'stiff_camera_table', 'look_ahead_calibration')
    return lambda *a, **kw: Runtime(*a, **kw, **options, **{k: b[k] for k in keys})


def run(b, out):
    record = {}
    def writer(path, value):
        if path.name == 'student_record.json':
            record.update(value)
        if path.name == 'result.json':
            from scripts.evaluate_s2_unknown_start import metrics
            value.update(seed=b['task']['seed'], known_start_information=False)
            try:
                value['unknown_start_evaluation'] = metrics(out, record)
                write(out/'eval_only/unknown_start.json', value['unknown_start_evaluation'])
            except Exception as exc:
                value['unknown_start_evaluation_error'] = str(exc)
        write(path, value)
    return bind(previous.run, c=SimpleNamespace(require_execution=contract.require_execution),
                runtime_factory=runtime_factory, write=writer)(b, out)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--output', type=Path, required=True)
    for key, value in contract.NEW_OPTIONS.items():
        p.add_argument('--'+key.replace('_', '-'), choices=('off', value), default='off')
    a = p.parse_args()
    b = contract.bundle(a.expected_source_sha, a.seed,
        **{k: getattr(a, k) for k in contract.NEW_OPTIONS})
    if not a.execute:
        print(json.dumps(dict(execution_started=False, execution_bundle_id=b['execution_bundle_id'],
            options=b['options'], seed=a.seed)))
        return
    check_source(a.expected_source_sha)
    contract.require_execution(b)
    from scripts import agent_lock
    from harness.zone_pair_highpose_exact_speedups import install
    primary = agent_lock.DEFAULT_ROOT.parent
    expected = primary / f's2-realism-{a.expected_source_sha[:8]}-s{a.seed}-v139-unknown-start'
    if not a.output.is_absolute() or a.output.resolve() != expected.resolve() or a.output.exists():
        raise ValueError('new preregistered primary output required')
    held = agent_lock.acquire(agent_lock.DEFAULT_ROOT, owner='codex', branch='codex/s2-realism',
        purpose=f's2v54 unknown-start full DEV seed {a.seed}', pid=os.getpid(),
        expected_minutes=45, timing_sensitive=True)
    undo = None
    try:
        _, undo = install('v98-exact-v6')
        result = run(b, a.output)
        print(json.dumps({k: result.get(k) for k in ('status', 'failure', 'evaluation', 'wall_per_sim')}), flush=True)
    finally:
        if undo:
            undo()
        released = agent_lock.release(agent_lock.DEFAULT_ROOT, owner='codex')
        write(a.output/'lock.json', dict(acquired=held, released=released,
            status_after=agent_lock.status(agent_lock.DEFAULT_ROOT)))


if __name__ == '__main__':
    main()
