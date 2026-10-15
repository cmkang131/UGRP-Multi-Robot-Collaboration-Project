"""Write an unapproved, non-runnable GCP diagnostic request. Never contacts GCP."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from scripts.generate_scene_textures import MAPS
from sim import render_profile as rp
from sim.natural_scene_texture import PROFILE, MANIFEST_SHA256


def viewpoints(static):
    # Authored diagnostic setup poses, not controller input or inferred location.
    nominal=[('floor_west',0,0,0),('north_wall',1.5,.8,math.pi/2),
             ('door_west_view',3.25,.75,math.pi),('goal_east',4.4,-2.1,0),
             ('south_wall',3.25,-2.6,-math.pi/2),('paint_west',0,-2,math.pi/4)]
    x0,x1,y0,y1=static['bounds_m'];out=[]
    def free(x,y):
        return x0+.18<x<x1-.18 and y0+.18<y<y1-.18 and not any(
            abs(x-w['center_m'][0])<w['half_extents_m'][0]+.18 and
            abs(y-w['center_m'][1])<w['half_extents_m'][1]+.18 for w in static['obstacles'])
    for label,x,y,yaw in nominal:
        candidates=[(x+dx,y+dy) for dx in (0,-.25,.25,-.5,.5) for dy in (0,-.25,.25,-.5,.5)]
        valid=next(((a,b) for a,b in candidates if free(a,b)),None)
        if valid is None:raise ValueError(f'no clear diagnostic setup: {static["map_id"]}/{label}')
        out.append({'id':label,'robot_id':'r3','setup_xyyaw':[*valid,yaw],
                    'issued_servo':{'1':2000,'3':740,'4':2320,'5':1320,'6':1500}})
    return out


def plan(sha):
    if not re.fullmatch(r'[0-9a-f]{40}',sha):raise ValueError('full committed source SHA required')
    return {'schema':'ugrp.coordinator_queue.v1','task':'floortex-static-and-selfmap-plan',
        'source_sha':sha,'branch':'claude/scene-floor-texture','host':'gcp1','project':'ugrp-act-train-1014',
        'status':'awaiting_consumer_integration_and_coordinator_approval',
        'approved':False,'ready':False,'ready_for_submission':False,'ready_for_vm':False,
        'ready_for_execution':False,'execute':False,'enabled':False,
        'render_profile':rp.profile_record(PROFILE),'asset_manifest_sha256':MANIFEST_SHA256,
        'needs':['consumer PR scene selector + compiled audits must use requested render_profile',
                 'coordinator fixes source SHA, machine type, live disk/budget and confirms no shared defect',
                 'GCP-only static gate before selfmap first30; no pending automatic submission'],
        'static_gate':{'approved':False,'ready':False,'execute':False,'model_calls':0,'physics_steps':0,
            'profiles':['floor_light_v1',PROFILE],'camera':'existing r3 own camera v3, unchanged calibration/FOV',
            'maps':[{'map_id':p.stem,'path':str(p.relative_to(p.parents[2])),
                     'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                     'viewpoints':viewpoints(json.loads(p.read_text()))} for p in MAPS],
            'views_per_map':6,'frames_per_profile':6*len(MAPS),'total_frames':12*len(MAPS),
            'record':['raw own RGB 640x480 + exact runtime JPEG bytes/hash',
                      'scene XML/profile/asset hash, camera/physics arrays before and after',
                      'per-frame color-mask false-positive pixels/components on floor/wall eval masks',
                      'colored box/band/lug/paint/robot retained pixel support compared with baseline',
                      'detect_boundaries: max_band_std=3 window acceptance n/N, correct boundary recall and false positives vs baseline',
                      'opencv_wall_observation: informative/correct/false columns n/N vs baseline, raw PNG and runtime JPEG',
                      'own_image_gates: exact floor_light_v1 values/hash, valid_frame and valid_frame_ob pass n/N plus dark/spread/std vs baseline',
                      'wall_floor_lorigo, wall_floor_ulrich, vendor/lu_vp: separate unverified-consumer checks; no inferred compatibility',
                      'ORB count before and after exact natural_floor_slam floor mask',
                      'face orientation/seams/scale/anti-aliasing visual inspection'],
            'gate':'no new color false-positive components; report all n/N, no lost target support; reject tiling or wrong face mapping; reject lost correct wall columns or new false wall columns/frame false accepts vs baseline; floor_light_v1 calibration is not textured-profile validation, threshold changes require a texture-only branch and new calibration',
            'evaluation_only':'GT labels/geometry only for setup and scoring; never delivered to controllers'},
        'selfmap_first30':{'approved':False,'ready':False,'execute':False,'pr':506,'model_calls':0,
            'baseline_context_sha':'380277b85911af71d5fcec58905cc650f44aab97',
            'same_new_source_both_arms':True,'profiles':['floor_light_v1',PROFILE],
            'sim_seconds_per_arm':30,'new_seed_requires_reservation':True,
            'metrics':['features','matches','inliers','visual_pose_fraction','command_only_fraction',
                       'rebuild_count','map_updated_fraction','stop_reason','wall/SIM'],
            'limitations':'30 SIM s cannot reproduce the old failure beginning around 93 SIM s or prove complete mapping',
            'stop':'confirmed physical/control defect stops own related runs; no filling failed cohort'},
        'storage_budget_mib':{'static_max':128,'selfmap_pair_max':384,'total_max':512,'live_verified':False},
        'guards':{'vm_max_run_duration':'8h','instance_termination_action':'STOP','idle_shutdown_minutes':20,
                  'budget_stop':'must remain enabled; stop and notify; no automatic host failover',
                  'max_task_wall_s':1800,'machine_type':'UNCONFIRMED; same machine type for both arms'},
        'speed':'record median wall/SIM in first30; >3.5 warning, >6 or incomplete/HOST_ERROR blocks',
        'pooling':'new scene version; never pool with previous profiles or other machine types',
        'remote_execution_performed':False,'camera_verified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();d=plan(a.source_sha)
    with a.output.open('x') as f:json.dump(d,f,indent=2);f.write('\n')
    print(a.output)
