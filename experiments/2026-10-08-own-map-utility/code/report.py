"""Saved-result diagnosis, figures and hashes; no prediction/score rerun."""
from replay import *
import copy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    result = load(EXP/'results/utility.json')
    details = load(RAW/'evaluation-details.json')
    prepared = load(RAW/'prepared.json')
    gt0 = rows(EP/'eval_only/trajectory.jsonl')[0]
    origin = [*gt0['robot_xyz_m'][:2],gt0['robot_yaw_rad']]
    diagnostic=[]
    for t in result['trials']:
        name=f"{t['condition']}-{t['trial']}"
        pred=load(RAW/(name+'.json')); rr=pred['rows']; d=details[name]
        correct=(np.asarray(d['xy_m'])<=.25)&(np.asarray(d['yaw_deg'])<=10.)
        yaw_ok=np.array([r['circular_yaw_std_rad']<=math.radians(5) for r in rr])
        # Original ready = all-particle XY support AND circular yaw std <=5deg.
        # When yaw passes but ready is false, XY-support rejection follows exactly.
        xy_veto=sum(ok and not r['resolved'] for ok,r in zip(yaw_ok,rr))
        world=np.asarray(d['true_world'][0])
        point=between(origin,world)[:2] if t['condition']=='own' else world[:2]
        g=load(RAW/f"maps/{t['condition']}.json")
        odds={tuple(c[:2]):c[2] for c in g['cells']}
        cell=tuple(np.floor(point/g['resolution_m']).astype(int))
        value=odds.get(cell,0.)
        diagnostic.append(dict(condition=t['condition'],trial=t['trial'],
            resolved_frames=sum(r['resolved'] for r in rr),
            yaw_std_pass_frames=int(yaw_ok.sum()),xy_support_veto_when_yaw_pass=int(xy_veto),
            final_yaw_std_deg=rr[-1]['circular_yaw_std_rad']*180/math.pi,
            true_accuracy_pass_frames=int(correct.sum()),
            initial_true_cell_status='free' if value<0 else 'occupied' if value>0 else 'unknown',
            interpretation='diagnostic only; no threshold or prior changes'))
    dump(EXP/'results/diagnosis.json',diagnostic)
    export=load(RAW/'wall-memory.json')
    dump(EXP/'results/wall-memory.json',export)
    (EXP/'results/wall-memory.txt').write_bytes((RAW/'wall-memory.txt').read_bytes())
    fig, axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    static=load(EP/'inputs/static_map.json')
    from matplotlib.patches import Rectangle
    for o in static['obstacles']:
        a=np.asarray(o['center_m'])-o['half_extents_m']
        axes[0].add_patch(Rectangle(a,* (2*np.array(o['half_extents_m'])),color='lightgrey'))
    for item in export['items']:
        line=transform(item['claim']['endpoints_m'],origin)
        support=item['evidence']['score'] or 0.
        axes[0].plot(*line.T,color=plt.cm.Blues(.3+.7*support),lw=2)
    goal=prepared['own_goal']
    if goal:
        p=transform([goal['center_m']],origin)[0]
        axes[0].scatter(*p,marker='*',s=140,c='orange',label='Remembered B (eval alignment only)')
    axes[0].scatter(*static['regions']['zone_B']['center_m'],marker='x',c='black',label='Authored B')
    trajectory=rows(EP/'eval_only/trajectory.jsonl')
    xy=np.array([r['robot_xyz_m'][:2] for r in trajectory])
    axes[0].plot(*xy.T,c='green',lw=1,alpha=.6,label='Recorded true path (evaluation)')
    axes[0].set(aspect='equal',title='Module F: 41 candidates / 381 occupied cells\n64 scans; original coverage 213/329',xlabel='World x (evaluation only)',ylabel='World y')
    axes[0].legend(fontsize=7)
    for t in result['trials']:
        name=f"{t['condition']}-{t['trial']}";d=details[name]
        axes[1].plot(np.array(d['t'])-prepared['start_t'],d['xy_m'],
            ls='-' if t['condition']=='own' else '--',c=f"C{t['trial']}",label=name)
    axes[1].axhline(.25,c='black',lw=.7,label='Registered XY check (not full convergence)')
    axes[1].set(title='Unknown-start replay: no declared convergence\nSame recording reused; 3 paired resets',xlabel='Recorded elapsed s',ylabel='Position error m')
    axes[1].legend(fontsize=7)
    (EXP/'figures').mkdir(exist_ok=True)
    fig.savefig(EXP/'figures/utility.png',dpi=150);plt.close(fig)

    for name,h in prepared['input_hashes'].items():assert sha(name)==h
    assert (RAW/'maps/own.json').read_bytes()==(EP/'grid.json').read_bytes()
    assert len([c for c in load(EP/'grid.json')['cells'] if c[2]>0])==381
    manifest={}
    for path,digest in result['sealed_predictions'].items():
        assert sha(path)==digest
        p=load(path)
        for name,h in p['source_code_hashes'].items():assert sha(ROOT/name)==h
        assert p['source_sha']==subprocess.check_output(['git','rev-parse','82b8aa9d'],cwd=ROOT,text=True).strip()
    prior=load(ROOT/'experiments/2026-10-08-wall-pr-operating-point/results/verification.json')
    for name,h in prior['original_untracked_hashes'].items():assert sha(ROOT/name)==h
    assert '22 passed' in (RAW/'tests-adapter-fix.log').read_text()
    assert len((RAW/'wall-memory.txt').read_text().rstrip('\n').encode())<=1024
    for p in EXP.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:assert p.stat().st_size<=1024*1024
    for p in sorted(RAW.rglob('*')):
        if p.is_file():manifest[str(p.relative_to(RAW))]=dict(bytes=p.stat().st_size,sha256=sha(p))
    dump(EXP/'results/raw-manifest.json',dict(root=str(RAW),files=manifest))
    dump(EXP/'results/verification.json',dict(tests=22,physics=0,models=0,retuning=0,
        off_nonempty_snapshot_bytes=True,off_rng_and_map_unchanged=True,peer_input_rejected=True,
        original_grid_bytes=True,original_inputs_hashes=True,original_untracked_unchanged=True,
        completed_prediction_runs=6,failed_unscored_attempts=1,gt_prediction_inputs=False,
        goal='first confirmed own RGB B entity; no GT target transform',
        generated_segments=len(export['items']),summary_utf8_bytes=len((RAW/'wall-memory.txt').read_text().rstrip('\n').encode()),
        source_code_sha=subprocess.check_output(['git','rev-parse','82b8aa9d'],cwd=ROOT,text=True).strip(),
        manifest_sha256=sha(EXP/'results/raw-manifest.json'),figure_sha256=sha(EXP/'figures/utility.png')))
    print(json.dumps(diagnostic,indent=2));print('PASS: 6 seals, original map/RGB/commands, 22 tests, own B provenance, no physics')


if __name__=='__main__':main()
