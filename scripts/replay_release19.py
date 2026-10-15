"""Manifest-verified release18 ledgers -> release19 look scheduler replay only.

No world, physics, renderer or remote connection. Ordered saved RGB feature
records are consumed at earlier times; this cannot predict a new trajectory.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from sim import release18, release19
from sim.lookaround_localization import ScriptRunner


def decoded(path):
    return subprocess.check_output(['zstd','-qdc',str(path)]) if path.suffix=='.zst' else path.read_bytes()


def load(raw, name):
    p=raw/name
    return decoded(p if p.exists() else raw/(name+'.zst'))


def verify_raw(raw):
    manifest=json.loads(load(raw,'manifest.json'))
    proofs=[]
    for name in ('result.json','teacher-r1.jsonl','teacher-r2.jsonl'):
        key=name if name in manifest else name+'.zst'
        meta=manifest[key];p=raw/key;payload=decoded(p)
        assert hashlib.sha256(p.read_bytes()).hexdigest()==meta['sha256'], str(p)
        digest=hashlib.sha256(payload).hexdigest()
        assert digest==meta.get('decoded_sha256',meta['sha256']), str(p)
        proofs.append(dict(path=str(p),sha256=meta['sha256'],decoded_sha256=digest))
    return proofs


def replay_sweep(sweep, rows, views, *, enabled):
    log=sweep['script'];start=log[0]['t'];end=sweep['t0']+sweep['sim_s']
    assert all(not e['label'].startswith('rotate') for e in log), 'unsupported rotating script'
    def row_at(at):
        return max((r for r in rows if r['t']<=at+1e-7),key=lambda r:r['t'])
    steps=[]
    for i,e in enumerate(log):
        stop=log[i+1]['t'] if i+1<len(log) else end
        steps.append(dict(label=e['label'],servo={int(k):v for k,v in row_at(e['t'])['pwm'].items()},
                          wait=round(stop-e['t'],6),capture=e['label'].startswith('view_')))
    teacher=SimpleNamespace(pwm={},holding=False)
    history=release18.CommandHistory()
    for r in rows:
        if r['t']>=start-1e-7:break
        teacher.pwm={int(k):v for k,v in r['pwm'].items()}
        teacher.holding=r['holding_belief'];history.observe(teacher.pwm,r['t'])
    args=dict(teacher=teacher,command_history=history,idle=lambda:True) if enabled else {}
    runner=(release19.ScriptRunner if enabled else ScriptRunner)(steps,start,**args)
    original=[v for v in views if start-1e-7<=v['t']<=end+1e-7]
    assert len(original)==sum(s['capture'] for s in steps)
    captured=[];issued=[]
    def set_servo(pose,now):
        delta={k:v for k,v in pose.items() if teacher.pwm.get(k)!=v}
        if delta:issued.append(delta)
        teacher.pwm.update(pose);history.observe(teacher.pwm,now)
    def capture(now):
        # Reuse saved own-input feature records in exactly their original order.
        value=copy.deepcopy(original[len(captured)])
        captured.append(dict(t=now,saved_world_t=value['t'],input_sha256=value['input_sha256'],
                             features_sha256=hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()))
    for k in range(200):
        now=start+k*.1;history.observe(teacher.pwm,now)
        runner.tick(now,set_servo=set_servo,set_wheels=lambda *a:(_ for _ in ()).throw(AssertionError('unexpected wheels')),
                    wheels_idle=lambda:True,capture=capture)
        if runner.done:break
    assert runner.done and len(captured)==len(original)
    if not enabled:
        assert abs(runner.end-end)<1e-6, ('stored scheduler end differs',runner.end,end)
        assert all(abs(a['t']-b['t'])<1e-6 for a,b in zip(captured,original))
    return dict(elapsed_s=round(runner.end-start,6),captures=captured,issued_commands=issued,
                reused_waits=getattr(runner,'reused_waits',[]))


def summarize(run):
    raw=Path(run['lite'])/'raw';proofs=verify_raw(raw)
    result=json.loads(load(raw,'result.json'))
    assert result['source_sha']=='a3bbc90e07d3d731278cb6c83185687a190e3c6b'
    expected={v['file']:v for v in run['decoded_verified']}
    for proof in proofs:
        name=Path(proof['path']).name
        meta=expected.get(name)
        if meta and 'decoded_sha256' in meta:
            assert proof['decoded_sha256']==meta['decoded_sha256'], (name,'diagnostic report hash mismatch')
    assert hashlib.sha256((raw/'result.json.zst').read_bytes()).hexdigest()==run['result_sha256']['sha256']
    rows={rid:[json.loads(x) for x in load(raw,f'teacher-{rid}.jsonl').splitlines()] for rid in ('r1','r2')}
    intervals=[]
    for i,row in enumerate(rows['r1']):
        end=rows['r1'][i+1]['t'] if i+1<len(rows['r1']) else row['t']+.1
        intervals.append(dict(start=row['t'],end=end,phase=row['teacher_phase']))
    sweeps=[]
    for rid,obs in result['lookaround_result'].items():
        for i,s in enumerate(obs['evaluation']['sweeps']):
            old=replay_sweep(s,rows[rid],obs['localizer']['views'],enabled=False)
            new=replay_sweep(s,rows[rid],obs['localizer']['views'],enabled=True)
            assert old['issued_commands']==new['issued_commands']
            assert [(v['input_sha256'],v['features_sha256']) for v in old['captures']]==[(v['input_sha256'],v['features_sha256']) for v in new['captures']]
            sweeps.append(dict(robot=rid,index=i,start_world_s=s['t0'],end_world_s=s['t0']+s['sim_s'],
                original_phase_s=round(s['sim_s'],6),omitted_wait_s=round(old['elapsed_s']-new['elapsed_s'],6),
                command_sequence_unchanged=True,ordered_input_hashes_unchanged=True,
                baseline=old,candidate=new))
    # Two robots sweep concurrently: count the slower one, never sum robot time.
    paired=[]
    for i in sorted({s['index'] for s in sweeps}):
        pair=[s for s in sweeps if s['index']==i]
        assert len(pair)==2 and max(s['start_world_s'] for s in pair)-min(s['start_world_s'] for s in pair)<1e-6
        before=max(s['baseline']['elapsed_s'] for s in pair)
        after=max(s['candidate']['elapsed_s'] for s in pair)
        paired.append(dict(index=i,start_world_s=pair[0]['start_world_s'],
                           omitted_wait_s=round(before-after,6)))
    choices=result['code_decisions'];epochs=[]
    for choice in [d for d in choices if d['action']=='shift']:
        stop=next(d['t'] for d in choices if d['t']>choice['t']+1e-6)
        totals=defaultdict(float)
        for v in intervals:
            totals[v['phase']]+=max(0.,min(v['end'],stop)-max(v['start'],choice['t']))
        saved=sum(s['omitted_wait_s'] for s in paired if choice['t']<s['start_world_s']<stop)
        baseline=stop-choice['t']
        epochs.append(dict(start_world_s=choice['t'],end_world_s=stop,shift_m=choice['shift_m'],
            phases_s={k:round(v,6) for k,v in totals.items() if v>1e-6},
            baseline_correction_s=round(baseline,6),candidate_scheduler_s=round(baseline-saved,6),
            omitted_wait_s=round(saved,6),physical_duration_prediction=None))
    return dict(seed=run['seed'],name=Path(run['lite']).name,source_sha=result['source_sha'],raw=str(raw),
                evidence=proofs,original_release_success=result['release_success'],
                input_audit=result['input_audit'],epochs=epochs,sweeps=sweeps,
                total_omitted_wait_s=round(sum(p['omitted_wait_s'] for p in paired),6),
                control_top_camera_reads=None,
                historical_top_camera_counter='not instrumented in a3bbc90e; do not infer runtime zero from source review')


def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report=json.loads(a.report.read_text())
    runs=[summarize(r) for r in report['runs']]
    epochs=[e for r in runs for e in r['epochs']]
    import statistics
    out=dict(schema='ugrp.release19.offline.v1',scope='same ordered stored own-RGB feature/issued-command trace; scheduler timing only',
        report_sha256=hashlib.sha256(a.report.read_bytes()).hexdigest(),simulation_calls=0,render_calls=0,
        remote_host_connections=0,new_physical_runs=0,physical_success_prediction=None,
        runs=runs,summary=dict(runs=len(runs),corrections=len(epochs),
            baseline_correction_median_s=statistics.median(e['baseline_correction_s'] for e in epochs),
            candidate_scheduler_median_s=statistics.median(e['candidate_scheduler_s'] for e in epochs),
            omitted_wait_per_correction_s=sorted({e['omitted_wait_s'] for e in epochs})))
    payload=(json.dumps(out,ensure_ascii=False,separators=(',',':'))+'\n').encode()
    if a.out.suffix=='.zst':
        payload_z=subprocess.check_output(['zstd','-q','-c'],input=payload)
        assert subprocess.check_output(['zstd','-qdc'],input=payload_z)==payload
        a.out.write_bytes(payload_z)
    else:a.out.write_bytes(payload)
    print(json.dumps(out['summary']))

if __name__=='__main__':main()
