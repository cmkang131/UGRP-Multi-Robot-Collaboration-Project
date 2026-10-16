"""Post-seal egomap32 fit, with preregistered direction-wise loaded admission."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import t as student_t

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCE=HERE/'references/egomap32_fit.py.txt'


def original_fit(records):
    tree=ast.parse(SOURCE.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='fit')
    namespace=dict(np=np,student_t=student_t)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE),'exec'),namespace)
    return namespace['fit'](records)


def score(raw,out):
    read=lambda p:json.loads(p.read_text())
    for rel,digest in read(raw/'artifacts.sha256.json').items():
        assert hashlib.sha256((raw/rel).read_bytes()).hexdigest()==digest,rel
    result=read(raw/'result.json');assert result['status']=='RECORDED'
    gt=[json.loads(s) for s in (raw/'eval-only.jsonl').read_text().splitlines()]
    times=np.array([r['t'] for r in gt]);yaw=np.unwrap([r['rpy'][2] for r in gt])
    xy=np.array([r['xyz'][:2] for r in gt])
    model=read(ROOT/'configs/s2_motion_v7_pulse_cal_v1.json');records=[]
    for b in read(raw/'schedule.json')['blocks']:
        begin=result['start_sim_s']+b['start_tick']/20;end=result['start_sim_s']+b['end_tick']/20
        key=f"1:turn:{b['sign']*.35:.2f}:0.10";p=model['profiles'][key]
        actual=float(np.degrees(np.interp(end,times,yaw)-np.interp(begin,times,yaw)))
        predicted=float(np.degrees(p['mean_delta'][2])*b['pulses'])
        records.append(dict(**b,profile=key,start_s=begin,end_s=end,actual_deg=actual,predicted_deg=predicted,
            error_deg=actual-predicted,gain=actual/predicted,
            tail_after_horizon_deg=float(np.degrees(np.interp(end+1,times,yaw)-np.interp(end,times,yaw))),
            drift_xy_m=float(np.linalg.norm([np.interp(end,times,xy[:,j])-np.interp(begin,times,xy[:,j]) for j in (0,1)]))))
    fit=original_fit(records);gates={};accepted={}
    for sign,d in fit['directions'].items():
        gates[sign]=dict(gain_ci_excludes_one=d['ci95'][0]>1 or d['ci95'][1]<1,
            single_continuous_agree=d['relative_mode_gap']<=.05,
            check_rmse_improves=d['check_rmse_deg_per_pulse_on']<d['check_rmse_deg_per_pulse_off'])
        if all(gates[sign].values()):accepted[f'1:turn:{int(sign)*.35:.2f}:0.10']=d['gain']
    report=dict(schema='ugrp.s2.loaded_rotation.fit.v1',source_sha=result['source_sha'],raw=str(raw),
        raw_manifest_sha256=hashlib.sha256((raw/'artifacts.sha256.json').read_bytes()).hexdigest(),
        criteria_sha256=hashlib.sha256((HERE/'loaded-rotation-criteria.json').read_bytes()).hexdigest(),
        source_fit_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),fit=fit,records=records,
        directional_gates=gates,accepted_gains=accepted,eligible=bool(accepted),
        physical_safety=dict(bilateral_fraction=result['bilateral_fraction'],
            max_tilt_deg=float(np.degrees(max(max(abs(x) for x in r['rpy'][:2]) for r in gt))),
            min_cargo_z_m=min(r['cargo_xyz'][2] for r in gt),
            wall_contact_samples=sum(any(c['category'].startswith('wall_') and c['force_contact_frame'][0]>0 for c in r['contacts']) for r in gt)),
        existing_search_option='not applied to this acquisition/loaded fit',not_independent_research_success=True)
    out.mkdir(parents=True,exist_ok=False)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    if accepted:
        artifact=dict(option='s2_pulse_v122_loaded_look_v1',profiles=accepted,
            base_model_sha256=hashlib.sha256((ROOT/'configs/s2_motion_v7_pulse_cal_v1.json').read_bytes()).hexdigest(),
            commanded_pose={1:1500,3:1050,4:2035,5:1894,6:1500},servo_stiffness='real_v1',loaded=True,
            fit_repeats=[1,2,3],check_repeats=[4,5],source=str(out/'result.json'),
            source_sha256=hashlib.sha256((out/'result.json').read_bytes()).hexdigest(),gt_runtime=False)
        (out/'candidate-calibration.json').write_text(json.dumps(artifact,indent=2)+'\n')
    print(json.dumps(dict(fit=fit['directions'],gates=gates,accepted=accepted,safety=report['physical_safety'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();score(a.raw,a.output)
