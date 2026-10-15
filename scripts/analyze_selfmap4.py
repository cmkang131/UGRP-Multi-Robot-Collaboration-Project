"""Evaluate stored selfmap RGB/commands and replay the recorded stall policy.

No simulator/render/remote connection. Evaluator poses are read only here, never
passed to the mapper, flow, static localizer, or command-selection probe.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

from scripts.offline_self_map import digest, dump, read, rows, score


def source_analysis(raw, images):
    from harness.natural_floor_slam import compose
    from harness.self_pulse_odom import command_odometry
    from harness.self_odom_grid import transform
    from harness.active_wall_vision import observe
    from harness import selfmap4_geometry as geometry
    from harness.self_map_landmark_sensor import Sensor
    from harness.own_map_amcl_vendor.landmarks import MapFeatures
    from harness.own_map_navigation import Footprint, footprint_clearance, reachable, frontier_candidates
    from harness.self_map_integration import SelfMapIntegration, Options, OPTION
    frames, fs = rows(raw/'robots/r3/frames.jsonl')
    trace, ts = rows(raw/'trace.jsonl')
    commands, cs = rows(raw/'robots/r3/commands.jsonl')
    static, _ = geometry.static_input()
    sensor = Sensor(MapFeatures(static).hues)
    detections = []
    for f in frames:
        p = images/f['path']
        if not p.exists():
            continue
        if digest(p) != f['sha256']:
            raise ValueError('SAVED_RGB_HASH_MISMATCH')
        rgb = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
        servo = {int(k):v for k,v in f['commanded_servo'].items()}
        detections.append(dict(frame_id=f['frame_id'], t=f['sim_time'], path=str(p), sha256=f['sha256'],
            before=observe(rgb, servo), after=geometry.observe(rgb, servo, sensor)))
    # All RGB extraction has finished before this evaluation-only section.
    truth, gs = rows(raw/'eval_only/trajectory.jsonl')
    by_t = {round(r['t'],8):r for r in truth}; by_trace = {round(r['t'],8):r for r in trace}
    origin = [*truth[0]['robot_xyz_m'][:2], truth[0]['robot_yaw_rad']]
    odom = command_odometry(commands[0]['t'], motion_model='s2_pulse_v122_rotL_v1')
    ci = 0; predicted = []; actual = []; paired_t = []; unpaired = []
    for f in frames:
        t = float(f['sim_time'])
        if round(t,8) not in by_t:
            unpaired.append(f['frame_id']); continue
        while ci < len(commands) and commands[ci]['t'] < t-1e-8:
            odom.command(commands[ci]); ci += 1
        odom.advance(t)
        predicted.append(compose(origin, odom.pose))
        gt = by_t[round(t,8)]
        actual.append([*gt['robot_xyz_m'][:2], gt['robot_yaw_rad']]); paired_t.append(t)
    predicted, actual = np.asarray(predicted), np.asarray(actual)
    d = np.linalg.norm(np.diff(predicted[:,:2],axis=0),axis=1)
    a = np.linalg.norm(np.diff(actual[:,:2],axis=0),axis=1)
    errors = np.linalg.norm(predicted[:,:2]-actual[:,:2],axis=1)
    rect = np.array([o['center_m']+o['half_extents_m'] for o in static['obstacles']])
    bounds = static['bounds_m']
    def geometry_error(points):
        if not len(points):return dict(N=0)
        q = abs(points[:,None,:]-rect[None,:,:2])-rect[None,:,2:]
        dist = abs(np.linalg.norm(np.maximum(q,0),axis=2)+np.minimum(q.max(2),0)).min(1)
        outside = ((points[:,0]<bounds[0])|(points[:,0]>=bounds[1])|
                   (points[:,1]<bounds[2])|(points[:,1]>=bounds[3]))
        return dict(N=len(points), outside=int(outside.sum()), wall_error_median_m=float(np.median(dist)),
                    wall_error_p95_m=float(np.quantile(dist,.95)))
    per_frame = []
    for f in detections:
        t = round(f['t'],8); gt = by_t[t]
        poses = dict(estimated=compose(origin, by_trace[t]['pose']),
                     truth_pose_only=[*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']])
        metrics = {}
        for label in ('before','after'):
            segments = f[label]['segments']
            pts = np.concatenate([np.linspace(*s,20) for s in segments]) if segments else np.empty((0,2))
            metrics[label] = {key:geometry_error(transform(pts, pose)) for key,pose in poses.items()}
        per_frame.append({k:f[k] for k in ('frame_id','t','path','sha256')} | dict(projection=metrics))
    snapshot = json.loads(read(raw/'map.json')[0])
    mapper = SelfMapIntegration('r3', options=Options(self_map_integration=OPTION,
        navigation_support='current_footprint_v1'))
    nav = mapper.grid.navigation
    nav.odds = {(x,y):v for x,y,v in snapshot['cells']}
    nav.floor_frames = {tuple(c):{0} for c in snapshot['floor_cells']}
    nav.wall_frames = {tuple(c):{0} for c in snapshot['wall_cells']}
    mapper.slam.pose = np.asarray(trace[-1]['pose']); grid = mapper.planning_grid()
    _, clear, _, lo = footprint_clearance(grid, Footprint(), mapper.nav_options.pose_margin_m,
                                         yaw=mapper.slam.pose[2])
    start = np.asarray(grid.cell(mapper.slam.pose[:2]))-lo
    candidates = frontier_candidates(grid, mapper.slam.pose, mapper.nav_options)
    frontier = dict(recorded_candidate_count=trace[-1]['candidate_count'],
        recorded_raw_frontier_cells=trace[-1]['raw_frontier_cells'],
        recorded_insertion_blockers=trace[-1]['insertion_blockers'],
        recomputed_geometric_candidates=len(candidates),
        start_footprint_clear=bool(clear[start[1],start[0]]),
        reachable_cells=int(reachable(clear,tuple(start)).sum()),
        note='final snapshot only; geometric candidates do not authorize drive under pose quarantine')
    return dict(sources=[fs,ts,cs,gs], declared_frames=len(frames), rgb_available=len(detections),
        observed_frames=per_frame, raw_map_evaluation=score(snapshot,static,origin), frontier=frontier,
        odometry=dict(model='s2_pulse_v122_rotL_v1', paired_N=len(actual), unpaired_frame_ids=unpaired,
            command_distance_m=float(d.sum()), gt_distance_m=float(a.sum()), ratio=float(d.sum()/a.sum()),
            position_error_median_m=float(np.median(errors)), position_error_final_m=float(errors[-1]),
            position_error_max_m=float(errors.max()),
            interval_ratio_gt_over_5mm_n=int((a>.005).sum()),
            interval_ratio_gt_over_5mm_median=float(np.median(d[a>.005]/a[a>.005])) if (a>.005).any() else None),
        original_rebuilds=snapshot['rebuilds'])


def stall_probe(raw):
    """Fixed old trace/commands, real executor; proposals are NOT fed to a plant.

    Keep the recorded estimate and final quarantined grid. This isolates the
    scheduler counterexample, not a counterfactual closed-loop RGB trajectory.
    """
    from harness.self_map_integration import SelfMapIntegration, Options, OPTION
    from harness.self_map_executor import SelfMapExecutor
    from harness.selfmap4_geometry import PROFILE, static_input, StaticRegistration
    trace, _ = rows(raw/'trace.jsonl'); commands, _ = rows(raw/'robots/r3/commands.jsonl')
    snap = json.loads(read(raw/'map.json')[0]); t0=trace[0]['t']
    selected = [r for r in trace if r['t']-t0 >= 100.-1e-8]
    output = {}
    for profile in ('off',PROFILE):
        mapper = SelfMapIntegration('r3', start_time=t0, options=Options(self_map_integration=OPTION,
            navigation_support='current_footprint_v1'))
        mapper.options = Options(self_map_integration=OPTION, navigation_support='current_footprint_v1',
                                 recovery_profile=profile)
        nav=mapper.grid.navigation
        nav.odds={(x,y):v for x,y,v in snap['cells']}
        nav.floor_frames={tuple(c):{0} for c in snap['floor_cells']}
        nav.wall_frames={tuple(c):{0} for c in snap['wall_cells']}
        current = {}
        def received(**kw):
            mapper.slam.pose = np.asarray(current['pose'])
            row=copy.deepcopy(current)
            # Original rows already contain executor output keys.
            for k in ('executor_stop_reason','issued_command','stage','frontier_arrivals'):
                row.pop(k,None)
            if profile!='off':
                row['rebuild_commits']=sum(r['committed'] for r in snap['rebuilds'] if r['t']<=row['t'])
                row['recovery_candidate']=dict(skill='relocalize',pans=[1500,1000,2000,1500])
            return row
        mapper.receive=received
        c=SelfMapExecutor('r3',start_time=t0,cap_s=180.,mapper=mapper)
        c.stage='select';c.initial_sweep_complete=True
        ci=0;issued=[]
        for r in selected:
            while ci<len(commands) and commands[ci]['t']<r['t']-1e-8:
                mapper.command(commands[ci]);ci+=1
            mapper.odom.advance(r['t']);current=r
            command,row=c.receive(robot_id='r3',t=r['t'],frame_id=r['frame_id'],rgb=None)
            issued.append(dict(t=r['t'],stage=row['stage'],command=command))
            if c.done:break
        output[profile]=dict(N=len(issued),stages=dict(Counter(r['stage'] for r in issued)),
            proposed_commands=dict(Counter((r['command'] or {}).get('kind','none') for r in issued)),
            pan_sequence=[r['command']['pan_pulse'] for r in issued if (r['command'] or {}).get('kind')=='look'],
            stop_reason=c.stop_reason,events=c.events,
            scope='fixed recorded estimates/commands, final quarantined map; new proposals not executed')
    return output


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw',type=Path,required=True);p.add_argument('--images',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--stall',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    result=source_analysis(a.raw,a.images)
    if a.stall:result['stall_probe']=stall_probe(a.raw)
    dump(a.output/'analysis.json',result)
    print(json.dumps(dict(raw=str(a.raw),rgb=result['rgb_available'],odometry=result['odometry'],frontier=result['frontier'],
        stall=None if not a.stall else {k:{x:v[x] for x in ('stages','proposed_commands','stop_reason')} for k,v in result['stall_probe'].items()})))


if __name__=='__main__':
    main()
