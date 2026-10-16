"""Post-seal evaluation and chronological 4x movie; no simulator imports."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys,subprocess
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1')
EP=RAW/'new-seed'
sys.path.insert(0,str(ROOT))
from harness.self_odom_grid import transform
from harness.self_map_prob import wrap
from harness.self_wall_evidence import build_evidence
from scripts.run_active_wall_nav2 import dump


def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(line) for line in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def metrics_module():
    spec=importlib.util.spec_from_file_location('frozen_eg22_score',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.RAW=RAW;m.EXP=EXP
    def prediction(case,partial=False):m.verify(RAW/case);return RAW/case
    m.prediction=prediction
    return m


def score():
    m=metrics_module();m.verify(EP)
    partial=load(EP/'result.json')['prediction_view']!='completed_graph'
    m.evaluate('new-seed',partial=partial)
    # Covariance belongs to frontend; graph's optimized endpoint is separate.
    truth={round(r['t'],6):r for r in rows(EP/'eval_only/trajectory.jsonl')}
    first=truth[min(truth)];origin=[*first['robot_xyz_m'][:2],first['robot_yaw_rad']]
    poses=rows(EP/'frontend-covariances.jsonl')
    est=transform([p['pose'][:2] for p in poses],origin)
    gt=np.array([truth[round(p['t'],6)]['robot_xyz_m'][:2] for p in poses])
    errors=np.linalg.norm(est-gt,axis=1)
    sigma=np.array([np.sqrt(np.linalg.eigvalsh(np.array(p['covariance'])[:2,:2]).max()) for p in poses])
    yaw=wrap(np.array([p['pose'][2]+origin[2]-truth[round(p['t'],6)]['robot_yaw_rad'] for p in poses]))
    sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metric
    walls=np.array([r['center_m']+r['half_extents_m'] for r in load(EP/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall'])
    g=load(EP/'frontend-grid.json');cells=np.array([c for c in g['cells'] if c[2]>0]).reshape(-1,3)
    xy=transform((cells[:,:2]+.5)*.1,origin)
    samples=metric.wall_samples(walls);q,cover=metric.quality(xy,walls,samples)
    cameras=rows(EP/'eval_only/camera.jsonl');visible=m.in_view(samples,cameras,walls);region=m.in_view(xy,cameras,walls)
    correct=metric.boundary_dist(xy,walls)<=.15
    decisions=load(EP/'decisions.json')
    baseline=load(ROOT/'experiments/2026-10-08-active-frontier-audit/results/new-seed.json')
    baseline_uncertainty=load(ROOT/'experiments/2026-10-08-active-frontier-audit/results/comparison.json')['frontend']
    front=dict(endpoint_error_m=float(errors[-1]),sigma_xy_m=float(sigma[-1]),error_sigma_ratio=float(errors[-1]/sigma[-1]),
        over_2sigma=int((errors>2*sigma).sum()),n=len(poses),path_rmse_m=float(np.sqrt(np.mean(errors**2))),
        yaw_end_deg=float(np.degrees(yaw[-1])),yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(yaw**2)))),
        full_map=q,region=dict(precision=float(correct[region].mean()) if region.any() else None,
            precision_correct=int(correct[region].sum()),precision_cells=int(region.sum()),
            recall=float(cover[visible].mean()),recalled_samples=int(cover[visible].sum()),visible_samples=int(visible.sum()),total_samples=len(samples)),
        occupied_cells=len(cells),mapped_frames=len(load(EP/'frontend-ledger.json')),resamples=g['resamples'],
        rejected_resamples=sum(bool(d.get('resampled')) for d in decisions if d['status']=='rejected'),
        rejected_csm_updates=sum(bool(d.get('sensor_weight_update')) for d in decisions if d['status']=='rejected'))
    gate=dict(within_2sigma=front['error_sigma_ratio']<=2,
        precision_improves=front['region']['precision'] is not None and front['region']['precision']>35/241)
    result=dict(baseline=baseline,baseline_uncertainty=baseline_uncertainty,
        fresh=load(EXP/'results/new-seed.json'),frontend=front,legacy_descriptive_gate=gate,supervisor_authorized_DEV=True,egomap33_gate_passed=False,
        qualification='Supervisor-authorized DEV seed32002 versus seed31001; NOT an egomap33 gate pass. Graph sigma unavailable.')
    controller=rows(EP/'own-controller.jsonl')
    hold=sum(r['command']['kind']=='hold' for r in controller)
    result['hold']=dict(n=hold,total=len(controller),fraction=hold/len(controller),baseline_n=40,baseline_total=891)
    fresh=result['fresh']
    result['recovery_gate']=dict(recorded=fresh['acquisition']['status']=='RECORDED',
        distance=fresh['coverage']['travelled_m']>1.0900284644319769,
        area=fresh['coverage']['footprint_union_m2']>.4850000000000001,
        hold_fraction=hold/len(controller)<695/891,no_contact=fresh['wall_contacts']==0)
    dump(EXP/'results/comparison.json',result)
    dump(RAW/'uncertainty-curve.json',dict(t=[p['t'] for p in poses],error=errors,sigma=sigma,yaw_error_deg=np.degrees(yaw)))
    print(json.dumps(dict(frontend=front,egomap27_gate=gate),indent=2))


# Movie renderer reused from egomap28, chronological snapshots unchanged; bundle seed label.

def movie():
    metrics_module().verify(EP)  # sealed acquisition only
    import cv2
    seed=load(EP/'bundle.json')['task']['seed']
    frames=rows(EP/'robots/r3/frames.jsonl');truth=rows(EP/'eval_only/trajectory.jsonl')
    cov=rows(EP/'frontend-covariances.jsonl');snapshots=rows(EP/'online-maps.jsonl')
    origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']]
    walls=[r for r in load(EP/'inputs/static_map.json')['obstacles'] if r.get('kind')=='wall']
    # Same fixed arena extent throughout movie; no final map/trajectory used to frame early views.
    mins=np.min([np.array(r['center_m'])-r['half_extents_m'] for r in walls],axis=0)-.4
    maxs=np.max([np.array(r['center_m'])+r['half_extents_m'] for r in walls],axis=0)+.4
    scale=min(580/(maxs[0]-mins[0]),360/(maxs[1]-mins[1]))
    center=(mins+maxs)/2
    def pixel(xy):
        z=(np.asarray(xy)-center)*scale
        return np.rint(np.c_[320+z[...,0].ravel(),250-z[...,1].ravel()]).astype(int)
    def label(im,text,y,color=(40,40,40)):
        cv2.putText(im,text,(16,y),cv2.FONT_HERSHEY_SIMPLEX,.48,color,1,cv2.LINE_AA)
    base=np.full((480,640,3),250,np.uint8)
    for r in walls:
        lo=np.array(r['center_m'])-r['half_extents_m'];hi=np.array(r['center_m'])+r['half_extents_m']
        a,b=pixel([lo,hi]);cv2.rectangle(base,tuple(a),tuple(b),(175,175,175),-1)
    label(base,'Online FRONTEND map (own RGB + commands)',22)
    label(base,'Gray: GT walls (evaluation only)',43)
    label(base,'Blue: TSDF support, NOT probability',64)
    label(base,'Orange: estimate   Green: actual (evaluation)',455)
    output=RAW/'wrist-map-4x.mp4'
    if output.exists():raise FileExistsError(output)
    encoder=subprocess.Popen(['ffmpeg','-nostdin','-v','error','-f','rawvideo','-pixel_format','bgr24',
        '-video_size','1280x480','-framerate','20','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','22',
        '-pix_fmt','yuv420p','-movflags','+faststart',str(output)],stdin=subprocess.PIPE)
    index=-1;layer=base.copy();map_count=0;insertions=0;checks=[]
    gt_times=np.array([r['t'] for r in truth]);gt_xy=np.array([r['robot_xyz_m'][:2] for r in truth])
    own_times=np.array([r['t'] for r in cov]);own_xy=transform([r['pose'][:2] for r in cov],origin)
    try:
        for i,frame in enumerate(frames):
            t=frame['sim_time']
            while index+1<len(snapshots) and snapshots[index+1]['t']<=t+1e-8:
                index+=1;s=snapshots[index];layer=base.copy()
                evidence=build_evidence([dict(r,robot_id='r3') for r in s['ledger']],robot_id='r3',wall_evidence='tsdf_weight_v1')
                support={tuple(r['cell']):r['support_score'] for r in evidence['cells']}
                cells=[c for c in s['grid']['cells'] if c[2]>0];map_count=len(cells);insertions=len(s['ledger'])
                if cells:
                    xy=transform((np.array(cells)[:,:2]+.5)*.1,origin)
                    for c,uv in zip(cells,pixel(xy)):
                        value=support.get(tuple(c[:2]),0.)
                        color=(int(240-40*value),int(210-160*value),int(170-160*value))
                        cv2.circle(layer,tuple(uv),max(2,round(.04*scale)),color,-1)
            right=layer.copy()
            for xy,mask,color in [(gt_xy,gt_times<=t+1e-8,(45,145,45)),(own_xy,own_times<=t+1e-8,(0,120,245))]:
                p=pixel(xy[mask])
                if len(p)>1:cv2.polylines(right,[p],False,color,2,cv2.LINE_AA)
                if len(p):cv2.circle(right,tuple(p[-1]),4,color,-1)
            label(right,f't={t-frames[0]["sim_time"]:.1f}s | {map_count} cells | {insertions} scans',85)
            left=cv2.imread(str(EP/frame['path']));assert left.shape==(480,640,3)
            cv2.rectangle(left,(0,0),(640,32),(25,25,25),-1)
            label(left,f'Own wrist RGB | seed {seed} | 4x | {t-frames[0]["sim_time"]:.1f}s',22,(245,245,245))
            pair=np.concatenate([left,right],axis=1);encoder.stdin.write(pair.tobytes())
            if i in (0,len(frames)//2,len(frames)-1):
                checks.append(pair)
            if i%200==0:print('video',i,'/',len(frames),flush=True)
    finally:
        encoder.stdin.close();code=encoder.wait()
    assert code==0
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)]))
    assert probe['streams'][0]['r_frame_rate']=='20/1'
    assert abs(float(probe['format']['duration'])-len(frames)/20)<.05
    (EXP/'figures').mkdir(exist_ok=True)
    cv2.imwrite(str(EXP/'figures/video-check.jpg'),np.concatenate(checks,axis=0),[cv2.IMWRITE_JPEG_QUALITY,80])
    dump(EXP/'results/video.json',dict(path=str(output),sha256=sha(output),bytes=output.stat().st_size,
        frames=len(frames),fps=20,duration_s=float(probe['format']['duration']),playback_speed=4,
        input_sha256=sha(EP/'robots/r3/frames.jsonl'),online_snapshots=len(snapshots),
        semantics='each frame uses only latest snapshot <= frame SIM time; no final-map backfill'))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['score','movie'],nargs='?',default='score')
    a=p.parse_args()
    score() if a.mode=='score' else movie()
