"""Offline analysis of the 40-run wide-start teacher gate (read-only).

Reads the gate summary, each world's adapter result and tail-10 Hz ring, and
produces one compact summary.  It never edits a run and never emits a command.

READY witness check: the recorded tail frames (10 Hz) and the recorded issued
servo PWM are replayed through the default-off witness decision function
(``ReadyWitness._evaluate`` plus the same streak/gap rule as ``observe``).
This is a *decision-function replay*, not a full student observation: the
student schema requires wheels/duration fields that the teacher record does
not contain, so ``validate_observation`` is not invoked here.  Coverage is the
recording ring only (last 100 control ticks per world), so a READY/GO event
outside that ring is reported as not observed, never as approval or failure.

The gate's teacher has no GO/ACK protocol.  The GO-equivalent is the first
tick whose teacher phase transitions READY -> pick, i.e. the tick at which the
teacher stops judging ready geometry and commits the pick motion.

Usage (on the run VM, next to the raw run):
  python analyze_gate40.py --run RUN --cases wide-cases.json \
      --prereg wide-pre-registration.json --dependency DEP --overlay OVERLAY \
      --out analysis.json
"""
import argparse
import bisect
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
import types
from collections import Counter, defaultdict
from pathlib import Path


def sha256_bytes(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def read_json(path):
    path = Path(path)
    if path.is_file():
        return json.loads(path.read_text())
    zst = Path(str(path) + '.zst')
    if zst.is_file():
        raw = subprocess.check_output(['zstd', '-qdc', str(zst)])
        return json.loads(raw)
    raise FileNotFoundError(str(path))


def read_jsonl(path):
    path = Path(path)
    if path.is_file():
        text = path.read_text()
    else:
        zst = Path(str(path) + '.zst')
        if not zst.is_file():
            return []
        text = subprocess.check_output(['zstd', '-qdc', str(zst)]).decode()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def synthetic_package(name, root):
    package = types.ModuleType(name)
    package.__path__ = [str(Path(root) / name)]
    sys.modules[name] = package
    return package


def import_witness(dependency, overlay):
    """Load the witness over the pinned dependency harness tree."""
    sys.path.insert(0, str(dependency))
    harness = synthetic_package('harness', dependency)
    synthetic_package('sim', dependency)
    for name in ('grasp_act_contract', 'beamact5_ready'):
        path = Path(overlay) / 'harness' / f'{name}.py'
        spec = importlib.util.spec_from_file_location(f'harness.{name}', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[f'harness.{name}'] = module
        setattr(harness, name, module)
        spec.loader.exec_module(module)
    return sys.modules['harness.beamact5_ready']


def nearest(rows, times, t, tol):
    index = bisect.bisect_left(times, t)
    best = None
    for candidate in (index - 1, index):
        if 0 <= candidate < len(rows):
            delta = abs(float(rows[candidate]['t']) - t)
            if delta <= tol and (best is None or delta < best[0]):
                best = (delta, rows[candidate])
    return None if best is None else best[1]


def failing_reason(report, world):
    teachers = (report or {}).get('teachers') or {}
    bad = {rid: (value.get('outcome') if value.get('outcome') is not None
                 else 'incomplete_no_outcome')
           for rid, value in teachers.items() if value.get('outcome') != 'success'}
    if world.get('cap_end') or (report or {}).get('cap_end'):
        return 'cap_end', bad
    if bad:
        return '+'.join(sorted(set(map(str, bad.values())))), bad
    if (report or {}).get('teacher_success_n') == (report or {}).get('teacher_N') and \
            (report or {}).get('joint_held') is False:
        return 'no_stable_joint_hold_3s', bad
    return 'teacher_failure_unspecified', bad


def clearance_evidence(report, rid):
    """Last path/frontier clearance row for one failing robot, if recorded."""
    teacher = ((report or {}).get('teachers') or {}).get(rid) or {}
    rows = teacher.get('search23_log') or []
    for row in reversed(rows):
        blockers = row.get('blocked_obstacles') or []
        if blockers:
            names = []
            gaps = []
            for blocker in blockers:
                name = blocker.get('id') or blocker.get('category') or 'unattributed'
                names.append(str(name))
                gap = blocker.get('gap_m')
                if isinstance(gap, (int, float)) and math.isfinite(gap):
                    gaps.append(float(gap))
            return dict(reason_category='path_or_frontier_block',
                        blocked_object=','.join(sorted(set(names))),
                        min_gap_m=min(gaps) if gaps else None,
                        gap_scope=row.get('min_gap_scope'), t=row.get('t'),
                        path_status=row.get('status'))
        if isinstance(row.get('min_gap_m'), (int, float)):
            return dict(reason_category='path_min_gap',
                        blocked_object=','.join(sorted(set(
                            str(b.get('id') or b.get('category') or 'unattributed')
                            for b in blockers))) or 'unattributed',
                        min_gap_m=float(row['min_gap_m']),
                        gap_scope=row.get('min_gap_scope'), t=row.get('t'),
                        path_status=row.get('status'))
    events = teacher.get('events') or []
    for row in reversed(events):
        category = row.get('reason_category')
        if category:
            return dict(reason_category=str(category),
                        blocked_object=str(row.get('blocked_object') or 'not_observed'),
                        min_gap_m=row.get('min_gap_m'),
                        gap_scope=row.get('gap_scope'), t=row.get('t'))
    return dict(reason_category='not_observed', blocked_object='not_observed',
                min_gap_m=None, gap_scope='no path/frontier/clearance row recorded',
                t=None)


def witness_replay(module, world_dir, report, roles):
    """Replay the READY witness on the recorded tail ring for this world."""
    witness = module.ReadyWitness()
    tail_path = Path(world_dir) / 'tail-10hz.json'
    ledger = read_jsonl(Path(world_dir) / 'adapter/beampair1-commands.jsonl')
    if not tail_path.is_file():
        return dict(skipped='no tail-10hz.json', robots={})
    tail = json.loads(tail_path.read_text())
    by_robot = defaultdict(list)
    for row in ledger:
        by_robot[row['robot_id']].append(row)
    for rows in by_robot.values():
        rows.sort(key=lambda row: float(row['t']))
    times = {rid: [float(row['t']) for row in rows] for rid, rows in by_robot.items()}
    teachers = (report or {}).get('teachers') or {}
    out = dict(tail_rows=len(tail), tail_sim_span_s=None,
               coverage_start_s=min((float(row['world_t']) for row in tail), default=None),
               coverage_end_s=max((float(row['world_t']) for row in tail), default=None),
               ledger_join_fail=0, robots={})
    if out['coverage_start_s'] is not None:
        out['tail_sim_span_s'] = out['coverage_end_s'] - out['coverage_start_s']
    for rid in (roles if roles else teachers):
        teacher = teachers.get(rid) or {}
        role = (roles or {}).get(rid)
        rows = by_robot.get(rid) or []
        go_t = None
        ready_t = None
        for row in rows:
            if row.get('phase_before') == 'ready' and row.get('phase_after') == 'pick':
                go_t = float(row['t'])
                break
        for row in rows:
            if row.get('phase_after') == 'ready':
                ready_t = float(row['t'])
                break
        entry = dict(role=role, outcome=teacher.get('outcome'),
                     ready_phase_t=ready_t, go_phase_t=go_t,
                     go_in_ledger=go_t is not None,
                     go_in_coverage=(go_t is not None and out['coverage_start_s'] is not None
                                     and out['coverage_start_s'] <= go_t + 1e-9),
                     frames=0, join_fail=0, aligned_frames=0,
                     witness_ready_t=None, approved_by_go=None,
                     last_decision=None, coverage_reason=None)
        if role not in ('teal', 'blue'):
            entry['coverage_reason'] = 'NO_ASSIGNED_BAND_ROLE'
            out['robots'][rid] = entry
            continue
        streak = 0
        last_sha = None
        last_t = None
        limit = go_t if go_t is not None else float('inf')
        for tail_row in tail:
            t = float(tail_row['world_t'])
            if t > limit + 1e-9:
                break
            path = (tail_row.get('files') or {}).get(rid)
            if not path or not Path(path).is_file():
                continue
            if rid not in times:
                entry['join_fail'] += 1
                continue
            command = nearest(by_robot[rid], times[rid], t, 0.05)
            if command is None:
                entry['join_fail'] += 1
                continue
            pwm = ((command.get('issued_command') or {}).get('pwm'))
            if not isinstance(pwm, dict) or not pwm:
                entry['join_fail'] += 1
                continue
            data = Path(path).read_bytes()
            entry['frames'] += 1
            frame = module.cv2.imdecode(module.np.frombuffer(data, module.np.uint8),
                                        module.cv2.IMREAD_COLOR)
            if frame is None or tuple(frame.shape[:2]) != tuple(module.IMAGE_HW):
                entry['coverage_reason'] = 'UNSUPPORTED_IMAGE_SIZE'
                entry['last_decision'] = dict(aligned=False, reason='UNSUPPORTED_IMAGE_SIZE',
                                              frame_t=t)
                continue
            digest = sha256_bytes(data)
            duplicate = digest == last_sha
            gap = 0. if last_t is None else t - last_t
            if duplicate or gap > module.MAX_FRAME_GAP_S + 1e-9:
                streak = 0
            decision = witness._evaluate(frame, {'issued': [{'pwm': pwm}]}, role)
            streak = streak + 1 if decision.get('aligned') else 0
            last_sha, last_t = digest, t
            if decision.get('aligned'):
                entry['aligned_frames'] += 1
            if (decision.get('aligned') and streak >= witness.config['alignment_frames']
                    and entry['witness_ready_t'] is None):
                entry['witness_ready_t'] = t
            entry['last_decision'] = dict(
                t=t, aligned=bool(decision.get('aligned')), reason=decision.get('reason'),
                streak=streak, errors=decision.get('errors'),
                observer=decision.get('observer'), band=decision.get('band'),
                frame_sha256=digest)
        if go_t is not None:
            if not entry['go_in_coverage']:
                entry['coverage_reason'] = 'GO_BEFORE_TAIL_WINDOW'
            elif entry['frames'] == 0:
                entry['coverage_reason'] = 'NO_JOINED_FRAMES_AT_GO'
            else:
                entry['approved_by_go'] = (entry['witness_ready_t'] is not None
                                           and entry['witness_ready_t'] <= go_t + 1e-9)
        else:
            entry['coverage_reason'] = 'NO_PICK_PHASE_IN_LEDGER'
        out['robots'][rid] = entry
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--prereg', type=Path, required=True)
    parser.add_argument('--dependency', type=Path, required=True)
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--witness', action='store_true')
    args = parser.parse_args()

    summary = json.loads((args.run / 'summary.json').read_text())
    cases = json.loads(args.cases.read_text())
    prereg = json.loads(args.prereg.read_text())
    manifest_path = args.run / 'artifact-sha256.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    worlds = {int(row['world']): row for row in summary.get('worlds') or []}
    layers = {row['id']: row for row in prereg['distance_layers']}

    module = import_witness(args.dependency, args.overlay) if args.witness else None

    run_rows = []
    layer_stats = {name: dict(planned_runs=layer['planned_runs'],
                              planned_robot_starts=layer['planned_robot_starts'],
                              run_success_n=0, run_N=0,
                              robot_success_n=0, robot_N=0,
                              cap_end_n=0, runs=[], robots=[])
                  for name, layer in layers.items()}
    failure_rows = []
    failure_categories = Counter()
    blocked_objects = Counter()
    witness_robots = []
    raw_index = {}

    for index, case in enumerate(cases):
        world = worlds.get(index)
        world_dir = args.run / f'world-{index:03d}'
        adapter = world_dir / 'adapter/beampair1-result.json'
        report = None
        if adapter.is_file() or Path(str(adapter) + '.zst').is_file():
            try:
                report = read_json(adapter).get('result')
            except Exception as error:  # partial/corrupt adapter output stays visible
                report = None
        success = bool(world and world.get('success'))
        cap_end_60s = bool(world and world.get('cap_end'))
        cap_end_safety = bool((report or {}).get('cap_end')) and \
            (report or {}).get('end_reason') == 'planning_wall_safety_cap'
        cap_end = cap_end_60s or cap_end_safety
        status = (report or {}).get('status')
        reason, bad = failing_reason(report, world or {})
        teachers = (report or {}).get('teachers') or {}
        row = dict(world=index, seed=(case.get('plan') or {}).get('seed'),
                   success=success, cap_end=cap_end,
                   cap_end_60s=cap_end_60s, cap_end_safety=cap_end_safety,
                   status=status, reason=None if success else reason,
                   sim_s=(world or {}).get('sim_s'),
                   end_reason=(report or {}).get('end_reason'),
                   teacher_success_n=(report or {}).get('teacher_success_n'),
                   teacher_N=(report or {}).get('teacher_N'),
                   joint_held=(report or {}).get('joint_held'),
                   raw=str(world_dir / 'raw'),
                   robots={rid: dict(layer=(case['plan'].get('start_layers') or {}).get(rid, {}).get('layer'),
                                     distance_m=(case['plan'].get('start_layers') or {}).get(rid, {}).get('target_distance_m'),
                                     yaw_bin=((case['plan'].get('start_layers') or {}).get(rid, {}).get('yaw_bin') or {}).get('index'),
                                     role=(case['plan'].get('roles') or {}).get(rid),
                                     end=(teachers.get(rid) or {}).get('end'),
                                     outcome=(teachers.get(rid) or {}).get('outcome'))
                           for rid in ('r1', 'r2')})
        if not success:
            evidence = {}
            for rid, rid_row in row['robots'].items():
                if rid_row.get('outcome') != 'success':
                    evidence[rid] = clearance_evidence(report, rid)
            row['clearance'] = evidence
            if cap_end:
                row['ledger'] = dict(
                    reason_category='cap_end',
                    blocked_object='none:' + str((report or {}).get('end_reason')
                                                 or ('cap_s' if cap_end_60s else 'cap_end')),
                    min_gap_m=None,
                    gap_scope='administrative cap_end; no clearance decision')
            else:
                row['ledger'] = dict(
                    reason_category=reason,
                    blocked_object=','.join(sorted(set(
                        item['blocked_object'] for item in evidence.values()
                        if item.get('blocked_object') not in (None, 'not_observed')))) or 'not_observed',
                    min_gap_m=min((item['min_gap_m'] for item in evidence.values()
                                   if isinstance(item.get('min_gap_m'), (int, float))),
                                  default=None),
                    gap_scope='per-failing-robot search23/frontier ledger; null = not measured')
            failure_rows.append(row)
            failure_categories[row['ledger']['reason_category']] += 1
            blocked_objects[row['ledger']['blocked_object']] += 1
        for rid, rid_row in row['robots'].items():
            name = rid_row.get('layer')
            if name in layer_stats:
                layer_stats[name]['robot_N'] += 1
                layer_stats[name]['robots'].append(rid_row)
                if rid_row.get('outcome') == 'success':
                    layer_stats[name]['robot_success_n'] += 1
        for name in {rid_row.get('layer') for rid_row in row['robots'].values() if rid_row.get('layer')}:
            if name in layer_stats:
                layer_stats[name]['run_N'] += 1
                layer_stats[name]['runs'].append(index)
                if success:
                    layer_stats[name]['run_success_n'] += 1
                if cap_end:
                    layer_stats[name]['cap_end_n'] += 1
        # per-world artifact hashes from the run's own manifest
        prefix = f'world-{index:03d}/'
        raw_index[index] = {key: value for key, value in manifest.items()
                            if key.startswith(prefix) and any(
                                key.endswith(name) for name in (
                                    'adapter/beampair1-result.json',
                                    'adapter/beampair1-result.json.zst',
                                    'adapter/beampair1-commands.jsonl',
                                    'adapter/beampair1-commands.jsonl.zst',
                                    'adapter/beampair1-result.json',
                                    'adapter/wall-layer.json',
                                    'adapter/manifest.json',
                                    'raw/result.json',
                                    'raw/result.json.zst',
                                    'tail-10hz.json'))}
        if module is not None:
            replay = witness_replay(module, world_dir, report,
                                    (case.get('plan') or {}).get('roles') or {})
            for rid, entry in replay['robots'].items():
                entry.update(world=index, seed=row['seed'], layer=row['robots'][rid]['layer'],
                             distance_m=row['robots'][rid]['distance_m'],
                             yaw_bin=row['robots'][rid]['yaw_bin'],
                             physical_success=success, outcome=entry.get('outcome'))
                witness_robots.append(entry)
            row['witness'] = {rid: dict(ready_phase_t=entry['ready_phase_t'],
                                        go_phase_t=entry['go_phase_t'],
                                        go_in_coverage=entry['go_in_coverage'],
                                        witness_ready_t=entry['witness_ready_t'],
                                        approved_by_go=entry['approved_by_go'],
                                        frames=entry['frames'],
                                        coverage_reason=entry['coverage_reason'])
                              for rid, entry in replay['robots'].items()}
        run_rows.append(row)

    go_observed = [entry for entry in witness_robots if entry.get('go_in_coverage')]
    go_all = [entry for entry in witness_robots if entry.get('go_phase_t') is not None]
    no_go = [entry for entry in witness_robots if entry.get('go_phase_t') is None]
    witness_summary = None
    if module is not None:
        witness_summary = dict(
            toggle='beamact5_ready_witness_v1', default_off=True,
            profile=module.PROFILE, camera_profile=module.CAMERA_PROFILE,
            image_hw=list(module.IMAGE_HW),
            robot_starts=len(witness_robots),
            go_in_ledger=len(go_all),
            go_inside_tail_coverage=len(go_observed),
            approved_by_go_n=sum(entry.get('approved_by_go') is True for entry in go_observed),
            approved_by_go_denominator=len(go_observed),
            go_before_tail_window=sum(entry.get('coverage_reason') == 'GO_BEFORE_TAIL_WINDOW'
                                      for entry in go_all),
            no_pick_phase=len(no_go),
            early_approval_without_go=sum(entry.get('witness_ready_t') is not None
                                          for entry in no_go),
            aligned_frame_total=sum(entry.get('aligned_frames') or 0 for entry in witness_robots),
            frame_total=sum(entry.get('frames') or 0 for entry in witness_robots),
            ledger_join_fail=sum(entry.get('join_fail') or 0 for entry in witness_robots),
            coverage_limit='tail-10hz ring only (last 100 control ticks per world)',
            witness_input='0 s own RGB + recorded issued PWM only',
            not_student_observation='wheels/duration schema absent; decision-function replay only')

    camera = summary.get('camera') or {}
    camera_audit = dict(
        resolution=camera.get('resolution'), K=camera.get('K'),
        remap_sha256=camera.get('remap_sha256'), D=camera.get('D'),
        renderer=camera.get('renderer'), quality_requested=camera.get('quality_requested'),
        note='MJWarp batch render; compare K/remap against masterpi_camera_profile')
    if module is not None:
        try:
            from sim.masterpi_camera_profile import scaled_camera_matrix, raw_fisheye_remap
            mx, my = raw_fisheye_remap(640, 480)
            camera_audit['K_matches_profile_640x480'] = bool(
                module.np.array_equal(module.np.asarray(camera.get('K'),
                                                        dtype=float),
                                      scaled_camera_matrix(640, 480)))
            camera_audit['remap_matches_profile_640x480'] = bool(
                hashlib.sha256(mx.tobytes() + my.tobytes()).hexdigest()
                == camera.get('remap_sha256'))
        except Exception as error:  # keep the audit fail-visible
            camera_audit['profile_compare_error'] = f'{type(error).__name__}: {error}'

    gate = dict(
        schema='ugrp.beamact5.gate40_analysis.v1',
        run=str(args.run), source_sha=summary.get('source_sha'),
        status=summary.get('status'), planned_N=summary.get('planned_N'),
        started_N=summary.get('started_N'), completed_N=summary.get('completed_N'),
        success_n=summary.get('success_n'), cap_end=summary.get('cap_end'),
        cap_end_60s_n=sum(row.get('cap_end_60s') for row in run_rows),
        cap_end_safety_n=sum(row.get('cap_end_safety') for row in run_rows),
        end_reasons=dict(Counter(row.get('end_reason') for row in run_rows
                                 if row.get('end_reason'))),
        HOST_ERROR=summary.get('HOST_ERROR'),
        min_success=prereg.get('min_success'), gate_pass=None,
        beamact5_gate_eligible=summary.get('beamact5_gate_eligible'),
        cases_sha256=summary.get('cases_sha256'),
        camera=camera_audit,
        first30_speed=(json.loads((args.run / 'first30-speed.json').read_text())
                       if (args.run / 'first30-speed.json').is_file() else None),
        layers=layer_stats,
        failure_categories=dict(failure_categories),
        blocked_objects=dict(blocked_objects),
        failures=failure_rows,
        witness=witness_summary,
        witness_robots=None,
        per_world=run_rows,
        raw_artifacts=raw_index,
        artifact_manifest=dict(path=str(manifest_path),
                               sha256=sha256_bytes(manifest_path.read_bytes())
                               if manifest_path.is_file() else None,
                               files=len(manifest)),
        unverified=[
            'raw remains on gcp6; this summary is the Mac-side record',
            'witness replay is a decision-function replay, not a student observation',
            'witness coverage is the last-100-tick ring only',
            'teacher success is not student success; no training data was recorded',
        ])
    if gate['success_n'] is not None and gate['completed_N'] == gate['planned_N']:
        gate['gate_pass'] = bool(gate['success_n'] >= gate['min_success'])
    if module is not None:
        gate['witness_robots'] = witness_robots
    args.out.write_text(json.dumps(gate, indent=2) + '\n')
    compact = dict(
        run=gate['run'], status=gate['status'], success=f"{gate['success_n']}/{gate['completed_N']}",
        cap_end=gate['cap_end'], cap_end_60s=gate['cap_end_60s_n'],
        cap_end_safety=gate['cap_end_safety_n'], end_reasons=gate['end_reasons'],
        host_error=gate['HOST_ERROR'],
        gate_pass=gate['gate_pass'], eligible=gate['beamact5_gate_eligible'],
        layers={name: f"{value['run_success_n']}/{value['run_N']} runs, "
                       f"{value['robot_success_n']}/{value['robot_N']} starts, "
                       f"cap_end {value['cap_end_n']}"
                for name, value in layer_stats.items()},
        failure_categories=gate['failure_categories'],
        witness=witness_summary,
        out=str(args.out))
    print(json.dumps(compact, indent=2))


if __name__ == '__main__':
    main()
