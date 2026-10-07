"""Evaluation-only oracle and immutable v1-log audit. Never imported by actors."""
import argparse
from collections import Counter
import copy
import json
import math
from pathlib import Path
import subprocess

import numpy as np

import run_grid as old
from grid_world import GridWorld, inverse
from harness.self_odom_grid import transform


class OracleWorld(GridWorld):
    """Zero process/projection noise, perfect *visible* detections, unchanged FOV/occlusion.

    The frozen B v3 temporal test still runs. No hidden goal/pose enters the actor.
    This is a diagnostic condition, not a deployable observation source.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.errors = np.zeros((1, 96, 4))
        self.errors[:, :, :2] = 1
        self.b_errors = np.zeros(1)
        self.b_model = {**self.b_model, 'recall': 1., 'fp_rate': 0.}

    def _motion_step(self, body_delta, variance):
        super()._motion_step(body_delta, np.zeros(3))


def rectangle_contacts(pose, rects, bounds, half=(.12, .10)):
    """Separating-axis test, exact oriented 2D rectangles (evaluation only)."""
    c, s = math.cos(pose[2]), math.sin(pose[2])
    axes = np.array([[c, s], [-s, c]])
    points = transform(np.array([[-1,-1],[-1,1],[1,1],[1,-1]])*half, pose)
    contacts = []
    for r in rects:
        a, b = math.cos(r['yaw']), math.sin(r['yaw'])
        other = np.array([[a,b],[-b,a]])
        separated = False
        for axis in np.concatenate([axes,other]):
            radius = np.abs(axes@axis)@np.asarray(half) + np.abs(other@axis)@np.asarray(r['half'])
            if abs(np.dot(np.asarray(pose[:2])-r['center'],axis)) > radius:
                separated = True
                break
        if not separated:
            contacts.append(r['id'])
    x0,x1,y0,y1 = bounds
    if (points[:,0]<=x0).any() or (points[:,0]>=x1).any() or (points[:,1]<=y0).any() or (points[:,1]>=y1).any():
        contacts.append('world_boundary')
    return contacts


def audit(folder):
    rows = []
    for file in sorted(folder.glob('*/result.json')):
        r = json.loads(file.read_text())
        logs = [json.loads(x) for x in (file.parent/'actor.jsonl').read_text().splitlines()]
        path = np.array(json.loads((file.parent/'eval_path.json').read_text()))
        w = GridWorld(int(r['scenario'][1:]),old.STARTS[r['start']],r['seed'],r['split'])
        w.events(r['time_s'])
        initial = old.Actor('static_map',*old.static_inputs(w)).plan()
        odom = old.V7CommandOdometry()
        for log in logs:
            t = log['t']
            odom.command({'t':t-2.,'kind':'stop'})
            odom.advance(t)
            if 'command' in log:
                odom.command(log['command'])
                odom.advance(t+1.)
        if r['time_s']>odom.t:
            odom.command({'t':odom.t,'kind':'stop'})
            odom.advance(r['time_s'])
        predicted = [*transform([odom.pose[:2]],w.start)[0], w.start[2]+odom.pose[2]]
        actual_contacts = rectangle_contacts(path[-1],w.rects,w.static['bounds_m'])
        predicted_contacts = rectangle_contacts(predicted,w.rects,w.static['bounds_m'])
        translation = sum(abs(x.get('command',{}).get('forward',0))+abs(x.get('command',{}).get('left',0))>1e-6 for x in logs)
        views = {}
        for log in logs:
            for p in log['patches']:
                views.setdefault(p['track_id'],[]).append(log['pose_odom'])
        baselines = [max(np.linalg.norm(np.array(a[:2])-b[:2]) for a in poses for b in poses) for poses in views.values()]
        rows.append(dict(episode=file.parent.name, initial_static_path=bool(initial['path_m']),
            frames_with_path=sum(bool(x['plan']['path_m']) for x in logs), translation_commands=translation,
            **r['sensor_draws'], B_confirmed=r['first_B'], status=r['status'],
            collision_circle_only=bool(r['collisions'] and not actual_contacts),
            rectangle_contacts=actual_contacts, commanded_pose_contacts=predicted_contacts,
            end_position_error_m=r['end_position_error_m'], max_track_baseline_m=max(baselines,default=0.),
            end_B_distance_m=float(np.linalg.norm(path[-1,:2]-w.static['regions']['zone_B']['center_m']))))
    return rows


def aggregate(rows):
    out = {}
    for mode in ('static_map','own_frontier'):
        rr = [r for r in rows if r['episode'].endswith(mode)]
        out[mode] = dict(n=len(rr), initial_static_path=sum(r['initial_static_path'] for r in rr),
            path_frames=sum(r['frames_with_path'] for r in rr), translations=sum(r['translation_commands'] for r in rr),
            visible_B_frames=sum(r['B_positive_frames'] for r in rr), detected_B_frames=sum(r['B_detections'] for r in rr),
            B_confirmed=sum(bool(r['B_confirmed'] and r['B_confirmed']['true']) for r in rr),
            statuses=dict(Counter(r['status'] for r in rr)), circle_only=sum(r['collision_circle_only'] for r in rr),
            rectangle_contact_episodes=sum(bool(r['rectangle_contacts']) for r in rr),
            commanded_pose_contact_episodes=sum(bool(r['commanded_pose_contacts']) for r in rr),
            rectangle_contact_ids=dict(Counter(x for r in rr for x in r['rectangle_contacts'])),
            max_track_baseline_m=max((r['max_track_baseline_m'] for r in rr),default=0.))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--audit',type=Path)
    p.add_argument('--oracle',action='store_true')
    a = p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    old.write(a.output/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              hashes=old.source_hashes(),condition='diagnostic_pre_fix'))
    if a.audit:
        rows = audit(a.audit)
        old.write(a.output/'audit.json',rows)
        old.write(a.output/'audit-summary.json',aggregate(rows))
    if a.oracle:
        old.GridWorld = OracleWorld
        results = []
        for i in range(1,9):
            for start in ('B','D'):
                for seed in (2701,2702):
                    for mode in ('static_map','own_frontier'):
                        name = f's{i}-{start}-{seed}-{mode}'
                        r = old.episode(i,start,seed,'confirmation',mode,a.output/name)
                        results.append(r)
                        print(name,r['status'],r['sensor_draws']['B_positive_frames'],flush=True)
        old.write(a.output/'results.json',results)
        rows = audit(a.output)
        old.write(a.output/'oracle-audit.json',rows)
        old.write(a.output/'oracle-summary.json',aggregate(rows))


if __name__=='__main__':
    main()
