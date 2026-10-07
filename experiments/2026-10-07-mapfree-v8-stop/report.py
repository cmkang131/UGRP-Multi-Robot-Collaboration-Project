"""Aggregate sealed v8 stop evidence; no new episodes or parameter selection."""
from pathlib import Path
from collections import Counter
import sys,json,csv
import numpy as np
sys.path.insert(0,str(Path(__file__).parent/'code'))
from stop_common import *
from gate import summary


def case(r):return f"{r['scenario']}-{r['start']}-{r['seed']}-{r['condition']}"


def main():
    raw=RAW/'development'
    source=read(raw/'source.json')
    assert hashes()==read(EXP/'freeze.json')['hashes']==source['hashes']
    rows=read(raw/'results.json')
    decision=summary(rows,True)
    decision.update(split='development',next_stage='REGISTER_NEW_COHORT' if decision['passed'] else 'STOP_TRACK_FINAL',
        observation_wait_stop_verified=True)
    assert decision==read(raw/'gate.json') and not decision['passed']
    waits=[]
    monitor_counts=Counter()
    active_counts=Counter()
    hold_counts=Counter()
    issues=[]
    for r in rows:
        folder=raw/case(r)
        assert r==read(folder/'result.json')
        checks=read(folder/'eval_wait_checks.json')
        assert len(checks)==r['observations']
        waits.extend(checks)
        mon=read(folder/'monitor.json')
        monitor_counts.update(m['reason'] for m in mon)
        active_counts.update(m['reason'] for m in mon if m.get('phase')!='observation_wait')
        hold_counts.update(m['reason'] for m in mon if m.get('phase')=='observation_wait')
        logs=lines(folder/'actor.jsonl')
        contacts=lines(folder/'eval_contacts.jsonl')
        assert len(contacts)==r['collisions']
        if r['condition']=='own_frontier' and (r['status']!='B_confirmed' or r['collisions'] or r['false_candidate_passage_attempts'] or r['wrong_door_attempts']):
            events=lines(folder/'navigation_events.jsonl')
            detail=[]
            for event in contacts:
                last=max((a for a in logs if a['t']<=event['t']),key=lambda a:a['t'])
                detail.append(dict(**event,last_camera_t=last['t'],phase='action',
                    since_camera_s=event['t']-last['t']))
            issues.append(dict(case=case(r),status=r['status'],time_s=r['time_s'],
                B_visible=r['sensor_draws']['B_positive_frames'],B_detected=r['sensor_draws']['B_detections'],
                collisions=r['collisions'],false_passages=r['false_candidate_passage_attempts'],
                wrong_doors=r['wrong_door_attempts'],contacts=detail,last_events=events[-8:]))
    assert all(w['distance_m']==0. and w['pose_delta']==[0.,0.,0.] and
        w['max_abs_model_velocity']==0. and w['new_contacts']==0 for w in waits)
    write(EXP/'results/stop-verification.json',dict(episodes=len(rows),wait_intervals=len(waits),
        wait_ticks=sum(hold_counts.values()),max_wait_distance_m=max(w['distance_m'] for w in waits),
        max_wait_velocity=max(w['max_abs_model_velocity'] for w in waits),new_wait_contacts=0,
        active_monitor=dict(active_counts),wait_monitor=dict(hold_counts),all_monitor=dict(monitor_counts),
        source_sha=source['sha'],frozen_source_paths=len(hashes()),unchanged_v7_paths=121))
    write(EXP/'results/gate.json',decision)
    write(EXP/'results/episodes.json',rows)
    write(EXP/'results/failures.json',issues)
    fields=['scenario','start','seed','condition','status','time_s','distance_m','coverage','collisions',
        'wrong_door_attempts','false_candidate_passage_attempts','door_attempts']
    with (EXP/'results/episodes.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)

    prior=read(EXP/'results/prior-events.json')
    table=['|기존 사건|시각(s)|판정/가시성|경로·후보 칸|실제 짧은 경로 접촉|',
        '|---|---:|---|---|---|']
    for r in prior['rows']:
        for e in r['false_passages']:
            table.append(f"|{r['case']} / 거짓 후보|{e['t']:.1f}|{e['candidate']['reason']}; authored 중심 거리 {e['nearest_authored_passage_m']:.3f}m|중심선9칸 free; 후보 {e['candidate_raw']}|없음|")
        for e in r['action_contacts']:
            table.append(f"|{r['case']} / 접촉|{e['contact']['t']:.2f}|wall_divider_1; 해당 벽 관측0/79, monitor clear|중심선9칸/footprint36칸 free|wall_divider_1|")
    (EXP/'results/prior-events.md').write_text('\n'.join(table)+'\n')

    # Historical cohorts are kept distinct. v6 never ran a full mission.
    root=ROOT/'experiments'
    v5s=read(root/'2026-10-07-mapfree-s4-final/results/confirmation-v5.json')
    versions=[dict(version='v5',cohort='I/J5701–5702 확인',mode='static oracle',n=32,
        true_B=sum(r['status']=='B_confirmed' for r in v5s),false_B=0,
        coverage_median=float(np.median([r['coverage'] for r in v5s])),collisions=sum(r['collisions'] for r in v5s),
        wrong_doors=sum(r['wrong_door_attempts'] for r in v5s),false_passage=sum(r['false_candidate_passage_attempts'] for r in v5s),
        gate='정적 선행32/32≥30/32')]
    for version,path,cohort in [
        ('v5',root/'2026-10-07-mapfree-frontier-oracle/results/gate.json','K/L6701–6702 확인'),
        ('v7',root/'2026-10-07-mapfree-unknown-footprint/results/gate.json','M/N7701–7702 확인→개발'),
        ('v8 수정 전',v8.EXP/'results/gate.json','동일 M/N32 개발'),
        ('v8 정지 수정',EXP/'results/gate.json','동일 M/N32 개발 재진단')]:
        g=read(path)
        versions.append(dict(version=version,cohort=cohort,mode='frontier oracle',**g['conditions']['own_frontier'],
            gate=f"{g['criteria_passed']}/5"))
    versions.insert(2,dict(version='v6',cohort='K/L32 첫 관측 개발',mode='연결 진단만',n=32,
        true_B=None,false_B=None,coverage_median=None,collisions=None,wrong_doors=None,false_passage=None,
        gate='유효 경로0/32; 임무 미실행'))
    write(EXP/'results/v5-v8.json',versions)
    table=['|버전|코호트/조건|B 참/분모(거짓)|coverage 중앙|접촉|잘못된 문|거짓 후보|관문|',
        '|---|---|---:|---:|---:|---:|---:|---|']
    for r in versions:
        b='미측정' if r['true_B'] is None else f"{r['true_B']}/32 ({r['false_B']})"
        cov='미측정' if r['coverage_median'] is None else f"{100*r['coverage_median']:.2f}%"
        value=lambda k:'미측정' if r[k] is None else str(r[k])
        table.append(f"|{r['version']}|{r['cohort']} / {r['mode']}|{b}|{cov}|{value('collisions')}|{value('wrong_doors')}|{value('false_passage')}|{r['gate']}|")
    (EXP/'results/v5-v8.md').write_text('\n'.join(table)+'\n')
    files=[dict(path=str(p.relative_to(RAW)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(RAW.rglob('*')) if p.is_file()]
    write(EXP/'results/raw-manifest.json',dict(root=str(RAW),files=files,
        total_bytes=sum(r['bytes'] for r in files),remote_backup=False))
    print(json.dumps(dict(gate=decision,waits=len(waits),monitor=monitor_counts,raw_files=len(files),raw_bytes=sum(r['bytes'] for r in files)),indent=2))


if __name__=='__main__':main()
