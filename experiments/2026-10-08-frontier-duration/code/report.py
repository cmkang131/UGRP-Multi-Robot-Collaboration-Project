"""egomap46 post-seal scores, causal coverage curves and two separate movies."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/frontier-duration-v1')
from scripts.run_active_wall_rotleft import dump
from harness.self_odom_grid import transform
from timeline import select_snapshots


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def curve(ep):
    result=load(ep/'result.json');cap=load(ep/'bundle.json')['case_cap_s']
    start=result['start_sim_s'];end=result['total_sim_s']
    actual=rows(ep/'eval_only/trajectory.jsonl');origin=[*actual[0]['robot_xyz_m'][:2],actual[0]['robot_yaw_rad']]
    static=load(ep/'inputs/static_map.json')
    rects=np.array([r['center_m']+r['half_extents_m'] for r in static['obstacles'] if r.get('kind')=='wall'])
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metrics
    samples=metrics.wall_samples(rects)
    snapshots=select_snapshots(rows(ep/'online-maps.jsonl'),start=start,end=end)
    output=[]
    for r in snapshots:
        if r['elapsed_s']>cap:
            output.append(dict(elapsed_s=r['elapsed_s'],status='not_applicable_budget'));continue
        snap=r.pop('snapshot');row=dict(**r)
        if r['status']=='censored':output.append(row);continue
        cells=np.array([c for c in snap['grid']['cells'] if c[2]>0]).reshape(-1,3) if snap else np.empty((0,3))
        xy=transform((cells[:,:2]+.5)*.1,origin)
        q,covered=metrics.quality(xy,rects,samples)
        row.update(coverage=q['wall_coverage'],covered_wall_samples=int(covered.sum()),total_wall_samples=len(samples),
            occupied_cells=len(cells),mapped_scans=len(snap['ledger']) if snap else 0,
            snapshot_elapsed_s=snap['t']-start if snap else None,view='online_frontend_past_only')
        output.append(row)
    return output


def condition(name):
    ep=RAW/name/'new-seed';exp=EXP/'conditions'/name
    m=module('egomap34_reporting',ROOT/'experiments/2026-10-08-wall-segment-dev/code/physical_report.py')
    m.EXP=exp;m.RAW=RAW/name;m.EP=ep
    metric=m.metrics_module();metric.verify(ep)
    metric.evaluate('new-seed',partial=load(ep/'result.json')['prediction_view']!='completed_graph')
    previous=module('egomap45_reporting',ROOT/'experiments/2026-10-08-frontier-visibility/code/report.py')
    fresh=load(exp/'results/new-seed.json');extra=previous.extras(ep)
    criteria=dict(coverage_ge_080=fresh['full_map']['wall_coverage']>=.80,
        region_precision_ge_0636=fresh['observed_region']['precision'] is not None and fresh['observed_region']['precision']>=.636)
    completed=fresh['acquisition']['status']=='RECORDED' and fresh['acquisition']['frames']==1801
    report=dict(condition=name,seed=46001,budget_s=360,n=1,result=fresh,extra=extra,curve=curve(ep),
        criteria=criteria,criteria_count=sum(criteria.values()),completed_360s=completed,
        passed=completed and all(criteria.values()),
        qualification='Separate360s_condition; no pooling with180s or across A/B; criterion fixed12915e74')
    dump(exp/'results/report.json',report)
    m.movie()
    dump(exp/'results/raw.json',dict(root=str(ep),source_sha=fresh['acquisition']['source_sha'],
        artifact_manifest_sha256=sha(ep/'artifacts.sha256.json'),scene_sha256=sha(ep/'scene.xml'),
        static_map_sha256=sha(ep/'inputs/static_map.json')))
    print(json.dumps(dict(condition=name,criteria=criteria,completed=completed,curve=report['curve']),indent=2))


def summary():
    allrows=[]
    old=[('egomap34',ROOT/'experiments/2026-10-08-wall-segment-dev/results/new-seed.json',
          Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')),
         ('egomap45',ROOT/'experiments/2026-10-08-frontier-visibility/results/new-seed.json',
          Path('/Users/changmin/projects/ugrp/outputs/frontier-visibility-v1/new-seed'))]
    extra=module('egomap45_reporting',ROOT/'experiments/2026-10-08-frontier-visibility/code/report.py')
    for label,file,ep in old:
        allrows.append(dict(condition=label,budget_s=180,seed=load(ep/'bundle.json')['task']['seed'],n=1,
            result=load(file),extra=extra.extras(ep),curve=curve(ep),qualification='historical development; separate180s'))
    for name in ('A','B'):allrows.append(load(EXP/'conditions'/name/'results/report.json'))
    a,b=[load(EXP/'conditions'/name/'results/raw.json') for name in ('A','B')]
    assert a['source_sha']==b['source_sha'] and a['scene_sha256']==b['scene_sha256'] and a['static_map_sha256']==b['static_map_sha256']
    dump(EXP/'results/comparison.json',dict(conditions=allrows,no_pooling=True,paired_fresh_seed=46001,
        same_source_scene_map=True,source_sha=a['source_sha']))
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4.5))
    for row in allrows:
        valid=[r for r in row['curve'] if 'coverage' in r]
        ax.plot([r['elapsed_s'] for r in valid],[r['coverage']*100 for r in valid],
            'o--' if row['budget_s']==180 else 'o-',label=f'{row["condition"]} / {row["budget_s"]}s / seed{row["seed"]}')
        for r in valid:ax.annotate(str(r['occupied_cells'])+' cells',(r['elapsed_s'],r['coverage']*100),xytext=(0,6),textcoords='offset points',fontsize=7)
    ax.axhline(80,color='gray',linestyle=':',label='preregistered80%')
    ax.set(xlabel='Elapsed SIM time (s)',ylabel='Covered walls (%)',xticks=[120,180,240,360],ylim=(0,100),
        title='Causal online frontend snapshots;180s and360s are separate cohorts')
    ax.legend(fontsize=8);ax.grid(alpha=.2);fig.tight_layout();(EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/coverage.png',dpi=140);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('condition',choices=['A','B','summary']);a=p.parse_args()
    summary() if a.condition=='summary' else condition(a.condition)
