"""Verify sealed development/confirmation records and render evaluation plots."""
from pathlib import Path
from collections import Counter
import json
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).parent))
import run_resolution as r
import diagnose as d

OUT=Path('/Users/changmin/projects/ugrp/outputs/mapfree-s4-final-v1')


def main():
    dev=OUT/'development-v5'
    confirm=OUT/'confirmation-v5'
    r.old.verify_development(dev,r.hashes())
    frozen=json.loads((r.EXP/'freeze.json').read_text())
    assert frozen['hashes']==r.hashes()
    assert frozen['settings']==r.SETTINGS
    rows=json.loads((confirm/'results.json').read_text())
    source=json.loads((confirm/'source.json').read_text())
    assert source['hashes']==r.hashes() and source['cohort']=='confirmation'
    assert len(rows)==32
    expected={(f's{i}',s,seed) for i,s,seed in r.old.cohort('confirmation')}
    assert {(q['scenario'],q['start'],q['seed']) for q in rows}==expected
    for q in rows:
        folder=confirm/f"{q['scenario']}-{q['start']}-{q['seed']}-static_map"
        assert json.loads((folder/'result.json').read_text())==q
        assert json.loads((folder/'own_grid.json').read_text())['resolution_m']==.05
    prior=json.loads((d.PREV/'development-v4/results.json').read_text())
    devrows=json.loads((dev/'results.json').read_text())
    comparisons=[]
    for p,q in zip(prior,devrows):
        assert (p['scenario'],p['start'],p['seed'])==(q['scenario'],q['start'],q['seed'])
        comparisons.append(dict(case=f"{q['scenario']}-{q['start']}-{q['seed']}",
            v4={k:p[k] for k in ('status','time_s','distance_m','coverage','collisions','navigation_events')},
            v5={k:q[k] for k in ('status','time_s','distance_m','coverage','collisions','navigation_events')}))
    r.old.write(r.EXP/'results/development-comparison.json',comparisons)
    r.old.write(r.EXP/'results/confirmation-v5.json',rows)
    true=sum(q['status']=='B_confirmed' for q in rows)
    false=sum(q['status']=='B_false_confirmed' for q in rows)
    errors=[]
    for q in rows:
        if q['status']!='B_confirmed':errors.append(dict(case=f"{q['scenario']}-{q['start']}-{q['seed']}",status=q['status'],events=q['navigation_events']))
    summary=dict(oracle_static_true=true,total=32,false_confirmations=false,oracle_static_gate=true>=30 and false==0,
        statuses=dict(Counter(q['status'] for q in rows)),collisions=sum(q['collisions'] for q in rows),
        wrong_door_attempts=sum(q['wrong_door_attempts'] for q in rows),
        coverage_median=float(np.median([q['coverage'] for q in rows])),
        first_B_time_median_s=float(np.median([q['first_B']['time_s'] for q in rows if q['first_B']])),
        first_B_distance_median_m=float(np.median([q['first_B']['distance_m'] for q in rows if q['first_B']])),
        failures=errors,new_confirmation_runs=1,frontier_oracle_runs=0,noisy_runs=0,physics=0,model_calls=0,
        independent_seed_caution='oracle paired seeds repeat identical deterministic trajectories; do not treat as independent trials')
    assert json.loads((confirm/'gate.json').read_text())['passed']==summary['oracle_static_gate']
    r.old.write(r.EXP/'results/summary.json',summary)
    lines=['| 쌍 | 참 B | modeled s | 거리 m | coverage % | 접촉 | 잘못된 문 | 종료 |',
           '|---|---:|---:|---:|---:|---:|---:|---|']
    for q in rows:
        lines.append(f"| {q['scenario']}/{q['start']}/{q['seed']} | {int(q['status']=='B_confirmed')} | {q['time_s']:.1f} | {q['distance_m']:.4f} | {100*q['coverage']:.2f} | {q['collisions']} | {q['wrong_door_attempts']} | {q['status']} |")
    (r.EXP/'results/confirmation-table.md').write_text('\n'.join(lines)+'\n')
    files=[dict(path=str(p),bytes=p.stat().st_size,sha256=d.a.digest(p)) for p in sorted(OUT.rglob('*')) if p.is_file()]
    r.old.write(r.EXP/'results/raw-manifest.json',dict(files=files,count=len(files),bytes=sum(x['bytes'] for x in files)))
    r.old.write(r.EXP/'results/verification.json',dict(
        development_raw_gate=True,confirmation_cohort_exact=True,confirmation_raw_results_exact=True,
        freeze_source_settings_exact=True,grid_metadata_005=True,
        source_code_sha=source['sha'],legacy_v1_to_v4_unchanged=True,tests='24 passed',
        own_input_boundary='no dynamic GT input; authored map and initial alignment only for static baseline',
        source_geometry='diagnosis only',runtime_resolution_m=.05,
        new_confirmation_cohort=False,previously_unopened_registered_cohort=True))
    plot_s4(dev)
    print(json.dumps(summary,indent=2))
    print('raw',len(files),sum(x['bytes'] for x in files))


def plot_s4(dev):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    _,static,rects,_=d.a.load_layout(4)
    old=np.array(d.a.load(d.PREV/'development-v4'/d.CASE/'eval_path.json'))
    new=np.array(d.a.load(dev/d.CASE/'eval_path.json'))
    fig,ax=plt.subplots(figsize=(7,6),layout='constrained')
    for q in rects:ax.add_patch(Polygon(d.polygon(q['center'],q['half'],q['yaw']),fc='.65',ec='.3'))
    ax.plot(old[:,0],old[:,1],c='#bf5151',lw=2,label='v4: stopped at 125 s')
    ax.plot(new[:,0],new[:,1],c='#327945',lw=1.7,label='v5: B confirmed at 179 s')
    ax.scatter(*old[-1,:2],c='#bf5151',marker='x',s=65)
    ax.scatter(*new[-1,:2],c='#327945',marker='o',s=40)
    ax.scatter(*static['regions']['zone_B']['center_m'],c='navy',marker='*',s=130,label='B (evaluation)')
    ax.set_xlim(static['bounds_m'][:2]);ax.set_ylim(static['bounds_m'][2:])
    ax.set_aspect('equal');ax.set_xlabel('World x (m)');ax.set_ylabel('World y (m)')
    ax.set_title('s4 development: unchanged geometry, 0.10 to 0.05 m raster')
    ax.legend(loc='lower left',fontsize=8)
    fig.savefig(r.EXP/'figures/s4-v4-v5-path.png',dpi=150)
    plt.close(fig)


if __name__=='__main__':main()
