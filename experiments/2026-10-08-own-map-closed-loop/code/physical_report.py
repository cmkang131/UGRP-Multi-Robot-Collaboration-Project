"""Post-seal egomap43 GT scoring / chronological wrist-map 4x video."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,importlib.util,json,math,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/own-map-closed-loop-v1')
EP=RAW/'new-seed'
from scripts.run_active_wall_rotleft import dump
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap
from harness.self_wall_evidence import build_evidence


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(l) for l in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def module():
    spec=importlib.util.spec_from_file_location('active_score',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def verified():
    module().verify(EP)
    return load(EP/'result.json')

def score():
    result=verified();trace=rows(EP/'own-controller.jsonl');truth=rows(EP/'eval_only/trajectory.jsonl')
    by_t={round(r['t'],6):r for r in truth};gt_pose=lambda r:[*r['robot_xyz_m'][:2],r['robot_yaw_rad']]
    origin=gt_pose(truth[0]);static=load(EP/'inputs/static_map.json');region=static['regions']['zone_B']
    usable=[r for r in trace if r.get('pose') is not None]
    predicted=np.array([r.get('local_pose',r['pose']) for r in usable]);world=transform(predicted[:,:2],origin)
    actual=np.array([gt_pose(by_t[round(r['t'],6)]) for r in usable])
    error=np.linalg.norm(world-actual[:,:2],axis=1);yaw=wrap(predicted[:,2]+origin[2]-actual[:,2])
    post=[i for i,r in enumerate(usable) if 'belief' in r]
    valid=[];false=[]
    for k,i in enumerate(post):
        r=usable[i]
        previous=post[max(0,k-4):k+1]
        correct=len(previous)==5 and all(error[j]<=.25 and abs(yaw[j])<=math.radians(10) for j in previous)
        if r['stable_resolved']:
            (valid if correct else false).append(i)
    declared=[i for i,r in enumerate(usable) if r.get('declared_goal')]
    inside=lambda xy:bool(np.all(abs(np.asarray(xy)-region['center_m'])<=region['half_extents_m']))
    declaration=[dict(t=usable[i]['t'],pose_error_m=float(error[i]),actual_inside_B=inside(actual[i,:2])) for i in declared]
    goal=load(EP/'remembered-goal.json');goal_world=None if not goal else transform([goal['center_m']],origin)[0]
    g=load(EP/'frontend-grid.json');ledger=load(EP/'frontend-ledger.json');cells=np.array(g['cells']).reshape(-1,3)
    occupied=cells[cells[:,2]>0];points=transform((occupied[:,:2]+.5)*g['resolution_m'],origin)
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metric
    walls=np.array([r['center_m']+r['half_extents_m'] for r in static['obstacles'] if r.get('kind')=='wall'])
    samples=metric.wall_samples(walls);quality,cover=metric.quality(points,walls,samples)
    events=load(EP/'utility-events.json');loss=next((r['t'] for r in events if r['reason']=='unknown_start_reset'),None)
    cameras=[r for r in rows(EP/'eval_only/camera.jsonl') if loss is None or r['t']<loss-1e-8]
    m=module();visible=m.in_view(samples,cameras,walls);visible_cells=m.in_view(points,cameras,walls)
    correct=metric.boundary_dist(points,walls)<=.15
    from harness.own_map_navigation import ObservedGrid
    from harness.public_navigation_unknown import footprint_cells
    eval_grid=ObservedGrid('evaluation',.05);visited=set().union(*(footprint_cells(eval_grid,gt_pose(r)) for r in truth))
    contacts=rows(EP/'eval_only/contact-audit.jsonl');contact_counts={kind:sum(any(p['kind']==kind for p in r['pairs']) for r in contacts) for kind in ('wall','robot')}
    decisions=load(EP/'decisions.json');counter=Counter((r['status'],r.get('reason','')) for r in decisions)
    sigma=usable[-1].get('sigma_xy')
    summary=dict(source_sha=result['source_sha'],acquisition=result,physical_attempts=1,seed=43001,
        phases=dict(Counter(r['stage'] for r in trace)),loss_t=loss,goal=goal,
        goal_center_error_m=None if goal is None else float(np.linalg.norm(goal_world-region['center_m'])),
        goal_center_inside_B=None if goal is None else inside(goal_world),
        internally_converged_frames=sum(r.get('stable_resolved',False) for r in trace),
        correct_convergence=bool(valid),convergence_after_loss_s=None if not valid else usable[valid[0]]['t']-loss,
        false_convergence_frames=len(false),post_loss_frames=len(post),
        declarations=declaration,correct_B_arrival=any(r['actual_inside_B'] for r in declaration),
        false_B_declarations=sum(not r['actual_inside_B'] for r in declaration),
        arrival_after_loss_s=None if not declared else usable[declared[0]]['t']-loss,
        actual_B_frames=sum(inside(r['robot_xyz_m'][:2]) for r in truth),
        final_xy_m=float(error[-1]),final_yaw_deg=float(np.degrees(yaw[-1])),final_sigma_xy_m=sigma,
        final_error_sigma_ratio=None if sigma is None else float(error[-1]/max(sigma,1e-12)),
        path_rmse_m=float(np.sqrt(np.mean(error**2))),
        travelled_m=float(np.linalg.norm(np.diff(np.array([r['robot_xyz_m'][:2] for r in truth]),axis=0),axis=1).sum()),
        footprint_union_m2=len(visited)*.05**2,hold_frames=sum(r['command']['kind']=='hold' for r in trace),command_frames=len(trace),
        contact_sample_frames=contact_counts,contact_samples=len(contacts),contact_scope='5Hz samples; not exhaustive continuous collision count',
        insertion_scans=len(ledger),decision_frames=len(decisions),decision_counts={a+'/'+b:n for (a,b),n in counter.items()},
        map=dict(coordinate_frame='r3/own_start',frozen_before_loss=loss is not None,
            occupied_cells=len(occupied),observed_cells=len(cells),observed_area_m2=len(cells)*g['resolution_m']**2,
            whole=quality,coverage=float(cover.mean()),covered_samples=int(cover.sum()),total_wall_samples=len(samples),
            potential_visible_samples=int(visible.sum()),region_P=float(correct[visible_cells].mean()) if visible_cells.any() else None,
            region_R=float(cover[visible].mean()) if visible.any() else None,
            region_precision_cells=int(visible_cells.sum()),region_correct_cells=int(correct[visible_cells].sum()),
            region_recalled_samples=int(cover[visible].sum()),visibility_scope='prefix true-camera FOV/range and walls; object occlusion unmodelled'),
        thresholds_unchanged=True,offline_independent=False,real_hardware=0,retuning=0)
    dump(EXP/'results/physical.json',summary)
    dump(RAW/'physical-errors.json',dict(t=[r['t'] for r in usable],xy_m=error,yaw_deg=np.degrees(yaw),predicted_world=world,true_world=actual))
    print(json.dumps(summary,indent=2))


def movie():
    verified()
    import cv2
    frames=rows(EP/'robots/r3/frames.jsonl');trace=rows(EP/'own-controller.jsonl');truth=rows(EP/'eval_only/trajectory.jsonl');snapshots=rows(EP/'online-maps.jsonl')
    origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    walls=[r for r in load(EP/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall']
    mins=np.min([np.array(r['center_m'])-r['half_extents_m'] for r in walls],axis=0)-.4
    maxs=np.max([np.array(r['center_m'])+r['half_extents_m'] for r in walls],axis=0)+.4
    scale=min(580/(maxs[0]-mins[0]),340/(maxs[1]-mins[1]));center=(mins+maxs)/2
    def pixel(xy):
        z=(np.asarray(xy)-center)*scale
        return np.rint(np.c_[320+z[...,0].ravel(),265-z[...,1].ravel()]).astype(int)
    def label(im,text,y,color=(40,40,40)):
        cv2.putText(im,text,(14,y),cv2.FONT_HERSHEY_SIMPLEX,.46,color,1,cv2.LINE_AA)
    base=np.full((480,640,3),250,np.uint8)
    for r in walls:
        a,b=pixel([np.array(r['center_m'])-r['half_extents_m'],np.array(r['center_m'])+r['half_extents_m']]);cv2.rectangle(base,tuple(a),tuple(b),(175,175,175),-1)
    label(base,'Own map; frozen at loss. No future map backfill.',20)
    label(base,'Gray walls / green actual path: EVALUATION ONLY',40)
    label(base,'Blue: own wall support. Orange: own estimated path',60)
    label(base,'Magenta: remembered B (own RGB; no GT goal)',80)
    output=RAW/'wrist-map-4x.mp4'
    if output.exists():raise FileExistsError(output)
    encoder=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pixel_format','bgr24','-video_size','1280x480','-framerate','20','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],stdin=subprocess.PIPE)
    index=-1;ti=-1;layer=base.copy();checks=[];cells=[]
    gt_times=np.array([r['t'] for r in truth]);gt_xy=np.array([r['robot_xyz_m'][:2] for r in truth])
    own=[r for r in trace if r.get('pose') is not None]
    own_times=np.array([r['t'] for r in own]);own_xy=transform([r.get('local_pose',r['pose'])[:2] for r in own],origin)
    try:
        for i,f in enumerate(frames):
            t=f['sim_time']
            while index+1<len(snapshots) and snapshots[index+1]['t']<=t+1e-8:
                index+=1;s=snapshots[index];layer=base.copy()
                evidence=build_evidence([dict(r,robot_id='r3') for r in s['ledger']],robot_id='r3',wall_evidence='tsdf_weight_v1')
                support={tuple(r['cell']):r['support_score'] for r in evidence['cells']}
                cells=[c for c in s['grid']['cells'] if c[2]>0]
                if cells:
                    xy=transform((np.array(cells)[:,:2]+.5)*s['grid']['resolution_m'],origin)
                    for c,uv in zip(cells,pixel(xy)):
                        value=support.get(tuple(c[:2]),0.)
                        cv2.circle(layer,tuple(uv),max(2,round(.04*scale)),(int(240-40*value),int(210-160*value),int(170-160*value)),-1)
            while ti+1<len(trace) and trace[ti+1]['t']<=t+1e-8:ti+=1
            current=trace[ti] if ti>=0 else {};right=layer.copy()
            for xy,mask,color in [(gt_xy,gt_times<=t+1e-8,(45,145,45)),(own_xy,own_times<=t+1e-8,(0,120,245))]:
                p=pixel(xy[mask])
                if len(p)>1:cv2.polylines(right,[p],False,color,2,cv2.LINE_AA)
                if len(p):cv2.circle(right,tuple(p[-1]),4,color,-1)
            goal=current.get('remembered_B') or (current.get('goal') if current.get('stage')!='explore' else None)
            if goal:
                uv=tuple(pixel(transform([goal['center_m']],origin))[0]);cv2.drawMarker(right,uv,(200,0,200),cv2.MARKER_CROSS,18,2)
                cv2.putText(right,'B',uv,cv2.FONT_HERSHEY_SIMPLEX,.7,(200,0,200),2)
            label(right,f't={t-frames[0]["sim_time"]:.1f}s | {current.get("stage","settle")} | {len(cells)} cells',102)
            label(right,f'status: {current.get("status","settle")} | declared: {current.get("declared_goal",False)}',459)
            left=cv2.imread(str(EP/f['path']));assert left.shape==(480,640,3)
            cv2.rectangle(left,(0,0),(640,32),(25,25,25),-1)
            label(left,f'Own wrist RGB | seed 43001 | 4x | {t-frames[0]["sim_time"]:.1f}s',22,(245,245,245))
            pair=np.concatenate([left,right],axis=1);encoder.stdin.write(pair.tobytes())
            if i in (0,len(frames)//2,len(frames)-1):checks.append(pair)
            if i%250==0:print('video',i,'/',len(frames),flush=True)
    finally:
        encoder.stdin.close();code=encoder.wait()
    assert code==0
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
    assert probe['streams'][0]['r_frame_rate']=='20/1'
    assert abs(float(probe['format']['duration'])-len(frames)/20)<.05
    subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],check=True)
    (EXP/'figures').mkdir(exist_ok=True)
    cv2.imwrite(str(EXP/'figures/video-check.jpg'),np.concatenate(checks,axis=0),[cv2.IMWRITE_JPEG_QUALITY,80])
    cv2.imwrite(str(EXP/'figures/final-map.jpg'),checks[-1],[cv2.IMWRITE_JPEG_QUALITY,90])
    dump(EXP/'results/video.json',dict(path=str(output),sha256=sha(output),bytes=output.stat().st_size,frames=len(frames),fps=20,
        duration_s=float(probe['format']['duration']),playback_speed=4,input_sha256=sha(EP/'robots/r3/frames.jsonl'),
        snapshots=len(snapshots),chronological=True,decode_verified=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['score','movie']);a=p.parse_args()
    score() if a.mode=='score' else movie()
