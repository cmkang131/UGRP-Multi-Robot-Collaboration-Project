"""Opt-in own-RGB/estimated-pose grid; surveyed map files are not actor inputs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def new_grid():
    from harness.self_odom_grid import OdomGrid
    # This adapter receives already-estimated poses and calls insert(), never
    # observe()/odom.advance(). Avoid loading an unused legacy motion table.
    return OdomGrid('r1',profiles={})


def run(a):
    # Use the complete pinned vision dependency closure, not mixed versions.
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.vision_source,text=True).strip()!='5974a181a2cec9731339a6ce3aadc0464b8dddcf':
        raise ValueError('PINNED_VISION_SOURCE_REQUIRED')
    sys.path.insert(0,str(a.vision_source))
    import cv2
    import numpy as np
    from mapbuild1_replay import read_frame,dump
    from harness.self_odom_grid import OdomGrid,transform
    from harness.active_wall_vision import observe,modules
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    from harness.servo_camera_fk import transform_from_commands
    from harness.e2e_rgb_vo import ground
    from harness.zone_color_boxes import detect_own,OWN_PROFILE_ZONE
    from harness.floor_goal_self_mask import self_body_mask
    from harness.floor_goal import FloorGoalOptions
    calibration=a.vision_source/'experiments/2026-10-16-reloc16/colour-calibration.json'
    paint=a.vision_source/'experiments/2026-10-16-warp7/paint-calibration.json'
    if hashlib.sha256(calibration.read_bytes()).hexdigest()!='a37cf96551abbfb8b38df3efc1cd61f3f357ac9eb3a1dcd0b4d9947242e4e24f':
        raise ValueError('FROZEN_COLOUR_CALIBRATION_REQUIRED')
    if hashlib.sha256(paint.read_bytes()).hexdigest()!='cd4b248fb0698f513aa7a299e6257ed23409527349d67641e37a7e19122cb957':
        raise ValueError('FROZEN_PAINT_CALIBRATION_REQUIRED')
    state=ColourBoundaryState('walls_floor_contrast_v5_indigo110_s80',json.loads(calibration.read_text()),option=RELOC16_OPTION)
    paints=json.loads(paint.read_text())['paint']
    manifest=json.loads((a.input/'own.json').read_text())
    trajectory=json.loads(a.trajectory.read_text());poses={(r['sequence'],r['frame_id']):r for r in trajectory}
    a.output.mkdir(exist_ok=False,parents=True);grids={};walls={};obstacles={};destinations={};events=[]
    for frame in manifest['frames']:
        name=frame['sequence'];estimate=poses[name,frame['frame_id']]
        if name not in grids:
            grids[name]=new_grid();walls[name]=set();obstacles[name]=set();destinations[name]=set()
        grid=grids[name];servo={int(k):v for k,v in frame['servo'].items()}
        camera,reason=transform_from_commands(servo,camera_pose='servo_fk_v1')
        event=dict(sequence=name,frame_id=frame['frame_id'],category='map_frame',reason=reason,
            blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured',segments=0)
        if camera is None:event['reason']='unqualified_camera:'+reason;events.append(event);continue
        if estimate['lk']['status'] not in ('measured','bootstrap'):
            event['reason']='unknown_visual_pose:'+estimate['lk']['status'];events.append(event);continue
        pose=np.asarray(estimate['lk_pose']);rgb=read_frame(a.input,frame)
        obs=observe(rgb,servo,wall_detector=RELOC16_OPTION,contact_state=state,
                    frame_id=frame['frame_id'],odometry_pose=pose)
        origin=transform([obs['camera']],pose)[0]
        segs=[transform(s,pose) for s in obs['segments']]
        if segs:grid.insert(origin,segs)
        def cell(p):return tuple(np.floor(np.asarray(p)/grid.resolution_m).astype(int).tolist())
        # Preserve semantic identity independently from generic occupied cells.
        for segment in segs:
            count=max(2,int(np.ceil(np.linalg.norm(segment[1]-segment[0])/(grid.resolution_m/2)))+1)
            walls[name].update(cell(p) for p in np.linspace(*segment,count))
        boxes=detect_own(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),servo,profile=OWN_PROFILE_ZONE)
        # The original cuboid detector's accepted floor estimate supplies the
        # centre; no surveyed obstacle or instance identity is consulted.
        for box in boxes['detections']:
            x,y,w,h=box['pixel_bbox']
            p,depth=ground(servo,np.asarray([[x+w/2,y+h]],float))
            if np.isfinite(p).all() and np.isfinite(depth).all() and depth[0]>0:
                point=transform(p,pose)[0];obstacles[name].add(cell(point));grid.insert(origin,[[point,point]])
        hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);body=self_body_mask(servo,'camera_v3',640,480)
        for kind,bounds in paints.items():
            mask=cv2.inRange(hsv,np.asarray(bounds['low'],np.uint8),np.asarray(bounds['high'],np.uint8))>0
            mask &= ~body
            yy,xx=np.nonzero(mask)
            # Every classified pixel is projected; quantize to the inherited
            # 10cm grid, without assuming the full rectangular destination.
            p,depth=ground(servo,np.column_stack((xx,yy)))
            keep=np.isfinite(p).all(1)&np.isfinite(depth)&(depth>0)&(depth<FloorGoalOptions().max_range_m)
            destinations[name].update(cell(p) for p in transform(p[keep],pose))
        event.update(reason='observed_wall_contacts' if segs else 'no_supported_wall_contacts',segments=len(segs),
            column_reasons=dict(Counter(state.last_result['column_reasons'])) if state.last_result else {})
        events.append(event)
    for name,grid in grids.items():
        cells={k:'occupied' if value>0 else 'free' for k,value in grid.cells.items() if value!=0}
        doors=set()
        # Grid-topological door CANDIDATES: two observed wall cells bound a
        # contiguous observed free gap, including free cells on both sides.
        # One-cell adjacency derives from grid discretization, not a fitted
        # physical minimum width/angle. No unobserved gap is filled in.
        for axis in (0,1):
            lines={}
            for key in walls[name]:lines.setdefault(key[axis],[]).append(key[1-axis])
            for line,positions in lines.items():
                for start,end in zip(sorted(positions),sorted(positions)[1:]):
                    gap=[]
                    for v in range(start+1,end):
                        k=(line,v) if axis==0 else (v,line)
                        crossing=[(line+offset,v) if axis==0 else (v,line+offset) for offset in (-1,0,1)]
                        if all(cells.get(c)=='free' for c in crossing):gap.append(k)
                    if gap and len(gap)==end-start-1:doors.update(gap)
        points=lambda keys:[[(x+.5)*grid.resolution_m,(y+.5)*grid.resolution_m] for x,y in sorted(keys)]
        dump(a.output/(name+'-predicted.json'),dict(frame='r1/start',resolution_m=grid.resolution_m,
            cells=[[x,y,label] for (x,y),label in sorted(cells.items())],wall=points(walls[name]),
            obstacle=points(obstacles[name]),destination=points(destinations[name]),door=points(doors),
            door_scope='observed free crossing candidates, not instance identity or certified transit'))
    dump(a.output/'rejection-table.json',dict(raw=str(a.input),reproduction=sys.argv,stages=[
        dict(stage='frames',cumulative_pass_n=len(events),rejected_n=0),
        dict(stage='qualified_camera',cumulative_pass_n=sum(not e['reason'].startswith('unqualified_camera') for e in events),
             rejected_n=sum(e['reason'].startswith('unqualified_camera') for e in events)),
        dict(stage='visual_pose',cumulative_pass_n=sum(not e['reason'].startswith(('unqualified_camera','unknown_visual_pose')) for e in events),
             rejected_n=sum(e['reason'].startswith('unknown_visual_pose') for e in events)),
        dict(stage='supported_wall_contacts',cumulative_pass_n=sum(e['segments']>0 for e in events),
             rejected_n=sum(e['reason']=='no_supported_wall_contacts' for e in events))],
        reasons=dict(Counter(e['reason'] for e in events))))
    dump(a.output/'events.json',events)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True)
    p.add_argument('--trajectory',type=Path,required=True);p.add_argument('--vision-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:p.error('explicit --execute required; default off')
    run(a)
