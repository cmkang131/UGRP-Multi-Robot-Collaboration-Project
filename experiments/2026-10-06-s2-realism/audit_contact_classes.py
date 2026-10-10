"""Evaluation-only semantic contact audit, no controller or simulator instance.
Own RGB detections are frozen. Saved camera/robot truth only labels/scorers.
"""
import json,hashlib,math,sys
from pathlib import Path
from types import SimpleNamespace as NS
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_s1050_projection as a
from collections import Counter

CLASSES=('true_wall_bottom','floor_color_boundary','object_or_other_robot','doorframe_pillar','self_body_shadow','unknown')

def main(out):
    assert not out.exists();out.mkdir(parents=True)
    raw=a.RAW;lines=lambda p:[json.loads(x) for x in (raw/p).read_text().splitlines()]
    frames=lines('robots/r3/frames.jsonl');truth={round(r['t'],6):r for r in lines('eval_only/trajectory.jsonl')}
    cams={round(r['t'],6):r for r in lines('eval_only/camera-pose.jsonl')}
    old=json.loads(Path('/Users/changmin/projects/ugrp/outputs/s2-observed-amcl-20261007/projection/columns.json').read_text())
    reference={(q['t'],q['column']):q for q in old}
    times=sorted(set(q['t'] for q in old));fs={f['sim_time']:f for f in frames}
    models=a.approximate(json.loads((a.c.ROOT/'configs/calibration/s2_camera_v3_unloaded_sag_v1.json').read_text()))
    static=a.c.hp.resolve(a.c.MAP_ID)[0];segments=a.geo.wall_segments(static)
    vl=a.vp.load_vis3()[0];cols=np.linspace(8,631,96).astype(int);gates=a.own_image_gates()['values']
    review=json.loads((Path(__file__).parent/'contact-review-labels.json').read_text())
    overrides={(q['t'],q['column']):q for q in review['overrides']}
    rows=[];sheets=[]
    for t in times:
        f=fs[t];g=truth[round(t,6)];ca=cams[round(t,6)];rot=a.geo.rz(g['robot_yaw_rad']);base=np.r_[g['robot_xyz_m'][:2],0.]
        servo={int(k):v for k,v in f['commanded_servo'].items()};key=','.join(str(servo[k]) for k in (3,4,5,6))
        cm=a.measured_column_model(vl.mp,a.floor_camera(models['loaded'][key]),cols)
        actual=NS(origin=rot.T@(np.array(ca['camera_cached_xyz_m'])-base),_rot=rot.T@np.array(ca['camera_cached_optical_rotation']),columns=cols)
        pose=np.r_[g['robot_xyz_m'][:2],g['robot_yaw_rad']]
        gtrows,_,_=a.geo.bottom_projection(actual,pose,segments)
        data=(raw/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
        bgr=cv2.imdecode(np.frombuffer(data,np.uint8),1);ob=a.observations(vl,bgr,cm,gates);und=vl.mp.undistort(bgr)
        # Rays above and below the boundary distinguish an in-plane floor edge
        # from a raised wall. Fixed +/-4px patch follows detector 3-row windows.
        layer=[]
        for offset in (-4,4):
            rays=a.geo.pixel_rays(actual,cols,np.nan_to_num(ob.b_lo)+offset)
            z=-actual.origin[2]/rays[:,2]
            wall=a.geo.wall_depths(actual,pose,rays,static)
            cargo=a.geo.box_depth(actual.origin,rays,rot.T@(np.array(g['cyan_xyz_m'])-base),rot.T@np.array(g['cyan_rotation']).reshape(3,3),np.array(g['box_half_m']))
            body=np.minimum.reduce(list(a.geo.shadow_depths(actual.origin,rays,a.geo.robot_boxes(servo,actual)).values()))
            floor=(z>0)&(wall>=z-1e-6)&(cargo>=z-1e-6)&(body>=z-1e-6)
            layer.append(dict(floor=floor,wall=wall<z-1e-6,cargo=cargo<np.minimum(z,wall),body=body<np.minimum(z,wall)))
        ann=und.copy();counts=Counter()
        for j in np.where(ob.b_kind==1)[0]:
            q=dict(reference[(t,int(cols[j]))]);d=float(ob.b_lo[j]-gtrows[j]);category='unknown'
            if layer[0]['floor'][j] and layer[1]['floor'][j]:category='floor_color_boundary'
            elif abs(d)<=4 and layer[0]['wall'][j] and layer[1]['floor'][j]:category='true_wall_bottom'
            # No semantic labels are guessed for unmatched geometry. Inspect
            # unknowns in saved sheets; never silently force them to floor.
            if (t,int(cols[j])) in overrides:category=overrides[(t,int(cols[j]))]['category']
            q.update(category=category,detected_row=float(ob.b_lo[j]),true_bottom_row=float(gtrows[j]),
                row_residual_px=d,above_floor=bool(layer[0]['floor'][j]),below_floor=bool(layer[1]['floor'][j]),
                frame=f['path'])
            rows.append(q);counts[category]+=1
            color=(0,255,0) if category=='true_wall_bottom' else ((0,0,255) if category=='floor_color_boundary' else (0,255,255))
            cv2.circle(ann,(int(cols[j]),round(ob.b_lo[j])),3,color,-1)
        cv2.putText(ann,f"{t:.0f}s wall {counts['true_wall_bottom']} floor {counts['floor_color_boundary']} ? {counts['unknown']}",(8,465),0,.55,(255,255,255),2)
        sheets.append(cv2.resize(ann,(320,240)))
    for i in range(0,len(sheets),16):
        batch=sheets[i:i+16]+[np.zeros_like(sheets[0])]*(16-len(sheets[i:i+16]))
        cv2.imwrite(str(out/f'sheet-{i//16:02d}.jpg'),np.vstack([np.hstack(batch[j:j+4]) for j in range(0,16,4)]))
    total_sse=sum(q['nearest_wall_error_m']**2 for q in rows)
    groups=[]
    for cat in CLASSES:
        qs=[q for q in rows if q['category']==cat];errors=[q['nearest_wall_error_m'] for q in qs]
        nv=[q for q in qs if not q['true_clear']]
        groups.append(dict(category=cat,n=len(qs),fraction=len(qs)/len(rows),nonvisible_n=len(nv),
            error_m=a.summary(errors),mae_contribution_m=sum(errors)/len(rows),sse_fraction=sum(e*e for e in errors)/total_sse,
            nonvisible_error_m=a.summary([q['nearest_wall_error_m'] for q in nv])))
    (out/'contacts.json').write_text(json.dumps(rows)+'\n')
    summary=dict(schema='ugrp.s2.contact_classes.v1',physics_runs=0,model_calls=0,gt_usage='evaluation only',
        sample_hz=1,sampled_frames=166,nonempty_frames=len(times),contacts=len(rows),classes=groups,
        unknown_times=sorted(set(q['t'] for q in rows if q['category']=='unknown')),
        manual_review=review,limitations='104 contact images and25 ambiguous enlarged patches reviewed; no dense semantic truth for other robots/shadows. Three wall-face artifacts unknown. No detected object/self/pillar boundary in this sample. Median errors are not additive; use SSE share and weighted MAE contribution.',
        source_hashes={str(raw/p):hashlib.sha256((raw/p).read_bytes()).hexdigest() for p in ['robots/r3/frames.jsonl','eval_only/trajectory.jsonl','eval_only/camera-pose.jsonl']})
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))

if __name__=='__main__':main(Path(sys.argv[1]))
