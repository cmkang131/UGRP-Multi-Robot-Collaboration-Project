"""Archived own-RGB frontend replay; no planner, renderer, simulator or GT.

Run the actual mapping consumer. The off arm must reproduce every original
frontend pose and covariance before comparisons are accepted. Command inputs
are the archived issued stream; this is not closed-loop mission evidence.
"""
import argparse,hashlib,importlib,json,sys,traceback
from pathlib import Path
import numpy as np
from PIL import Image
from harness.pf_observation_consistency import attach_ownmap, OPTIONS


def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def replay(raw,out,adapter,option,limit=None):
    for name in ('harness','scripts','sim'):
        importlib.import_module(name).__path__=[str(adapter/name)]
    from harness.active_camera import SEARCH
    from harness.active_wall_vision import observe
    from scripts.run_own_map_return_repeat import actor
    from scripts.run_active_wall_rotleft import install_profile
    bundle=json.loads((raw/'bundle.json').read_text())
    frames=rows(raw/'robots/r3/frames.jsonl');commands=rows(raw/'robots/r3/commands.jsonl')
    expected=rows(raw/'frontend-covariances.jsonl'); expected_by_t={r['t']:r for r in expected}
    recorded_contacts={r['t']:r for r in rows(raw/'own-contacts.jsonl')}
    out.mkdir(parents=True,exist_ok=False);poses=[];failure=None;cmdindex=1;pixel_equivalent=True
    try:
        explorer=actor('r3',frames[0]['sim_time'],SEARCH,active_mapping='frontier_rbpf_v1',
            active_loop='information_gain_v1',seed=bundle['task']['seed'],active_recovery='nav2_frontier_v1',
            navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
        grid=explorer.memory.self_map
        install_profile(grid,profile='egomap27_wide')
        attach_ownmap(grid,observation_consistency=option)
        for i,f in enumerate(frames):
            if i<10:continue
            if limit is not None and len(poses)>=limit:break
            t=f['sim_time']
            while cmdindex<len(commands) and commands[cmdindex]['t']<t-1e-8:
                grid.odom.command(commands[cmdindex]);cmdindex+=1
            jpeg=(raw/f['path']).read_bytes();assert hashlib.sha256(jpeg).hexdigest()==f['sha256']
            rgb=np.asarray(Image.open(raw/f['path']).convert('RGB'))
            ob=observe(rgb,SEARCH,body_settling=.7)
            saved=recorded_contacts[t];pixel_equivalent &= digest(ob)==digest({k:v for k,v in saved.items() if k not in ('t','frame_id')})
            grid.odom.advance(t)
            if ob['segments']:
                grid.observe_contacts_confident(t=t,frame_id=f['frame_id'],segments=ob['segments'],features=ob['features'],camera_xy=ob['camera'],robot_id='r3')
            poses.append(dict(t=t,frame_id=f['frame_id'],pose=list(grid.odom.pose),covariance=grid.odom.covariance.tolist()))
            if len(poses)%100==0:print(json.dumps(dict(frames=len(poses),sim=t)),flush=True)
    except Exception:
        failure=traceback.format_exc()
    (out/'frontend-covariances.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in poses))
    equivalent=all(r==expected_by_t[r['t']] for r in poses)
    result=dict(option=option,raw=str(raw),adapter=str(adapter),physics_runs=0,frames=len(poses),
        expected_frames=len(expected),failure=failure,original_frontend_equal=equivalent,
        original_contacts_equal=pixel_equivalent,poses_sha256=digest(poses),
        input_hashes={n:hashlib.sha256((raw/n).read_bytes()).hexdigest() for n in ('bundle.json','robots/r3/frames.jsonl','robots/r3/commands.jsonl')})
    if failure is None:
        result.update(audit=getattr(grid,'observation_consistency_audit',{'option':'off'}),
            particles_sha256=hashlib.sha256(grid.poses.tobytes()).hexdigest(),
            weights_sha256=hashlib.sha256(grid.weights.tobytes()).hexdigest(),rng=grid.rng.bit_generator.state)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    if failure:raise RuntimeError(failure)
    if option=='off' and not equivalent:raise RuntimeError('OFF_FRONTEND_PARITY_FAILED')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--adapter',type=Path,required=True);p.add_argument('--option',choices=OPTIONS,default='off');p.add_argument('--limit',type=int);a=p.parse_args()
    replay(a.raw,a.output,a.adapter,a.option,a.limit)
