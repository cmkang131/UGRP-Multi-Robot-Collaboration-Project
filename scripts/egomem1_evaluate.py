"""Post-record evaluator ONLY. Never imported by the physical controller.

Uses GT/scene labels after completed, sealed recordings. Appearance return,
same-zone evidence, departure, and actual mission success are separate fields.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import numpy as np
import cv2
from harness.egocentric_landmark_memory import observation_model, wrap, CHI2_99
from harness.egomem_vision import colour_component_pixels
from harness.own_map_amcl_vendor import landmarks as lm


def read(p):
    return json.loads(p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst']))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,allow_nan=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'):raise ValueError('GCP5_ORIGINAL_ONLY')
    a.output.mkdir(exist_ok=False,parents=True);b=a.input
    summary=read(b/'summary.json');trace=read(b/'online-trajectory.json');truth=read(b/'eval-only.json')['frames'];own=read(b/'own.json')['frames'];events=read(b/'events.json')
    source_hash={str(b/n):sha(b/n) for n in ('summary.json','online-trajectory.json','eval-only.json','events.json','own.json','commands.json')}
    if not len(trace)==len(truth)==len(own):raise ValueError('EVAL_JOIN_REQUIRED')
    for f in own:
        if sha(b/f['rgb'])!=f['sha256']:raise ValueError('RGB_CHANGED')
    labels=[]
    for name,zone in read(b/'static-map-eval-only.json')['regions'].items():
        rgba=np.fromstring(zone['rgba'],sep=' ') if isinstance(zone['rgba'],str) else np.asarray(zone['rgba'])
        hue=lm.hue(rgba[:3]);xy=np.asarray(zone['center_m']);size=np.asarray(zone['half_extents_m'])
        for j,normal in enumerate(([1,0],[-1,0],[0,1],[0,-1])):
            normal=np.asarray(normal);edge=xy-normal*size
            labels.append(dict(id=f'{name}-edge{j}',zone=name,hue=hue,state_world=[float(normal@edge),math.atan2(normal[1],normal[0])]))
    def assign(obs,pose):
        candidates=[]
        for label in labels:
            dh=abs(label['hue']-obs['hue']);dh=min(dh,180-dh)
            if dh>lm.PARAMS['hue_tolerance']:continue
            z,_=observation_model(np.r_[label['state_world'],pose],0,'oriented_line')
            residual=np.asarray(obs['measurement_state'])-z;residual[1]=wrap(residual[1])
            d2=float(residual @ np.linalg.solve(np.asarray(obs['covariance_m2']),residual))
            candidates.append(dict(**label,mahalanobis2=d2,distance_error_m=abs(float(residual[0])),angle_error_deg=abs(math.degrees(residual[1]))))
        if not candidates:return None
        nearest=min(candidates,key=lambda p:p['mahalanobis2']);nearest['qualified']=nearest['mahalanobis2']<=CHI2_99
        return nearest
    chosen=next((e for e in events if e['reason']=='visual_zone_remembered'),None)
    goal=chosen['memory_id'] if chosen else None;initial=None;last=None;path=0.;travel=[];misses=0;creation=None
    frame_counts=Counter();memory_events=Counter();motion=Counter()
    for r,g,f in zip(trace,truth,own):
        if not r['t']==g['t']==f['t']:raise ValueError('TIME_JOIN_REQUIRED')
        pose=np.asarray(g['pose']);motion[r['command_motion_source']]+=1;frame_counts[r['stage']]+=1
        if last is not None:path+=float(np.linalg.norm(pose[:2]-last[:2]))
        last=pose
        for e in r['memory']['events']:
            memory_events[e['reason']]+=1
            if e['reason']=='created' and e['memory_id']==goal:
                obs=next(o for o in r['observations'] if o['id']==e['observation'])
                initial=assign(obs,pose);creation=dict(t=r['t'],pose=g['pose'],observation=obs,label=initial)
        travel.append(dict(t=r['t'],path_m=path,pose=g['pose'],stage=r['stage']))
        if chosen and r['t']>chosen['t'] and r['stage'] in ('depart_turn','depart') and r['detector'] is not None:
            misses+=not any(o['kind']=='zone_boundary' and o['signature']==chosen['signature'] for o in r['observations'])
    departure=next((e for e in events if e['reason']=='departure_command_distance_reached'),None)
    reacquired=next((e for e in events if e['reason']=='rgb_signature_reacquired'),None)
    poses={r['t']:r['pose'] for r in truth};net_departure=None
    if chosen and departure:net_departure=float(np.linalg.norm(np.asarray(poses[departure['t']])[:2]-poses[chosen['t']][:2]))
    final_labels=[]
    if reacquired:
        row=next(r for r in trace if r['t']==reacquired['t'])
        for obs in row['observations']:
            if obs['kind']=='zone_boundary' and obs['signature']==chosen['signature']:
                final_labels.append(assign(obs,poses[reacquired['t']]))
    same_zone=bool(initial and initial['qualified'] and any(v and v['qualified'] and v['zone']==initial['zone'] for v in final_labels))
    departed=bool(net_departure is not None and net_departure>=summary['geometric_departure_distance_floor_m'])
    weak_pass=bool(reacquired and same_zone and departed and misses)
    # Boundary-detector misses do NOT prove a colored region left the image.
    # Recount color components in every stored own frame after goal selection.
    colour_rows=[];target_hue=creation['observation']['hue'] if creation else None
    for row,frame in zip(trace,own):
        if target_hue is None or not chosen or row['t']<=chosen['t']:continue
        pixels=colour_component_pixels(cv2.cvtColor(cv2.imread(str(b/frame['rgb'])),cv2.COLOR_BGR2RGB),target_hue)
        colour_rows.append(dict(t=row['t'],stage=row['stage'],pixels=pixels))
    absent=[r for r in colour_rows if r['stage'] in ('depart_turn','depart') and r['pixels']==0]
    final_colour=colour_rows[-1]['pixels'] if colour_rows else 0
    from harness.e2e_rgb_vo import K
    final_memory=next((m for m in trace[-1]['memory']['memories'] if m['id']==goal),None) if trace else None
    heading_ok=bool(final_memory and abs(final_memory['bearing_rad'])<=math.atan(320/K[0,0]))
    passed=bool(weak_pass and absent and final_colour and heading_ok)
    result=dict(status='DEV_VISUAL_RETURN_PASS' if passed else 'NOT_READY',recording_status=summary['status'],
        recordings=1,appearance_reacquired=bool(reacquired),actual_same_zone_reacquired=same_zone,
        departure_verified=departed,actual_departure_m=net_departure,required_departure_m=summary['geometric_departure_distance_floor_m'],
        sensor_samples_without_goal_during_departure=misses,actual_return_reacquisition_rate=float(passed),
        weak_same_colour_boundary_pass=weak_pass,rgb_colour_absent_frames=len(absent),memory_heading_verified=heading_ok,
        final_colour_component_pixels=final_colour,
        physical_diagnostic_pass=passed,physical_delivery_success=False,student_success=False,llm_success=False,
        initial_assignment=initial,final_assignments=final_labels,creation=creation,events=events,actual_path_m=path,
        frames=len(trace),stage_frames=dict(frame_counts),motion_sources=dict(motion),memory_event_reasons=dict(memory_events),
        input_hashes=source_hash,rgb_sha_verified=len(own),raw=str(b),source_sha=summary['source_sha'],
        assignment_gate='Inherited line covariance + chi-square(2)99%; evaluator only, not proof of detector semantics',
        control_input_audit=dict(static_map=0,global_pose=0,spawn=0,top_rgb=0,truth=0,scope='separate API fields and saved command/memory trace; model calls0'),
        rejection_table=str((a.output/'rejection_table.json').resolve()))
    dump(a.output/'summary.json',result);dump(a.output/'travel.json',travel);dump(a.output/'colour-visibility.json',colour_rows)
    gates=[];left=1
    for name,ok in [('rgb_sha',bool(own)),('visual_memory',bool(chosen)),('gt_label_qualified',bool(initial and initial['qualified'])),('departure_verified',departed),('colour_left_camera',bool(absent)),('memory_heading',heading_ok),('same_zone_reacquired',same_zone)]:
        passed=left*bool(ok);gates.append(dict(stage=name,input_n=left,cumulative_pass_n=passed,rejected_n=left-passed));left=passed
    dump(a.output/'rejection_table.json',dict(unit='recording',funnel=gates,raw=str(b),reproduction=__import__('sys').argv,
         reasons=dict(reason='see first rejected funnel gate',blocked_object='not_observed',minimum_gap_m=None,gap_status='not_measured')))
    print(json.dumps({k:result[k] for k in ('status','recording_status','appearance_reacquired','actual_same_zone_reacquired','departure_verified','actual_departure_m','sensor_samples_without_goal_during_departure','actual_path_m','stage_frames')}),flush=True)


if __name__=='__main__':main()
