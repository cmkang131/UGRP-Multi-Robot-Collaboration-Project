"""Read-only comparison of already-seen failures; does not run evaluation episodes."""
import hashlib
import json
from pathlib import Path
import sys
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-mapfree-navigation-recovery/code')]
from run_recovery import hashes,write,cohort,verify_gate


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    source=json.loads((a.input/'source.json').read_text())
    assert source['hashes']==hashes()
    rows=json.loads((a.input/'results.json').read_text())
    assert {(int(r['scenario'][1:]),r['start'],r['seed']) for r in rows}==set(cohort('diagnostic'))
    old_root=ROOT/'outputs/mapfree-public-navigation-confirmation-a-v1'
    details=[]
    for r in rows:
        name=f"{r['scenario']}-{r['start']}-{r['seed']}-{r['condition']}"
        old=json.loads((old_root/name/'result.json').read_text())
        log=[json.loads(x) for x in (a.input/name/'actor.jsonl').read_text().splitlines()]
        def view_metrics(logs):
            import numpy as np
            tracks={}
            for l in logs:
                for patch in l['patches']:
                    tracks.setdefault(patch['track_id'],[]).append(l['pose_odom'][:2])
            baselines=[float(np.max(np.linalg.norm(np.asarray(v)[:,None,:]-np.asarray(v)[None,:,:],axis=2)))
                       for v in tracks.values() if len(v)>=3]
            return dict(path_frames=sum(bool(l['plan']['path_m']) for l in logs),
                max_three_view_baseline_m=max(baselines,default=0.))
        oldlogs=[json.loads(x) for x in (old_root/name/'actor.jsonl').read_text().splitlines()]
        def compact(row,logs):
            return {**{k:row[k] for k in ('status','time_s','distance_m','coverage','collisions','navigation_events','sensor_draws')},**view_metrics(logs)}
        details.append(dict(pair=name,before=compact(old,oldlogs),after=compact(r,log)))
    summary=dict(cohort='already_seen_10_failure_diagnostic_not_confirmation',source_sha=source['sha'],
        before=dict(total=10,true_B=0,statuses=dict(Counter(d['before']['status'] for d in details))),
        after=dict(total=10,true_B=sum(r['status']=='B_confirmed' for r in rows),
            statuses=dict(Counter(r['status'] for r in rows))),
        stop_reason='SAME_CAUSE_RECURRED: projected footprint deadlock and unobserved can collision; no more patching or evaluation',
        new_confirmation=dict(registered=32,executed=0,gate='NOT_EVALUATED',stage_b='NOT_RUN',stage_c='NOT_RUN'),
        development_A_C='NOT_RUN: stop rule triggered by already-seen diagnostic first',
        criteria='unchanged; fresh criteria not evaluated; no pass claim')
    write(a.output/'summary.json',summary)
    write(a.output/'failure-comparison.json',details)
    lines=['| pair | before → after | time s | B visible | path frames | ≥3 view baseline m | predicted collision ticks |',
        '|---|---|---:|---:|---:|---:|---:|']
    for d in details:
        b,c=d['before'],d['after']
        lines.append(f"| {d['pair']} | {b['status']} → {c['status']} | {b['time_s']:.1f} → {c['time_s']:.1f} | "
            f"{b['sensor_draws']['B_positive_frames']} → {c['sensor_draws']['B_positive_frames']} | {b['path_frames']} → {c['path_frames']} | "
            f"{b['max_three_view_baseline_m']:.4g} → {c['max_three_view_baseline_m']:.4g} | "
            f"{b['navigation_events'].get('predicted_footprint_collision',0)} → {c['navigation_events'].get('predicted_footprint_collision',0)} |")
    (a.output/'tables.md').write_text('\n'.join(lines)+'\n')
    files=[]
    for f in sorted(a.input.rglob('*')):
        if f.is_file():
            files.append(dict(path=str(f.resolve()),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()))
    write(a.output/'artifacts.json',dict(files=files,count=len(files),bytes=sum(f['bytes'] for f in files)))
    original=json.loads((ROOT/'experiments/2026-10-07-mapfree-public-navigation/freeze.json').read_text())['hashes']
    checks={path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected for path,expected in original.items()}
    assert all(checks.values())
    try:
        verify_gate(a.input,'a',hashes())
    except ValueError as e:
        blocked=str(e)
    else:
        raise AssertionError('DIAGNOSTIC_MUST_NOT_PASS_CONFIRMATION_GATE')
    write(a.output/'verification.json',dict(runtime_source_unchanged=True,legacy_source_hashes=checks,
        diagnostic_rejected_as_gate=blocked,unit_tests=24,simulation_calls=0,model_calls=0,new_confirmation_episodes=0))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
