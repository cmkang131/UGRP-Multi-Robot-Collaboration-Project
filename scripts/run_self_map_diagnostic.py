"""Prepare by default; GCP-only finite own-RGB self-map physical diagnostic."""
import argparse
from collections import Counter
import hashlib
import json
import math
import platform
import importlib.util
from pathlib import Path
import signal
import shutil
import subprocess
from time import monotonic

import numpy as np
import cv2

from harness.self_map_executor import OPTION, make_executor
from harness.self_map_input_audit import InputAudit
from scripts.offline_self_map import digest, dump, read, rows, score

ROOT = Path(__file__).resolve().parents[1]


def bundle(source, seed, cap_s, *, bootstrap='off', initial_sweep='off', recovery_profile='off',
           revision_gate='off', multiframe_registration='off', render_profile='floor_light_v1', correction_safety='off'):
    from harness.active_camera import SEARCH
    if not math.isfinite(cap_s) or not 1 <= cap_s <= 300 or abs(cap_s*10-round(cap_s*10)) > 1e-8:
        raise ValueError('CAP_MUST_BE_0_1S_GRID_IN_1_TO_300')
    result = dict(schema='ugrp.self_map_diagnostic.v2', execution_bundle_id='selfmap2-frontier-drive-v1',
        source_sha=source, check='selfmap2', case='active-selfmap2',
        map_id='zone_wide_two_doors_final_v3', contact_profile='cargo_noslip_v1',
        task=dict(robot_id='r3', seed=seed, destination='B', pickup_slot='P1-2'),
        spawn=[3.25, .75, math.pi], initial_servo=SEARCH, case_cap_s=cap_s, capture_s=.1,
        controller_inputs=['own_rgb', 'own_issued_commands', 'fixed_camera_calibration'],
        top_camera='not captured; evaluation only if separately recorded',
        supplied_map_to_controller=False, model_calls=0, weld=False,
        options=dict(self_map_executor=OPTION, pose_rebuild='refit_history_v1',
            navigation_support='current_footprint_v1', motion_model='s2_pulse_v122_rotL_v1',
            servo_stiffness='real_v1', wall_texture='off', camera_pose='SEARCH',
            drive_profile='masterpi_drive_friction_v7', camera_profile='camera_v3',
            roller_collision='mesh', idle_robot_contacts='off', min_wheel_cmd='real_v1'),
        recording=dict(own_rgb_hz=10, retain='every captured JPEG and ledger row',
            resolution=[640, 480], online_pixels='decoded saved JPEG, identical replay input'),
        scope='single active robot MuJoCo diagnostic, no E2E/real-hardware success claim')
    if bootstrap != 'off' or initial_sweep != 'off':
        from harness.self_map_integration import Options
        Options(bootstrap=bootstrap)  # validate even in prepare-only mode
        if initial_sweep not in ('off', 'required_360_v1'):
            raise ValueError('UNKNOWN_INITIAL_SWEEP')
        result.update(execution_bundle_id='selfmap3-prior-bootstrap-v1', check='selfmap3', case='active-selfmap3')
        result['options'].update(bootstrap=bootstrap, initial_sweep=initial_sweep)
    from harness.self_map_integration import Options
    Options(recovery_profile=recovery_profile, revision_gate=revision_gate,
            multiframe_registration=multiframe_registration, correction_safety=correction_safety)
    if recovery_profile != 'off':
        from harness.selfmap4_geometry import static_input
        _, sha = static_input()
        result.update(execution_bundle_id='selfmap4_recovery_v1', check='selfmap4', case='active-selfmap4',
                      supplied_map_to_controller=True, authored_static_map_sha256=sha)
        result['options'].update(recovery_profile=recovery_profile)
        result['controller_inputs'].append('authored_static_geometry')
    if render_profile not in ('floor_light_v1', 'floor_light_textured_v1'):
        raise ValueError('UNKNOWN_SELFMAP_RENDER_PROFILE')
    if revision_gate != 'off' or multiframe_registration != 'off' or render_profile != 'floor_light_v1':
        result.update(execution_bundle_id='selfmap5-opt-in-v1', check='selfmap5', case='active-selfmap5',
            pool_with_previous_results=False, scene_version=render_profile,
            dependencies=([dict(pr=511, branch='claude/scene-floor-texture',
                source_sha='6a73c3aab305f250d0ecd9591922b160b9c709ab',
                required='render_profile + natural_scene_texture assets + nearclip API',
                merged_verified=False)] if render_profile == 'floor_light_textured_v1' else []))
        result['options'].update(revision_gate=revision_gate, multiframe_registration=multiframe_registration,
                                 render_profile=render_profile)
    if correction_safety != 'off':
        result.update(execution_bundle_id='selfmap6-opt-in-v1', check='selfmap6', case='active-selfmap6')
        result['options']['correction_safety'] = correction_safety
    return result


def storage_estimate(cap_s):
    frames = round(cap_s*10)+1
    # Existing sparse JPEGs are ~14 KiB. Reserve 128 KiB/frame plus text and
    # transient lossless-compression copies; no unmeasured size guarantee.
    return dict(frames=frames, jpeg_budget_bytes_each=131072,
                per_run_bytes=frames*131072+128*1024**2, measured=False)


def compress_one(path, out):
    """Verify decompressed bytes before removing newly generated large text."""
    target = Path(str(path)+'.zst')
    original = digest(path)
    subprocess.run(['zstd', '-q', '-3', str(path), '-o', str(target)], check=True)
    restored = subprocess.check_output(['zstd', '-dc', str(target)])
    if hashlib.sha256(restored).hexdigest() != original:
        raise ValueError('LOSSLESS_COMPRESSION_MISMATCH')
    receipt = dict(path=str(path.relative_to(out)), sha256=original,
        archive=str(target.relative_to(out)), archive_sha256=digest(target))
    path.unlink()
    return receipt


def compress_text(out):
    manifest = [compress_one(p, out) for p in sorted(out.rglob('*'))
                if p.suffix in ('.json', '.jsonl') and p.stat().st_size > 65536]
    dump(out/'compression-manifest.json', manifest)


def evaluate_saved(out):
    """Post-stop evaluator only. No result is fed back to the controller."""
    snapshot = json.loads(read(out/'map.json')[0])
    static = json.loads(read(out/'inputs/static_map.json')[0])
    truth, _ = rows(out/'eval_only/trajectory.jsonl')
    trace, _ = rows(out/'trace.jsonl')
    origin = [*truth[0]['robot_xyz_m'][:2], truth[0]['robot_yaw_rad']]
    metrics = score(snapshot, static, origin)
    from harness.natural_floor_slam import compose, wrap
    paired = {round(r['t'], 8): r for r in truth}
    errors, yaw = [], []
    for row in trace:
        gt = paired.get(round(row['t'], 8))
        if gt is None:
            continue
        p = compose(origin, row['pose'])
        errors.append(float(np.linalg.norm(p[:2]-gt['robot_xyz_m'][:2])))
        yaw.append(abs(wrap(p[2]-gt['robot_yaw_rad'])))
    metrics.update(pose_error_N=len(errors), trace_N=len(trace),
        pose_rmse_m=float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
        yaw_rmse_rad=float(np.sqrt(np.mean(np.square(yaw)))) if yaw else None)
    dump(out/'eval_only/selfmap-metrics.json', metrics)
    return metrics


def acquire(out, b, backend_factory, *, controller_factory=make_executor, wall_cap_s=1800.):
    """Backend injection permits a no-physics 10 Hz/termination contract test."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    dump(out/'bundle.json', b)
    dump(out/'RUN_META.json', dict(schema='ugrp.run_meta.v1', **{'class': 'dev'},
        pr=506, branch='claude/map-selfmap', sha=b['source_sha'], batch=b['check']))
    backend = controller = None
    started = monotonic()
    audit = InputAudit(b['task']['robot_id'])
    result = dict(status='HOST_ERROR', source_sha=b['source_sha'], seed=b['task']['seed'],
        model_calls=0, complete=False, physical_success_unverified=True, frames=0)
    if b.get('check') in ('selfmap5', 'selfmap6'):
        result.update(scene_version=b['scene_version'], render_profile=b['options']['render_profile'],
            revision_gate=b['options']['revision_gate'],
            multiframe_registration=b['options']['multiframe_registration'], pool_with_previous_results=False)
        if b.get('check') == 'selfmap6':
            result['correction_safety'] = b['options']['correction_safety']
    try:
        if backend_factory.__module__.startswith('sim.'):
            missing = [name for name in ('scipy', 'matplotlib', 'mujoco')
                       if importlib.util.find_spec(name) is None]
            missing += [name for name in ('zstd', 'c++') if shutil.which(name) is None]
            if missing:
                raise RuntimeError('MISSING_EXISTING_ENV_DEPENDENCIES: '+','.join(missing))
        from scripts.run_wall_servo_stiffness import arm
        if backend_factory.__module__.startswith('sim.') and b['options'].get('render_profile') == 'floor_light_textured_v1':
            # Fail closed before constructing the plant when PR511 is absent.
            from sim.render_profile import profile_record
            profile_record('floor_light_textured_v1')
        backend = backend_factory(b, out, seed=b['task']['seed'])
        backend.reset(5.)
        start, cap, robot = backend.now, b['case_cap_s'], b['task']['robot_id']
        loop_started = monotonic()
        backend.set_deadline(round(start+cap, 9))
        extra = {}
        if b['options'].get('recovery_profile', 'off') != 'off':
            from harness.selfmap4_geometry import static_input
            static, sha = static_input()
            if sha != b['authored_static_map_sha256']:
                raise ValueError('SELFMAP4_STATIC_MAP_HASH_MISMATCH')
            extra = dict(recovery_profile=b['options']['recovery_profile'],
                         static_map=audit.static_map(static, sha))
            result['authored_static_map_sha256'] = sha
        for option in ('revision_gate', 'multiframe_registration', 'correction_safety'):
            if b['options'].get(option, 'off') != 'off':
                extra[option] = b['options'][option]
        controller = controller_factory(self_map_executor=OPTION, robot_id=robot,
            start_time=start, cap_s=cap, bootstrap=b['options'].get('bootstrap', 'off'),
            initial_sweep=b['options'].get('initial_sweep', 'off'), **extra)
        # This is the plant's issued reset-command history, never measured joints.
        audit.command(controller, dict(t=start, kind='initial_servo_command', pulses=backend.commands[robot]))
        for action in arm(b['initial_servo']):
            backend.issue(robot, action)
            audit.command(controller, dict(t=start, **action))
        with (out/'trace.jsonl').open('x') as stream:
            for tick in range(round(cap*10)+1):
                t = backend.now
                obs, _ = backend.capture()[robot]
                # Reject a camera/owner mismatch before giving any pixels to control.
                if obs['robot_id'] != robot or obs.get('camera', 'robot_cam') != 'robot_cam':
                    audit.counts['rejected_inputs'] += 1
                    raise ValueError('OWN_ROBOT_CAMERA_REQUIRED')
                saved = out/f'robots/{robot}/rgb/{tick:05d}.jpg'
                if digest(saved) != obs['sha256']:
                    raise ValueError('LIVE_SAVED_RGB_HASH_MISMATCH')
                bgr = cv2.imdecode(np.frombuffer(saved.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
                if bgr is None:
                    raise ValueError('LIVE_SAVED_RGB_DECODE_FAILED')
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                command, trace = audit.receive(controller, camera=obs.get('camera', 'robot_cam'),
                    payload=dict(robot_id=robot, t=t, frame_id=int(obs['frame_id']),
                                 rgb=rgb, sha256=obs['sha256']))
                stream.write(json.dumps(trace, allow_nan=False)+'\n')
                stream.flush()
                result['frames'] = tick+1
                if command is not None:
                    backend.issue(robot, {k: v for k, v in command.items() if k != 't'})
                    audit.command(controller, command)
                backend.eval_sample()  # write-only safety supervisor; no success feedback
                if tick % 100 == 0:
                    progress = dict(elapsed_sim_s=t-start, frames=tick+1,
                        stage=controller.stage,
                        wall_per_sim=(monotonic()-loop_started)/(t-start) if t > start else None,
                        pose_sources=dict(Counter(e['pose_source'] for e in controller.mapper.events)),
                        input_audit=audit.snapshot(),
                        frontier_arrivals=sum(e['reason'] == 'frontier_arrival' for e in controller.events))
                    dump(out/'progress.json', progress)
                    if tick == 300:
                        dump(out/'first30.json', progress)
                if controller.done:
                    break
                if monotonic()-started > wall_cap_s:
                    raise TimeoutError('SELF_MAP_HOST_TIME_CAP')
                backend.advance_to(round(start+(tick+1)*.1, 9))
        result.update(status='HOST_ERROR' if controller.stop_reason == 'selfmap4_relocalization_exhausted' else 'RECORDED', elapsed_sim_s=backend.now-start,
            stop_reason=controller.stop_reason, complete=controller.stop_reason == 'self_map_complete')
        ledger, _ = rows(out/f'robots/{robot}/frames.jsonl')
        if len(ledger) != result['frames'] or any(
            abs(r['sim_time']-(start+i*.1)) > 1e-7 for i, r in enumerate(ledger)):
            raise ValueError('INCOMPLETE_10HZ_FRAME_LEDGER')
        result['rgb_ledger_verified'] = True
    except (Exception, KeyboardInterrupt) as exc:
        result.update(status='PHYSICAL_FAILURE' if type(exc).__name__ == 'PhysicalStop' else 'HOST_ERROR',
                      complete=False, failure=dict(type=type(exc).__name__, message=str(exc)))
    finally:
        # Stop only our robot/plant. Preserve partial results on interrupt/error.
        if backend is not None:
            try:
                backend.issue(b['task']['robot_id'], dict(kind='hold'))
            except Exception as exc:
                result.update(status='HOST_ERROR', complete=False, stop_failure=str(exc))
            try:
                backend.close()
            except Exception as exc:
                result.update(status='HOST_ERROR', complete=False, close_failure=str(exc))
        if controller is not None:
            try:
                dump(out/'map.json', controller.mapper.snapshot())
                dump(out/'executor-events.json', controller.events)
                dump(out/'sweep-events.json', controller.sweep.events)
                result.update(frontier_selections=sum(e['reason'] == 'frontier_selected' for e in controller.events),
                    frontier_arrivals=sum(e['reason'] == 'frontier_arrival' for e in controller.events),
                    map_updated_frames=sum(e['map_updated'] for e in controller.mapper.events),
                    pose_sources=dict(Counter(e['pose_source'] for e in controller.mapper.events)))
            except Exception as exc:
                result.update(status='HOST_ERROR', complete=False, artifact_failure=str(exc))
        result['wall_s'] = monotonic()-started
        result['input_audit'] = audit.snapshot()
        result['invisible_measurements'] = result['input_audit']['invisible_measurements']
        result['held_world_reads'] = result['input_audit']['held_world_reads']
        dump(out/'result.json', result)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--cap-s', type=float, default=180.)
    p.add_argument('--execution-host', choices=['gcp1'], default='gcp1')
    p.add_argument('--project', choices=['ugrp-act-train-1014'], default='ugrp-act-train-1014')
    p.add_argument('--self-map-executor', choices=['off', OPTION], default='off')
    p.add_argument('--bootstrap', choices=['off', 'command_prior_v1'], default='off')
    p.add_argument('--initial-sweep', choices=['off', 'required_360_v1'], default='off')
    p.add_argument('--recovery-profile', choices=['off', 'selfmap4_recovery_v1'], default='off')
    p.add_argument('--revision-gate', choices=['off', 'selfmap4_revision_gate_v2'], default='off')
    p.add_argument('--multiframe-registration', choices=['off', 'selfmap4_multiframe_registration_v1'], default='off')
    p.add_argument('--correction-safety', choices=['off', 'selfmap6_correction_safety_v1'], default='off')
    p.add_argument('--render-profile', choices=['floor_light_v1', 'floor_light_textured_v1'], default='floor_light_v1')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args(argv)
    b = bundle(a.expected_source_sha, a.seed, a.cap_s, bootstrap=a.bootstrap, initial_sweep=a.initial_sweep,
               recovery_profile=a.recovery_profile, revision_gate=a.revision_gate,
               multiframe_registration=a.multiframe_registration, render_profile=a.render_profile,
               correction_safety=a.correction_safety)
    if not a.execute or a.self_map_executor == 'off':
        print(json.dumps(dict(status='PREPARED_NOT_EXECUTED', bundle=b, storage=storage_estimate(a.cap_s))))
        return 0
    if platform.system() != 'Linux':
        raise RuntimeError('GCP_LINUX_ONLY_NO_MAC_PHYSICS_OR_RENDER')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True)
    if head != a.expected_source_sha or dirty:
        raise RuntimeError('CLEAN_PINNED_SOURCE_REQUIRED')
    # Import the plant only after explicit execution and platform/source checks.
    from sim.own_map_closed_loop import PhysicsBackend
    def interrupted(*_):
        raise KeyboardInterrupt('owned diagnostic interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    def timeout(*_):
        raise TimeoutError('SELF_MAP_HOST_TIME_CAP')
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, 1800.)
    try:
        result = acquire(a.output, b, PhysicsBackend)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    try:
        if result['status'] == 'RECORDED':
            result['evaluation'] = evaluate_saved(a.output)
    except Exception as exc:
        result.update(status='HOST_ERROR', complete=False, evaluation_failure=str(exc))
    dump(a.output/'result.json', result)
    try:
        compress_text(a.output)
    except Exception as exc:
        result.update(status='HOST_ERROR', archive_failure=str(exc), complete=False)
        dump(a.output/'result.json', result)
    dump(a.output/'artifacts.sha256.json', {str(f.relative_to(a.output)): digest(f)
        for f in sorted(a.output.rglob('*')) if f.is_file() and f.name != 'artifacts.sha256.json'})
    manifest = a.output/'artifacts.sha256.json'
    if manifest.stat().st_size > 65536:
        try:
            dump(a.output/'artifact-manifest-receipt.json', compress_one(manifest, a.output))
        except Exception as exc:
            result.update(status='HOST_ERROR', manifest_archive_failure=str(exc), complete=False)
            dump(a.output/'result.json', result)
    print(json.dumps(result, allow_nan=False))
    return 0 if result['status'] == 'RECORDED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
