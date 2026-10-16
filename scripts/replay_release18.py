"""Stored ledgers only: timing, yaw, and release18 scheduler trace replay.

No backend import or physics/render calls. Reusing the *same ordered feature
trace at earlier times* measures scheduler waits, never a new physical result.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from scripts.replay_release14 import decoded
from sim import release17, release18
from sim.lookaround_localization import Camera

RUNS = ('r16d-00-be2d749a', 'r16d-01-be2d749a', 'r17d-00-6b263c9b', 'r17d-01-6b263c9b')


def load(raw, name):
    path = raw/name
    if not path.exists():
        path = raw/(name+'.zst')
    return decoded(path)


def ledger(raw, name):
    return [json.loads(v) for v in load(raw, name).splitlines()]


def pwm(row):
    return {int(k): v for k, v in row['pwm'].items()}


def replay_check(check, rows, reuse, after_approach):
    """Replay actual LineAlign on stored features, including the real waits.

    Clearance is held permissive for this *scheduler-only* replay. All emitted
    wheel requests must match the stored ones; this is not motion validation.
    """
    start = check['events'][0]['t']
    history = release18.CommandHistory()
    for row in rows:
        if row['t'] > start+1e-7:
            break
        history.observe(pwm(row), row['t'])
    teacher = SimpleNamespace(rid=check['robot'], pwm=dict(history.pwm), holding=False,
                              reach_mid=lambda: .152, odometry_profile='yaw_cal_v1')
    history.observe(teacher.pwm, start)
    queued, emitted = [], []
    a = release18.LineAlign(teacher, start, camera=Camera(), undistort=lambda f: f,
                           wheel_command=lambda *args: emitted.append(args[1:3]),
                           clearance=lambda *args: True, fov_step=release17.FOV_STEP,
                           settle_reuse=reuse, command_history=history,
                           after_approach=after_approach,before_approach=not after_approach, idle=lambda: not queued)
    # Consume the original feature sequence; do not predict a new image.
    features = iter([{k:v for k,v in e.items() if k not in ('event','t')}
                     for e in check['events'] if e['event']=='image'])
    a.features = lambda frame: frame
    def capture(*args):
        return next(features)
    def schedule(rid, seq, now):
        queued.extend((now+dt, p) for dt, p in seq)
    for k in range(161):
        now = start+k*.1
        while queued and queued[0][0] <= now+1e-7:
            _, pose = queued.pop(0)
            teacher.pwm.update(pose)
        history.observe(teacher.pwm, now)
        status = a.tick(now, capture, schedule)
        if status in ('ready', 'failed'):
            break
    stored = [[e['wheels'], e['durations']] for e in check['events'] if 'wheels' in e]
    assert json.dumps(emitted) == json.dumps(stored), 'scheduler replay changed wheel requests'
    return dict(state=a.state, failure=a.failure, elapsed_s=round(now-start, 6),
                reused=any(e['event'].startswith('reuse_settled_open') for e in a.records),
                image_count=sum(e['event']=='image' for e in a.records),
                wheel_requests_unchanged=True)


def summarize(root, name):
    raw = root/name/'raw'
    manifest = json.loads(load(raw, 'manifest.json'))
    if (raw/'manifest-compression.json').exists():
        compression = json.loads((raw/'manifest-compression.json').read_text())
        assert hashlib.sha256((raw/'manifest.json.zst').read_bytes()).hexdigest() == compression['sha256']
        assert hashlib.sha256(load(raw, 'manifest.json')).hexdigest() == compression['decoded_sha256']
    evidence = []
    for file in ('result.json', 'plan.json', 'teacher-r1.jsonl', 'teacher-r2.jsonl', 'eval-only.jsonl'):
        data = load(raw, file)
        digest = hashlib.sha256(data).hexdigest()
        key = file if file in manifest else file+'.zst'
        meta = manifest[key]
        assert hashlib.sha256((raw/key).read_bytes()).hexdigest() == meta['sha256'], (name,key,'stored hash')
        assert digest == meta.get('decoded_sha256',meta['sha256']), (name,file,'decoded hash')
        evidence.append(dict(path=str(raw/key),sha256=meta['sha256'],decoded_sha256=digest,decoded_bytes=len(data)))
    result = json.loads(load(raw, 'result.json'))
    rows = {r:ledger(raw, 'teacher-'+r+'.jsonl') for r in ('r1','r2')}
    first, last = rows['r1'][0]['t'], rows['r1'][-1]['t']+.1
    assert [(r['t'],r['teacher_phase']) for r in rows['r1']] == [(r['t'],r['teacher_phase']) for r in rows['r2']]
    changes = []
    for row in rows['r1']:
        if not changes or changes[-1]['phase'] != row['teacher_phase']:
            changes.append(dict(t=row['t'], phase=row['teacher_phase']))
    totals = defaultdict(float)
    for i, row in enumerate(changes):
        end = changes[i+1]['t'] if i+1<len(changes) else last
        row.update(start_release_s=round(row['t']-first,6),end_release_s=round(end-first,6),seconds=round(end-row['t'],6))
        totals[row['phase']] += row['seconds']
    epochs = []
    shifts = [d for d in result['code_decisions'] if d['action']=='shift']
    for i, d in enumerate(shifts):
        end = shifts[i+1]['t'] if i+1<len(shifts) else last
        local = {p:round(sum(max(0.,min(row['t']+row['seconds'],end)-max(row['t'],d['t']))
                                 for row in changes if row['phase']==p),6) for p in totals}
        epochs.append(dict(epoch=i+1,start_world_s=d['t'],end_world_s=end,
                           phases_s=local,choice=d))
    yaw = [dict(check=i,robot=c['robot'],**e) for i,c in enumerate(result['line_rechecks'])
           for e in c['events'] if 'wheels' in e and abs(e.get('yaw',0.))>1e-9]
    replay = []
    if name.startswith('r17'):
        # Four sequential checks per leg: two before approach, two afterwards.
        for i,c in enumerate(result['line_rechecks']):
            old = replay_check(c,rows[c['robot']],'off',i%4 in (2,3))
            new = replay_check(c,rows[c['robot']],release18.REUSE,i%4 in (2,3))
            replay.append(dict(check=i,robot=c['robot'],world_t=c['events'][0]['t'],baseline=old,candidate=new,
                               omitted_wait_s=round(old['elapsed_s']-new['elapsed_s'],6)))
    decisions = []
    for choice in result['code_decisions']:
        if 'margins_m' not in choice:
            continue
        reports = {rid:max((r for r in rows[rid] if r['t']<=choice['t']+1e-7),key=lambda r:r['t'])['report']
                   for rid in rows}
        baseline = release18.pair_choice(reports,tuple(rows),choice['t'],lateral_recovery='bounded_v1',axis_recovery=True)
        assert baseline == choice, (name,'stored pair choice mismatch')
        candidate = release18.pair_choice(reports,tuple(rows),choice['t'],lateral_recovery='bounded_v1',
                                           axis_recovery=True,goal_region=release18.GOAL_REGION)
        decisions.append(dict(world_t=choice['t'],reports=reports,baseline=baseline,candidate=candidate))
    sweeps = {rid:[dict(start_world_s=s['t0'],seconds=s['sim_s'],accepted=s['decision']['accepted'],
                        script=s['script']) for s in v['evaluation']['sweeps']]
              for rid,v in result['lookaround_result'].items()}
    return dict(run=name,source_sha=result['source_sha'],seed=json.loads(load(raw,'plan.json'))['seed'],
                outcome=result['release_outcome'],success=result['release_success'],raw=str(raw),evidence=evidence,
                release_start_world_s=first,control_end_world_s=last,control_elapsed_s=round(last-first,6),
                report_release_sim_s=result['release_sim_s'],report_includes_evaluation_tail=True,
                phase_totals_s={k:round(v,6)for k,v in totals.items()},phase_intervals=changes,epochs=epochs,
                alignments=[dict(robot=c['robot'],state=c['state'],failure=c['failure'],
                                  seconds=round(c['events'][-1]['t']-c['events'][0]['t'],6),
                                  events=dict(Counter(e['event'] for e in c['events'])))for c in result['line_rechecks']],
                yaw_commands=yaw,sweeps=sweeps,replay=replay,decision_replay=decisions,
                omitted_wait_total_s=round(sum(r['omitted_wait_s']for r in replay),6),
                evaluation_last=result['evaluation_last'],evaluation_settled_s=result['evaluation_settled_s'],
                held_world_reads=result['input_audit']['held_world_reads'],
                invisible_measurements=result['input_audit']['invisible_measurements'])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    result = dict(schema='ugrp.release18.offline.v1',scope='stored feature/command trace, scheduler replay only',
                  simulation_calls=0,remote_host_connections=0,physical_success_prediction=None,
                  runs=[summarize(args.root,name)for name in RUNS])
    payload=(json.dumps(result,indent=2)+'\n').encode()
    args.out.write_bytes(subprocess.check_output(['zstd','-q','-c'],input=payload) if args.out.suffix=='.zst' else payload)
    print(json.dumps([dict(run=r['run'],outcome=r['outcome'],phase_totals_s=r['phase_totals_s'],
                           omitted_wait_total_s=r['omitted_wait_total_s'])for r in result['runs']],indent=2))


if __name__=='__main__':
    main()
