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
EPISODES = {f's{s}': Path('/Users/changmin/projects/ugrp/outputs')/f's2-realism-{sha}-s{s}-P1-2-{stage}'
            for s,sha,stage in [(1042,'ef820ab2','pick'),(1043,'f6cb04b3','pick'),(1044,'97c05e41','pick'),
                                (1045,'f0bb26e7','place'),(1046,'e619ee57','place'),(1047,'1a2dbf5e','place')]}


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
    valid,decision = filter_segments(segs if segs else np.empty((0,2,2)),wall_projection_guard='positive_depth_v1',
        camera_origin=cm.origin+offset,camera_rotation=cm._rot)
    ids = [e['segment'] for e in decision['segments'] if e['accepted']]
    return valid,[features[i] for i in ids],decision


def extract(case,mode):
    episode,robot = EPISODES[case],'r3'
    fs,cs = own_inputs(episode,robot)
    out = OUT/case/mode
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):
        raise FileExistsError(out)
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


def predict_case(case,mode,weighted):
    from harness.self_wall_memory import SelfWallMemory
    from harness.self_pose_graph import rebuild
    episode,robot=EPISODES[case],'r3'
    directory=OUT/case/mode
    extraction=load(directory/'extract-summary.json')
    for name,h in extraction['prediction_hashes'].items():
        assert base.sha(directory/name)==h
    fs,cs=own_inputs(episode,robot)
    contacts={r['frame_id']:r for r in base.read_rows(directory/'contacts.jsonl')}
    out=directory/('confidence' if weighted else 'unweighted')
    out.mkdir(exist_ok=False)
    memory=SelfWallMemory(robot,self_map='odom_grid_v1',pose_correction='own_map_rbpf_v1',
        pose_correction_options={'particles':100},wall_projection_guard='positive_depth_v1',pose_graph='own_submap_v1',
        wall_confidence='inverse_sensor_v1' if weighted else 'off',self_map_options={'start_time':fs[0]['sim_time']})
    memory.command({'t':fs[0]['sim_time'],'kind':'initial_servo_command','pulses':fs[0]['commanded_servo']})
    grid=memory.self_map
    cursor=0
    poses=[]
    for i,f in enumerate(fs):
        t=f['sim_time']
        while cursor<len(cs) and cs[cursor]['t']<t-1e-8:
            memory.command(cs[cursor])
            cursor+=1
        grid.odom.advance(t)
        contact=contacts.get(f['frame_id'])
        if contact:
            kwargs=dict(t=t,frame_id=f['frame_id'],segments=contact['segments'],camera_xy=contact['camera'],robot_id=robot)
            if weighted:
                grid.observe_contacts_confident(features=contact['features'],**kwargs)
            else:
                grid.observe_contacts(**kwargs)
        poses.append({'robot_id':robot,'t':t,'pose':grid.odom.pose})
        if i%1000==0:
            print(case,mode,weighted,'RBPF frame',i,'inserted',grid.frames,flush=True)
    rows(out/'frontend-poses.jsonl',poses)
    rows(out/'frontend-ledger.jsonl',grid.ledger)
    rows(out/'frontend-decisions.jsonl',grid.decisions)
    base.dump(out/'frontend-grid.json',grid.export())
    assert rebuild(robot,grid.ledger).export()['cells']==grid.export()['cells']
    print(case,mode,weighted,'graph started scans',len(grid.ledger),flush=True)
    graph=memory.finalize_pose_graph(poses)
    rows(out/'graph-poses.jsonl',graph['poses'])
    rows(out/'graph-ledger.jsonl',graph['ledger'])
    base.dump(out/'graph-diagnostics.json',graph['diagnostics'])
    base.dump(out/'grid.json',memory._graph_view.export())
    (out/'llm.txt').write_text(memory.snapshot()['self_map_text']+'\n')
    base.dump(out/'prediction.json',{'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'case':case,'camera':mode,'confidence':weighted,'frontend_counts':grid.export()['correction_counts'],
        'inserted':grid.frames,'loop_counts':graph['diagnostics']['loop_counts'],
        'inputs_sha256':base.sha(directory/'contacts.jsonl'),
        'hashes':{p.name:base.sha(p) for p in out.iterdir() if p.is_file()}})
    print(case,mode,weighted,'prediction frozen',flush=True)


def current_truth(episode):
    values=base.read_rows(episode/'eval_only/trajectory.jsonl')
    return {round(r['t'],6):np.array([*r['robot_xyz_m'][:2],r['robot_yaw_rad']]) for r in values}


def path_score(poses,truth):
    origin=truth[round(poses[0]['t'],6)]
    gt=np.array([truth[round(p['t'],6)] for p in poses])
    p=np.array([p['pose'] for p in poses])
    error=np.linalg.norm(transform(p[:,:2],origin)-gt[:,:2],axis=1)
    yaw=abs((origin[2]+p[:,2]-gt[:,2]+np.pi)%(2*np.pi)-np.pi)
    stats={name:float(np.quantile(error,q)) for name,q in [('median_m',.5),('p90_m',.9),('p95_m',.95),('max_m',1.)]}
    stats.update(rmse_m=float(np.sqrt(np.mean(error**2))),count=len(error))
    return {'path_position_error':stats,'end_position_error_m':float(error[-1]),
            'end_yaw_error_deg':float(np.degrees(yaw[-1]))}


def score_case(case):
    from harness.self_pose_graph import rebuild
    from own_map_csm_replay import acceptance
    import map_error_oracle as diag
    episode=EPISODES[case]
    # Confirm all prediction files are sealed before opening GT.
    predictors={}
    for camera,weighted in [('off',False),('v3_unloaded_extrinsic_v1',False),('v3_unloaded_extrinsic_v1',True)]:
        path=OUT/case/camera/('confidence' if weighted else 'unweighted')
        frozen=load(path/'prediction.json')
        for name,h in frozen['hashes'].items():
            assert base.sha(path/name)==h
        predictors[(camera,weighted)]=(path,frozen)
    truth=current_truth(episode)
    first=base.read_rows(OUT/case/'off/dr-poses.jsonl')[0]
    origin=truth[round(first['t'],6)]
    walls=[w for w in load(episode/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall']
    rects=np.array([w['center_m']+w['half_extents_m'] for w in walls])
    samples=base.wall_samples(rects)
    evaluation=OUT/case/'evaluation'
    evaluation.mkdir(exist_ok=False)
    metrics,grid_hashes={},{}
    detections_eval=[]
    for camera in ('off','v3_unloaded_extrinsic_v1'):
        path=OUT/case/camera
        contacts=base.read_rows(path/'contacts.jsonl')
        drposes=base.read_rows(path/'dr-poses.jsonl')
        dr=dict((p['t'],p['pose']) for p in drposes)
        for label,oracle,weighted in [('dr',False,False),('gt',True,False),('gt_confidence',True,True)]:
            ledger=[]
            for r in contacts:
                pose=diag.relative_pose(truth[round(r['t'],6)],origin) if oracle else dr[r['t']]
                item={**r,'pose':np.asarray(pose).tolist()}
                scores=[confidence(s,r['camera'],f,np.zeros((3,3))) for s,f in zip(r['segments'],r['features'])]
                if weighted: item['insertion_weights']=[c['weight'] for c in scores]
                ledger.append(item)
                if label=='gt':
                    for seg,c in zip(r['segments'],scores):
                        ends=transform(seg,truth[round(r['t'],6)])
                        ps=np.linspace(*ends,max(2,int(np.linalg.norm(ends[1]-ends[0])/.05)+1))
                        ok=base.boundary_dist(ps,rects)<=.15
                        detections_eval.append({'camera':camera,'frame_id':r['frame_id'],**c,'correct':int(ok.sum()),'samples':len(ps)})
            g=rebuild('r3',ledger)
            name=camera+'__'+label
            metrics[name]={'final':base.quality(transform(g.occupied_points(),origin),rects,samples)[0]}
            if not oracle: metrics[name].update(path_score(drposes,truth))
            base.dump(evaluation/(name+'-grid.json'),g.export())
    for (camera,weighted),(path,frozen) in predictors.items():
        name=camera+'__'+('confidence' if weighted else 'rbpf_graph')
        g=OdomGrid('r3')
        g.cells={(x,y):v for x,y,v in load(path/'grid.json')['cells']}
        metrics[name]={'final':base.quality(transform(g.occupied_points(),origin),rects,samples)[0],
            **path_score(base.read_rows(path/'graph-poses.jsonl'),truth),'inserted_scans':frozen['inserted'],
            'loop_counts':frozen['loop_counts'],'frontend_counts':frozen['frontend_counts']}
    checks={}
    for camera,label in [('off','rbpf_graph'),('v3_unloaded_extrinsic_v1','rbpf_graph'),('v3_unloaded_extrinsic_v1','confidence')]:
        name=camera+'__'+label
        baseline=metrics[camera+'__dr']
        on=metrics[name]
        if baseline['final']['precision_015'] is None or on['final']['precision_015'] is None:
            checks[name]={'map_present':False}
        else:
            checks[name]=acceptance(baseline,on)['checks']
        checks[name]['guard_visible_recall_verified']=False # no recorded actual camera pose, not a fabricated 0
        checks[name]['zero_invalid_endpoints']=all(
            e['accepted_segments']==0 or all(s['accepted'] and min(s['optical_z_m'])>0 and min(s['ray_t'])>0
            for s in e['segments'] if s['accepted'])
            for r in base.read_rows(OUT/case/camera/'extraction.jsonl') if 'guard' in r for e in [r['guard']])
    rows(evaluation/'detection-calibration.jsonl',detections_eval)
    base.dump(evaluation/'summary.json',{'case':case,'split':'development' if case in ('s1042','s1043') else 'confirmation_replay',
        'origin_eval_only':origin.tolist(),'wall_samples':len(samples),'metrics':metrics,'checks':checks,
        'success':{k:all(v.values()) for k,v in checks.items()},'actual_visible_recall':None,
        'visibility_limitation':'No actual camera pose/joints in these recordings; exact visibility unscorable.',
        'truth_sources':[{'path':str(p),'sha256':base.sha(p)} for p in [episode/'eval_only/trajectory.jsonl',episode/'inputs/static_map.json']],
        'prediction_hashes':{str(path):base.sha(path/'prediction.json') for path,_ in predictors.values()}})
    print(case,'scored', {k:(v.get('end_position_error_m'),v['final']['precision_015'],v['final']['wall_coverage']) for k,v in metrics.items()},flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['extract','diagnostic','predict','score'])
    p.add_argument('--case',required=True)
    p.add_argument('--camera',default='off',choices=['off','v3_unloaded_extrinsic_v1'])
    p.add_argument('--confidence',action='store_true')
    args=p.parse_args()
    if args.action=='extract': extract(args.case,args.camera)
    elif args.action=='diagnostic': diagnostic(args.case)
    elif args.action=='predict': predict_case(args.case,args.camera,args.confidence)
    else: score_case(args.case)

if __name__=='__main__': main()
