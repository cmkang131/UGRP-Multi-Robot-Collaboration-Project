#!/usr/bin/env python3
"""Dev-only camera-model residuals; diagnosis, never a runtime correction."""
import json
import math

import numpy as np

import diagnose_v4 as d
import vision_loc as vl
import vision_loc_cli_v4 as cli
import vision_loc_io as vio


def camera_residual(label,servo,loaded,sag):
    r,p=cli.true_camera_in_base(label)
    bias,dz=vl.sag(sag,loaded,servo)
    expected,_=vl.mp.camera_in_base(servo)
    expected=expected+np.array([0.,0.,dz])
    true_bias,_,az=vl.elevation_and_dz(r,p,servo)
    return [*list(p-expected), math.degrees(true_bias-bias), math.degrees(az)]


def main():
    plan=vio.load_json(d.PLAN);eps=plan['fit_episodes']+plan['validation_episodes'];d.require_dev(eps)
    cal=vio.load_json(d.HERE/'calibration_train.json');groups={}
    for ep in eps:
        folder=vio.RENDER_ROOT/ep;data=vl.student_inputs(folder)
        labels={r['frame_id']:r for r in vl.read_jsonl(folder/'eval_only'/'labels.jsonl')}
        own=cli.OwnState(vl.mp.load_m1_localizer());ci=0
        for row in data['frames']:
            while ci<len(data['commands']) and data['commands'][ci]['t']<row['t']-1e-9:
                own.command(data['commands'][ci]);ci+=1
            lab=labels[row['frame_id']];x,y,_=lab['base_gt']
            if not own.load.loaded or abs(x-2.2)>=.6 or not -.45<y<.55 or row['t']-own.last_servo_cmd_t<.2-1e-9:
                continue
            pose={int(k):int(v) for k,v in row['commanded_servo'].items()}
            residual=camera_residual(lab,pose,True,cal['sag'])
            for key in ('door_loaded',f's3_{pose[3]}',f'episode_{ep}'):
                groups.setdefault(key,[]).append(residual)
    result={'schema':'ugrp.vis4.camera_diagnosis.v1','units':['m','m','m','deg','deg'],
            'fields':['camera_origin_dx','camera_origin_dy','camera_origin_dz','pitch_bias_residual','azimuth_residual'],
            'scope':'Offline dev GT camera vs frozen train calibration; NOT fitted or applied at runtime',
            'groups':{}}
    for key,rows in groups.items():
        a=np.array(rows)
        result['groups'][key]={'n':len(a),'mean':np.mean(a,axis=0).tolist(),
                               'median':np.median(a,axis=0).tolist(),'abs_p90':np.percentile(np.abs(a),90,axis=0).tolist()}
    d.save(d.OUT/'camera_residuals.json',result)
    print(json.dumps({k:v for k,v in result['groups'].items() if not k.startswith('episode_')},indent=1))


if __name__=='__main__':main()
