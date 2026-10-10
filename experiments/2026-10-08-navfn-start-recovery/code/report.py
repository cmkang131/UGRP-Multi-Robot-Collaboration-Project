"""Sealed egomap47 prediction versus GT evaluation; existing metric definitions."""
from pathlib import Path
import importlib.util,json,sys,hashlib
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/navfn-start-recovery-v1');EP=RAW/'new-seed'
from scripts.run_active_wall_rotleft import dump

def load(p):return json.loads(p.read_text())
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    source=ROOT/'experiments/2026-10-08-frontier-duration'
    sys.path.insert(0,str(source/'code'))
    duration=module('duration_report',source/'code/report.py')
    m=module('wall_report',ROOT/'experiments/2026-10-08-wall-segment-dev/code/physical_report.py')
    m.EXP=EXP;m.RAW=RAW;m.EP=EP
    metric=m.metrics_module();metric.verify(EP)
    metric.evaluate('new-seed',partial=load(EP/'result.json')['prediction_view']!='completed_graph')
    extra=module('visibility_report',ROOT/'experiments/2026-10-08-frontier-visibility/code/report.py').extras(EP)
    fresh=load(EXP/'results/new-seed.json');completed=fresh['acquisition']['status']=='RECORDED' and fresh['acquisition']['frames']==1801
    criteria=dict(coverage_ge_080=fresh['full_map']['wall_coverage']>=.80,
        region_precision_ge_0636=fresh['observed_region']['precision'] is not None and fresh['observed_region']['precision']>=.636)
    row=dict(condition='egomap47 B+start',seed=47001,budget_s=360,n=1,result=fresh,extra=extra,
        curve=duration.curve(EP),criteria=criteria,criteria_count=sum(criteria.values()),
        completed_360s=completed,passed=completed and all(criteria.values()))
    prior=[load(source/'conditions'/c/'results/report.json') for c in 'AB']
    dump(EXP/'results/comparison.json',dict(conditions=prior+[row],no_pooling=True,
        qualification='egomap46 A/B seed46001 pair; egomap47 fresh seed47001 DEV1, not a same-seed causal estimate'))
    dump(EXP/'results/report.json',row)
    m.movie()
    dump(EXP/'results/raw.json',dict(root=str(EP),source_sha=fresh['acquisition']['source_sha'],
        artifact_manifest_sha256=sha(EP/'artifacts.sha256.json'),scene_sha256=sha(EP/'scene.xml'),
        static_map_sha256=sha(EP/'inputs/static_map.json')))
    sys.path.insert(0,str(ROOT/'outputs/self-map-plot-deps'))
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4.5))
    for r in prior+[row]:
        valid=[x for x in r['curve'] if 'coverage' in x]
        ax.plot([x['elapsed_s'] for x in valid],[100*x['coverage'] for x in valid],'o-',label=f'{r["condition"]} seed{r["seed"]}')
    ax.axhline(80,color='gray',linestyle=':',label='registered80%')
    ax.set(xlabel='Elapsed SIM time (s)',ylabel='Coverage (%)',xticks=[120,180,240,360],ylim=(0,100),
        title='360s conditions separately; causal online frontend snapshots')
    ax.grid(alpha=.2);ax.legend();fig.tight_layout();fig.savefig(EXP/'figures/coverage.png',dpi=140);plt.close(fig)
    print(json.dumps(dict(criteria=criteria,completed=completed,extra=extra,curve=row['curve']),indent=2))

if __name__=='__main__':main()
