"""Remote own-record replay and ORB diagnostic; no policy changes or truth fit."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
import cv2
import numpy as np
from scripts.mapbuild1_replay import read_frame, replay, score, dump, percentiles
from harness.e2e_rgb_vo import K,D,image_mask,compose
from harness.natural_floor_slam import _matches
from harness.servo_camera_fk import transform_from_commands
from scripts.mapbuild2_commands import increments


def pipeline(images, frames, *, corrected=False, masked=False, features=500, fast=20, stride=1, codec='jpg', levels=8, half=False, blur=False):
    """OpenCV API defaults, except documented diagnostic factors.

    ORB.create default nfeatures500, scaleFactor1.2/nlevels8/FAST20;
    800 is existing mapbuild1; 2000 is a compute-budget comparator, not
    an acceptance threshold. FAST7 is prior warp5 comparator. Hamming KNN,
    Lowe ratio .75: OpenCV tutorial_py_matcher. Essential RANSAC uses the
    API defaults prob=.999, threshold=1px, maxIters1000; algebraic minimum5.
    Mutual ratio is separately counted and is not a standard prerequisite.
    """
    # Pyramid 1/4 are finite compute-budget ablations of default8. Half-VGA
    # preserves FOV and scales K with OpenCV resize's pixel-centre convention.
    # Gaussian3x3/sigma0 is a diagnostic OpenCV operator, not a claim that the
    # camera has this PSF and never an actor acceptance/quality threshold.
    orb=cv2.ORB_create(nfeatures=features,fastThreshold=fast,nlevels=levels)
    intrinsic=K.copy()
    if half:intrinsic=np.array([[.5,0,-.25],[0,.5,-.25],[0,0,1.]])@K
    computed=[];rows=[]
    for frame in frames:
        rgb=images[frame['frame_id']][codec]
        servo={int(k):v for k,v in frame['servo'].items()}
        mask=None
        if masked:
            camera,_=transform_from_commands(servo,camera_pose='servo_fk_v1')
            if camera is None:computed.append(None);continue
            mask=image_mask(rgb,servo)
        if corrected:
            rgb=cv2.fisheye.undistortImage(rgb,K,D,Knew=K,new_size=(640,480))
            if mask is not None:mask=cv2.fisheye.undistortImage(mask,K,D,Knew=K,new_size=(640,480))
        if half:
            rgb=cv2.resize(rgb,(320,240),interpolation=cv2.INTER_AREA)
            if mask is not None:mask=cv2.resize(mask,(320,240),interpolation=cv2.INTER_NEAREST)
        if blur:rgb=cv2.GaussianBlur(rgb,(3,3),0)
        gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
        kp,desc=orb.detectAndCompute(gray,mask)
        uv=np.asarray([p.pt for p in kp],np.float64).reshape(-1,2)
        computed.append((uv,desc,float(gray.std()),float(cv2.Laplacian(gray,cv2.CV_64F).var())))
    for i in range(0,len(frames)-stride,stride):
        a,b=computed[i],computed[i+stride]
        row=dict(frame=i,next_frame=i+stride,features_a=0,features_b=0,ratio_n=0,mutual_n=0,ransac_n=0,reason='unqualified_camera')
        if a is not None and b is not None:
            u,da,contrast,lap=a;v,db,_,_=b
            row.update(features_a=len(u),features_b=len(v),contrast=contrast,laplacian_variance=lap,reason='insufficient_descriptors')
            if da is not None and db is not None and min(len(da),len(db))>=2:
                pairs=cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da,db,k=2)
                matches=[m for pair in pairs if len(pair)==2 for m,n in [pair] if m.distance<.75*n.distance]
                row.update(ratio_n=len(matches),mutual_n=len(_matches(da,db,.75)),reason='fewer_than_five_ratio_matches')
                if len(matches)>=5:
                    ua=np.asarray([u[m.queryIdx] for m in matches]);vb=np.asarray([v[m.trainIdx] for m in matches])
                    # Essential geometry consumes ideal pixel coordinates even
                    # when descriptor detection was performed on raw fisheye.
                    if not corrected:
                        ua=cv2.fisheye.undistortPoints(ua.reshape(-1,1,2),intrinsic,D,P=intrinsic).reshape(-1,2)
                        vb=cv2.fisheye.undistortPoints(vb.reshape(-1,1,2),intrinsic,D,P=intrinsic).reshape(-1,2)
                    cv2.setRNGSeed(i)
                    e,mask=cv2.findEssentialMat(ua,vb,intrinsic,method=cv2.RANSAC,prob=.999,threshold=1.,maxIters=1000)
                    row.update(ransac_n=int(mask.sum()) if mask is not None else 0,reason='essential_returned' if e is not None else 'essential_failed')
        row.update(category='orb_pair_diagnostic',blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured')
        rows.append(row)
    return rows


def run(a):
    a.output.mkdir(exist_ok=False,parents=True)
    manifest=json.loads((a.input/'own.json').read_text())
    raw_manifest=manifest
    computed=increments(manifest['frames'],json.loads((a.input/'commands.json').read_text()))
    normalized=[]
    for row in manifest['frames']:
        increment=computed[row['sequence'],row['frame_id']]
        if not np.array_equal(row['command_delta'],increment['command_delta']):raise ValueError('ISSUED_MEAN_REPLAY_MISMATCH')
        normalized.append({**row,**increment})
    manifest={**manifest,'frames':normalized}
    dump(a.output/'command-covariance-replay.json',dict(scope='own issued history only; original capture retained',
        reason='capture-r4 serialized cumulative prior covariance; replay uses per-frame independent increments',
        frame_n=len(normalized),changed_n=sum(not np.array_equal(a['command_covariance'],b['command_covariance'])
            for a,b in zip(raw_manifest['frames'],normalized))))
    summaries={};outputs={}
    for candidate in ('legacy','orange-columns-fast7'):
        rows=replay(a.input,manifest,candidate=candidate)
        # Save the causal estimates BEFORE opening evaluation labels.
        dump(a.output/(candidate+'-trajectory.json'),rows);outputs[candidate]=rows
    command_rows=[];poses={}
    for row in manifest['frames']:
        name=row['sequence'];poses[name]=compose(poses.get(name,np.zeros(3)),row['command_delta'])
        command_rows.append(dict(sequence=name,frame_id=row['frame_id'],lk_pose=poses[name].tolist(),
            lk=dict(status='command_only'),slam=dict(status='command_only',pose=poses[name].tolist())))
    dump(a.output/'command-trajectory.json',command_rows)
    labels=json.loads((a.input/'eval-only.json').read_text())
    for candidate,rows in outputs.items():summaries[candidate]=score(rows,labels)
    summaries['issued_v122_prediction']=score(command_rows,labels)
    grouped=defaultdict(list)
    for frame in manifest['frames']:grouped[frame['sequence']].append(frame)
    configs=[dict(name='opencv-default-raw'),dict(name='opencv-default-rectified',corrected=True),
        dict(name='existing800-masked',features=800,masked=True),dict(name='800-raw',features=800),
        dict(name='2000-raw',features=2000),dict(name='800-fast7',features=800,fast=7),
        dict(name='800-gap500ms',features=800,stride=5),dict(name='800-lossless',features=800,codec='png'),
        dict(name='800-pyramid1',features=800,levels=1),dict(name='800-pyramid4',features=800,levels=4),
        dict(name='800-half-vga',features=800,half=True),dict(name='800-blur3',features=800,blur=True)]
    diagnostic=[];events=[]
    for name,frames in sorted(grouped.items()):
        images={r['frame_id']:dict(jpg=read_frame(a.input,r),png=cv2.cvtColor(cv2.imread(str((a.input/r['rgb']).with_suffix('.png'))),cv2.COLOR_BGR2RGB)) for r in frames}
        for config in configs:
            cfg={k:v for k,v in config.items() if k!='name'}
            rows=pipeline(images,frames,**cfg)
            events.extend(dict(sequence=name,config=config['name'],**r) for r in rows)
            diagnostic.append(dict(sequence=name,config=config['name'],pairs=len(rows),
                feature_a=percentiles([r['features_a'] for r in rows]),ratio=percentiles([r['ratio_n'] for r in rows]),
                mutual=percentiles([r['mutual_n'] for r in rows]),ransac=percentiles([r['ransac_n'] for r in rows]),
                reasons=dict(Counter(r['reason'] for r in rows)),stages=[
                dict(stage='pairs',cumulative_pass_n=len(rows),rejected_n=0),
                dict(stage='descriptors_both',cumulative_pass_n=sum(min(r['features_a'],r['features_b'])>=2 for r in rows),
                     rejected_n=sum(min(r['features_a'],r['features_b'])<2 for r in rows)),
                dict(stage='ratio_ge5',cumulative_pass_n=sum(r['ratio_n']>=5 for r in rows),
                     rejected_n=sum(min(r['features_a'],r['features_b'])>=2 and r['ratio_n']<5 for r in rows)),
                dict(stage='essential_matrix_returned',cumulative_pass_n=sum(r['reason']=='essential_returned' for r in rows),
                     rejected_n=sum(r['ratio_n']>=5 and r['reason']!='essential_returned' for r in rows))]))
    dump(a.output/'orb-events.json',events)
    dump(a.output/'rejection-table.json',dict(raw=str(a.input),reproduction=sys.argv,orb=diagnostic,
        tracking=[dict(candidate=k,reasons=dict(Counter(r['lk']['status'] for r in rows))) for k,rows in outputs.items()]))
    ranges=json.loads((a.input/'range.json').read_text())
    dump(a.output/'summary.json',dict(status='ANALYSIS_COMPLETE',tracking=summaries,orb=diagnostic,
        ranges={name:dict(n=sum(r['sequence']==name for r in ranges),status=dict(Counter(r['status'] for r in ranges if r['sequence']==name)),
            range_m=percentiles([r['range_m'] for r in ranges if r['sequence']==name and r['range_m'] is not None])) for name in grouped},
        scope='same acquisition diagnostic, no holdout; essential return is not metric tracking success'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
