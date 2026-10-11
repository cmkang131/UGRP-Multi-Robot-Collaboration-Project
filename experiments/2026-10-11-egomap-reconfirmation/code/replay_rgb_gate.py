"""Bounded historical own-RGB gate replay; no simulation, commands or LLM.

Run with the frozen source checkout on sys.path. Archived RGB remains remote;
the output contains hashes, counts and small diagnostics only. B replay is a
geometric necessary-condition check, not reconstruction of its semantic track.
"""
import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import pickle
import subprocess
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    path = Path(path)
    if path.is_file():
        return path.read_bytes()
    compressed = Path(str(path)+'.zst')
    if compressed.is_file():
        return subprocess.check_output(['zstd', '-qdc', str(compressed)])
    raise FileNotFoundError(str(path))


def load(path):
    return json.loads(read(path))


def rows(path):
    return [json.loads(line) for line in read(path).splitlines() if line]


def load_bank(root, seed, start):
    import numpy as np
    from harness.own_rgb_homing import Memory
    metadata_bytes = read(root/f'bank-{seed}.json')
    metadata = json.loads(metadata_bytes)
    payload = read(root/f'bank-{seed}.npz')
    if sha(payload) != metadata['sha256']:
        raise ValueError('BANK_SHA256_MISMATCH')
    if metadata['cutoff_sim_s'] > start+1e-6:
        raise ValueError('NONCAUSAL_BANK_CUTOFF')
    # Trusted project-generated feature artifact, hash checked before pickle.
    with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
        data = pickle.loads(archive['payload'].tobytes())
    bank = Memory('r3')
    bank.frames = data['frames']
    bank.home = [f for f in bank.frames if f.frame_id in data['home']]
    if any(f.t > metadata['cutoff_sim_s']+1e-6 for f in bank.frames):
        raise ValueError('NONCAUSAL_BANK_FRAME')
    return bank, dict(npz_sha256=sha(payload), metadata_sha256=sha(metadata_bytes),
        cutoff_sim_s=metadata['cutoff_sim_s'], checkpoint_sha256=metadata['checkpoint_sha256'],
        home_frames=len(bank.home), frames=len(bank.frames))


def frame_path(run, recorded):
    path = Path(recorded)
    if not path.is_absolute():
        return run/path
    parts = path.parts
    if 'robots' not in parts:
        raise ValueError('ABSOLUTE_FRAME_WITHOUT_ROBOT_PATH')
    return run.joinpath(*parts[parts.index('robots'):])


def compact(row):
    pairs = row.get('pair_match', {})
    reference = row.get('reference_match', {})
    trials = row.get('reference_trials', [])
    return dict(t=row['t'], frame_id=row['frame_id'], sha256=row['sha256'], accepted=row['accepted'],
        reason=row['reason'], reference_frame=row.get('reference_frame'),
        pair_inliers=pairs.get('inliers'), reference_inliers=reference.get('inliers'),
        best_rejected_reference_inliers=max((r.get('inliers', 0) for r in trials), default=None),
        optical_angle_rad=pairs.get('minimum_optical_angle_rad'),
        own_yaw_separation_rad=row.get('own_yaw_separation_rad'))


def replay_event(run, event, trace, images, bank, max_frames):
    import cv2
    import numpy as np
    from harness.active_camera import SEARCH
    from harness.own_rgb_reconfirmation import TwoViewGate, MAX_AGE
    timestamp = event['t']
    kind = event['reason']
    selected = [r for r in trace if timestamp-MAX_AGE <= r['t'] <= timestamp+1e-8][-max_frames:]
    result = dict(t=timestamp, kind=kind, selected_frames=len(selected), max_frames=max_frames,
        selected_frame_ids=[r['frame_id'] for r in selected], replayed_frames=0, input_errors=[],
        semantics_replayed=False, geometry_only=kind == 'goal_reached',
        counterfactual_acquisition_replayed=False, rows=[])
    gate = TwoViewGate(bank.K)
    for row in selected:
        try:
            info = images[row['frame_id']]
            data = read(frame_path(run, info['path']))
            if sha(data) != info['sha256']:
                raise ValueError('OWN_RGB_SHA256_MISMATCH')
            bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if bgr is None:
                raise ValueError('OWN_RGB_DECODE_FAILED')
            current = bank.extract(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), SEARCH,
                row['local_pose'], row['t'], row['frame_id'], info['sha256'])
            references = bank.home if kind == 'return_start_declared' else None
            result['rows'].append(compact(gate.observe(kind, current, references=references,
                semantic=True, evidence={'scope': 'historical_geometry_only'})))
        except Exception as exc:
            result['input_errors'].append(dict(frame_id=row['frame_id'], t=row['t'], error=repr(exc)))
    result['replayed_frames'] = len(result['rows'])
    final = result['rows'][-1] if result['rows'] else None
    complete = bool(selected and not result['input_errors'] and final
                    and abs(final['t']-timestamp) <= 1e-6 and len(selected) >= 5)
    result.update(complete=complete, status='REPLAYED' if complete else 'MISSING_OR_INCOMPLETE_INPUT',
        geometry_accepted_frames=sum(row['accepted'] for row in result['rows']),
        reasons=dict(Counter(row['reason'] for row in result['rows'])),
        final_frame_geometry_accepted=final['accepted'] if complete else None,
        last_five_geometry_accepted=all(row['accepted'] for row in result['rows'][-5:]) if complete else None,
        full_controller_declaration_counterfactual=None)
    return result


def replay_run(archive, seed, condition, max_frames):
    run = archive/'egomap70-wave1/data'/f'egomap70-{seed}-{condition}'
    result = load(run/'result.json')
    start = result['start_sim_s']
    events = [e for e in load(run/'utility-events.json') if e['t'] >= start
        and (e['reason'] == 'return_start_declared' or
             (e['reason'] == 'goal_reached' and e.get('entity') == 'B'))]
    report = dict(seed=seed, condition=condition, raw=str(run), original_status=result['status'],
        start_sim_s=start, result_sha256=sha(read(run/'result.json')), declarations=[],
        model_calls=0, physics_runs=0, selected_for='available historical RGB, not a random cohort')
    if not events:
        report.update(status='NO_DECLARATIONS', event_denominator=0)
        return report
    # Preserve known declarations and their evaluation denominator even when
    # a bank or controller/manifest artifact cannot be read.
    report.update(event_denominator=len(events), declarations=[dict(t=e['t'], kind=e['reason'],
        complete=False, status='INPUT_ERROR', last_five_geometry_accepted=None) for e in events])
    try:
        bank, record = load_bank(archive/'egomap68-banks/data', seed, start)
        trace = [r for r in rows(run/'own-controller.jsonl') if r['t'] >= start]
        images = {r['frame_id']: r for r in rows(run/'robots/r3/frames.jsonl')}
    except Exception as exc:
        report.update(status='INPUT_ERROR', error=repr(exc))
        return report
    report['bank'] = record
    report['declarations'] = [replay_event(run, e, trace, images, bank, max_frames) for e in events]
    report.update(status='REPLAYED' if all(e['complete'] for e in report['declarations']) else 'PARTIAL',
        event_denominator=len(events))
    return report


def score_truth_only(report):
    """Called only after every run's visual gate replay has finished."""
    if not report.get('declarations'):
        return
    import numpy as np
    run = Path(report['raw'])
    gt_bytes = read(run/'eval_only/trajectory.jsonl')
    gt = [json.loads(line) for line in gt_bytes.splitlines() if line]
    truth = {round(row['t'], 6): row for row in gt}
    origin = np.asarray(gt[0]['robot_xyz_m'][:2])
    region = load(run/'inputs/static_map.json')['regions']['zone_B']
    report['evaluation_trajectory_sha256'] = sha(gt_bytes)
    for declaration in report['declarations']:
        row = truth.get(round(declaration['t'], 6))
        if row is None:
            declaration['truth_valid'] = None
            declaration['truth_error'] = 'MISSING_DECLARATION_GT'
            continue
        xy = np.asarray(row['robot_xyz_m'][:2])
        if declaration['kind'] == 'return_start_declared':
            distance = float(np.linalg.norm(xy-origin))
            declaration.update(truth_valid=distance <= .20, actual_distance_to_start_m=distance)
        else:
            delta = np.abs(xy-region['center_m'])-region['half_extents_m']
            declaration.update(truth_valid=bool(np.all(delta <= 0)),
                actual_B_boundary_distance_m=float(np.linalg.norm(np.maximum(delta, 0))))


def summarize(reports):
    aggregate = {}
    for kind in ('goal_reached', 'return_start_declared'):
        declarations = [d for r in reports for d in r.get('declarations', []) if d['kind'] == kind]
        scored = [d for d in declarations if d.get('truth_valid') is not None]
        replayed = [d for d in scored if d['complete']]
        aggregate[kind] = dict(declarations=len(declarations), truth_scored=len(scored),
            truth_valid=sum(d['truth_valid'] for d in scored), truth_false=sum(not d['truth_valid'] for d in scored),
            fully_replayed=len(replayed),
            geometry_last_five_accepted=sum(d['last_five_geometry_accepted'] for d in replayed),
            false_geometry_accepted=sum(not d['truth_valid'] and d['last_five_geometry_accepted'] for d in replayed),
            false_geometry_rejected=sum(not d['truth_valid'] and not d['last_five_geometry_accepted'] for d in replayed),
            true_geometry_rejected=sum(d['truth_valid'] and not d['last_five_geometry_accepted'] for d in replayed),
            full_B_semantic_acceptance=None if kind == 'goal_reached' else 'not_applicable')
    return aggregate


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[3])
    p.add_argument('--seeds', type=int, nargs='+', default=[63001, 63002])
    p.add_argument('--condition', default='calib_traversed')
    p.add_argument('--max-frames', type=int, default=20, choices=range(5, 21))
    args = p.parse_args()
    sys.path.insert(0, str(args.source_root))
    from harness import own_rgb_reconfirmation as gate
    from harness import own_rgb_homing as homing
    reports = []
    for seed in args.seeds:
        try:
            reports.append(replay_run(args.archive, seed, args.condition, args.max_frames))
        except Exception as exc:
            reports.append(dict(seed=seed, condition=args.condition, status='INPUT_ERROR', error=repr(exc), declarations=[]))
    # GT is unavailable to the gate, including when processing the next run.
    for report in reports:
        try:
            score_truth_only(report)
        except Exception as exc:
            report['evaluation_error'] = repr(exc)
    output = dict(kind='historical_geometry_replay', class_='dev', pr=405,
        source_root=str(args.source_root), script_sha256=sha(Path(__file__).read_bytes()),
        module_sha256={m.__name__: sha(Path(m.__file__).read_bytes()) for m in (gate, homing)},
        gate_option=gate.OPTION, gate_params=homing.PARAMS, minimum_angle_rad=gate.MIN_ANGLE,
        seeds=args.seeds, condition=args.condition, max_frames_per_event=args.max_frames,
        physics_runs=0, model_calls=0, images_exported=0, thresholds_changed=False,
        counterfactual_actions_executed=False, aggregate=summarize(reports), runs=reports,
        limitations=[
            'Historical frames only: missing active other-angle views cannot be synthesized or counted as a runtime failure.',
            'B semantics and candidate association were not replayed; geometric acceptance is necessary, not sufficient.',
            'The last five historical frames approximate the original streak; modified earlier actions and graph corrections are not replayed.',
            'Missing inputs and missing GT remain explicit; zero declarations are not successful return or evidence of gate benefit.',
            'Same development seeds, bounded selected windows, no E2E/causal improvement/independent confirmation claim.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(output=str(args.output), aggregate=output['aggregate'],
        input_errors=sum(r['status'] == 'INPUT_ERROR' for r in reports))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
