"""Replay saved own inputs through the exact diagnostic controller, no physics."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import platform
import numpy as np
from harness.egomem_navigation import MemoryReturn
from harness.egocentric_landmark_memory import wrap
from harness.e2e_rgb_vo import K
from scripts.egomem1_offline import read,dump,digest


def replay(raw):
    summary=read(raw/'summary.json');rows=read(raw/'online-trajectory.json')
    c=MemoryReturn(sweep_steps=summary['work_cap']['phase_steps'],
                   footprint_diameter_m=summary['geometric_departure_distance_floor_m'],
                   horizontal_half_fov_rad=math.atan(320/K[0,0]),
                   strict_return=summary.get('strict_reacquisition',False),
                   translated_return=summary.get('translated_return',False),
                   observed_segment_aim=summary.get('observed_segment_aim',False))
    reasons=Counter();modes=Counter();details=[];changes=[];previous_sign=None;segments=[]
    for row in rows:
        phase=c.stage;memories=row['memory']['memories']
        target=next((m for m in memories if m['id']==c.goal),None)
        action=c.step(row['t'],row['motion_delta'],memories,row['observations'],
                      colour_pixels=row['colour_component_pixels'])
        if action!=row['action']:raise ValueError('SAVED_ACTION_REPLAY_MISMATCH:'+str(row['t']))
        mode='forward' if action[0] else 'turn' if action[2] else 'stop'
        if not segments or segments[-1]['phase']!=phase or segments[-1]['mode']!=mode:
            segments.append(dict(phase=phase,mode=mode,first_t=row['t'],last_t=row['t'],frames=1))
        else:segments[-1].update(last_t=row['t'],frames=segments[-1]['frames']+1)
        if phase!='return':continue
        modes[mode]+=1
        if target is None:reasons['memory_absent']+=1;continue
        if target['representation']=='oriented_line':
            sign=bool(target['measurement_state'][0]>=0)
            if previous_sign is not None and previous_sign!=sign:
                changes.append(dict(t=row['t'],rho_m=target['measurement_state'][0],
                                    memory_bearing_deg=math.degrees(target['bearing_rad']),
                                    mode=mode,own_return_path_m=c.return_path))
            previous_sign=sign
        matching=any(o['kind']=='zone_boundary' and o['signature']==target['signature'] for o in row['observations'])
        if not matching:reasons['no_matching_boundary_this_frame']+=1;continue
        angle=math.atan2(c.aim[1],c.aim[0]) if c.aim is not None else target['bearing_rad']
        gates=dict(visual_exit=c.visual_exit,colour_visible=bool(row['colour_component_pixels']),
                   memory_heading=abs(angle)<=c.half_fov,
                   translated=(not c.translated_return or c.return_path>=c.diameter))
        failed=next((k for k,v in gates.items() if not v),'all_passed')
        reasons[failed]+=1
        details.append(dict(t=row['t'],gates=gates,first_reject=failed,own_return_path_m=c.return_path,
                            memory_bearing_deg=math.degrees(target['bearing_rad']),mode=mode))
    return dict(status='EXACT_OWN_INPUT_REPLAY',frames_verified=len(rows),action_mismatches=0,
                reason_distribution=dict(reasons),return_action_frames=dict(modes),
                final_own_return_path_m=c.return_path,required_return_path_m=c.diameter,
                matching_rgb_frames=details,rho_sign_changes=changes,action_segments=segments,
                controller_events=c.events,raw=str(raw),
                blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured',
                sha256=dict(controller=digest(Path(__import__('harness.egomem_navigation',fromlist=['x']).__file__)),
                            trace=digest(raw/'online-trajectory.json')))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ORIGINAL_CPU_ONLY')
    dump(a.output,replay(a.input))
