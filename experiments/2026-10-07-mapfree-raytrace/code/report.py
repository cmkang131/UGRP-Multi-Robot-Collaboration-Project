"""Read-only reconstruction of first-view diagnostics; no mission or tuning."""
from collections import Counter
import math
from common import *
from development import diagnose
from harness.public_navigation_resolution import ResolutionActor
from harness.public_navigation_persistent import raytrace_cells
import numpy as np


def connector(actor, data):
    cm, connected, pose, frontiers = data
    start = cm.world_to_map(pose[:2])
    yy,xx=np.nonzero(cm.costs<253)
    cells=np.column_stack([xx,yy])
    points=cm.map_to_world(cells)
    route=None
    for f in frontiers:
        for cell in cells[np.linalg.norm(points-f[:2],axis=1)<=.5]:
            found=actor.navigator.core.plan(cm.costs,start,tuple(cell))
            if len(found):
                route=found
                break
        if route is not None:break
    assert route is not None
    end=np.r_[cm.map_to_world(route)[0],pose[2]]
    steps=max(1,math.ceil(np.linalg.norm(end[:2]-pose[:2])/.025))
    checks=[]
    for u in np.linspace(0,1,steps+1):
        p=pose+u*(end-pose)
        _,polygon=cm.footprint_mask(p)
        corners=[cm.world_to_map(q) for q in polygon]
        assert None not in corners
        perimeter={cell for x,y in zip(corners,corners[1:]+corners[:1]) for cell in raytrace_cells(x,y)}
        bad=[dict(cell=list(c),xy=cm.map_to_world(c).tolist(),raw=int(cm.raw[c[1],c[0]]),cost=int(cm.costs[c[1],c[0]]))
             for c in sorted(perimeter) if cm.costs[c[1],c[0]]>=254]
        checks.append(dict(u=float(u),pose=p.tolist(),clear=cm.pose_clear(p),bad=bad))
    plan=actor.plan()  # same initial observation only, no command execution
    return dict(start_pose=pose.tolist(),first_path_point=end.tolist(),distance_m=float(np.linalg.norm(end[:2]-pose[:2])),
                checks=checks,initial_plan_status=plan['status'],initial_path_length=len(plan['path_m']),
                initial_navigation_events=actor.navigator.events)


def figure(before, after, detail, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Polygon,Patch
    fig,axes=plt.subplots(1,3,figsize=(12,4),layout='constrained')
    cmap=ListedColormap(['#b8bec6','#ffffff','#333333'])
    for ax,data,title in zip(axes,[before,after,after],['v5: 36 connected cells','v6: 1,474 connected cells','v6: first 3.54 cm connector rejected']):
        m,conn,pose,frontiers=data
        extent=[m.origin[0],m.origin[0]+m.raw.shape[1]*m.resolution,m.origin[1],m.origin[1]+m.raw.shape[0]*m.resolution]
        state=np.where(m.raw==255,0,np.where(m.raw==254,2,1))
        ax.imshow(state,origin='lower',extent=extent,cmap=cmap,vmin=0,vmax=2,interpolation='nearest')
        _,poly=m.footprint_mask(pose)
        ax.add_patch(Polygon(poly,fill=False,color='#136f8a',lw=1.3))
        ax.plot(*pose[:2],'+',color='#136f8a')
        ax.set(title=title,xlabel='own x (m)',ylabel='own y (m)',xlim=(-.3,3.4),ylim=(-1.4,1.4),aspect='equal')
    m=after[0]
    failed=next(c for c in detail['checks'] if not c['clear'])
    _,poly=m.footprint_mask(failed['pose'])
    axes[2].add_patch(Polygon(poly,fill=False,color='#b62947',lw=1.5,ls='--'))
    axes[2].scatter([b['xy'][0] for b in failed['bad']],[b['xy'][1] for b in failed['bad']],marker='s',s=100,facecolors='none',edgecolors='#b62947')
    p=np.array([detail['start_pose'],detail['first_path_point']])
    axes[2].plot(p[:,0],p[:,1],'-o',color='#b62947',ms=3)
    axes[2].scatter([.1252442319520474,.21213326744820363],[0,0],marker='x',c='#6c43a1',s=40,label='Camera XY origins')
    axes[2].set(xlim=(-.2,.45),ylim=(-.22,.22),xticks=np.arange(-.2,.451,.05),yticks=np.arange(-.2,.21,.05))
    axes[2].tick_params(axis='x',labelrotation=90)
    axes[2].grid(alpha=.25)
    axes[2].legend(fontsize=7,loc='upper right')
    axes[0].legend(handles=[Patch(color='#b8bec6',label='Unknown'),Patch(color='white',ec='gray',label='Ray free / body support'),Patch(color='#333333',label='Observed obstacle')],fontsize=7,loc='lower right')
    destination.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(destination,dpi=150)
    plt.close(fig)


def main():
    source=read(RAW/'development/source.json')
    assert hashes()==source['hashes']
    results=read(RAW/'development/results.json')
    gate=read(RAW/'development/gate.json')
    assert gate==dict(n=32,passed=False)
    manifest=read(prior.EXP/'cohort.json')
    details=[]
    inputs=[]
    for row, result in zip(manifest['rows'],results):
        path=PRIOR_RAW/result['case']/'actor.jsonl'
        record=lines(path)[0]
        inputs.append(dict(case=result['case'],path=str(path),sha256=sha(path)))
        world=RayOracleWorld(row['scenario'],row['pose'],row['seed'],'confirmation')
        world.advance(dict(t=0.,kind='stop'),2.)
        obs,patches,_=world.observe(0)
        assert {k:v for k,v in obs.items() if not k.endswith('_origins_xy')}==record['observation'] and not patches
        actor=RaytraceActor('own_frontier',navigation='public_ros_v6')
        reproduced,data=diagnose(actor,{**record,'observation':obs})
        assert reproduced==result['after']
        detail=connector(actor,data)
        detail.update(case=result['case'])
        details.append(detail)
        if result['case']=='s1-K-6701-own_frontier':
            _,before=diagnose(ResolutionActor('own_frontier',navigation='public_ros_v5'),record)
            figure(before,data,detail,EXP/'figures/connectivity-and-connector.png')
    def aggregate(mode):
        total=Counter()
        for r in results:
            total.update({k:r[mode][k] for k in ('candidates','connected_candidates','valid','native_empty','connector_rejected')})
        return dict(**total,robot_component_range=[min(r[mode]['robot_component_cells'] for r in results),max(r[mode]['robot_component_cells'] for r in results)],
                    components_range=[min(r[mode]['navigable_components'] for r in results),max(r[mode]['navigable_components'] for r in results)])
    summary=dict(n=32,source_sha=source['sha'],before=aggregate('before'),after=aggregate('after'),development_passed=False,
        all_start_footprints_clear=all(d['checks'][0]['clear'] for d in details),
        connector_bad_raw_values=sorted({b['raw'] for d in details for c in d['checks'] for b in c['bad']}),
        connector_distance_range=[min(d['distance_m'] for d in details),max(d['distance_m'] for d in details)],
        initial_plan_statuses=dict(Counter(d['initial_plan_status'] for d in details)),
        confirmation_runs=0,noisy_runs=0,physics=0,model_calls=0,mission_replays=0)
    assert hashes()==source['hashes'] and 'mujoco' not in sys.modules
    out=EXP/'results'
    write(out/'development.json',results)
    write(out/'gate.json',gate)
    write(out/'summary.json',summary)
    write(out/'connectors.json',details)
    write(out/'development-inputs.json',inputs)
    write(out/'verification.json',dict(frozen_files=len(source['hashes']),hashes_unchanged=True,
         old_endpoint_equality=32,diagnoses_reconstructed=32,new_confirmation_cohort_generated=False,
         confirmation_runs=0,noisy_runs=0,physics=0,model_calls=0))
    write(out/'raw-manifest.json',dict(root=str(RAW),files=[dict(path=str(p.relative_to(RAW)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(RAW.rglob('*')) if p.is_file()]))
    table=['|맵/시작 (각 seed2)|출발 연결 v5→v6|성분 v5→v6|후보 NavFn 경로 v5→v6|연결 검사 통과|','|---|---:|---:|---:|---:|']
    for r in results[::2]:
        a,b=r['before'],r['after']
        table.append(f"|{'/'.join(r['case'].split('-')[:2])}|{a['robot_component_cells']}→{b['robot_component_cells']}|{a['navigable_components']}→{b['navigable_components']}|{a['candidates']-a['native_empty']}→{b['candidates']-b['native_empty']}|{b['valid']}|")
    (out/'table.md').write_text('\n'.join(table)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
