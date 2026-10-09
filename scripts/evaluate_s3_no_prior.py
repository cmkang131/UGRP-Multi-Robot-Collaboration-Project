"""Post-run S3 metrics and own-camera 4x video; no simulator or controller."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

from scripts.run_final_environment_checks import write


def load_lines(path):
    with path.open() as stream:
        for line in stream:
            yield json.loads(line)


def cause(value):
    name = str(value).upper()
    for needles, category in [(('LOCAL', 'POSE', 'LOOK_RECOVERY', 'LOOK_FAILED'), 'LOCALIZATION'),
                              (('DOOR', 'DEADLOCK'), 'DOOR_DEADLOCK'),
                              (('COLLISION', 'CONTACT'), 'COLLISION'),
                              (('GRIP', 'GRASP', 'PICK'), 'PICK_GRASP'),
                              (('DROP', 'TILT'), 'DROP_TILT'),
                              (('GO_', 'SYNC'), 'GO_SYNC')]:
        if any(x in name for x in needles):
            return category
    return 'DELIVERY_PLACEMENT'


def metrics(out):
    from scripts.evaluate_s2_unknown_start import score
    result = json.loads((out/'result.json').read_text())
    student = json.loads((out/'student_record.json').read_text()) if (out/'student_record.json').exists() else {}
    rows, counts = {}, Counter()
    evaluation = result.get('evaluation') or {}
    for rid in ('r1', 'r2', 'r3'):
        local = student.get('localizers', {}).get(rid, {})
        truth_path = out/f'eval_only/{rid}/trajectory.jsonl'
        truth = list(load_lines(truth_path)) if truth_path.exists() else []
        loc = score(local, truth) if truth and local.get('poses') else {'converged': False, 'first_convergence': None}
        convergence = loc['first_convergence']
        correct = bool(convergence and not convergence['wrong_mode'] and convergence['actual_yaw_error_deg'] <= 15)
        oid = 'order-1' if rid == 'r3' else 'order-5'
        delivered = evaluation.get('orders', {}).get(oid, {}).get('complete')
        failure = (result.get('controller_failures') or student.get('failures', {})).get(rid)
        categories = []
        if not correct:
            categories.append('LOCALIZATION')
        if failure:
            categories.append(cause(failure))
        if delivered is not True:
            categories.append('DELIVERY_PLACEMENT' if truth else 'NOT_EVALUATED')
        categories = sorted(set(categories))
        counts.update(categories)
        rows[rid] = dict(success=bool(correct and delivered and not failure),
            cargo_order=oid, delivery_complete=delivered, first_convergence=convergence,
            correct_convergence=correct, own_failure=failure, failure_categories=categories)
    collisions = []
    path = out/'eval_only/contacts.jsonl'
    last = {}
    if path.exists():
        for row in load_lines(path):
            for contact in row['contacts']:
                a, b = [(contact.get(k) or '').partition('__')[0] for k in ('geom1', 'geom2')]
                if a in rows and b in rows and a != b and contact['dist_m'] < 0:
                    key = tuple(sorted((a, b)))
                    if key not in last or row['t']-last[key] > 1:
                        collisions.append(dict(t=row['t'], robots=list(key)))
                    last[key] = row['t']
    counts['COLLISION_EPISODES'] = len(collisions)
    protocol = student.get('door_yield', {})
    events = protocol.get('events', [])
    waits = {r: 0 for r in rows}
    deadlocks = []
    end = result.get('reset_sim_s', 0)+result.get('check_sim_s', 0)
    for i, event in enumerate(events):
        states = {s['robot_id']: s['state'] for s in event['signals']}
        previous = {} if i == 0 else {s['robot_id']: s['state'] for s in events[i-1]['signals']}
        for rid in waits:
            waits[rid] += int(states.get(rid) == 'REQUEST' and previous.get(rid) != 'REQUEST')
        until = events[i+1]['sim_s'] if i+1 < len(events) else end
        if 'REQUEST' in states.values() and until-event['sim_s'] >= 120:
            deadlocks.append(dict(start=event['sim_s'], end=until, duration_s=until-event['sim_s']))
    counts['DOOR_DEADLOCK_EPISODES'] = len(deadlocks)
    if result['status'] == 'HOST_ERROR':
        counts['HOST_ERROR'] += 1
    if result['status'] == 'DEV_PHYSICAL_STOP':
        counts[cause(result['failure']['message'])] += 1
    return dict(schema='ugrp.s3_no_prior_evaluation.v142', gt_use='post-run eval_only; no feedback',
        robots=rows, failure_counts=dict(counts), failure_count_denominator='robot-category pairs; shared beam delivery can affect two robots',
        collision_episodes=collisions, door_wait_episodes=waits,
        door_wait_robot_s=protocol.get('wait_robot_s', {}), door_deadlocks=deadlocks,
        wall_s=result.get('wall_s'), sim_s=result.get('check_sim_s'), wall_per_sim=result.get('wall_per_sim'),
        commands=result.get('commands_issued'), model_calls=0, raw=str(out.resolve()))


def video(out):
    import cv2
    import numpy as np
    paths = [out/f'robots/{r}/frames.jsonl' for r in ('r1', 'r2', 'r3')]
    if not all(p.exists() for p in paths):
        return None
    dest = out/'s3-own-cameras-4x.mp4'
    if dest.exists():
        raise FileExistsError(dest)
    writer = cv2.VideoWriter(str(dest), cv2.VideoWriter_fourcc(*'mp4v'), 20, (1920, 480))
    if not writer.isOpened():
        raise RuntimeError('video writer failed')
    count = 0
    try:
        for i, triple in enumerate(zip(*(load_lines(p) for p in paths))):
            if i % 4:
                continue
            images = [cv2.imread(str(out/q['path'])) for q in triple]
            if any(im is None for im in images):
                raise ValueError('missing retained own RGB')
            for rid, q, im in zip(('r1', 'r2', 'r3'), triple, images):
                cv2.putText(im, f'{rid} | SIM {q["sim_time"]:.2f}s | 4x', (12, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 2)
            writer.write(np.hstack(images))
            count += 1
    finally:
        writer.release()
    check = cv2.VideoCapture(str(dest))
    ok, frame = check.read()
    observed = int(check.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = check.get(cv2.CAP_PROP_FPS)
    check.release()
    if not ok or observed != count or fps != 20:
        raise RuntimeError('saved video verification failed')
    return dict(path=str(dest), frames=count, fps=fps, playback=4, source='three own cameras; eval presentation only')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--video', action='store_true')
    a = p.parse_args()
    report = metrics(a.source)
    if a.video:
        report['video'] = video(a.source)
    write(a.source/'eval_only/s3-summary.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
