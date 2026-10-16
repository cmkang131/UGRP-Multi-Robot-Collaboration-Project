"""Frozen-input replay only. No physics, render, remote host or evaluation input."""
import hashlib
import json
import math
import shutil
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from sim.grasp_act_release_teacher import ReleaseTeacher
from sim.release_global_observation import margin_report,pair_choice
from sim.release_regrasp import near_grip
from sim.release_axis_correction import correction_angle

BASE=Path(__file__).parent
RAW=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
SOURCE='8e520ea2816c46a0f0d7aac250fcf0969416c808'


def read(path,lines=False):
    if not path.exists() and path.suffix=='.zst':path=path.with_suffix('')
    b=subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else path.read_bytes()
    return [json.loads(s) for s in b.splitlines()] if lines else json.loads(b)


def main():
    evidence=[];runs=[]
    for no,seed in enumerate((74940,74963)):
        raw=RAW/f'release9-diagnostic-{no:02d}-{SOURCE[:8]}/raw'
        manifest=read(raw/'manifest.json.zst')
        for name in ('plan.json','result.json.zst','teacher-r1.jsonl.zst','teacher-r2.jsonl.zst'):
            p=raw/name;sha=hashlib.sha256(p.read_bytes()).hexdigest()
            assert sha==manifest[name]['sha256']
            evidence.append(dict(path=str(p),sha256=sha))
        result=read(raw/'result.json.zst');plan=read(raw/'plan.json')
        assert result['source_sha']==SOURCE and plan['seed']==seed
        from harness.zone_final_environment import resolve
        zone=resolve(plan['map_id'])[0]['regions'][plan['destination_region']]
        rect=(*zone['center_m'],*zone['half_extents_m'])
        choices=result['code_decisions'][1:]
        reports={str(c['t']):{} for c in choices};maximum_error=0.
        for rid in ('r1','r2'):
            ts=read(raw/f'teacher-{rid}.jsonl.zst',lines=True)
            teacher=ReleaseTeacher(rid,plan['roles'][rid],ts[0]['pwm'],handoff_pose_estimate=None,
                zone_rect=rect,reach_mode=result['reach_mode'],odometry_profile=result['command_motion'])
            indices={i:min(range(len(ts)),key=lambda j:abs(ts[j]['t']-c['t'])) for i,c in enumerate(choices)}
            for index,row in enumerate(ts):
                now=row['t'];teacher.pwm={int(k):v for k,v in row['pwm'].items()}
                if teacher.holding and not row['holding_belief']:teacher.released_here(now)
                teacher.holding=row['holding_belief']
                for ci,choice in enumerate(choices):
                    if index!=indices[ci]:continue
                    # Only stored own-RGB fits + own-command target/odometry.
                    sweeps=result['lookaround_result'][rid]['evaluation']['sweeps']
                    sweep=max((s for s in sweeps if s['t0']+s['sim_s']<=now+1e-6),key=lambda s:s['t0']+s['sim_s'])
                    decision=sweep['decision']
                    loc=SimpleNamespace(decision=decision,own=SimpleNamespace(x=decision.get('proposed',[0.,0.,0.])))
                    old=margin_report(loc,teacher,choice['t'],lateral_recovery='bounded_v1')
                    new=margin_report(loc,teacher,choice['t'],lateral_recovery='bounded_v1',axis_recovery=True)
                    saved=row['report']
                    assert old['kind']==saved['kind'] and old.get('reason')==saved.get('reason')
                    for key in ('margin_m','lateral_clearance_m','lateral_shift_lo_m','lateral_shift_hi_m'):
                        if old.get(key) is not None:
                            maximum_error=max(maximum_error,abs(old[key]-saved[key]))
                            assert abs(old[key]-saved[key])<1e-6
                    reports[str(choice['t'])][rid]=dict(old=saved,new=new)
                dt=np.clip(np.array(row['wheel_until'])-now,0.,.1);duration=float(max(dt))
                if duration:teacher.dead_reckon(np.array(row['wheels'])*dt/duration,duration)
        replay=[]
        for original in choices:
            own=reports[str(original['t'])]
            old=pair_choice({r:v['old'] for r,v in own.items()},('r1','r2'),original['t'],lateral_recovery='bounded_v1')
            assert old==original
            new=pair_choice({r:v['new'] for r,v in own.items()},('r1','r2'),original['t'],lateral_recovery='bounded_v1',axis_recovery=True)
            if new['action']=='axis_correct':
                try:new['axis_turn_rad']=correction_angle(new)
                except ValueError as error:new['axis_path_refusal']=str(error)
            same=all(new.get(k)==v if not isinstance(v,float) else abs(new.get(k,math.inf)-v)<1e-6 for k,v in old.items()) and new.keys()==old.keys()
            replay.append(dict(t=original['t'],old=old,new=new,equivalent=same))
        frames=[];reviewed=[]
        for p in sorted((Path('/private/tmp/r9f')/f'{no:02d}').rglob('*.jpg')):
            rel=str(p.relative_to(Path('/private/tmp/r9f')/f'{no:02d}'))
            sha=hashlib.sha256(p.read_bytes()).hexdigest();assert sha==manifest[rel]['sha256']
            saved=ROOT/'outputs/release11-review/reviewed-originals'/str(seed)/rel
            saved.parent.mkdir(parents=True,exist_ok=True)
            if not saved.exists():shutil.copy2(p,saved)
            assert hashlib.sha256(saved.read_bytes()).hexdigest()==sha
            reviewed.append(dict(path=str(saved),original=rel,sha256=sha))
            if rel.startswith('eval-own/'):
                row=dict(path=str(saved),original=rel,sha256=sha,near_grip=near_grip(cv2.imread(str(saved))))
                frames.append(row)
        assert len(frames)==(18 if no==0 else 16)
        runs.append(dict(seed=seed,source_sha=SOURCE,raw=str(raw),
            original_success=result['release_success'],original_outcome=result['release_outcome'],
            input_audit={k:result['input_audit'][k] for k in ('invisible_measurements','held_world_reads')},
            decisions=replay,equivalent=sum(r['equivalent'] for r in replay),N=len(replay),
            margin_max_error_m=maximum_error,review_rgb=frames,reviewed_frames=reviewed,
            first_new_barrier='repick timer expiry -> sequential own RGB test, never direct shift',
            missing_evidence='No new sequential test-lift images in saved runs. Full enabled trajectory/outcome equivalence unverified.',
            frozen_path_warning='Later stored inputs are old-path branch tests, not predictions after the new barrier.'))
    out=dict(schema='ugrp.release11.replay.v1',scope='saved own command / own RGB fit / sparse review RGB only',
             runs=runs,source_files=evidence,physics_runs=0)
    (BASE/'release11-replay.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([dict(seed=r['seed'],equivalent=r['equivalent'],N=r['N'],margin_max_error_m=r['margin_max_error_m']) for r in runs]))


if __name__=='__main__':main()
