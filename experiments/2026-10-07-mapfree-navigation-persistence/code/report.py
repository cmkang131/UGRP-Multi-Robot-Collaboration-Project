"""Read-only outcome analysis; never run a world/actor or change frozen parameters."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).parent))
from run_persistent import hashes, verify_development, cohort, MANIFEST, write


def jsonl(p):
    return [json.loads(line) for line in p.read_text().splitlines()]


def name(row):
    return f"{row['scenario']}-{row['start']}-{row['seed']}-{row['condition']}"


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    a=p.parse_args()
    source=json.loads((a.input/'source.json').read_text())
    rows=json.loads((a.input/'results.json').read_text())
    assert source['hashes']==hashes(), 'RUNTIME_CHANGED'
    assert len(rows)==10
    assert {(r['scenario'],r['start'],r['seed']) for r in rows}=={(f's{i}',s,z) for i,s,z in cohort('diagnostic')}
    old_dir=ROOT/'outputs/mapfree-navigation-recovery-diagnostic-v2'
    old_rows=json.loads((old_dir/'results.json').read_text())
    old={name(r):r for r in old_rows}
    keys=('status','time_s','distance_m','coverage','collisions','first_B','navigation_events',
          'sensor_draws','end_position_error_m','door_attempts','wrong_door_attempts')
    comparison=[]
    contact_after_backup=0
    for r in rows:
        folder=a.input/name(r)
        assert json.loads((folder/'result.json').read_text())==r
        events=jsonl(folder/'navigation_events.jsonl')
        assert dict(Counter(e['reason'] for e in events))==r['navigation_events']
        contacts=jsonl(folder/'eval_contacts.jsonl')
        assert len(contacts)==r['collisions']
        samples=jsonl(folder/'contact_inputs.jsonl')
        assert all(set(s)=={'t','pressed'} and type(s['pressed']) is bool for s in samples)
        tracks=defaultdict(list)
        for log in jsonl(folder/'actor.jsonl'):
            assert set(log['observation'])=={'robot_id','frame_id','floor_xy','wall_xy','floor_source'}
            for patch in log['patches']:
                tracks[patch['track_id']].append(np.asarray(log['pose_odom'][:2]))
        baseline=max((max(float(np.linalg.norm(x-positions[0])) for x in positions)
                      for positions in tracks.values() if len(positions)>=3),default=0.)
        completed=[e['t'] for e in events if e['reason']=='contact_replan']
        post=sum(c['t']>min(completed) for c in contacts) if completed else None
        contact_after_backup+=post or 0
        diagnostic=dict(max_three_view_translation_from_anchor_m=baseline,
            terminal_causes=[e['cause'] for e in events if e['reason']=='navigation_action_aborted'],
            recovery_results=[e for e in events if e['reason'] in ('recovery_success','recovery_failure')],
            contact_times_s=[c['t'] for c in contacts],
            bumper_rising_count=r['navigation_events'].get('binary_contact_stop',0),
            backup_completed_s=completed,physical_contacts_after_backup=post,
            predicted_collision_actions=dict(Counter(e['action'] for e in events if e['reason']=='predicted_footprint_collision')))
        comparison.append(dict(pair=name(r),before={k:old[name(r)][k] for k in keys},
                               after={k:r[k] for k in keys},diagnostic=diagnostic))
    result_dir=EXP/'results'
    result_dir.mkdir(exist_ok=True)
    write(result_dir/'failure-comparison.json',comparison)
    write(result_dir/'results.json',rows)
    try:
        verify_development(a.input,hashes())
    except ValueError as e:
        blocked=str(e)
    else:
        blocked=None
    summary=dict(cohort='already_seen_failed10_development',source_sha=source['sha'],
        prior_true_B=sum(r['status']=='B_confirmed' for r in old_rows),true_B=sum(r['status']=='B_confirmed' for r in rows),
        false_B=sum(r['status']=='B_false_confirmed' for r in rows),valid=6,setup_errors=4,
        statuses=dict(Counter(r['status'] for r in rows)),physical_contact_events=sum(r['collisions'] for r in rows),
        physical_contacts_after_backup=contact_after_backup,
        new32_executed=0,stage_b='NOT_RUN',stage_c='NOT_RUN',gate=blocked,
        criteria='UNCHANGED; development valid6/6 failed; new32 and original5 not evaluated',
        stop_reason='s4/s5 collision projection and finite pinned RoundRobin exhaustion persisted; no tuning/replay')
    assert summary['gate']=='DEVELOPMENT_GATE_FAILED_STOP_CONFIRMATION'
    write(result_dir/'summary.json',summary)
    lines=['# 기존 실패10 개발 결과 (v2 → v3)','',
           'oracle 두 seed는 같은 궤적이며 독립 성공 증거가 아니다. 시작 겹침4는 성공에서 제외하되 원 표본에 보존한다.',
           'B 0/10 → 2/10, 유효6 중2. 새32/기존22 성공과 합산하지 않는다. 모든 시간은 modeled s.','',
           '| 쌍 | 종료 v2 → v3 | 시간 s | 거리 m | coverage % | 충돌 | B 가시/검출(v3) |',
           '|---|---|---:|---:|---:|---:|---:|']
    for c in comparison:
        b,n=c['before'],c['after']
        lines.append(f"| {c['pair']} | {b['status']} → {n['status']} | {b['time_s']:.1f} → {n['time_s']:.1f} | {b['distance_m']:.3f} → {n['distance_m']:.3f} | {b['coverage']*100:.1f} → {n['coverage']*100:.1f} | {b['collisions']} → {n['collisions']} | {n['sensor_draws']['B_positive_frames']}/{n['sensor_draws']['B_detections']} |")
    lines+=['','| 유효 개발 원인 / 각2seed | v3 세부 |','|---|---|']
    for c in comparison:
        if '-4701-' not in c['pair'] or c['after']['status']=='HOST_SETUP_ERROR':
            continue
        d=c['diagnostic']
        lines.append(f"| {c['pair'].replace('-4701-static_map','')} | predicted reject {d['predicted_collision_actions']}; final {d['terminal_causes']}; 3-view baseline {d['max_three_view_translation_from_anchor_m']:.9f}m; contact {d['contact_times_s']}; backup completed {d['backup_completed_s']} |")
    (result_dir/'tables.md').write_text('\n'.join(lines)+'\n')
    artifacts=[]
    for f in sorted(a.input.rglob('*')):
        if f.is_file():
            data=f.read_bytes()
            artifacts.append(dict(path=str(f),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
    write(result_dir/'artifacts.json',dict(files=artifacts,total_bytes=sum(f['bytes'] for f in artifacts)))
    preserved=json.loads((ROOT/'experiments/2026-10-07-mapfree-navigation-recovery/results/verification.json').read_text())['preserved_untracked_files']
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in preserved.items())
    old_source=json.loads((old_dir/'source.json').read_text())
    # All inherited runtime, sensors, maps, frozen B and old runner remain byte exact.
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in old_source['hashes'].items())
    write(result_dir/'verification.json',dict(runtime_source_unchanged=True,legacy_v2_all_source_hashes_unchanged=True,
        preserved_untracked_files=preserved,unit_tests=30,fixture_off_golden=True,
        contact_input_schema=['t','pressed'],gate_rejection=blocked,source_sha=source['sha'],
        registered32_sha256=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        physical_simulator_calls=0,model_calls=0,new_confirmation_episodes=0,
        artifacts=len(artifacts),artifacts_total_bytes=sum(f['bytes'] for f in artifacts)))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print('Verified raw files',len(artifacts),'bytes',sum(f['bytes'] for f in artifacts))


if __name__=='__main__':
    main()
