"""Hash-checked saved-own-input replay. No simulator or evaluation truth in decisions."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from scripts.replay_release14 import decoded
from sim import release14, release15
from sim.release_regrasp import lift_evidence, continuity
from sim.global_landmark_localization import GlobalLandmarkMatcher
from sim.lookaround_localization import Camera, OwnPose
from sim.visible_belief import odometry
from harness.vision_loc_protocol import load_vis3

ROOT=Path(__file__).resolve().parents[1]
NAMES=('r12d-01-97942a82','release11-diag-08-c9ba20a6','r14d-00-7369ad5e','r14d-01-7369ad5e')


def replay(root, reports):
    runs=[];u=load_vis3()[0].mp.undistort
    static=json.loads((ROOT/'maps/zones/zone_wide_door_geometry_v3.json').read_text())
    for name in NAMES:
        p=root/name/'raw';mp=p/'manifest.json'
        if not mp.exists():mp=p/'manifest.json.zst'
        manifest=json.loads(decoded(mp));verified={}
        def payload(file):
            path=p/file;digest=hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest==manifest[file]['sha256'],file
            data=decoded(path)
            if manifest[file].get('decoded_sha256'):
                assert hashlib.sha256(data).hexdigest()==manifest[file]['decoded_sha256']
            verified[file]=digest;return data
        result=json.loads(payload('result.json.zst'))
        rows={r:[json.loads(s) for s in payload(f'teacher-{r}.jsonl.zst').splitlines()] for r in ('r1','r2')}
        inputs=result['regrasp_input_frames'];images={};payload_n=len(verified)
        def image(ref):
            file=p/ref['path']
            if not file.exists():file=reports/name/'native-input/raw'/ref['path']
            digest=hashlib.sha256(file.read_bytes()).hexdigest()
            assert digest==ref['sha256']==manifest[ref['path']]['sha256']
            verified[ref['path']]=digest
            if ref['path'] not in images:images[ref['path']]=cv2.imread(str(file))
            return images[ref['path']]
        # A saved global RGB fit + issued wheel integrals can reconstruct the
        # pose used for later line checks. Do not touch eval-only or spawn pose.
        def localizer(rid,at):
            rec=result.get('lookaround_result',{}).get(rid,{}).get('localizer',{})
            dec=rec.get('decision') or {}
            if not dec.get('accepted') or 'proposed' not in dec:
                return None
            own=OwnPose(dec['proposed'],dec['sigma'][0],dec['sigma'][2])
            own.P=np.diag(np.asarray(dec['sigma'])**2)
            last_view=max(v['t'] for v in rec['views'])
            for row in rows[rid]:
                if row['t']<last_view-1e-6 or row['t']>=at-1e-6:continue
                dt=min(.1,at-row['t'])
                effective=[w*max(0.,min(dt,end-row['t']))/.1 for w,end in zip(row['wheels'],row['wheel_until'])]
                own.propagate(*odometry(effective,.1,'native_yaw_v1'))
            return SimpleNamespace(own=own,map_pose_known=True,decision=dec,global_matcher=GlobalLandmarkMatcher(static))
        reconstruction={}
        for rid in rows:
            rec=result.get('lookaround_result',{}).get(rid,{}).get('localizer',{})
            last=localizer(rid,rows[rid][-1]['t']+.1)
            if last is not None:
                delta=last.own.x-np.asarray(rec['final_estimate'])
                delta[2]=np.arctan2(np.sin(delta[2]),np.cos(delta[2]))
                reconstruction[rid]=dict(position_error_m=float(np.linalg.norm(delta[:2])),yaw_error_rad=float(abs(delta[2])))
                assert np.linalg.norm(delta)<1e-6, (name,rid,reconstruction[rid])
        align=[]
        for ref in inputs:
            if ref['label'] not in ('realign_back','realign_final','line_recheck'):continue
            rid=ref['robot'];row=max((x for x in rows[rid] if x['t']<=ref['t']+1e-6),key=lambda x:x['t'])
            assert ref['t']-row['t']<.101
            pwm={int(k):v for k,v in row['pwm'].items()};im=u(image(ref));end='teal' if rid=='r1' else 'blue'
            feature=release15.line_features(im,end)
            loc=localizer(rid,ref['t'])
            # Old run may lack an accepted global fix. Report the image proposal
            # separately; never invent a map acceptance for that saved state.
            proposal=release15.line_step(feature,Camera(),pwm,clearance=lambda *a:True)
            gated=None if loc is None else release15.line_step(feature,Camera(),pwm,
                clearance=lambda *a:release15.map_motion_clear(loc,*a))
            old=release14.line_step(release14.line_features(im),Camera(),pwm)
            align.append(dict(t=ref['t'],robot=rid,pwm_ledger_t=row['t'],feature=feature,
                release14=old,release15_image_proposal=proposal,release15_map_gated=gated,
                map_fix_available=loc is not None))
        challenges=[];hues=[]
        for barrier in result['regrasp_verification']:
            starts=[e for e in barrier['events'] if e['event']=='test_start']
            for start in starts:
                rid=start['robot'];end='teal' if rid=='r1' else 'blue'
                stop=min((e['t'] for e in starts if e['robot']==rid and e['t']>start['t']+1e-6),default=float('inf'))
                fs=[f for f in inputs if f['robot']==rid and f['epoch']==barrier['epoch'] and start['t']-1e-6<=f['t']<stop-1e-6]
                b=next(f for f in fs if f['label']=='before_test');a=next(f for f in fs if f['label']=='lift_complete')
                cmd=[dict(t=x['t'],pwm=x['pwm'],wheels=x['wheels']) for x in rows[rid] if b['t']-1e-6<=x['t']<=a['t']+1e-6]
                before,after=image(b),image(a);samples=[]
                for ref in [f for f in fs if f['label']=='settled_test']:
                    im=image(ref)
                    old=lift_evidence(before,after,im,cmd,end=end)
                    new=lift_evidence(before,after,im,cmd,end=end,colour_profile=release15.PROFILE)
                    samples.append(dict(t=ref['t'],old=old['answer'],new=new['answer'],reason=new['reason']))
                    if rid=='r1' and start['attempt']>1:
                        hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
                        # Audit of OLD candidate pixels, not ground-truth labels.
                        mask=cv2.inRange(hsv,np.array([70,120,90]),np.array([90,255,255]))>0
                        vals=hsv[:,:,0][mask]
                        if len(vals):hues.append(dict(t=ref['t'],candidate_pixels=len(vals),retained=int((vals<=83).sum()),quantiles=np.quantile(vals,[0,.01,.5,.99,1]).tolist()))
                restored=next((f for f in fs if f['label']=='restored_test'),None)
                retention=None if restored is None else continuity(before,image(restored),end=end,colour_profile=release15.PROFILE)
                challenges.append(dict(robot=rid,epoch=barrier['epoch'],attempt=start['attempt'],samples=samples,
                    old_counts=dict(Counter(s['old'] for s in samples)),new_counts=dict(Counter(s['new'] for s in samples)),restored=retention))
        viewed=[]
        ep=reports/name/'evidence.json'
        if ep.exists():
            evidence=json.loads(ep.read_text())
            for ref in evidence['selected_frames']:
                f=reports/name/'frames'/ref['relative'];digest=hashlib.sha256(f.read_bytes()).hexdigest()
                assert digest==ref['sha256']
                viewed.append(dict(path=str(f),sha256=digest,t_relative=ref['time_relative_s']))
        first=next((a for a in align if a['release14']['kind']!=a['release15_image_proposal']['kind']),None)
        runs.append(dict(name=name,source_sha=result['source_sha'],raw=str(p),stored_outcome=result['release_outcome'],
            payloads_verified=payload_n,jpegs_verified=len(images),pose_reconstruction=reconstruction,sha256=verified,line_replay=align,challenges=challenges,
            first_image_branch_difference=None if first is None else dict(t=first['t'],robot=first['robot'],old=first['release14']['kind'],new=first['release15_image_proposal']['kind'],map_gated=first['release15_map_gated']),
            first_runner_difference_vs_pre14=None if name.startswith('r14d') else dict(t=14.9,action='pre-backoff RGB localization inherited from release14'),
            teal_hue_audit=hues,visually_reviewed_overview_and_own=viewed))
    return dict(schema='ugrp.release15.replay.v1',profile=release15.PROFILE,runs=runs,
        scope='Independent decisions on saved old states, not a counterfactual closed-loop trajectory',
        physical_effect='unverified',new_runs=0,truth_inputs=False,render_calls=0)


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--reports',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=replay(a.raw_root,a.reports);a.out.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(dict(runs=len(r['runs']),payloads=sum(x['payloads_verified'] for x in r['runs']),jpegs=sum(x['jpegs_verified'] for x in r['runs']),
        branches=[dict(run=x['name'],first=x['first_image_branch_difference']) for x in r['runs']],physical_effect='unverified')))
if __name__=='__main__':main()
