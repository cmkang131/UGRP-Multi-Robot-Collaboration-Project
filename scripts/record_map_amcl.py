"""Default-off GCP own-camera drive recording using the existing E2E owners.

No model, grasp, top-camera input, restored checkpoint or online AMCL candidate.
Physics imports happen only after Linux/GCP/approval/source admission.
"""
import argparse
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import time
from statistics import median

from harness.e2e_result_writer import Finalizer, write
from harness.map_recording_audit import InputAudit, Metrics
from harness.map_recording_speed import using as rectangle_batch
from harness.map_recording_speed import PROFILES, configure, controller_profile
from scripts.extract_e2e_pose_features import sha256

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / 'experiments/2026-10-15-map-amcl/recording-spec.json'


def load_spec(path=SPEC):
    spec = json.loads(Path(path).read_text())
    if (spec['schema'] != 'map-amcl-recording-spec/1' or
            spec['host'] != 'gcp1' or spec['project'] != 'ugrp-act-train-1014' or
            spec['robots'] != ['r1', 'r2'] or spec['period_s'] != .1 or
            spec['command_period_s'] != .2 or spec['sim_cap_s'] != 60. or
            spec['frames_per_robot'] != 601 or len(set(spec['seeds'])) != 40 or
            spec['expected_intervals'] != 80):
        raise ValueError('REGISTERED_40_RUN_10HZ_SPEC_REQUIRED')
    if spec['first_run_speed_gate'] != dict(at_sim_s=30., warn_wall_per_sim=3.5,
            max_wall_per_sim=6., statistic='median', measurement='first30_of_actual_run'):
        raise ValueError('CURRENT_SPEED_POLICY_REQUIRED')
    if type(spec['performance']['rectangle_batch']) is not bool:
        raise ValueError('BOOLEAN_RECTANGLE_BATCH_REQUIRED')
    if spec['performance'].get('controller_profile', 'off') not in PROFILES:
        raise ValueError('UNKNOWN_RECORDING_CONTROLLER_PROFILE')
    for name, digest in spec['source_inputs'].items():
        if sha256(ROOT/name) != digest:
            raise ValueError('INPUT_HASH_MISMATCH:'+name)
    return spec


def speed_summary(receipts):
    """One actual run initially; then all first30 receipts in a submitted wave.

    Missing/unfinished measurements fail closed. Individual slow members of a
    completed wave are reported, not used in place of its median.
    """
    values = [r.get('wall_per_sim') if r else None for r in receipts]
    complete = bool(values) and all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                                   for v in values)
    value = median(values) if complete else None
    blocked = not complete or value > 6.
    return dict(measurement_N=len(values), complete=complete, median_wall_per_sim=value,
                warning=complete and value > 3.5, blocked=blocked,
                reason='INCOMPLETE_MEASUREMENT' if not complete else
                       'MEDIAN_ABOVE_6' if blocked else None)


@contextmanager
def recording_slot(root, limit, metrics):
    """Nonblocking slots under one queue's recording root; scheduler owns waits."""
    import fcntl
    if type(limit) is not int or limit < 1:
        raise ValueError('QUEUE_PARALLEL_LIMIT_REQUIRED')
    folder = root/'.map-amcl-record-slots'
    folder.mkdir(parents=True, exist_ok=True)
    selected = None
    with metrics.measure('flock_acquire'):
        for index in range(limit):
            candidate = (folder/f'{index}.lock').open('a')
            try:
                fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                candidate.close()
            else:
                selected = candidate
                break
    if selected is None:
        raise BlockingIOError('QUEUE_PARALLEL_LIMIT_REACHED')
    try:
        yield index
    finally:
        with metrics.measure('flock_release'):
            fcntl.flock(selected, fcntl.LOCK_UN)
            selected.close()


def run_name(seed):
    return f'map-amcl-record-s{seed}'


def admission(spec, seed, source_sha, approval_path, output):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('GCP_LINUX_ONLY_NO_MAC_PHYSICS')
    if (os.environ.get('UGRP_EXECUTION_HOST') != spec['host'] or
            os.environ.get('MUJOCO_GL') != 'osmesa'):
        raise ValueError('GCP1_OSMESA_REQUIRED')
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()
    if actual != source_sha or dirty:
        raise ValueError('CLEAN_PINNED_SOURCE_REQUIRED')
    q = json.loads(approval_path.read_text())
    a = q['coordinator_approval']
    if not (q['project'] == spec['project'] and q['host'] == spec['host'] and
            q['source_sha'] == source_sha and a['approved'] is True and
            a['source_sha'] == source_sha and q['execution_enabled'] is True and
            q['physical_execution_authorized'] is True and q['rendering_authorized'] is True and
            q['recording_spec_sha256'] == sha256(SPEC) and
            q['machine_type'] == spec['machine_type'] and
            a.get('credit_stop_verified') is True and a.get('seeds_unused_verified') is True and
            a.get('storage_budget_verified') is True and a.get('machine_verified') is True):
        raise ValueError('EXACT_SOURCE_COORDINATOR_APPROVAL_REQUIRED')
    if seed not in spec['seeds'] or output.exists():
        raise ValueError('REGISTERED_NEW_RUN_REQUIRED')
    if output.parent.resolve() != Path(q['raw_root']).resolve() or output.name != run_name(seed):
        raise ValueError('QUEUE_RECORDING_ROOT_REQUIRED')
    limit = q.get('limits', {}).get('max_parallel_jobs')
    if type(limit) is not int or limit < 1:
        raise ValueError('QUEUE_PARALLEL_LIMIT_REQUIRED')
    amcl4 = q.get('amcl4')
    if amcl4 is not None and amcl4.get('offline_speed_and_accuracy_verified') is not True:
        raise ValueError('AMCL4_OFFLINE_RECORDING_SPEED_AND_ACCURACY_REQUIRED')
    # First actual recording measures speed; 3.5 is warning only. Completion,
    # integrity and the first-run median <=6 are required before the rest.
    if seed != spec['seeds'][0]:
        first = json.loads((output.parent/run_name(spec['seeds'][0])/'raw/result.json').read_text())
        if (first['source_sha'] != source_sha or first['status'] != 'RECORDED' or
                speed_summary([first.get('first30')])['blocked'] or
                not first.get('finalization_complete') or first.get('finalization_errors') or
                first.get('frames_per_robot') != spec['frames_per_robot']):
            raise ValueError('FIRST_RECORDING_SPEED_AND_INTEGRITY_GATE_REQUIRED')
        if amcl4 is not None:
            # A source-bound coordinator review of the actual first recording
            # is a separate gate. A speed pass must not auto-authorize the rest.
            review = amcl4.get('first_recording_accuracy_review', {})
            first_raw = output.parent/run_name(spec['seeds'][0])/'raw'
            if (amcl4.get('remaining_recordings_authorized') is not True or
                    review.get('passed') is not True or review.get('source_sha') != source_sha or
                    review.get('seed') != spec['seeds'][0] or
                    review.get('result_sha256') != sha256(first_raw/'result.json') or
                    review.get('artifacts_sha256') != sha256(first_raw/'artifacts.sha256.json')):
                raise ValueError('AMCL4_FIRST_RECORDING_ACCURACY_REVIEW_REQUIRED')
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < spec['min_free_bytes'] + spec['per_run_disk_bytes']:
        raise ValueError('DISK_BUDGET_REQUIRED')
    return limit


def bundle(spec, seed, source_sha):
    # Same calibrated drive/camera/contact configuration as the E2E workflow.
    b = json.loads((ROOT/'configs/e2e_s3_test_runtime_v1.json').read_text())
    b.update(schema='ugrp.map_amcl_record.v2', execution_bundle_id='map-amcl-record-v2',
             source_sha=source_sha, seed=seed, host=spec['host'], project=spec['project'],
             scenario_id=spec['scenario_id'], map_id=spec['map_id'], weld=False,
             case='pair', check='mapping-recording', condition='no_comm',
             case_cap_s=spec['sim_cap_s'], reset_cap_s=spec['reset_cap_s'],
             research_result=False, physical_hardware=False, model_calls=0,
             e2e_options=dict(pulse_budget='off', speed3='off'), recording=spec['recording'],
             recording_performance=spec['performance'])
    return b


def make_robots(spec, seed):
    from harness.e2e_live_mapping import Robot
    from harness.e2e_stall_odometry import Options as StallOptions
    from harness.s4_event_policy import Options
    cov = json.loads((ROOT/'configs/e2e_nees_egomap70_dev_v1.json').read_text())
    e = spec['estimator']
    return {rid: configure(Robot(rid, 2*seed+i, cov, Options(), **spec['navigation'],
                stall_options=StallOptions(**{k: e[k] for k in
                    ('stall_odometry', 'stall_recovery', 'stall_noise')}),
                vo_floor_mask=e['vo_floor_mask'], vo_rotation_policy=e['vo_rotation_policy']),
                spec['performance'].get('controller_profile', 'off'))
            for i, rid in enumerate(spec['robots'])}


def record_loop(backend, robots, spec, out, *, clock=time.monotonic, metrics=None,
                audit=None, first_run=True):
    """Injectable existing backend/actors for offline cadence/field-boundary tests."""
    from harness.active_camera import SEARCH
    from scripts.run_e2e_ownmap_live import ownmap_record
    from harness.e2e_record_scalars import normalize
    from sim.lazy_camera import capture_robot_frames
    metrics, audit = metrics or Metrics(), audit or InputAudit()
    origin = backend.now
    backend.set_deadline(origin+spec['sim_cap_s'])
    for rid, robot in robots.items():
        for sid, pwm in SEARCH.items():
            action = dict(kind='look', pan_pulse=pwm) if sid == 6 else dict(kind='arm', servo_id=sid, pulse=pwm)
            backend.issue(rid, action)
            robot.commanded(action, 0.)
    started = clock()
    receipt = dict(origin_s=origin, frames_per_robot=0, first30=None)
    for tick in range(spec['frames_per_robot']):
        now = round(tick*spec['period_s'], 8)
        if abs(backend.now-origin-now) > 1e-6:
            raise ValueError('CAPTURE_CLOCK_MISMATCH')
        if clock()-started > spec['wall_cap_s']:
            raise TimeoutError('RECORD_WALL_CAP')
        if (out.parent/'SUPERVISOR_STOP.json').exists() or (out/'SUPERVISOR_STOP.json').exists():
            raise InterruptedError('SUPERVISOR_STOP')
        # This existing writer retains exact encoded bytes and frame ledgers.
        # Only the two participant cameras are offered; no top camera exists
        # in this input surface. The third robot remains at its standard reset.
        with metrics.measure('capture_batch'):
            frames = capture_robot_frames(backend, tuple(robots))
        for rid, robot in robots.items():
            with metrics.measure('capture_materialize'):
                obs, rgb = frames[rid]
            with metrics.measure('controller_'+rid), rectangle_batch(spec['performance']['rectangle_batch']), \
                    controller_profile(spec['performance'].get('controller_profile', 'off')):
                trace = audit.receive(robot, obs, rgb, now)
            with metrics.measure('ownmap_serialize'):
                row = normalize(ownmap_record(robot, obs, trace, now))
            backend._append(f'robots/{rid}/ownmap.jsonl', row)
        # Write-only referee; never read by either controller or estimator.
        backend.eval_sample()
        receipt['frames_per_robot'] = tick+1
        if tick % 10 == 0:
            backend.flush()
            with metrics.measure('disk_scan'):
                used = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
            if used > spec['per_run_disk_bytes'] or shutil.disk_usage(out).free < spec['min_free_bytes']:
                raise OSError('DISK_BUDGET_EXCEEDED')
            with metrics.measure('progress_write_fsync'):
                write(out/'progress.json', dict(sim_s=now, frames_per_robot=tick+1, bytes=used,
                    timing=metrics.snapshot(), input_audit=audit.snapshot()))
        if tick == 300:
            ratio = (clock()-started)/now
            speed = speed_summary([dict(wall_per_sim=ratio)])
            receipt['first30'] = dict(wall_per_sim=ratio,
                frames_per_robot=tick+1, observation_period_s=spec['period_s'],
                issued_translation_commands={rid: robot.translation_commands for rid, robot in robots.items()},
                model_calls=0, top_camera_input=False,
                warning=speed['warning'], passed=not speed['blocked'],
                speed_policy=speed, blocking_scope='singleton_first_run' if first_run else 'wave_median_external',
                timing=metrics.snapshot(), input_audit=audit.snapshot())
            write(out/'first30.json', receipt['first30'])
            if first_run and speed['blocked']:
                raise TimeoutError('10HZ_SPEED_GATE_FAILED')
        if tick == spec['frames_per_robot']-1:
            break
        # Preserve the existing 5 Hz command cadence; every 10 Hz frame is
        # consumed by the unchanged fused odometry, also while stopped.
        if tick % 2 == 0:
            for rid, robot in robots.items():
                backend.issue(rid, robot.nav_command)
                robot.commanded(robot.nav_command, now)
        backend.advance_to(round(origin+(tick+1)*spec['period_s'], 8))
    return receipt


def record(spec, seed, source_sha, output, *, metrics=None, slot=None, parallel_limit=None):
    from sim.e2e_ownmap_live import PhysicsBackend
    out = output/'raw'
    out.mkdir(parents=True, exist_ok=False)
    b = bundle(spec, seed, source_sha)
    metrics, audit = metrics or Metrics(), InputAudit()
    write(out/'bundle.json', b)
    write(out/'RUN_META.json', dict(schema='ugrp.run_meta.v1', **{'class': 'dev'}, pr=507,
          branch='claude/map-amcl', sha=source_sha, batch='map-amcl-record-v2'))
    result = dict(schema='map-amcl-recording/1', status='HOST_ERROR', source_sha=source_sha,
        seed=seed, host=spec['host'], machine_type=spec['machine_type'], project=spec['project'],
        spec_sha256=sha256(SPEC), model_calls=0, candidate_in_control=False, top_camera_input=False,
        origin_s=None, frames_per_robot=0, sim_cap_s=spec['sim_cap_s'],
        queue_parallel_limit=parallel_limit, queue_slot=slot)
    finalizer = Finalizer(out, result)
    finalizer.install()
    def deadline(*_):
        raise TimeoutError('RECORD_PROCESS_WALL_CAP')
    previous_alarm = signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, spec['wall_cap_s'])
    backend = None
    started = time.monotonic()
    try:
        robots = make_robots(spec, seed)
        backend = PhysicsBackend(b, out, seed=seed)
        backend.reset(spec['reset_cap_s'])
        metrics.install(backend)
        result['origin_s'] = backend.now
        result.update(record_loop(backend, robots, spec, out, metrics=metrics, audit=audit,
            first_run=seed == spec['seeds'][0]), status='RECORDED')
    except (Exception, KeyboardInterrupt) as error:
        result.update(status='PHYSICAL_STOP' if type(error).__name__ == 'PhysicalStop' else 'HOST_ERROR',
                      error=type(error).__name__+':'+str(error))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.)
        signal.signal(signal.SIGALRM, previous_alarm)
        finalizer.finalizing = True
        if backend is not None:
            result['frames_per_robot'] = backend.frame
            if (out/'first30.json').exists():
                result['first30'] = json.loads((out/'first30.json').read_text())
            result['sim_s'] = backend.now-result['origin_s'] if result['origin_s'] is not None else None
            for rid in spec['robots']:
                finalizer.attempt(rid+'-hold', lambda rid=rid: backend.issue(rid, dict(kind='hold')))
            finalizer.attempt('close', backend.close)
        result['wall_s'] = time.monotonic()-started
        result['input_audit'] = audit.snapshot()
        result['timing'] = metrics.snapshot()
        write(out/'input-audit.json', result['input_audit'])
        write(out/'stage-timing.json', result['timing'])
        finalizer.finish()
        # Original JPEG hashes remain online for observation provenance. Full
        # artifact hashes were already post-run; time them without changing bytes.
        with metrics.measure('postrun_artifact_hash'):
            hashes = {str(p.relative_to(out)): sha256(p)
                for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'artifacts.sha256.json'}
        write(out/'stage-timing.json', metrics.snapshot())
        hashes['stage-timing.json'] = sha256(out/'stage-timing.json')
        write(out/'artifacts.sha256.json', hashes)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--approval', type=Path)
    p.add_argument('--execute', action='store_true')
    a = p.parse_args(argv)
    spec = load_spec()
    if a.seed not in spec['seeds']:
        p.error('seed is outside the reserved cohort')
    if not a.execute:
        print(json.dumps(dict(status='EXECUTION_OFF', seed=a.seed, spec=spec)))
        return 0
    if a.approval is None:
        p.error('--execute requires --approval')
    limit = admission(spec, a.seed, a.expected_source_sha, a.approval, a.output)
    metrics = Metrics()
    with recording_slot(a.output.parent, limit, metrics) as slot:
        result = record(spec, a.seed, a.expected_source_sha, a.output,
                        metrics=metrics, slot=slot, parallel_limit=limit)
    print(json.dumps(result))
    return 0 if result['status'] == 'RECORDED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
