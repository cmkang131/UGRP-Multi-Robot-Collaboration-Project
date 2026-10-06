"""Post-replay scoring and frozen admission; GT used only in marked diagnostics."""
import json
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import replay_unloaded_sag as m


def quantiles(values):
    a=np.asarray([x for x in values if x is not None],float)
    return dict(n=len(a),median=float(np.median(a)),p90=float(np.quantile(a,.9))) if len(a) else dict(n=0,median=None,p90=None)


def summarize(out):
    geometry=json.loads((out/'geometry-evaluation.json').read_text())['rows']
    rows=[];hashes={}
    for seed,sha in m.RUNS.items():
        raw=m.RAW/f's2-realism-{sha}-s{seed}-P1-2-place'
        # Opened only after PF replay has terminated: never fed back to it.
        truth=[json.loads(l) for l in (raw/'eval_only/trajectory.jsonl').read_text().splitlines()]
        source_poses=json.loads((raw/'student_record.json').read_text())['poses']
        estimate_times={p['t']:p['t_est'] for p in source_poses}
        ts=np.array([g['t'] for g in truth]);xy=np.array([g['robot_xyz_m'][:2] for g in truth])
        for variant in m.CRITERIA['variants']:
            p=out/f's{seed}-{variant}.json';r=json.loads(p.read_text());hashes[p.name]=m.digest(p)
            assert r['gt_inputs'] is False and r['commands_fixed'] is True
            assert r['criteria_sha256']==m.digest(m.HERE/'unloaded-sag-criteria.json')
            metrics=m.fix_metrics(r['rows'],r['metrics']['carry_window'])
            assert metrics==r['metrics']
            start,end=metrics['carry_window'];carry=[x for x in r['rows'] if start<=x['t']<end]
            errors=[]
            for x in carry:
                t=estimate_times[x['t']]
                actual=np.array([np.interp(t,ts,xy[:,i]) for i in (0,1)])
                errors.append(float(np.linalg.norm(np.array([x['x'],x['y']])-actual)))
            gs=[x['variants'][variant] for x in geometry if x['seed']==seed]
            gates=[x['gate'] for x in carry if x['gate'] is not None]
            entry=dict(seed=seed,variant=variant,**{k:v for k,v in metrics.items() if k!='fix_times'},
                frames=r['frames'],trailing_pose_without_rgb=r['trailing_pose_without_rgb'],
                baseline_max_pose_delta=r['baseline_max_pose_delta'] if variant=='legacy' else None,
                gate_rows=len(gates),gate_informative=sum(bool(g.get('informative')) for g in gates),
                gate_fraction_below_066=sum(g.get('inlier_fraction',0)<.66 for g in gates),
                gate_support_below_010=sum(g.get('posterior_support',0)<.10 for g in gates),
                wall_visible_residual_px_eval_only=quantiles([x['visible_abs_residual_median_px'] for x in gs]),
                wall_all_residual_px_eval_only=quantiles([x['all_abs_residual_median_px'] for x in gs]),
                actual_camera_residual_px_eval_only=quantiles([x['actual_eval_abs_residual_median_px'] for x in gs]),
                carry_position_error_m_eval_only=quantiles(errors),carry_end_error_m_eval_only=errors[-1],
                projected_pitch_deg=gs[0]['pitch_deg'],projected_height_m=gs[0]['height_m'])
            rows.append(entry)
    valid_baselines=all(x['baseline_max_pose_delta']<=m.CRITERIA['baseline_max_pose_delta'] for x in rows if x['variant']=='legacy')
    admitted=[v for v in m.CRITERIA['selection_order'] if valid_baselines and all(x['admission_pass'] for x in rows if x['variant']==v)]
    result=dict(schema='ugrp.s2.unloaded_sag_replay.summary.v1',criteria_commit='adfd53a1',
        criteria=m.CRITERIA,rows=rows,baseline_reproduction_pass=valid_baselines,
        selected_candidate=admitted[0] if admitted else None,full_dev_permitted=bool(admitted),
        physics_runs=0,model_calls=0,raw_hashes=hashes,
        scope='fixed recorded command replay; no closed-loop transport claim; GT diagnostics not admission criteria')
    for name in ('geometry-evaluation.json','fixture-loss-audit.json'):
        result['raw_hashes'][name]=m.digest(out/name)
    dest=out/'summary.json'
    if dest.exists():raise FileExistsError(dest)
    dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('criteria','raw_hashes')},indent=2))


if __name__=='__main__':summarize(Path(sys.argv[1]))
