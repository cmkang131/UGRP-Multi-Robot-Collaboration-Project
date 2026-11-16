"""Exact own-input replay of egomap34; audit frontier admission, not physics."""
from pathlib import Path
import sys,json,hashlib,importlib.util
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
RAW=Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')
OUT=Path('/Users/changmin/projects/ugrp/outputs/frontier-visibility-v1/diagnosis')
from harness.active_wall_recovery import RecoveryMapper
from harness.active_camera import SEARCH
from scripts.run_active_wall_rotleft import install_profile,dump

def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]

def main():
    import cv2
    spec=importlib.util.spec_from_file_location('previous_audit',ROOT/'experiments/2026-10-08-active-frontier-audit/code/diagnose.py')
    prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
    OUT.mkdir(parents=True,exist_ok=False)
    for name,digest in load(RAW/'artifacts.sha256.json').items():
        assert hashlib.sha256((RAW/name).read_bytes()).hexdigest()==digest,name
    actor=RecoveryMapper('r3',load(RAW/'result.json')['start_sim_s'],SEARCH,
        active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',seed=32002,
        navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
    install_profile(actor.memory.self_map,profile='egomap27_wide')
    frames={r['frame_id']:r for r in rows(RAW/'robots/r3/frames.jsonl')}
    original=rows(RAW/'own-controller.jsonl');contacts=rows(RAW/'own-contacts.jsonl')
    audits=[];updates=[];last=-1e9
    original_update=actor.navigator.update
    def update(costmap,pose,t,static_goal=None):
        nonlocal last
        n=actor.navigator
        before=prior.nav_state(n);nevents=len(n.events)
        result=original_update(costmap,pose,t,static_goal=static_goal)
        updates.append(dict(t=t,requested_goal=static_goal,actual_target=n.target,
            static_mode=n.static_mode,status=result['status'],pose=pose))
        if t-last>=3.-1e-8 or result['status']=='no_path':
            last=t
            fs=n.core.frontiers(costmap.raw,costmap.origin,costmap.resolution,pose[:2])
            audit=dict(t=t,pose=pose,before=before,after=prior.nav_state(n),
                requested_goal=static_goal,events=n.events[nevents:],epoch=None if not np.isfinite(actor.navigation_epoch) else actor.navigation_epoch,
                grid_cells=len(actor.grid.odds),target=prior.inspect(n,costmap,pose,n.target),
                frontiers=[dict(center=f[:2],min_distance=f[4],size=int(f[5]),cost=f[6],
                    blacklisted=n.blocked(f[:2],costmap.resolution),
                    path_points=len(n.plan_to(costmap,pose,f[:2]))) for f in fs])
            idx=len(audits);audits.append(audit)
            np.savez_compressed(OUT/f'{idx:03d}.npz',raw=costmap.raw,costs=costmap.costs,
                origin=costmap.origin,resolution=costmap.resolution,pose=pose)
        return result
    actor.navigator.update=update
    with (OUT/'traces.jsonl').open('x') as stream:
        for i,(old,contact) in enumerate(zip(original,contacts)):
            rgb=cv2.cvtColor(cv2.imread(str(RAW/frames[old['frame_id']]['path'])),cv2.COLOR_BGR2RGB)
            obs={k:v for k,v in contact.items() if k not in ('t','frame_id')}
            _,trace=actor.receive(robot_id='r3',t=old['t'],frame_id=old['frame_id'],rgb=rgb,servo=SEARCH,observation=obs)
            stream.write(json.dumps(trace,allow_nan=False)+'\n')
            assert json.dumps(trace)==json.dumps(old),('REPLAY_DIFF',i,old['t'])
            if i<len(original)-1:actor.command(old['command'])
            if i%100==0:print('reproduced',i+1,'frames',flush=True)
    dump(OUT/'audits.json',audits);dump(OUT/'updates.json',updates)
    dump(OUT/'seal.json',dict(frames=len(original),trace_bytes_equal=True,gt_read=False,
        input_sha256={f:hashlib.sha256((RAW/f).read_bytes()).hexdigest() for f in ['own-controller.jsonl','own-contacts.jsonl','robots/r3/frames.jsonl']},
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}))
    print('SEALED',len(audits),'audits',flush=True)

if __name__=='__main__':main()
