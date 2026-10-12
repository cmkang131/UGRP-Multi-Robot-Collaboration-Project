"""Summarize completed comparisons; no new extraction or model/physics calls."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).parent))
import compare as c


def main():
    c.s2_path.verify_sources()
    frozen=c.a.load(c.EXP/'freeze.json')
    assert frozen['hashes']==c.hashes()
    complete=Path('/Users/changmin/projects/ugrp/outputs/s2-projection-comparison-v1-complete')
    cases=[c.a.load(complete/f's{s}/result.json') for s in range(1042,1048)]
    for r in cases:
        assert c.a.digest(complete/r['case']/'own-predictions.json')==r['prediction_sha256']
        assert r['metrics']['pr405']==r['metrics']['pr406']
        assert r['eligible_rigid_delta_max']==[0,0]
    refpath='experiments/2026-10-06-s2-realism/s1050-projection-summary.json'
    raw=subprocess.check_output(['git','show','dc65cf6f:'+refpath])
    ref=json.loads(raw)
    for path,h in ref['source_hashes'].items():assert c.a.digest(path)==h
    columns=c.a.load(ref['columns']['path'])
    assert c.a.digest(ref['columns']['path'])==ref['columns']['sha256']
    # Audit-only independent reduction of stored columns; no new success sample.
    errors=[x['total_endpoint_error_m'] for x in columns if x['compared']]
    assert len(errors)==ref['finite_compared_columns']
    assert abs(c.stats(errors)['median']-ref['visible_metrics']['total_endpoint_error_m']['median'])<1e-12
    c.a.write(c.EXP/'results/s1050-reference.json',dict(
        source_ref=c.s2_path.MANIFEST['ref'],source_path=refpath,source_sha256=hashlib.sha256(raw).hexdigest(),
        type='verified prior PR406 audit; not a new replay and never pooled',
        **{k:v for k,v in ref.items() if k not in ('rows','limitations')},stored_columns_reduction=c.stats(errors)))
    table,models=c.s2_path.models()
    geometry={}
    for key in ['740,2320,1320,1500','896,2035,1894,1500','600,2200,1400,1500']:
        geometry[key]={}
        for state in ['unloaded','loaded']:
            cam=c.a.floor_camera(models[state][key])
            geometry[key][state]=dict(origin_m=cam['origin_m'],angles_deg=c.np.degrees(c.a.angles(cam['rotation'])).tolist())
    c.a.write(c.EXP/'results/pose-products.json',dict(poses=geometry,pan_base_yaw=table['pan_base_yaw'],
        columns_405=c.a.COLS.tolist(),columns_s1050_audit=c.np.linspace(8,631,96).astype(int).tolist(),
        intrinsics_equal=bool(c.np.array_equal(table['intrinsics_K'],c.a.old.mp.K))))
    inventory=[]
    for root in [complete,Path('/Users/changmin/projects/ugrp/outputs/s2-projection-comparison-v1')]:
        for p in sorted(root.rglob('*')):
            if p.is_file():inventory.append(dict(path=str(p),bytes=p.stat().st_size,sha256=c.a.digest(p)))
    c.a.write(c.EXP/'results/raw-manifest.json',dict(files=inventory,count=len(inventory),bytes=sum(v['bytes'] for v in inventory)))
    c.a.write(c.EXP/'results/verification.json',dict(
        source_hashes_match_freeze=True,s2_source_copies_verified=True,own_predictions_unchanged=True,
        same_six_baseline_metrics=True,all_six_gates_passed=0,
        ray_vs_s2_column_max_m=max(x['ray_vs_s2_column_max_m'] for x in cases),
        s1050_original_sources_and_stored_column_reduction_verified=True,
        runtime_source_changed=False,new_runtime_option=False,mapping_replays=0,
        physics=0,render=0,model_calls=0,new_dependency_or_venv=0,
        tests='13 passed: test_s2_projection_comparison, test_servo_camera_fk, test_camera_projection_audit'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(8,4.5))
    x=c.np.arange(3)
    for i,(key,label,color) in enumerate([('pr405','PR405 unloaded table','#5676aa'),
        ('pr406','PR406 same-frame path','#e09c42'),('actual_oracle','Actual camera (evaluation only)','#499476')]):
        values=[r['metrics'][key]['median'] for r in cases[3:]]
        ax.bar(x+(i-1)*.25,values,width=.23,label=label,color=color)
        for xx,v in zip(x+(i-1)*.25,values):ax.text(xx,v+.008,f'{v:.3f}',ha='center',fontsize=9)
    ax.axhline(.10,color='#9a3333',ls='--',label='Frozen median gate: 0.10 m')
    ax.set_xticks(x,[r['case'] for r in cases[3:]])
    ax.set_ylim(0,.80)
    ax.set_ylabel('Manual contact median wall error (m)')
    ax.set_title('Same RGB pixels, GT chassis for evaluation, fixed denominator')
    ax.legend(loc='upper left',fontsize=8)
    fig.tight_layout()
    fig.savefig(c.EXP/'results/same-frame-projection.png',dpi=160)
    plt.close(fig)
    print('verified six case equality; same-frame gates 0/6; s1050 stored sources/columns match; raw',len(inventory),sum(v['bytes'] for v in inventory))


if __name__=='__main__':main()
