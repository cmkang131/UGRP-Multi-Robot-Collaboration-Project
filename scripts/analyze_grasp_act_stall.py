"""Saved-file ACT6 stall census. No inference, simulation, render or remote access."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
from PIL import Image

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_rows, read_json, paired_segments, sha256, write_json


def color_geometry(path, kind):
    import cv2
    a = np.asarray(Image.open(path).convert('RGB'), dtype=float)/255
    r, g, b = a.transpose(2, 0, 1)
    masks = {'cyan': (g>r*1.4)&(b>r*1.4)&(g>.12)&(b>.12),
             'red': (r>g*1.6)&(r>b*1.6)&(r>.15)}
    n, labels, sizes, centers = cv2.connectedComponentsWithStats(masks[kind].astype(np.uint8), 8)
    if n <= 1: return None
    i = 1 + np.argmax(sizes[1:, cv2.CC_STAT_AREA]); x,y,w,h,pixels = sizes[i]
    return {'pixels': int(pixels), 'center': (centers[i]/[a.shape[1],a.shape[0]]).tolist(),
            'wh': [int(w),int(h)]}


def stop_counts(pairs):
    by_phase = defaultdict(lambda: Counter(N=0, zero=0, pan_changed=0, pwm_changed=0))
    targets=[]
    for o, label, *_ in pairs:
        cmd=label['clean_teacher_command']; p=by_phase[label['teacher_phase']]
        zero = not any(cmd['wheels']); p['N']+=1; p['zero']+=zero
        p['pan_changed']+=zero and cmd['pwm']['6'] != o['issued'][-1]['pwm']['6']
        p['pwm_changed']+=zero and cmd['pwm'] != o['issued'][-1]['pwm']
        targets.append(c.encode_action(cmd))
    a=np.asarray(targets)
    return {'N':len(a), 'zero':int((a[:,:4]==0).all(1).sum()),
            'per_wheel_zero':(a[:,:4]==0).sum(0).tolist(),
            'wheel_median':np.median(a[:,:4],axis=0).tolist(),
            'phase':{k:dict(v) for k,v in by_phase.items()}}


def analyze(root, output):
    root,output=Path(root),Path(output)
    admin=root/'e2e18-admin'; raw=root/'gcp1-runs/act-student-main-91100-f609979c/raw'
    paths=[raw/'student-inputs.jsonl',raw/'commands.jsonl',
           admin/'act5-offline-40a21045/pixel-trace.json.zst',
           admin/'act5-offline-40a21045/probes.json.zst',
           admin/'act4-offline-f609979c/actor/adapter.json',
           admin/'gcp-reports/act4-40a21045-ops/measurement/baseline-analysis/timesteps.jsonl.zst']
    obs,commands=map(read_rows,paths[:2]); pixels,probes,adapter=map(read_json,paths[2:5])
    stats=adapter['stats']; teachers=[]; missing=[]; pairs=[]; visual=[]
    for seed in range(86000,86050):
        d=root/f'gcp1-runs/solo-record-{seed}-6f057f7e/raw'
        sp,tp=d/'student-r1.jsonl.zst',d/'teacher-r1.jsonl.zst'
        if not (sp.exists() and tp.exists()): missing.append(seed);continue
        paths += [sp,tp]
        oo,ll=read_rows(sp),read_rows(tp)
        pp=[p for group in paired_segments(oo,ll,done_label='last_local_row_v1') for p in group]
        pairs+=pp
        teachers.append({'seed':seed,'local':stop_counts(pp),
                         'all_recorded':stop_counts(list(zip(oo,ll)))})
        for o,l,*_ in pp:
            if o['skill']!='grasp':continue
            path=d/o['rgb'][-1]['path']
            if sha256(path)!=o['rgb'][-1]['sha256']:raise ValueError('teacher RGB reference mismatch')
            geom=color_geometry(path,o['object_kind'])
            if geom and geom['pixels']>=20:
                visual.append({'seed':seed,'sample_id':o['sample_id'],'t':o['t'],
                    'phase':l['teacher_phase'],'kind':o['object_kind'],'geometry':geom,
                    'command':l['clean_teacher_command'],'path':str(path),'sha256':sha256(path),
                    'pwm':o['issued'][-1]['pwm']})
    zero=np.array([not any(r['command']['wheels']) for r in commands]); visible=np.array([x['full']['pixels']>=20 for x in pixels])
    ages=np.arange(13,c.HISTORY*14,14); sx=np.array([c.context(o) for o in obs])
    sz=(sx-np.array(stats['state_mean']))/np.array(stats['state_std'])
    teacher_states=np.array([c.context(o) for o,_,_ in pairs])
    tz=(teacher_states-np.array(stats['state_mean']))/np.array(stats['state_std'])
    nearest=[]
    for i in (0,32,56,112,256,448,896):
        g=pixels[i]['full']; candidates=[v for v in visual if v['kind']=='cyan']
        # Descriptive RGB-box similarity, not a teacher counterfactual; same kind only.
        feat=lambda x:np.array(x['center']+[x['wh'][0]/640,x['wh'][1]/480])
        ranked=sorted(candidates,key=lambda v:float(np.linalg.norm(feat(g)-feat(v['geometry']))))[:10]
        nearest.append({'row':i,'elapsed_s':round(obs[i]['t']-obs[0]['t'],1),'student_zero':bool(zero[i]),
            'student_geometry':g,'distance_definition':'Euclidean(cx,cy,width/640,height/480); not identical camera/arm/history',
            'nearest_distance':float(np.linalg.norm(feat(g)-feat(ranked[0]['geometry']))),
            'teacher_zero_n':sum(not any(v['command']['wheels']) for v in ranked),'N':len(ranked),
            'teacher_phases':dict(Counter(v['phase'] for v in ranked)),
            'nearest':ranked[0]})
    probe_rows=[]
    for p in probes:
        if p['group']!='rollout':continue
        a=np.array(p['variants']['baseline']['first_action']); dec=c.decode_action(a)
        probe_rows.append({'row':p['row'],'elapsed_s':p['row']*.1,'raw_wheels':a[:4].tolist(),
            'max_abs_wheel':float(abs(a[:4]).max()), 'raw_durations_s':(a[4:8]*.15).tolist(),
            'wheel_below_deadzone':int((abs(a[:4])<.155).sum()),
            'pulse_below_minimum':int((a[4:8]*.15<.001).sum()),'decoded_wheels':dec['wheels'],
            'done':dec['done'], 'normalized_wheel':((a[:4]-stats['action_mean'][:4])/stats['action_std'][:4]).tolist(),
            'normalized_zero_command':(-np.array(stats['action_mean'][:4])/stats['action_std'][:4]).tolist()})
    held=read_rows(paths[5]); by_skill={}
    for skill in ('grasp','release'):
        rows=[r for r in held if r['metadata']['skill']==skill]
        by_skill[skill]={'N':len(rows),'all_drive_axes_stationary':sum(all(r['first_action']['direction']['raw_'+k]['stationary_target_N']==1 for k in ('forward','lateral','yaw')) for r in rows)}
    a=np.array([c.encode_action(l['clean_teacher_command']) for _,l,_ in pairs])
    med=np.median(a[:,:4],axis=0)
    out={'schema':'ugrp.act6.stall.v1','complete_available_saved_analysis':True,
         'physical_runs':0,'inference_calls':0,'training_steps':0,
         'teacher_coverage':{'available_N':len(teachers),'cohort_N':50,'missing_seeds':missing},
         'teacher':teachers,'teacher_local_combined':stop_counts(pairs),
         'teacher_normalized_median':((med-stats['action_mean'][:4])/stats['action_std'][:4]).tolist(),
         'teacher_normalized_zero':(-np.array(stats['action_mean'][:4])/stats['action_std'][:4]).tolist(),
         'heldout_direction_proxy':by_skill,
         'student':{'N':len(obs),'zero':int(zero.sum()),'visible':int(visible.sum()),
             'visible_and_zero':int((visible&zero).sum()),'last_nonzero_s':round(np.where(~zero)[0][-1]*.1,1),
             'zero_at_inference_boundary':[int(zero[::8].sum()),len(zero[::8])],
             'late_zero_at_new_inference':[int(zero[264::8].sum()),len(zero[264::8])],
             'predictions_observation_age_s':{'mean':float(np.mean(np.arange(len(obs))%8*.1)),'max':.7},
             'done_requested':sum(r['done_requested'] for r in commands)},
         'history_shift':{'start_max_abs_age_z':float(abs(sz[0,ages]).max()),
             'ticks_any_age_above_3sigma':int((abs(sz[:,ages]).max(1)>3).sum()),
             'last_tick_any_age_above_3sigma':int(np.where(abs(sz[:,ages]).max(1)>3)[0][-1]),
             'local_teacher_ticks_any_age_above_3sigma':int((abs(tz[:,ages]).max(1)>3).sum()),
             'local_teacher_N':len(tz)},
         'saved_probes':probe_rows,'similar_visible_states':nearest,
         'visual_review':{'student_frames_s':[0,3,5,8,12,18,36,54,72,89.9],
             'path':str(admin/'act5-offline-40a21045/contact-sheet.jpg'),
             'observation':'solo cyan shifts right and remains clipped; late frames nearly unchanged; no partner'},
         'limits':['48 teacher command/RGB originals unavailable locally: census is 2/50, not 50/50',
             'No exact teacher counterfactual for 91100; nearest image box geometry is descriptive only',
             'No causal allocation of L1/history/chunk without matched interventions and closed-loop trials',
             'Full signed heldout residuals unavailable; off-diagonal covariance unidentifiable from absolute errors'],
         'artifacts':{str(p):sha256(p) for p in paths}}
    write_json(output,out);return out


def teacher_census(runs_root, seeds, output):
    episodes=[];all_pairs=[];sources={}
    for seed in seeds:
        root=Path(runs_root)/f'solo-record-{seed}-6f057f7e'/'raw'
        sp,tp=root/'student-r1.jsonl.zst',root/'teacher-r1.jsonl.zst'
        oo,ll=read_rows(sp),read_rows(tp)
        pairs=[p for g in paired_segments(oo,ll,done_label='last_local_row_v1') for p in g]
        episodes.append({'seed':seed,'local':stop_counts(pairs),'all_recorded':stop_counts(list(zip(oo,ll)))})
        all_pairs.extend(pairs);sources.update({str(p):sha256(p) for p in (sp,tp)})
    report={'schema':'ugrp.act6.full_teacher_stall.v1','complete':True,'N':len(episodes),
            'episodes':episodes,'combined_local':stop_counts(all_pairs),'artifacts':sources,
            'physical_runs':0,'inference_calls':0,'training_steps':0}
    write_json(output,report);return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outputs-root',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--teacher-runs-root',type=Path)
    a=p.parse_args()
    if a.teacher_runs_root:teacher_census(a.teacher_runs_root,range(86000,86050),a.output)
    elif a.outputs_root:analyze(a.outputs_root,a.output)
    else:p.error('outputs-root or teacher-runs-root required')


if __name__=='__main__':main()
