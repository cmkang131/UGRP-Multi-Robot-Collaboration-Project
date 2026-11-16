"""egomap45 sealed offline evaluation and reuse of chronological 4x movie."""
from pathlib import Path
import sys,json,importlib.util,math,collections,hashlib
import numpy as np
ROOT=Path('/Users/changmin/projects/ugrp-wt/ego-wall-map');sys.path.insert(0,str(ROOT))
EXP=ROOT/'experiments/2026-10-08-frontier-visibility'
RAW=Path('/Users/changmin/projects/ugrp/outputs/frontier-visibility-v1');EP=RAW/'new-seed'
from scripts.run_active_wall_rotleft import dump
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap

def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def report_module():
    spec=importlib.util.spec_from_file_location('egomap34_reporting',ROOT/'experiments/2026-10-08-wall-segment-dev/code/physical_report.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.EXP=EXP;m.RAW=RAW;m.EP=EP
    return m

def extras(ep):
    tr=rows(ep/'own-controller.jsonl');actual=rows(ep/'eval_only/trajectory.jsonl')
    truth={round(r['t'],6):r for r in actual};origin=[*actual[0]['robot_xyz_m'][:2],actual[0]['robot_yaw_rad']]
    c=rows(ep/'frontend-covariances.jsonl')
    gt=np.array([truth[round(r['t'],6)]['robot_xyz_m'][:2] for r in c]);p=transform([r['pose'][:2] for r in c],origin)
    err=np.linalg.norm(p-gt,axis=1);sig=np.array([np.sqrt(np.linalg.eigvalsh(np.array(r['covariance'])[:2,:2]).max()) for r in c])
    crossings=[]
    for a,b in zip(actual,actual[1:]):
        ax,ay=a['robot_xyz_m'][:2];bx,by=b['robot_xyz_m'][:2]
        if ax>2.2>=bx:
            f=(2.2-ax)/(bx-ax);y=ay+f*(by-ay)
            theta=a['robot_yaw_rad']+f*float(wrap(b['robot_yaw_rad']-a['robot_yaw_rad']))
            for name,lo,hi in [('middle',-.2,.3),('lower',-3.125,-2.125)]:
                if lo<y<hi:
                    half=.14*abs(math.sin(theta))+.12*abs(math.cos(theta))
                    crossings.append(dict(t=b['t'],door=name,y=y,padded_footprint_margin_m=min(y-lo,hi-y)-half,
                        later_center_left=any(r['robot_xyz_m'][0]<2.175 for r in actual if r['t']>=b['t'])))
    contacts={'wall':[],'robot':[]}
    for row in rows(ep/'eval_only/contacts.jsonl'):
        present=set()
        for pair in row['contacts']:
            ns=[pair['geom1'] or '',pair['geom2'] or '']
            if any(n.startswith('r3__') for n in ns):
                if any('wall' in n for n in ns):present.add('wall')
                if any(n.startswith(('r1__','r2__')) for n in ns):present.add('robot')
        for k in present:contacts[k].append(row['t'])
    dec=load(ep/'decisions.json');events=load(ep/'navigation.json')
    return dict(hold_n=sum(r['command']['kind']=='hold' for r in tr),n=len(tr),
        hold_fraction=sum(r['command']['kind']=='hold' for r in tr)/len(tr),
        frontend=dict(endpoint_error_m=float(err[-1]),sigma_xy_m=float(sig[-1]),overconfidence_ratio=float(err[-1]/sig[-1]),
            path_rmse_m=float(np.sqrt(np.mean(err**2)))),
        insertions=len(load(ep/'frontend-ledger.json')),decisions=dict(collections.Counter((str(d.get('status'))+':'+str(d.get('reason'))) for d in dec)),
        geometry_frames=sum(bool(r['wall_segments']) for r in tr),rgb_frames=len(rows(ep/'robots/r3/frames.jsonl')),
        door_crossings=crossings,confirmed_left_crossings=sum(c['later_center_left'] for c in crossings),
        contact_frames={k:len(v) for k,v in contacts.items()},
        contact_events={k:sum(i==0 or t-v[i-1]>.201 for i,t in enumerate(v)) for k,v in contacts.items()},
        event_counts=dict(collections.Counter(e['reason'] for e in events)),
        sweep_events=[e for e in events if e['reason'].startswith('sensor_sweep')],
        no_frontier_times=[e['t'] for e in events if e['reason']=='exploration_finished_no_frontier'])

def main():
    m=report_module();metrics=m.metrics_module();metrics.verify(EP)
    partial=load(EP/'result.json')['prediction_view']!='completed_graph'
    metrics.evaluate('new-seed',partial=partial)
    old_ep=Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')
    baseline=load(ROOT/'experiments/2026-10-08-wall-segment-dev/results/new-seed.json')
    fresh=load(EXP/'results/new-seed.json');new=extras(EP);old=extras(old_ep)
    gate=dict(recorded_180s=fresh['acquisition']['status']=='RECORDED' and fresh['acquisition']['frames']==901,
        left_door_crossing=new['confirmed_left_crossings']>=1,
        visible_wall_samples=fresh['observed_region']['visible_samples']>146,
        wall_coverage=fresh['full_map']['wall_coverage']>213/329,
        no_wall_or_robot_contact=not any(new['contact_frames'].values()))
    dump(EXP/'results/comparison.json',dict(baseline=baseline,fresh=fresh,baseline_extra=old,fresh_extra=new,
        operational_gate=gate,passed=sum(gate.values()),total=len(gate),n=1,
        qualification='one fresh-seed MuJoCo DEV vs one development baseline, NOT causal confirmation; old quality gate not reapplied'))
    m.movie()
    dump(EXP/'results/raw.json',dict(root=str(RAW),physics_source=fresh['acquisition']['source_sha'],
        preregistration='d19fe326',prediction_manifest_sha256=hashlib.sha256((EP/'artifacts.sha256.json').read_bytes()).hexdigest()))
    print(json.dumps(dict(gate=gate,new=new),indent=2))
if __name__=='__main__':main()
