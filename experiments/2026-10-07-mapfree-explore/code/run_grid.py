"""Fixed offline DEV/confirmation runner. No MuJoCo/render/model/network calls."""
import argparse
import copy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
import numpy as np
from harness.own_map_navigation import (ObservedGrid, OwnMapNavigator, NavigationOptions, Footprint,
    astar, footprint_clearance, wrap)
from harness.self_map_prob import V7CommandOdometry
from harness.self_odom_grid import motion_profiles, transform
from harness.floor_goal_v3 import FloorGoalMemoryV3
from grid_world import GridWorld, EXP, inverse, boxes_occupied, SEARCH

STARTS = {'A':[-.65,-2.8,0.], 'B':[-.65,.95,0.], 'C':[1.65,-2.8,math.pi/2], 'D':[1.65,.95,math.pi]}
OPTIONS = dict(exploration='own_frontier_v1',door_detection='own_gap_v1',partial_planning='own_astar_v1')


def write(p,d):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')


def source_hashes():
    paths = ['harness/own_map_navigation.py','harness/self_map_prob.py','harness/self_odom_grid.py',
             'harness/floor_goal.py','harness/floor_goal_v3.py',
             'experiments/2026-10-07-mapfree-explore/sensor-errors.npz',
             'experiments/2026-10-07-mapfree-explore/sensor-model.json']
    paths += [str(p.relative_to(ROOT)) for p in sorted((EXP/'code').glob('*.py')) if p.name!='report.py']
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}


class PatchMemory(FloorGoalMemoryV3):
    """Test sensor replaces ONLY image segmentation; frozen production accumulation runs unchanged."""
    def add(self,patches,t,frame,pose):
        self.detector = lambda *_a,**_k:(copy.deepcopy(patches),None,{})
        return self.observe(None,robot_id='r1',frame_id=frame,t=t,pose=pose,servo=SEARCH,profile='camera_v3',settled=True)[0]


class Actor:
    def __init__(self,condition,static_grid=None,static_goal=None):
        self.condition = condition
        self.grid = static_grid if static_grid is not None else ObservedGrid('r1')
        self.grid.initial_support()
        self.odom = V7CommandOdometry()
        self.navigator = OwnMapNavigator('r1',NavigationOptions(**OPTIONS))
        opt = json.loads((ROOT/'experiments/2026-10-07-mapfree-goal-floor/v3-selection.json').read_text())['selected']['options']
        self.goal = PatchMemory('r1',options=opt)
        self.static_goal = static_goal
        self.t,self.steps = 0.,0
        self.counts = {}
        self.last_goal_t = -100.

    def receive(self,observation,patches):
        self.grid.observe(**observation,pose=self.odom.pose)
        detected = self.goal.add(patches,self.t,self.steps,self.odom.pose)
        if detected:
            self.last_goal_t = self.t
        return detected

    def plan(self):
        pose = self.odom.pose
        snapshot = self.goal.snapshot()
        # Stale candidates stay in memory, but do not monopolize exploration.
        if self.t-self.last_goal_t > 3.:
            snapshot = {**snapshot,'candidates':[p for p in snapshot['candidates'] if p['confirmed_t'] is not None]}
        if self.condition=='static_map':
            state,clear,dist,lo = footprint_clearance(self.grid,Footprint(),.02)
            start = tuple(np.array(self.grid.cell(pose[:2]))-lo)
            target = tuple(np.array(self.grid.cell(self.static_goal))-lo)
            path = astar(clear,start,target,.1,dist)
            if path:
                return {'status':'static_map','path_m':[self.grid.point(np.array(c)+lo).tolist() for c in path],
                        'heading_rad':math.atan2(self.static_goal[1]-pose[1],self.static_goal[0]-pose[0]),'doors':[]}
            return {'status':'static_no_path','path_m':[],'heading_rad':wrap(pose[2]+math.radians(25)),'doors':[]}
        return self.navigator.update(None,grid=self.grid,pose=pose,goal=snapshot)

    def command(self,plan):
        pose = self.odom.pose
        path = plan.get('path_m',[])
        gain = np.asarray(motion_profiles()['motion']['gain'])
        if len(path)>1:
            # One short holonomic step; no waypoint from hidden truth.
            target = np.array(path[min(2,len(path)-1)])
            delta = inverse([target],pose)[0]
            delta *= min(1.,.12/max(1e-9,np.linalg.norm(delta)))
            requested = np.linalg.solve(gain,np.array([*delta,0.]))
            command = {'t':self.t,'kind':'mecanum','forward':float(np.clip(requested[0],-.25,.25)),
                       'left':float(np.clip(requested[1],-.25,.25)), 'turn':0.,'duration_s':1.}
        else:
            heading = plan.get('heading_rad',pose[2]+math.radians(25))
            error = wrap(heading-pose[2])
            if abs(error)<.05:
                error = math.radians(25)
            command = {'t':self.t,'kind':'mecanum','forward':0.,'left':0.,
                       'turn':float(np.clip(error/gain[2,2],-.5,.5)), 'duration_s':1.}
        self.steps += 1
        self.counts[plan['status']] = self.counts.get(plan['status'],0)+1
        return command


def static_inputs(world):
    """Authored baseline exception, exact initial alignment only; no dynamic GT state."""
    grid = ObservedGrid('r1')
    points = inverse(world.floor,world.start)
    rects = [dict(center=o['center_m'],half=o['half_extents_m'],yaw=0.) for o in world.static['obstacles']]
    occupied = boxes_occupied(world.floor,rects,padding=.04)
    for p,hit in zip(points,occupied):
        c = grid.cell(p)
        # Public static map is separate from measured sensor odds (same navigation API).
        grid.odds[c] = 4. if hit else -4.
        (grid.wall_frames if hit else grid.floor_frames)[c] = {'authored_static'}
    goal = inverse([world.static['regions']['zone_B']['center_m']],world.start)[0].tolist()
    return grid,goal


def episode(index,start_id,seed,split,condition,out):
    world = GridWorld(index,STARTS[start_id],seed,split)
    inputs = static_inputs(world) if condition=='static_map' else (None,None)
    actor = Actor(condition,*inputs)
    log,truth_log = [],[]
    status = 'budget'
    first = None
    door_reasons = {}
    if world.collision(world.pose[:2]):
        status = 'HOST_SETUP_ERROR'
    else:
        for step in range(300):
            if actor.t >= 600 or world.distance >= 40 or world.collision_latched:
                status = 'collision' if world.collision_latched else 'budget'
                break
            # Two commanded fixed camera poses + settle/read costs; stop command integrates inertia.
            hold = {'t':actor.t,'kind':'stop'}
            actor.odom.command(hold)
            world.advance(hold,actor.t+2.)
            actor.odom.advance(actor.t+2.)
            actor.t += 2.
            if world.collision_latched:
                status = 'collision'
                break
            observation,patches,truth = world.observe(step)
            accepted = actor.receive(observation,patches)
            for p,is_true in zip(accepted,truth):
                if p['confirmed_t'] is not None:
                    # Evaluation matches the track's evidence, never tells actor whether B is true.
                    first = {'time_s':actor.t,'distance_m':world.distance,'true':bool(is_true)}
                    status = 'B_confirmed' if is_true else 'B_false_confirmed'
                    break
            plan = actor.plan()
            for d in plan['doors']:
                door_reasons[d['reason']] = door_reasons.get(d['reason'],0)+1
            log.append({'frame':step,'t':actor.t,'pose_odom':list(actor.odom.pose),'observation':observation,
                        'patches':accepted,'plan':plan})
            truth_log.append({'frame':step,'t':actor.t,'pose_world':world.pose.tolist(),'coverage':world.coverage(),
                              'B_component_truth':truth,'distance_m':world.distance})
            if first is not None:
                break
            if plan['status']=='search_exhausted':
                status = 'search_exhausted'
                break
            command = actor.command(plan)
            log[-1]['command'] = command
            actor.odom.command(command)
            world.advance(command,actor.t+1.)
            actor.odom.advance(actor.t+1.)
            actor.t += 1.
        else:
            status = 'budget'
    # Physical-style geometry labels remain solely in evaluation output.
    result = {'scenario':f's{index}','start':start_id,'seed':seed,'split':split,'condition':condition,
        'status':status,'first_B':first,'time_s':actor.t,'distance_m':world.distance,'coverage':world.coverage(),
        'collisions':world.collisions,'door_attempts':world.door_attempts,'wrong_door_attempts':world.wrong_doors,
        'door_reasons':door_reasons,'plans':actor.counts,'observations':len(log),
        'sensor_draws':world.sensor_counters,'end_position_error_m':float(np.linalg.norm(
            transform([actor.odom.pose[:2]],world.start)[0]-world.pose[:2])),
        'sources':world.sources,'options':asdict(actor.navigator.options) if condition!='static_map' else {'static_map':True}}
    out.mkdir(parents=True,exist_ok=False)
    (out/'actor.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in log))
    (out/'eval_only.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in truth_log))
    write(out/'result.json',result)
    write(out/'eval_path.json',world.path)
    write(out/'own_grid.json',{'resolution_m':.1,'cells':[[*c,v] for c,v in sorted(actor.grid.odds.items())]})
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--split',choices=['development','confirmation'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--freeze',type=Path)
    p.add_argument('--smoke',action='store_true',help='only s1/A development, never confirmation')
    a = p.parse_args()
    if a.smoke and a.split!='development':
        p.error('smoke is DEV only')
    if a.split=='confirmation':
        frozen = json.loads(a.freeze.read_text()) if a.freeze else {}
        if frozen.get('hashes') != source_hashes() or frozen.get('options') != OPTIONS:
            raise ValueError('CONFIRMATION_REQUIRES_UNCHANGED_FREEZE')
    a.output.mkdir(parents=True,exist_ok=False)
    source = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    write(a.output/'source.json',{'sha':source,'hashes':source_hashes(),'split':a.split,'smoke':a.smoke,'options':OPTIONS})
    starts = ['A','C'] if a.split=='development' else ['B','D']
    seeds = [1701] if a.split=='development' else [2701,2702]
    results = []
    for i in ([1] if a.smoke else range(1,9)):
        for start in (['A'] if a.smoke else starts):
            for seed in seeds:
                for condition in ['static_map','own_frontier']:
                    name = f's{i}-{start}-{seed}-{condition}'
                    r = episode(i,start,seed,a.split,condition,a.output/name)
                    results.append(r)
                    print(name,r['status'],round(r['time_s'],1),round(r['distance_m'],2),round(r['coverage'],3),flush=True)
    write(a.output/'results.json',results)


if __name__=='__main__':
    main()
