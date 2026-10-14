"""Hash audit + evaluation-only static geometry, NOT a new-view replay.

Reads retrieved originals. Never constructs a simulator or supplies truth to
the policy. Predicted visibility does not certify pixels/detection/success.
"""
import collections
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
import cv2
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness.zone_final_environment import resolve, digest
from sim.lookaround_localization import Camera, map_landmarks, visible_fn_for, look_servo, LOOK_ARM, LOOK_ARM_V2
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D

BASE=Path(__file__).parent
RAW=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
REVIEW=ROOT/'outputs/release7-review'
RUNS=('release5-diagnostic-02-e96386d3','release6-diagnostic-07-63201b88')


def decoded(path):
    return subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else path.read_bytes()


def raw_fov(camera,pose,heading,pan,arm,lm):
    origin,rot=camera.pose(look_servo(pan,arm))[0]
    a=pose[2]+math.radians(heading);c,s=math.cos(a),math.sin(a)
    dx,dy=np.asarray(lm['xy'])-pose[:2]
    point=rot.T@(np.array([c*dx+s*dy,-s*dx+c*dy,0.])-origin)
    if point[2]<=.05:return False
    uv,_=cv2.fisheye.projectPoints(point.reshape(1,1,3),np.zeros(3),np.zeros(3),
                                   camera.K,np.array(CAMERA_FISHEYE_D))
    u,v=uv[0,0]
    return 12<=u<=628 and 12<=v<=468


def main():
    REVIEW.mkdir(parents=True,exist_ok=True)
    all_hashes={}; runs=[]; reviewed=[]; geometries=[]
    for name in RUNS:
        folder=RAW/name; raw=folder/'raw'
        remote_hashes={s.split(maxsplit=1)[1]:s.split()[0] for s in (folder/'SHA256SUMS').read_text().splitlines()}
        manifest=json.loads((raw/'manifest.json').read_text())
        for relative, receipt in manifest.items():
            path=raw/relative; h=hashlib.sha256(path.read_bytes()).hexdigest()
            assert h==receipt['sha256']
            remote='/home/ugrp/ugrp-sim/runs/'+str(path.relative_to(RAW))
            assert h==remote_hashes[remote]
            if 'decoded_sha256' in receipt:
                assert hashlib.sha256(decoded(path)).hexdigest()==receipt['decoded_sha256']
            all_hashes[str(path)]=h
        result=json.loads(decoded(raw/'result.json.zst'))
        plan=json.loads((raw/'plan.json').read_text());scene=json.loads((raw/'scene.json').read_text())
        static=resolve(plan['map_id'])[0]; assert digest(static)==scene['static_map_sha256']
        teachers={r:[json.loads(s) for s in decoded(raw/f'teacher-{r}.jsonl.zst').splitlines()] for r in ('r1','r2')}
        metrics={}
        for rid, item in result['lookaround_result'].items():
            views=item['localizer']['views']
            metrics[rid]=dict(released_t=next(x['t'] for x in teachers[rid] if not x['holding_belief']),
                holding_ticks=dict(collections.Counter(str(x['holding_belief']) for x in teachers[rid])),
                frames=len(views),frames_with_landmarks=sum(bool(v.get('wall_points',0)+v.get('floor_lines',0)+v.get('doors',0)) for v in views),
                detections={k:sum(v.get(k,0) for v in views) for k in ('wall_points','floor_lines','doors')},
                sweeps=[dict(t0=s['t0'],end=s['t0']+s['sim_s'],**s['decision']) for s in item['evaluation']['sweeps']],
                final_decision={k:item['localizer']['decision'].get(k) for k in
                    ('accepted','reason','normal_rank','score_gap','groups')})
            # Truth is read ONLY in this analysis. It never enters script().
            before=item['evaluation']['sweeps'][1]['before']['truth']
            # First extra sweep has no base motion: this is the recovery site.
            sites={'after_original_backoff':np.array(before,float)}
            target=np.array(before,float);target[:2]+=.10*np.array([math.cos(target[2]),math.sin(target[2])])
            sites['after_nominal_retrace']=target
            camera=Camera();lms=map_landmarks(static)
            geometry=dict(run=name,robot=rid,map_id=plan['map_id'],map_sha256=digest(static),sites={})
            for site,pose in sites.items():
                sets={};views_out=[]
                for heading in (-90.,90.):
                    for arm_name,arm in (('surroundings',LOOK_ARM_V2),('floor',LOOK_ARM)):
                        see=visible_fn_for(static,camera,arm)
                        for pan in (-60.,0.,60.):
                            groups={}
                            for lm in lms:
                                if see(pose,heading,pan,lm) and raw_fov(camera,pose,heading,pan,arm,lm):
                                    groups.setdefault(lm['group'],[]).append(lm)
                            usable={g:ls for g,ls in groups.items() if len(ls)>=2 and math.dist(ls[0]['xy'],ls[-1]['xy'])>=.12}
                            for g,ls in usable.items():sets[g]=ls[0]['type']
                            normals=[lm['normal'] for ls in usable.values() for lm in ls if 'normal' in lm]
                            views_out.append(dict(body_yaw_deg=heading,arm=arm_name,pan_deg=pan,
                                groups={g:ls[0]['type'] for g,ls in usable.items()},
                                line_normal_rank=int(np.linalg.matrix_rank(normals)) if normals else 0))
                # Euclidean center clearance, analysis only, no safety threshold substitution.
                from harness.static_keepouts import rect_distance, keepout_rects
                distances=[rect_distance(pose[:2],r) for r in keepout_rects(static,perimeter=True)]
                geometry['sites'][site]=dict(evaluation_pose=pose.tolist(),
                    min_static_center_clearance_m=min(distances),
                    unique_groups=sets,counts_by_type=dict(collections.Counter(sets.values())),views=views_out)
            geometries.append(geometry)
        run=dict(name=name,raw=str(raw),seed=plan['seed'],source_sha=result['source_sha'],
            outcome=result['release_outcome'],success=result['release_success'],
            position=result['evaluation_position_error'],evaluation_last=result['evaluation_last'],
            input_audit={k:result['input_audit'][k] for k in ('held_world_reads','invisible_measurements')},
            robots=metrics,active_observation=[{k:e.get(k) for k in ('robot','stage','t','action','body_yaw_deg','backstep_m')} for e in result['active_observation']])
        runs.append(run)
        # Original JPEG review only, no rendering. First/middle/end at <=15 s spacing.
        last=max(int(p.name[:6]) for p in (raw/'eval-overview').glob('*-release-*'))
        indices=sorted(set([0,40,80,*[round(last*i/5/10)*10 for i in range(1,6)]]))
        sheet=Image.new('RGB',(960,len(indices)*260),'white');draw=ImageDraw.Draw(sheet)
        for row,idx in enumerate(indices):
            for col,sub in enumerate(('eval-overview','eval-own/r1','eval-own/r2')):
                path=next((raw/sub).glob(f'{idx:06d}-release-*.jpg'))
                sheet.paste(Image.open(path).resize((320,240)),(col*320,row*260+20))
                draw.text((col*320+2,row*260+3),f'{sub} {path.name}',fill='black')
                # Link to actual frame clock, not an assumed prefix origin.
                at=teachers['r1'][min(idx,len(teachers['r1'])-1)]['t']
                reviewed.append(dict(path=str(path),sha256=all_hashes[str(path)],t=at))
        sheet.save(REVIEW/f'{name}-review.jpg')
    detail=dict(files=all_hashes,runs=runs,static_geometry=geometries,reviewed_frames=reviewed,
        geometry_scope='Evaluation-only true base poses + static map/FK/pinhole AND raw fisheye FOV/2D wall occlusion; not rendered images. '
                       'No dynamic occlusion, lens edge detection, or motion realization guarantee. Groups require >=2 samples spanning >=.12m. '
                       'Wall faces are not certified corner detections; door samples are predicted but unused by the current line matcher.')
    blob=json.dumps(detail,ensure_ascii=False).encode()
    target=BASE/'release7-analysis-detail.json.zst'
    target.write_bytes(subprocess.check_output(['zstd','-q','-c'],input=blob))
    summary=dict(scope='retrieved original audit and static geometry only; no new detection replay or physics',
        source_parent='63201b88ce5342d57fa81bc0e141ec2d10beec49',
        runs=runs,verified_file_count=len(all_hashes),reviewed_frame_count=len(reviewed),
        geometry=[dict(run=g['run'],robot=g['robot'],sites={k:{f:v[f] for f in
            ('evaluation_pose','min_static_center_clearance_m','counts_by_type','unique_groups')} for k,v in g['sites'].items()}) for g in geometries],
        detail=dict(path=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest()),
        new_physical_success='unmeasured',offline_replay_is_improvement_evidence=False)
    (BASE/'release7-analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(verified_files=len(all_hashes),frames=len(reviewed),geometry=summary['geometry']),ensure_ascii=False))


if __name__=='__main__':main()
