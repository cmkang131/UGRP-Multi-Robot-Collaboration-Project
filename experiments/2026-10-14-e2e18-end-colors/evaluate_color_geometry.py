"""Evaluation only: match own RGB band estimates to independent recorded truth.

No controller imports or consumes this output. Frame sha256 matches acquisition
time; world transforms here diagnose RGB geometry independently of own odometry.
"""
import sys,json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.e2e_stage_pose_eval import read

def evaluate(p):
    bundle=read(p/'raw/bundle.json')
    if bundle['e2e_options'].get('end_color_scene','off')=='off':return None
    truth=read(p/'raw/eval_only/referee_truth.jsonl',True)
    bt=np.array([r['t'] for r in truth])
    beam=np.array([[r['items']['beam_1'][k] for k in ('x','y','yaw')] for r in truth])
    rows=[]
    for rid,sign in [('r1',-1),('r2',1)]:
        trajectory=read(p/f'raw/eval_only/{rid}/trajectory.jsonl',True)
        times=np.array([r['t'] for r in trajectory])
        xy=np.array([r['robot_xyz_m'][:2] for r in trajectory])
        yaw=np.unwrap([r['robot_yaw_rad'] for r in trajectory])
        frames={r['sha256']:r for r in read(p/f'raw/robots/{rid}/frames.jsonl',True)}
        errors=[];angles=[];closer=[];dt=[]
        for r in read(p/f'raw/robots/{rid}/ownmap.jsonl',True):
            o=r.get('own_beam_observation') or {};v=o.get('result',{})
            if not v.get('end_visible') or v.get('perception')!='teal_blue_v1':continue
            f=frames[o['rgb']['sha256']];t=f['sim_time'];i=int(np.abs(bt-t).argmin())
            if t<times[0] or t>times[-1] or abs(bt[i]-t)>.051:raise ValueError('EVAL_TIME_MISMATCH')
            pose=np.array([np.interp(t,times,xy[:,0]),np.interp(t,times,xy[:,1])])
            a=np.interp(t,times,yaw);rot=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
            predicted=pose+rot@np.array(v['grip_base_m'])
            u=np.array([math.cos(beam[i,2]),math.sin(beam[i,2])])
            target=beam[i,:2]+sign*.27*u;other=beam[i,:2]-sign*.27*u
            e=float(np.linalg.norm(predicted-target));errors.append(e)
            closer.append(e<float(np.linalg.norm(predicted-other)))
            target_inward=beam[i,2]+(math.pi if sign==1 else 0.)
            da=a+v['axis_heading_rad']-target_inward
            angles.append(abs(math.degrees(math.atan2(math.sin(da),math.cos(da)))))
            dt.append(abs(bt[i]-t))
        rows.append(dict(robot=rid,N=len(errors),closer_to_assigned_end=sum(closer),band_error_median_m=float(np.median(errors)) if errors else None,band_error_p90_m=float(np.quantile(errors,.9)) if errors else None,inward_yaw_error_median_deg=float(np.median(angles)) if angles else None,max_truth_frame_gap_s=max(dt,default=None)))
    return dict(name=p.name,analysis_set=read(p/'STAGE_PLAN.json')['analysis_set'],robots=rows)

if __name__=='__main__':
    rows=[r for p in sorted((ROOT/'outputs/azure3-runs').glob(sys.argv[1])) if (r:=evaluate(p))]
    out=dict(evaluation_only=True,scope='Instant own-RGB band geometry transformed with evaluation-only body pose; does not assess integrated own-map drift. Beam truth sampled within 51ms of sha256-matched RGB acquisition. Actual grasp remains a separate metric.',runs=rows)
    Path(sys.argv[2]).write_text(json.dumps(out,indent=2)+'\n')
    for r in rows:print(r)
