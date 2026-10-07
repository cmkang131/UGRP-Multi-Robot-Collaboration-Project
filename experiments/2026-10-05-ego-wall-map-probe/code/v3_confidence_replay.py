"""Own-RGB extraction/prediction, separate GT scoring. Never import MuJoCo."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import odom_grid_replay as base
import markerless_probe as mp
import height_free_wall as hfw
import wall_probe as wp
import ego_wall_map as ewm
from harness.self_odom_grid import CommandOdometry, OdomGrid, transform
from harness.wall_camera_calibration import calibration, camera_transform
from harness.wall_confidence import confidence, weighted_insert
from harness.wall_projection_guard import filter_segments

ROOT = base.ROOT
OUT = ROOT/'outputs/self-map-v3-confidence-v1'
RESULTS = ROOT/'experiments/2026-10-05-ego-wall-map-probe/results/v3_confidence_v1'
PARAMS = {'floor_patch_max_m':.81,'run_step_window':3,'top_edge_px':4}
EPISODES = {f's{s}': next(p for p in Path('/Users/changmin/projects/ugrp/outputs').glob(f's2-realism-*-s{s}-P1-2-*')
                          if (p/'robots/r3/frames.jsonl').exists()) for s in range(1042,1048)}


def load(path):
    return json.loads(Path(path).read_text())


def rows(path, values):
    Path(path).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in values))


def own_inputs(episode,robot):
    # Drop simulator actuator_state and every unapproved frame field immediately.
    fs = [{k:r[k] for k in ('robot_id','frame_id','sim_time','sha256','camera','path','commanded_servo')}
          for r in base.read_rows(episode/f'robots/{robot}/frames.jsonl')]
    cs = sorted(base.read_rows(episode/f'robots/{robot}/commands.jsonl'),key=lambda r:r['t'])
    assert all(f['robot_id']==robot and f['camera']=='robot_cam' for f in fs)
    return fs,cs


def geometry(servo,mode):
    cols = mp.column_positions(96,2)
    if mode == 'off':
        cm = mp.column_model(servo,wp.detector_bias(servo,wp.is_loaded(servo),True),cols)
        return cm,np.array([ewm.ARM_AXIS_OFFSET_M,0.,0.]),'legacy'
    rigid,reason = camera_transform(servo,wall_camera_calibration=mode)
    if rigid is None:
        return None,None,reason
    assert np.allclose(mp.K,calibration()['intrinsics_K'],atol=1e-12,rtol=0)
    from sim.masterpi_camera_profile import CAMERA_FISHEYE_D
    assert np.allclose(CAMERA_FISHEYE_D,calibration()['fisheye_D'],atol=1e-12,rtol=0)
    cm = mp.ColumnModel(tuple(sorted(servo.items())),0.,cols,camera_transform=rigid)
    return cm,np.zeros(3),reason


def detections(episode,frame,cm,offset,body_settling):
    import cv2
    path = episode/frame['path']
    if base.sha(path) != frame['sha256']:
        raise ValueError('FRAME_HASH_MISMATCH')
    image = cv2.imread(str(path))
    und = mp.undistort(image)
    grey = cv2.cvtColor(und,cv2.COLOR_BGR2GRAY).astype(float)
    servo = {int(k):int(v) for k,v in frame['commanded_servo'].items()}
    scan = hfw.detect(und,cm,params=PARAMS,loaded=wp.is_loaded(servo))
    linked = hfw.link_segments(scan,PARAMS)
    segs,features = [],[]
    for segment in linked:
        polar = ewm.segment_to_chassis(segment,cm.origin[:2],offset[0])
        r,a,s,b,_ = polar
        segs.append([[r*math.cos(a),r*math.sin(a)],[s*math.cos(b),s*math.sin(b)]])
        ix = np.arange(segment['col_first'],segment['col_last']+1)
        v = np.rint(scan['vb'][ix,0]).astype(int).clip(1,mp.HEIGHT-2)
        u = cm.columns[ix].astype(int)
        features.append({'height_m':float(cm.origin[2]),'fy':mp.FY,
            'contrast':segment['contrast_med'],'band_std':float(np.median(scan['s'][ix,0])),
            'sharpness':float(np.median(abs(grey[v+1,u]-grey[v-1,u]))),
            'body_settling':float(body_settling)})
    valid,decision = filter_segments(segs,wall_projection_guard='positive_depth_v1',
        camera_origin=cm.origin+offset,camera_rotation=cm._rot)
    ids = [e['segment'] for e in decision['segments'] if e['accepted']]
    return valid,[features[i] for i in ids],decision


def extract(case,mode):
    episode,robot = EPISODES[case],'r3'
    fs,cs = own_inputs(episode,robot)
    out = OUT/case/mode
    out.mkdir(parents=True,exist_ok=False)
    odom = CommandOdometry(fs[0]['sim_time'])
    odom.command({'t':fs[0]['sim_time'],'kind':'initial_servo_command','pulses':fs[0]['commanded_servo']})
    cursor,expiry = 0,-math.inf
    contacts,events,poses = [],[],[]
    for idx,f in enumerate(fs):
        t = f['sim_time']
        while cursor < len(cs) and cs[cursor]['t'] < t-1e-8:
            cmd = cs[cursor]
            odom.command(cmd)
            if cmd['kind'] in ('mecanum','drive'):
                expiry = cmd['t']+cmd['duration_s']
            elif cmd['kind'] in ('hold','stop'):
                expiry = min(expiry,cmd['t'])
            cursor += 1
        odom.advance(t)
        poses.append({'t':t,'pose':odom.pose})
        if idx%2:
            continue
        e = {'frame_id':f['frame_id'],'t':t}
        if t-odom.servo_since+1e-8 < (.25,2.25)[int(odom.loaded)]:
            e['reason']='unsettled'
        else:
            servo = {int(k):int(v) for k,v in f['commanded_servo'].items()}
            cm,offset,reason = geometry(servo,mode)
            e['reason'] = reason
            if cm is not None:
                segs,features,guard = detections(episode,f,cm,offset,.5+.5*np.clip((t-expiry)/.25,0,1))
                origin = cm.origin+offset
                keep = [i for i,s in enumerate(segs) if np.linalg.norm(np.array(s)-origin[:2],axis=1).max()<4.]
                e.update(detected=len(segs),near=len(keep),guard=guard)
                if keep:
                    contacts.append({'robot_id':robot,'t':t,'frame_id':f['frame_id'],
                        'camera':origin[:2].tolist(),'camera_origin':origin.tolist(),'camera_rotation':cm._rot.tolist(),
                        'segments':[segs[i] for i in keep],'features':[features[i] for i in keep]})
        events.append(e)
        if idx%1000==0:
            print(case,mode,'frame',idx,'/',len(fs),'contacts',len(contacts),flush=True)
    rows(out/'contacts.jsonl',contacts)
    rows(out/'extraction.jsonl',events)
    rows(out/'dr-poses.jsonl',poses)
    span = np.ptp(np.array([p['pose'] for p in poses]),axis=0)
    summary = {'case':case,'episode':str(episode),'robot':robot,'camera':mode,'frames':len(fs),
        'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'contacts':len(contacts),'segments':sum(len(r['segments']) for r in contacts),
        'counts':dict(Counter(e['reason'] for e in events)),'command_dr_span':span.tolist(),
        'sufficient':len(contacts)>=20 and (np.linalg.norm(span[:2])>=1 or span[2]>=math.pi/2),
        'sources':[{'path':str(p),'sha256':base.sha(p)} for p in [episode/f'robots/{robot}/frames.jsonl',episode/f'robots/{robot}/commands.jsonl']],
        'prediction_hashes':{p.name:base.sha(p) for p in out.iterdir() if p.is_file()}}
    base.dump(out/'extract-summary.json',summary)
    print(case,mode,{k:summary[k] for k in ('contacts','counts','command_dr_span','sufficient')},flush=True)


def diagnostic(case):
    """Old GT-pose slanted-line diagnosis, never a mapping/control input."""
    import map_error_oracle as diag
    source = ROOT/'outputs/own-submap-v1-complete'/case
    ref = load(ROOT/'outputs/self-map-odom-grid-v1-complete'/case/'summary.json')
    episode,robot = Path(ref['episode']),case[-2:]
    fs,cs = own_inputs(episode,robot)
    frames = {f['frame_id']:f for f in fs}
    ledger = base.read_rows(ROOT/'outputs/wall-projection-guard-v1-complete'/case/'guarded-ledger.jsonl')
    own_features, unmatched = [],0
    # Feature extraction phase has no GT; frozen before evaluation begins.
    for r in ledger:
        f=frames[r['frame_id']]
        servo={int(k):int(v) for k,v in f['commanded_servo'].items()}
        cm,offset,_=geometry(servo,'off')
        moves=[c for c in cs if c['t']<r['t']-1e-8 and c['kind'] in ('mecanum','drive','hold','stop')]
        expiry=-math.inf
        for c in moves:
            expiry = c['t']+c['duration_s'] if c['kind'] in ('mecanum','drive') else min(expiry,c['t'])
        segs,features,_=detections(episode,f,cm,offset,.5+.5*np.clip((r['t']-expiry)/.25,0,1))
        for segment in r['segments']:
            distances=[np.linalg.norm(np.array(segment)-s) for s in segs]
            if not distances or min(distances)>.02:
                unmatched+=1
                continue
            feature=features[int(np.argmin(distances))]
            conf=confidence(segment,r['camera'],feature,np.zeros((3,3)))
            own_features.append({'t':r['t'],'frame_id':r['frame_id'],'segment':segment,
                'camera':r['camera'],'features':feature,**conf})
    out=OUT/'old'/case
    out.mkdir(parents=True,exist_ok=False)
    rows(out/'own-features.jsonl',own_features)
    feature_hash=base.sha(out/'own-features.jsonl')
    # GT starts here; no feedback into extraction/coefficients.
    times,truth=base.ground_truth(episode,robot)
    truth=dict(zip(np.round(times,6),truth))
    walls=[w for w in load(episode/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall']
    rects=np.array([w['center_m']+w['half_extents_m'] for w in walls])
    records=[]
    for r in own_features:
        ends=transform(r['segment'],truth[round(r['t'],6)])
        samples=np.linspace(*ends,max(2,int(np.linalg.norm(ends[1]-ends[0])/.05)+1))
        correct=base.boundary_dist(samples,rects)<=.15
        angle=abs(math.atan2(*(ends[1]-ends[0])[::-1]))%(math.pi/2)
        slanted=min(angle,math.pi/2-angle)>math.radians(10)
        records.append({**r,'correct':int(correct.sum()),'samples':len(samples),'slanted':bool(slanted)})
    rows(out/'evaluated-detections.jsonl',records)
    groups={}
    for name,filtered in [('all',records),('slanted_false',[r for r in records if r['slanted'] and r['correct']/r['samples']<.5]),
                           ('mostly_correct',[r for r in records if r['correct']/r['samples']>=.5])]:
        groups[name]={'detections':len(filtered),'mean_weight':float(np.mean([r['weight'] for r in filtered])) if filtered else None,
            'median_weight':float(np.median([r['weight'] for r in filtered])) if filtered else None,
            'correct_samples':sum(r['correct'] for r in filtered),'samples':sum(r['samples'] for r in filtered)}
    base.dump(out/'summary.json',{'case':case,'groups':groups,'unmatched':unmatched,'feature_hash':feature_hash})
    assert base.sha(out/'own-features.jsonl')==feature_hash
    print(case,groups,'unmatched',unmatched,flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['extract','diagnostic'])
    p.add_argument('--case',required=True)
    p.add_argument('--camera',default='off',choices=['off','v3_unloaded_extrinsic_v1'])
    args=p.parse_args()
    if args.action=='extract': extract(args.case,args.camera)
    else: diagnostic(args.case)

if __name__=='__main__': main()
