"""P0-2 fixed-record FIRST convergence; reference checkout is read-only.

Prediction imports no evaluator/GT. A legacy map-name alias admits the fixed
camera calibration; the supplied obstacle/region geometry is the counterfactual.
No controller step/drive is called. Stop on own std, never on truth.
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
REF=Path('/Users/changmin/projects/ugrp-wt/ownmap-s2')
sys.path.insert(0,str(REF))
import argparse,base64,copy,hashlib,json,subprocess
from unittest.mock import patch
import cv2,numpy as np
from scripts import replay_ownmap_s2 as old
from harness import vision_pose_source_highpose as high
RAW=Path('/Users/changmin/projects/ugrp/outputs/goal-route-p0-v1')


def predict(pair,condition):
    out=RAW/'pf'/pair['id']/condition;out.mkdir(parents=True,exist_ok=False)
    raw=Path(pair['raw']);bundle=old.read(raw/'bundle.json');record=old.read(raw/'student_record.json')
    frames=old.rows(raw/'robots/r3/frames.jsonl')
    for name in ('bundle.json','student_record.json','robots/r3/frames.jsonl'):
        assert old.sha(raw/name)==pair['hashes'][str(raw/name)]
    geometry=old.contract.hp.resolve(old.contract.MAP_ID)[0] if condition=='off' else old.read(ROOT/'maps/zones_final_v3/zone_wide_two_doors_final_v3.json')
    original_map_id=geometry['map_id'];geometry=copy.deepcopy(geometry);geometry['map_id']=old.contract.MAP_ID
    commands={}
    for c in record['commands']:commands.setdefault(round(c['t'],6),[]).append(c)
    init=commands[round(frames[0]['sim_time'],6)].pop(0)
    assert init['kind']=='initial_servo_command'
    reference={round(r['t'],6):r for r in record['poses']}
    _,undo=old.install('v98-exact-v6');runtime=None;results=[];maximum=0
    try:
        # Only the exact-static-map admission lookup is rebound in this process.
        # Numeric PF, priors, likelihood, camera, motion and seed are untouched.
        with patch.object(high.contract,'resolve',lambda *a:(geometry,None,None)):
            runtime=old.adapter.build_runtime(bundle,geometry,old.contract.ROOT/old.contract.CALIBRATION,
                old.contract.CALIBRATION_SHA,option='off')
        runtime.initial_commands(init['t'],{'r3':{int(k):v for k,v in init['pulses'].items()}})
        for i,f in enumerate(frames):
            data=(raw/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(data,np.uint8),1),cv2.COLOR_BGR2RGB)
            now=f['sim_time'];verdict,_=old.gate.gate().assess({**f,'image':base64.b64encode(data).decode()},'r3',now,ob=False)
            report=runtime.pose.on_frame(now,rgb if verdict==old.gate.VALID else None)
            r=old.adapter.report_row(report,now);r['pose_uncertain']=old.adapter.warned(r);results.append(r)
            a={k:r[k] for k in old.FIELDS};b={k:reference[round(now,6)][k] for k in old.FIELDS}
            maximum=max(maximum,max(abs(a[k]-b[k]) if a[k] is not None and b[k] is not None else float(a[k]!=b[k]) for k in a))
            if r.get('initialized',True) and r['std_xy_m']<=.05:break
            for c in commands.get(round(now,6),[]):runtime.on_command('r3',now,{k:v for k,v in c.items() if k!='t'})
            if i%500==0:print(pair['id'],condition,i,'/',len(frames),flush=True)
        old.write(out/'poses.json',results)
        result=dict(pair=pair['id'],condition=condition,frames=len(results),available_frames=len(frames),
            first=results[-1] if results and results[-1].get('initialized',True) and results[-1]['std_xy_m']<=.05 else None,
            baseline_identical=maximum==0 if condition=='off' else None,reference_delta=maximum,
            source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REF,text=True).strip(),
            map_id=original_map_id,runtime_admission_alias=old.contract.MAP_ID,
            geometry_sha256=hashlib.sha256(json.dumps(geometry,sort_keys=True).encode()).hexdigest(),
            prediction_sha256=old.sha(out/'poses.json'),gt_inputs=False,physics=0,models=0)
        old.write(out/'prediction.json',result);print(pair['id'],condition,'SEALED',len(results),flush=True)
        if condition=='off':assert result['baseline_identical'],'REFERENCE_PREFIX_MISMATCH'
    finally:
        if runtime is not None:runtime.close()
        undo()


def main():
    p=argparse.ArgumentParser();p.add_argument('--pair',required=True);p.add_argument('--condition',choices=['off','two_doors_static_v1'],required=True);a=p.parse_args()
    pair=next(p for p in old.read(old.PLAN)['pairs'] if p['id']==a.pair)
    predict(pair,a.condition)

if __name__=='__main__':main()
