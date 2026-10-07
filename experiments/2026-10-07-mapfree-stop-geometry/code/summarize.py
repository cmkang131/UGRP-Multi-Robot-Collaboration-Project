"""Record completed diagnostic/candidate results without opening confirmation."""
from collections import Counter
from pathlib import Path
import json
import hashlib
import sys
import audit as a
import run_outline as runner


def main():
    exp=a.EXP/'results';exp.mkdir(exist_ok=False)
    folder=a.OUT/'development-v4'
    before=a.load(a.OLD/'results.json');after=a.load(folder/'results.json')
    source=a.load(folder/'source.json')
    assert source['hashes']==runner.hashes()
    for n,h in source['hashes'].items():assert a.digest(a.ROOT/n)==h,n
    assert not runner.old.development_pass(after)
    try:runner.old.verify_development(folder,runner.hashes())
    except ValueError as e:assert str(e)=='DEVELOPMENT_GATE_FAILED_STOP_CONFIRMATION'
    else:raise AssertionError('FAILED_GATE_ADMITTED')
    for root in (a.OUT,Path('/Users/changmin/projects/ugrp/outputs/mapfree-navigation-persistence-v3')):
        assert not any(p.name.startswith('confirmation') for p in root.iterdir())
    # Match four raw input episodes to their preserved hashes.
    for name,h in a.load(a.OUT/'audit-v2/source.json')['inputs'].items():assert a.digest(name)==h
    comparisons=[]
    text=['# v3 → v4 개발10 (동일 자료, 새 확인 아님)','',
        '| 건 | B v3→v4 | 종료 v3→v4 s | 거리 v4 m | coverage v4 | 접촉 v4 | 종료 |',
        '|---|---:|---:|---:|---:|---:|---|']
    for b,r in zip(before,after):
        key=lambda x:(x['scenario'],x['start'],x['seed'])
        assert key(b)==key(r)
        name=f"{r['scenario']}-{r['start']}-{r['seed']}-static_map"
        assert a.load(folder/name/'result.json')==r
        same={}
        if r['scenario']=='s4' and r['start']=='G':
            for f in ['actor.jsonl','commands.jsonl','eval_path.json','own_grid.json','navigation_events.jsonl']:
                same[f]=a.digest(a.OLD/name/f)==a.digest(folder/name/f)
            assert all(same.values())
        comparisons.append(dict(case=name,before=b,after=r,s4_raw_parity=same))
        text.append(f"| {name} | {int(bool(b['first_B']))}→{int(bool(r['first_B']))} | {b['time_s']:.1f}→{r['time_s']:.1f} | {r['distance_m']:.4f} | {100*r['coverage']:.2f}% | {r['collisions']} | {r['status']} |")
    a.write(exp/'comparison.json',comparisons)
    (exp/'tables.md').write_text('\n'.join(text)+'\n')
    a.write(exp/'stop-geometry.json',a.load(a.OUT/'audit-v2/results.json'))
    a.write(exp/'oriented-certificates.json',a.load(a.OUT/'certificates/results.json'))
    a.write(exp/'development-results.json',after)
    summary=dict(source_sha=source['sha'],navigation='public_ros_v4',
        before=dict(true_B=sum(bool(x['first_B']) for x in before),valid=6,total=10),
        after=dict(true_B=sum(x['status']=='B_confirmed' for x in after),false_B=sum(x['status']=='B_false_confirmed' for x in after),
                   collisions=sum(x['collisions'] for x in after),statuses=dict(Counter(x['status'] for x in after))),
        development_gate=False,unopened_confirmation_runs=0,frontier_runs=0,noisy_runs=0,
        stop_reason='S4_IDENTICAL_GEOMETRIC_RASTER_REJECTION_AND_PINNED_RR_ABORT_RECURRED',
        parameters_unchanged=True,unit_tests=27,physics=0,model_calls=0,render=0)
    a.write(exp/'summary.json',summary)
    files=[]
    for p in sorted(a.OUT.rglob('*')):
        if p.is_file():files.append(dict(path=str(p),bytes=p.stat().st_size,sha256=a.digest(p)))
    a.write(exp/'artifacts.json',dict(files=files,total_bytes=sum(x['bytes'] for x in files)))
    expected={'analyze_wall_detection.py':'26c818f1cd4673c7f4a1b6ab535b4e70ac68167f1f56989f10c8c6bebe0c3dd0','create_wall_visualizations.py':'e2b77c1f678d1ba27658dffecf99bcf7bfd7c12c056d41869a7a38cc482f8efa','create_wall_visualizations_v2.py':'8e6fa7f6598336bc6f7c61ad956d1902be9925443d7656cea2801362195d83c8','parameter_probe.py':'43f91584406ba91a73032514b8409357fc9c7ac2c3cbc3e72d26bce5257e103b'}
    for n,h in expected.items():assert a.digest(a.ROOT/n)==h
    a.write(exp/'verification.json',dict(runtime_source_hashes=source['hashes'],original_snapshot_input_hashes_verified=True,
        reconstructed_own_grids=4,s4_raw_bytes_equal=10,failed_development_rejected=True,
        preserved_user_untracked_hashes=expected,raw_files=len(files),raw_bytes=sum(x['bytes'] for x in files)))
    print(json.dumps(summary,ensure_ascii=False));print('RAW',len(files),sum(x['bytes'] for x in files))


if __name__=='__main__':main()
