"""Replay frozen egomap28 commands/RGB without physics; capture planner failures."""
from pathlib import Path
import sys,json,hashlib,math
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/rbpf-wide-confirm-v1/new-seed')
OUT=Path('/Users/changmin/projects/ugrp/outputs/active-recovery-v1/diagnostic-off')
from harness.active_wall_mapping import ActiveMapper
from harness.active_camera import SEARCH
from harness.public_navigation_unknown import from_observed_grid,UnknownCostmap
from harness.self_odom_grid import transform
from scripts.run_active_wall_wide import install_profile,dump

def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def nav_state(n):
    return dict(target=None if n.target is None else np.asarray(n.target).tolist(),
        frontier=None if n.frontier is None else np.asarray(n.frontier).tolist(),phase=n.phase,
        failed=n.failed,finished=n.finished,static_mode=n.static_mode,retry=n.retry,round_index=n.round_index,
        blacklist=[np.asarray(p).tolist() for p in n.blacklist])


def inspect(nav,costmap,pose,target):
    start=costmap.world_to_map(pose[:2]);goal=None if target is None else costmap.world_to_map(target)
    out=dict(start=start,goal=goal,start_raw=None if start is None else int(costmap.raw[start[1],start[0]]),
        start_cost=None if start is None else int(costmap.costs[start[1],start[0]]),
        goal_raw=None if goal is None else int(costmap.raw[goal[1],goal[0]]),
        goal_cost=None if goal is None else int(costmap.costs[goal[1],goal[0]]),footprint_clear=costmap.pose_clear(pose))
    mask,polygon=costmap.footprint_mask(pose)
    out.update(footprint_cells=int(mask.sum()),footprint_occupied=int((costmap.raw[mask]==254).sum()))
    if target is not None:
        bare=UnknownCostmap(costmap.raw.copy(),costmap.origin.copy(),costmap.resolution)
        bare.costs=bare.raw.copy()
        out['path_without_inflation']=len(nav.plan_to(bare,pose,target))
        if start is None or goal is None:reason='outside_costmap'
        elif out['goal_cost'] in (253,254):reason='target_lethal' if out['goal_raw']==254 else 'target_inflation'
        else:
            cells=nav.core.plan(costmap.costs,start,goal)
            reason='navfn_no_path' if not len(cells) else ('start_connector_collision' if not costmap.sweep_clear(pose,[*costmap.map_to_world(cells)[0],pose[2]]) else 'path_exists')
        out['path_failure']=reason
    fronts=nav.core.frontiers(costmap.raw,costmap.origin,costmap.resolution,pose[:2])
    out['frontiers']=[dict(center=f[:2].tolist(),blacklisted=nav.blocked(f[:2],costmap.resolution),path_points=len(nav.plan_to(costmap,pose,f[:2]))) for f in fronts]
    return out


def main():
    import cv2
    OUT.mkdir(parents=True,exist_ok=False)
    for name,digest in load(RAW/'artifacts.sha256.json').items():assert hashlib.sha256((RAW/name).read_bytes()).hexdigest()==digest
    bundle=load(RAW/'bundle.json');start=load(RAW/'result.json')['start_sim_s']
    actor=ActiveMapper('r3',start,SEARCH,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',seed=bundle['task']['seed'])
    install_profile(actor.memory.self_map,profile='egomap27_wide')
    frames={r['frame_id']:r for r in rows(RAW/'robots/r3/frames.jsonl')}
    original=rows(RAW/'own-controller.jsonl');contacts=rows(RAW/'own-contacts.jsonl')
    audits=[];saved_failed=False;update=actor.navigator.update
    def audited_update(costmap,pose,t,static_goal=None):
        nonlocal saved_failed
        before=nav_state(actor.navigator)
        result=update(costmap,pose,t,static_goal)
        if result['status']=='no_path' or (actor.navigator.failed and not saved_failed):
            name=f'{len(audits):02d}-{t:.1f}'
            row=dict(t=t,status=result['status'],supplied_goal=None if static_goal is None else np.asarray(static_goal).tolist(),
                before=before,after=nav_state(actor.navigator),**inspect(actor.navigator,costmap,pose,actor.navigator.target),snapshot=name)
            audits.append(row)
            np.savez_compressed(OUT/(name+'.npz'),raw=costmap.raw,costs=costmap.costs,origin=costmap.origin,
                resolution=costmap.resolution,pose=pose,target=np.array([]) if actor.navigator.target is None else actor.navigator.target)
            saved_failed|=actor.navigator.failed
        return result
    actor.navigator.update=audited_update
    with (OUT/'traces.jsonl').open('x') as stream:
        for i,(old,contact) in enumerate(zip(original,contacts)):
            frame=frames[old['frame_id']]
            rgb=cv2.cvtColor(cv2.imread(str(RAW/frame['path'])),cv2.COLOR_BGR2RGB)
            obs={k:v for k,v in contact.items() if k not in ('t','frame_id')}
            command,trace=actor.receive(robot_id='r3',t=old['t'],frame_id=old['frame_id'],rgb=rgb,servo=SEARCH,observation=obs)
            stream.write(json.dumps(trace,allow_nan=False)+'\n')
            # Independent admission: commands/status/path and full trace must reproduce the acquisition.
            assert json.dumps(trace)==json.dumps(old),('REPLAY_DIFF',i,old['t'])
            if i<len(original)-1:actor.command(old['command'])
            if i%150==0:print('reproduced',i+1,'frames',flush=True)
    dump(OUT/'audits.json',audits)
    dump(OUT/'navigation.json',actor.navigator.events)
    dump(OUT/'seal.json',dict(frames=len(original),trace_bytes_equal=True,gt_read=False,
        input_sha256={f:hashlib.sha256((RAW/f).read_bytes()).hexdigest() for f in ['own-controller.jsonl','own-contacts.jsonl','robots/r3/frames.jsonl']},
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}))
    print('SEALED',len(audits),'failures',flush=True)

if __name__=='__main__':main()
