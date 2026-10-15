"""Local frozen-input replay and SEPARATE evaluation-only cause table. No simulator."""
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from sim import release_regrasp as check
from sim.grasp_act_release_teacher import ReleaseTeacher
from sim.release_regrasp_recovery import shaft_features
from sim.visible_belief import relative
from harness.visual_arm_v3 import forward_grip
BASE=Path(__file__).parent
RAW=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
SOURCE='c9ba20a605c1c4117d553550268c20fa6ac2c3a3'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p,lines=False):
    if not p.exists() and p.suffix=='.zst':p=p.with_suffix('')
    data=subprocess.check_output(['zstd','-dc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
    return [json.loads(x) for x in data.splitlines()] if lines else json.loads(data)


def replay(raw,result,rows,epoch,enabled,receipt_only):
    """Controller boundary replay: real RGB when present, saved RGB receipts otherwise.

    No evaluation file is opened here. No post-divergence input is used to
    predict a closed-loop result. Successful receipt replay is NOT pixel replay.
    """
    recorded=next(b for b in result['regrasp_verification'] if b['epoch']==epoch)
    start=recorded['events'][0]['t']
    ts={}
    for rid in ('r1','r2'):
        old=max((x for x in rows[rid] if x['t']<start-1e-8),key=lambda x:x['t'])
        ts[rid]=ReleaseTeacher(rid,'teal' if rid=='r1' else 'blue',
            {int(k):v for k,v in old['pwm'].items()},handoff_pose_estimate=None,
            zone_rect=(4.6,.4,.3,.7),reach_mode='pad_window_v2',odometry_profile='native_yaw_v1')
        # Reconstruct the old target from issued release PWM and its wheel
        # history. Do not replace it with an evaluation-derived band position.
        for row in rows[rid]:
            if row['t']>=start-1e-8:break
            ts[rid].pwm={int(k):v for k,v in row['pwm'].items()}
            if ts[rid].holding and not row['holding_belief']:ts[rid].released_here(row['t'])
            ts[rid].holding=row['holding_belief']
            dt=np.clip(np.array(row['wheel_until'])-row['t'],0.,.1)
            ts[rid].dead_reckon(np.array(row['wheels'])*dt/.1,.1)
    captured=[x for x in result['regrasp_input_frames'] if x['epoch']==epoch]
    lookup={(round(x['t'],5),x['robot'],x['label']):x for x in captured}
    pending={r:[] for r in ts};scheduled=[];used=[];factory_calls=[];now=start
    def factory(t,at):
        factory_calls.append(dict(robot=t.rid,t=round(at,5)))
        return SimpleNamespace(record=lambda:dict(branch_only=True),tick=lambda *a:'pending')
    b=check.RegraspBarrier(ts,epoch,start-.1,wheel_commands=lambda r:[0.]*4,
                          recovery_factory=factory if enabled else None)
    def schedule(rid,seq,at):
        scheduled.append(dict(t=round(at,5),robot=rid,sequence=copy.deepcopy(seq)))
        pending[rid]=[(at+dt,p) for dt,p in seq]
    def capture(rid,at,label):
        row=lookup[(round(at,5),rid,label)];used.append(row)
        if receipt_only:return np.full((2,2,3),len(used)%255,np.uint8)
        return np.asarray(Image.open(raw/row['path']).convert('RGB'))[:,:,::-1].copy()
    def evidence(*args):
        matches=[s for s in recorded['samples'] if round(s['t'],5)==round(now,5) and s['robot']==b.rid and 'attempt' in s]
        assert len(matches)==1
        return {k:v for k,v in matches[0].items() if k not in ('t','robot','epoch','attempt')}
    def retained(*args):
        # Restored yes is recorded as a confirmed event; final yes has its own
        # sample. Do not infer success from the episode result or contact labels.
        matches=[s for s in recorded['samples'] if round(s['t'],5)==round(now,5) and 'attempt' not in s]
        confirmed=[s for s in recorded['events'] if round(s['t'],5)==round(now,5) and s['event']=='confirmed']
        assert matches or confirmed
        return dict(answer='yes',reason='own_rgb_retained')
    def loop():
        nonlocal now
        for row in rows['r1']:
            now=row['t']
            if now<start-1e-8:continue
            for rid,seq in pending.items():
                while seq and seq[0][0]<=now+1e-9:
                    _,p=seq.pop(0);ts[rid].pwm.update(p)
            status=b.tick(now,capture,schedule)
            if factory_calls or any(e['event']=='retry' for e in b.records):break
            if status in ('ready','failed'):break
        if status=='ready':
            for at in sorted(set(x['t'] for x in captured if x not in used)):
                now=at;assert b.fresh(at,capture)==(None,None)
        return status
    if receipt_only:
        with patch.object(check,'lift_evidence',evidence),patch.object(check,'continuity',retained):status=loop()
    else:status=loop()
    events=[{**e,'t':round(e['t'],5)} for e in b.records]
    expected=[{**e,'t':round(e['t'],5)} for e in recorded['events']]
    if status=='ready':assert events==expected
    return dict(epoch=epoch,status=status,events=events,schedules=scheduled,
        captured_count=len(used),factory_calls=factory_calls,
        first_branch_time=factory_calls[0]['t'] if factory_calls else None)


def cause_only(raw,rows):
    """Evaluation-only poses. Never returned to replay/controllers."""
    ev=[x for x in read(raw/'eval-only.jsonl.zst',True) if 'beam' in x]
    phases=[];last=None
    for row in rows['r1']:
        if row['teacher_phase']==last:continue
        last=row['teacher_phase'];t=row['t'];e=min(ev,key=lambda x:abs(x['t']-t))
        pose=e['robots']['r1']['pose'];body=relative(pose,e['beam']['ends']['teal'][:2])
        fk=forward_grip({int(k):v for k,v in row['pwm'].items()})
        phases.append(dict(command_t=t,evaluation_t=e['t'],phase=last,robot_pose=pose,
            visible_label_not_control_band_body=body[:2],commanded_grip=list(fk),
            lateral_label_minus_command_m=body[1]-fk[1],pwm=row['pwm']))
    wheel=[]
    for phase in dict.fromkeys(x['teacher_phase'] for x in rows['r1']):
        entries=[x for x in rows['r1'] if x['teacher_phase']==phase]
        wheel.append(dict(phase=phase,n=len(entries),nonzero=sum(any(x['wheels']) for x in entries),
            unique_commands=[list(x) for x in sorted(set(tuple(x['wheels']) for x in entries))]))
    return dict(scope='evaluation-only, no controller/replay input',phase_transitions=phases,wheel_commands=wheel)


def main():
    results=[];evidence=[]
    for no,seed in enumerate((74940,74963)):
        raw=RAW/f'release11-diag-{no:02d}-{SOURCE[:8]}/raw'
        manifest=read(raw/'manifest.json.zst')
        for name in ('plan.json','result.json.zst','teacher-r1.jsonl.zst','teacher-r2.jsonl.zst'):
            p=raw/name;h=digest(p);assert h==manifest[name]['sha256']
            evidence.append(dict(path=str(p),sha256=h))
        result=read(raw/'result.json.zst');assert result['source_sha']==SOURCE
        rows={r:read(raw/f'teacher-{r}.jsonl.zst',True) for r in ('r1','r2')}
        frames=[];missing=[]
        for f in result['regrasp_input_frames']:
            p=raw/f['path']
            if not p.exists():missing.append(f);continue
            h=digest(p);assert h==f['sha256']==manifest[f['path']]['sha256']
            im=cv2.imread(str(p));ys,xs=np.nonzero(check.beam_mask(im));h_,w=im.shape[:2]
            frames.append(dict(**f,raw_center_x_px=float(xs.mean()) if len(xs) else None,
                raw_offset_from_image_midpoint_px=float(xs.mean()-(w-1)/2) if len(xs) else None,
                near_grip=check.near_grip(im)))
        replays=[]
        for b in result['regrasp_verification']:
            old=replay(raw,result,rows,b['epoch'],False,bool(missing))
            new=replay(raw,result,rows,b['epoch'],True,bool(missing))
            same=old['schedules']==new['schedules'] and old['events']==new['events']
            replays.append(dict(epoch=b['epoch'],old=old,new=new,behavior_changes=0 if same else 1,
                scope='stored own RGB verdict + command boundary replay; JPEG unavailable' if missing else 'stored original JPEG + command boundary replay to first divergence'))
        entry=dict(seed=seed,raw=str(raw),source_sha=SOURCE,old_success=result['release_success'],
            old_input_audit={k:result['input_audit'][k] for k in ('invisible_measurements','held_world_reads')},
            rgb_frames_available=len(frames),rgb_frames_missing=len(missing),replays=replays,
            frames=frames,old_attempts=[b['attempts'] for b in result['regrasp_verification']],
            old_samples=[b['samples'] for b in result['regrasp_verification']],
            physical_candidate_result='UNMEASURED; no post-branch images or remote execution')
        # Keep large classifier details in compressed original, not this summary.
        entry.pop('old_samples')
        if seed==74963:
            entry['evaluation_cause']=cause_only(raw,rows)
            p=raw/'eval-only.jsonl.zst';assert digest(p)==manifest[p.name]['sha256']
            evidence.append(dict(path=str(p),sha256=digest(p),scope='evaluation only'))
            reviewed=[]
            for n in (0,40,70,120,160,220,360,560):
                f=next((raw/'eval-overview').glob(f'{n:06d}-release-*.jpg'))
                for folder in ('eval-overview','eval-own/r1','eval-own/r2'):
                    p=raw/folder/f.name;h=digest(p);assert h==manifest[str(p.relative_to(raw))]['sha256']
                    reviewed.append(dict(path=str(p),sha256=h,world_sim_s=rows['r1'][0]['t']+n*.1))
            reviewed += [dict(path=str(raw/f['path']),sha256=f['sha256'],world_sim_s=f['t']) for f in frames if f['label'] in ('before_test','lift_complete','restored_test')]
            entry['visually_reviewed']=reviewed
        results.append(entry)
    out=dict(source=SOURCE,mode='offline stored evidence only',runs=results,verified_payloads=evidence,
        original_74940_missing_jpegs='96; no remote access. Receipt replay cannot verify pixel classifier.',
        new_physics=0,new_renderer=0,new_remote_access=0)
    dest=BASE/'release12-replay.json'
    blob=json.dumps(out,ensure_ascii=False,indent=2)+'\n'
    # Store detailed frame metrics compactly; repository 64 KiB text rule.
    if len(blob.encode())>64000:blob=json.dumps(out,ensure_ascii=False,separators=(',',':'))+'\n'
    assert len(blob.encode())<=65536
    dest.write_text(blob)
    print(json.dumps(dict(path=str(dest),runs=[dict(seed=r['seed'],changes=[x['behavior_changes'] for x in r['replays']],frames=r['rgb_frames_available'],missing=r['rgb_frames_missing']) for r in results])))


if __name__=='__main__':main()
