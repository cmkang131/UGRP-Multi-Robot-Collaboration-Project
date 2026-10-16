"""Saved own-input diagnosis and static algebra only; no physics/model/network.

Run in the existing simulation venv. Output lives beside this script. No raw
file is modified. GT, contacts, measured joints and top cameras are not read.
"""
from __future__ import annotations

import base64
from collections import Counter
import inspect
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS
import sys

import replay as r

HERE = Path(__file__).resolve().parent
REF = '3ea2edc08e5addafaf3cedc934c463ad8e1635c8'
RAW = r.RAW / ('zone-pair-dev-v5b-' + REF)
loader = r.FrozenPairs(REF)
sys.meta_path.insert(0, loader)
import cv2
import numpy as np
from PIL import Image, ImageDraw
from harness.wall_tags import TagDetector, tag_world_frame
from harness.owncam_view import project_base_points, valid_pixel_mask
from harness.owncam_drive import LOOK_P20
from harness.zone_pair_align import PairAlignRelook
from harness.zone_pair_grasp import stationary_beam_estimate
from harness.zone_pair_geometry import PairSweepGuard
from harness.zone_own_guards import (SweepGuard, OwnPose, UncertaintyGate, GATE_LOADED,
                                    GATE_UNLOADED, body_spheres, CHASSIS_X_M, CHASSIS_Y_M)
from harness.zone_own_perception import judge_route_blockage
from harness.owncam_pair_beam_v2 import observe_beam, pose_of
from harness.zone_pair_beam_track import RestingBeamTrack, standoff_estimate

HASHES = {}
def read(p, lines=False):
    p = Path(p)
    HASHES[str(p)] = r.sha(p)
    return r.rows(p) if lines else r.read(p)

def own_image(root, rid, f):
    obs = read(root / 'inputs' / rid / f"{f['frame']:05d}.json")
    path = root / obs['image_file']
    data = path.read_bytes()
    h = r.sha(path)
    HASHES[str(path)] = h
    assert h == obs['sha256'] == f['sha256']
    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    obs['image'] = base64.b64encode(data).decode()
    return obs, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

def projection(static, xyz, servo):
    """No ray casting / occlusion inference. Same candidate test as v5b."""
    x, y, yaw = xyz
    c, s = math.cos(yaw), math.sin(yaw)
    rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])
    valid = valid_pixel_mask()
    found = []
    for tag in static['landmarks']['tags']:
        center, axes = tag_world_frame(tag)
        if np.dot(np.array([x, y]) - center[:2], tag['normal_xy']) <= 0:
            continue
        h = tag['size_m'] / 2
        corners = np.array([[-h,h,0],[h,h,0],[h,-h,0],[-h,-h,0]]) @ axes.T + center
        px = project_base_points(servo, (corners - [x, y, 0]) @ rot)
        if not np.isfinite(px).all() or not ((px >= 1).all() and (px < [639,479]).all()):
            continue
        uv = px.astype(int)
        side = float(np.mean(np.linalg.norm(px - np.roll(px, 1, axis=0), axis=1)))
        if side >= 8 and valid[uv[:,1], uv[:,0]].all():
            found.append({'id': tag['id'], 'side_px': round(side,3),
                          'center_px': np.mean(px,axis=0).round(2).tolist()})
    return found

def gate_check(f, obs, start, gate_ok):
    """Execute exact frozen predicate, then isolated clock-clause counterfactual.

    Report scalars are saved/rounded; same-loc identity is guaranteed by the
    frozen property. last_tag_t is the current own capture (age=0). This is a
    predicate replay, not a reconstructed full PF/controller state.
    """
    report = r.report(f)
    now = obs['sim_time']
    loc = NS(last_tag_t=now)
    own = NS(last_report=report, gate=NS(ok=gate_ok), pose=NS(loc=loc))
    ctl = NS(driver=NS(loc=loc), port=NS(own=own), align_look_started_at=start)
    baseline = PairAlignRelook._align_fix_ready(ctl, now)
    from harness.zone_own_contract import POSE_TIME_ROUNDING_S
    # Compile in memory only, preserving all other conjuncts and thresholds.
    source = loader.sources['harness.zone_pair_align'].replace(
        'start < r.t_est - r.since_tag_s <= now',
        'start < r.t_est - r.since_tag_s <= now + 0.0001')
    ns = {'__name__':'diagnostic_clock_variant'}
    exec(compile(source, '<diagnostic clock clause only>', 'exec'), ns)
    tolerant = ns['PairAlignRelook']._align_fix_ready(ctl, now)
    return {'exact_frozen_predicate': baseline, 'clock_clause_only_variant': tolerant,
            'gate_ok_reconstructed': gate_ok, 'estimated_tag_time_minus_now_s':report.t_est-report.since_tag_s-now,
            'existing_pose_time_tolerance_s':POSE_TIME_ROUNDING_S,
            'variant_time_tolerance_s':.0001,
            'sigma_xy_m':report.std_xy_m,'sigma_yaw_deg':math.degrees(report.std_yaw_rad)}

def contact_sheet(tiles, dest, cols=3):
    w, h = 480, 385
    sheet = Image.new('RGB', (cols*w, math.ceil(len(tiles)/cols)*h), 'white')
    dr = ImageDraw.Draw(sheet)
    for i,(im,txt) in enumerate(tiles):
        x,y=(i%cols)*w,(i//cols)*h
        sheet.paste(im.resize((480,360)), (x,y))
        dr.text((x+5,y+362),txt,fill='black')
    sheet.save(dest, quality=86)

def dev_diagnosis():
    runs=[];decision_tiles=[];block_tiles=[]
    for run in ('dev09','dev10'):
        root=RAW/run
        bots=read(root/'robots.json'); pair=read(root/'pair_records.json')[0]
        events=read(root/'events.jsonl',True);commands=read(root/'commands.jsonl',True)
        static=read(root/'inputs/static.json');manifest=read(root/'manifest.json')
        read(root/'prereg.json'); read(root/'result.json')
        det=TagDetector.for_map(static['map'])
        item={'id':run,'source_sha':manifest['source']['source_sha'],'robots':{},'blockages':[]}
        for rid in ('r1','r2'):
            pe=pair['robots'][rid]['events']
            trigger=next(e for e in pe if e['event']=='align_relook_trigger')
            selection=next(e for e in pe if e['event']=='align_view_selection')
            failure=next(e for e in events if e['robot_id']==rid and e['event']=='job_failed')
            t0,t1=trigger['sim_s'],failure['sim_s']
            decisions={i['frame_id']:i for i in pair['robots'][rid]['inputs'] if i['phase']=='align_relook'}
            gate=UncertaintyGate(); frames=[];checks=[]
            transition=next(e['sim_s'] for e in pe if e.get('state')=='align_start')
            for f in bots[rid]['frames']:
                # Own report time matches the runtime capture to 1e-4.
                gate.set_profile(GATE_LOADED if f['t']>=transition else GATE_UNLOADED)
                rep=f['report']
                gate.update(f['t'],rep['initialized'],rep['std_xy_m'],rep['std_yaw_rad'])
                if f['t'] < t0-1e-7 or f['t']>t1+1e-7:
                    continue
                obs,rgb=own_image(root,rid,f);dets=det.detect(rgb)
                ds=sorted(d['id'] for d in dets)
                assert ds==rep['last_valid_obs']['tag_ids'] and rep['since_tag_s']==0
                servo={int(k):v for k,v in f['commanded_servo'].items()}
                proj=projection(static['map'],rep['xyyaw'],servo)
                row={'frame':f['frame'],'frame_id':f['frame_id'],'t':f['t'],'capture_time':obs['sim_time'],
                     'sha256':f['sha256'],'commanded_servo':f['commanded_servo'],
                     'detected_tag_ids':ds,'projected_tag_ids':[p['id'] for p in proj],
                     'report_sigma_xy_m':rep['std_xy_m'],'report_sigma_yaw_rad':rep['std_yaw_rad'],
                     'since_tag_s':rep['since_tag_s'],'decision_frame':f['frame_id'] in decisions}
                frames.append(row)
                if row['decision_frame']:
                    check={'frame_id':f['frame_id'],'t':f['t'],'pan':servo[6],'detected_tag_ids':ds,
                           'projected_tags':proj, **gate_check(f,obs,t0,gate.ok)}
                    checks.append(check)
                    im=Image.fromarray(rgb);draw=ImageDraw.Draw(im)
                    for d in dets:
                        pts=[tuple(v) for v in d['corners_px']]
                        draw.line(pts+[pts[0]],fill='red',width=2);draw.text(pts[0],str(d['id']),fill='red')
                    decision_tiles.append((im,f"{run} {rid} t={f['t']} pan={servo[6]} tags={len(ds)}"))
            # The first panorama itself has no beam manipulation command.
            acts=[c for c in commands if c['robot_id']==rid and t0-1e-6<=c['t']<=t1+1e-6
                  and c['kind'] in ('arm','look','mecanum','drive')]
            item['robots'][rid]={'trigger':trigger,'selection':selection,'failure':failure,
                'relook_sequences':1,'selected_pan_targets':[x['pan'] for x in selection['candidates'][:3]],
                'decision_checks':checks,'frames':frames,'frame_count':len(frames),
                'frames_with_detected_tags':sum(bool(f['detected_tag_ids']) for f in frames),
                'base_motion_commands':sum(c['kind'] in ('mecanum','drive') for c in acts),
                'arm_command_count':len(acts),
                'nominal_prestation_projection':{str(p):[x['id'] for x in projection(static['map'],pair['plan']['prestations'][rid],{**LOOK_P20,1:2000,6:p})]
                                                for p in (700,970,1230,1500,1770,2030,2300)}}
        for ev in events:
            if ev['event']!='blockage_seen':continue
            rid=ev['robot_id'];f=next(f for f in bots[rid]['frames'] if f['frame_id']==ev['detail']['frame_id'])
            obs,rgb=own_image(root,rid,f);rep=f['report'];s={int(k):v for k,v in f['commanded_servo'].items()}
            from harness.zone_own_status import uncertainty_level
            belief=dict(zip(('x_m','y_m','yaw_rad'),rep['xyyaw']))
            belief['confidence']={'low':'high','medium':'medium'}.get(uncertainty_level(r.report(f)),'low')
            result=judge_route_blockage(rgb,s,static_map=static['map'],pose_belief=belief,
                                        passage_id=ev['detail']['passage_id'])
            item['blockages'].append({'event':ev,'frame':f['frame'],'sha256':f['sha256'],
                                    'replayed':result,'servo':s})
            im=Image.fromarray(rgb);dr=ImageDraw.Draw(im)
            for candidate in result.get('evidence',result).get('candidates',[]):
                x,y,w,h=candidate['pixel_bbox'];dr.rectangle([x,y,x+w,y+h],outline='red',width=3)
            block_tiles.append((im,f"{run} {rid} blockage t={f['t']}"))
        runs.append(item)
    contact_sheet(decision_tiles,HERE/'dev09_10_relook.jpg')
    contact_sheet(block_tiles,HERE/'dev09_10_blockage.jpg',cols=2)
    return runs

def signed_box_distance(box,x,y):
    cx,cy=box['center'];hx,hy=box['half'];c,s=math.cos(box['yaw']),math.sin(box['yaw'])
    dx,dy=x-cx,y-cy;q=[abs(c*dx+s*dy)-hx,abs(-s*dx+c*dy)-hy]
    return math.hypot(max(q[0],0),max(q[1],0))+min(max(q),0)

def sigma_cap(clearance, lever, yaw_sigma_rad, bias=0., relative=0., stop=0., sampling=0.,k=2.):
    """Conservative legacy isotropic-margin inversion; no sigma clipping."""
    return (clearance-.035-bias-relative-stop-sampling-k*lever*yaw_sigma_rad)/k

def static_budget():
    root=RAW/'dev09';static=read(root/'inputs/static.json')['map'];plan=read(root/'pair_records.json')[0]['plan']
    rows=[]
    for rid,role in (('r1','end_neg'),('r2','end_pos')):
        guard=PairSweepGuard(SweepGuard(static),plan['beam_geometry'],role)
        poses={'prestation':plan['prestations'][rid],
               'nominal_grasp_station':[.575 if rid=='r1' else 1.425,0.,0. if rid=='r1' else -math.pi]}
        for stage,xyz in poses.items():
            for name,servo in [('LOOK_P20',LOOK_P20),*[(p,pose_of(p)) for p in ('search','p45','inspect')]]:
                servo={1:2000,6:1500,**servo}
                spheres=body_spheres(servo,loaded=False,mount_xyz_m=guard.mount)
                # Full beam hypothesis is included only as an envelope stress case;
                # pregrasp it remains separate, in the static sheet's coarse region.
                if stage=='nominal_grasp_station':spheres+=guard.beam_spheres(servo)
                points=[(x,y,0.,0.) for x in CHASSIS_X_M for y in (-CHASSIS_Y_M,CHASSIS_Y_M)]
                spheres+=points;c,s=math.cos(xyz[2]),math.sin(xyz[2]);values=[]
                for bx,by,bz,rad in spheres:
                    for box in guard.boxes:
                        # Conservative planar test of all walls, including low walls.
                        d=signed_box_distance(box,xyz[0]+c*bx-s*by,xyz[1]+s*bx+c*by)-rad
                        lever=math.hypot(bx,by)+rad
                        values.append({'wall':box['id'],'clearance_m':d,'lever_m':lever,
                            'sigma_xy_cap_at_yaw3deg_bias0_m':sigma_cap(d,lever,math.radians(3))})
                worst=min(values,key=lambda v:v['sigma_xy_cap_at_yaw3deg_bias0_m'])
                rows.append({'robot':rid,'position_basis':stage,'xyyaw':xyz,'posture':name,
                             'limiting':worst,'min_nominal_clearance_m':min(v['clearance_m'] for v in values),
                             'max_lever_m':max(v['lever_m'] for v in values)})
    example=[{'clearance_m':d,'lever_m':L,'yaw_sigma_deg':y,'bias_and_other_m':b,
              'sigma_xy_cap_m':sigma_cap(d,L,math.radians(y),bias=b)}
             for d in (.5,.55,.6) for L in (.2,.9) for y in (3,5,10) for b in (0,.1,.3,.8)]
    return {'scope':'Static nominal positions/postures, conservative planar walls; not live swept safety certification',
            'static_map_sha256':r.sha(root/'inputs/static.json'),'rows':rows,'sensitivity':example,
            'formula':'sigma_xy_max=(d-.035-B-relative-stop-sampling-2*L*sigma_yaw)/2',
            'directional_formula':'sqrt(n.T P_xy n)_max=(d-.035-B-relative-stop-sampling-yaw_bound)/k',
            'nonpositive_means':'REJECT; never clamp to zero and permit',
            'covariance_calibrated':False,'bias_bound_calibrated':False}

def historical():
    source=read(HERE/'m2-shadow-main.json');contracts=read(HERE/'m2-input-contracts.json');rows=[]
    for run in source['runs']:
        root=r.RAW/run['id'];meta=read(root/'result.json');ev=read(root/'events.jsonl',True)
        ins=read(root/'inputs.jsonl',True);read(root/'commands.jsonl',True)
        for fn,h in run['hashes'].items():assert HASHES[str(root/fn)]==h
        row={'id':run['id'],'source_sha':run['source_sha'],'stage':meta['stage'],
             'development_seed':meta.get('development_seed'),'robots':{},
             'new_design_verdict':'INSUFFICIENT_EVIDENCE',
             'reason':'Missing calibrated relative/global bounds and new dual certificates; changed viewpoints unavailable'}
        for rid in ('r1','r2'):
            ee=[e for e in ev if e['robot']==rid]
            vv=[e for e in ee if e['event']=='vo_pose'];obs=[e for e in ee if e['event']=='beam_obs']
            aligned=meta.get('claims',{}).get(rid,{}).get('aligned')
            # Inspect saved first and last align image; no future frame substituted.
            fs=[f for f in ins if f['robot']==rid and f['state']=='align']
            samples=[]
            for f in [fs[0],fs[-1]] if fs else []:
                p=root/'inputs'/f['file'];h=r.sha(p);HASHES[str(p)]=h;assert h==f['sha256']
                ob={'image':base64.b64encode(p.read_bytes()).decode()}
                fit=observe_beam(ob['image'],f['own_pose_commands'])
                samples.append({'t':f['sim_time'],'sha256':h,'file':str(p),
                                'visible':fit.get('visible'),'end_visible':fit.get('end_visible'),
                                'grip_base_m':fit.get('grip_base_m'),'reason':fit.get('reason'),
                                'anchor_fit':standoff_estimate(ob,f['own_pose_commands'])})
            row['robots'][rid]={'vo_events':vv,'aligned_claim':aligned,'align_sample_fits':samples,
                'original_shadow_first_reject':run['robots'][rid]['first_shadow_postapproach_gate_reject'],
                'grasp_pose_estimate':meta.get('claims',{}).get(rid,{}).get('grasp_pose_estimate'),
                'relative_anchor_calibrated':False}
        rows.append(row)
    dev=read(HERE/'dev-grasp-v5.json')
    return {'scope':'success-selected M2 49 plus dev03-10; necessary-evidence audit, not new closed-loop replay',
            'm2_runs':rows,'m2_run_count':len(rows),'m2_trace_count':len(rows)*2,
            'vo_trace_count':sum(any(e.get('pose') is not None for e in x['vo_events']) for z in rows for x in z['robots'].values()),
            'initial_anchor_fit_count':sum(bool(x['align_sample_fits'] and x['align_sample_fits'][0]['anchor_fit']) for z in rows for x in z['robots'].values()),
            'last_align_anchor_fit_count':sum(bool(x['align_sample_fits'] and x['align_sample_fits'][-1]['anchor_fit']) for z in rows for x in z['robots'].values()),
            'm2_existing_preclose_attempts':sum(len(b['close_attempts']) for z in contracts['runs'] for b in z['robots'].values()),
            'm2_existing_fresh_preclose_pass':sum(c['necessary_preclose_input_pass'] for z in contracts['runs'] for b in z['robots'].values() for c in b['close_attempts']),
            'dev_old_ids':[x['id'] for x in dev['runs']],
            'all_m2_full_design_passes':0,'all_m2_full_design_unknown':len(rows)}

def main():
    data={'schema':'ugrp.beam_frame_diagnosis.v1','run_source_sha':REF,
          'analysis_checkout':r.git('rev-parse','HEAD'),'physics_steps':0,'model_calls':0,
          'GT_read':False,'dev':dev_diagnosis(),'static_budget':static_budget(),'history':historical()}
    source_paths=['harness/owncam_localizer.py','harness/owncam_pose_source.py','harness/wall_tags.py',
                  'harness/owncam_view.py','harness/zone_own_perception.py','harness/zone_own_guards.py',
                  'harness/zone_own_contract.py','scripts/run_m2_pair.py']
    import hashlib
    data['source_checks']={}
    for path in source_paths:
        blob=r.git('show',REF+':'+path)+'\n';current=(r.ROOT/path).read_text()
        assert blob==current, path
        data['source_checks'][path]={'matches_run_source':True,'sha256':hashlib.sha256(current.encode()).hexdigest()}
    data['frozen_pair_modules']={k:hashlib.sha256(v.encode()).hexdigest() for k,v in loader.sources.items()}
    data['hashes']=HASHES
    data['blocked_modules_not_imported']=all(m not in sys.modules for m in ('mujoco','torch','tensorflow','requests','httpx'))
    assert data['blocked_modules_not_imported']
    r.write(HERE/'dev09_10_diagnosis.json',data)
    print(json.dumps({'runs':[{'id':x['id'],'frames':sum(z['frame_count'] for z in x['robots'].values()),
          'clock_only_passes':sum(c['clock_clause_only_variant'] for z in x['robots'].values() for c in z['decision_checks'])} for x in data['dev']],
          'history':{k:v for k,v in data['history'].items() if k!='m2_runs'},'hashed_files':len(HASHES)},ensure_ascii=False))

if __name__=='__main__':main()
