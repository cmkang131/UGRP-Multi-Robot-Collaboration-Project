"""Saved own-input branch replay only. Does not import or construct a world."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from sim import release14
from sim.release_regrasp import lift_evidence, continuity
from sim.lookaround_localization import Camera
from harness.vision_loc_protocol import load_vis3


def decoded(path):
    return subprocess.check_output(['zstd','-dc',str(path)]) if path.suffix=='.zst' else path.read_bytes()


def replay(root):
    runs=[]
    for name in ('r12d-01-97942a82','release11-diag-08-c9ba20a6'):
        p=root/name/'raw'
        manifest_path=p/'manifest.json'
        if not manifest_path.exists():manifest_path=p/'manifest.json.zst'
        manifest=json.loads(decoded(manifest_path))
        payloads={}
        for f in ('result.json.zst','teacher-r1.jsonl.zst','teacher-r2.jsonl.zst'):
            digest=hashlib.sha256((p/f).read_bytes()).hexdigest()
            if digest!=manifest[f]['sha256']:raise ValueError('payload hash mismatch: '+f)
            expected=manifest[f].get('decoded_sha256')
            if expected and hashlib.sha256(decoded(p/f)).hexdigest()!=expected:
                raise ValueError('decoded hash mismatch: '+f)
            payloads[f]=digest
        r=json.loads(decoded(p/'result.json.zst'))
        rows={rid:[json.loads(l) for l in decoded(p/f'teacher-{rid}.jsonl.zst').splitlines()] for rid in ('r1','r2')}
        checked={}
        def image(ref):
            file=p/ref['path'];digest=hashlib.sha256(file.read_bytes()).hexdigest()
            if digest!=ref['sha256'] or digest!=manifest[ref['path']]['sha256']:
                raise ValueError('JPEG hash mismatch: '+str(file))
            checked[ref['path']]=digest
            return cv2.imread(str(file))
        inputs=r['regrasp_input_frames'];challenges=[]
        for barrier in r['regrasp_verification']:
            starts=[e for e in barrier['events'] if e['event']=='test_start']
            for start in starts:
                rid=start['robot']
                later=[e['t'] for e in starts if e['robot']==rid and e['t']>start['t']+1e-6]
                stop=min(later,default=float('inf'))
                fs=[f for f in inputs if f['robot']==rid and f['epoch']==barrier['epoch'] and start['t']-1e-6<=f['t']<stop-1e-6]
                b=next(f for f in fs if f['label']=='before_test');a=next(f for f in fs if f['label']=='lift_complete')
                cmd=[dict(t=row['t'],pwm=row['pwm'],wheels=row['wheels']) for row in rows[rid] if b['t']-1e-6<=row['t']<=a['t']+1e-6]
                before,after=image(b),image(a);samples=[]
                for s in [f for f in fs if f['label']=='settled_test']:
                    frame=image(s);old=lift_evidence(before,after,frame,cmd)
                    new=lift_evidence(before,after,frame,cmd,end='teal' if rid=='r1' else 'blue')
                    samples.append(dict(t=s['t'],old=old['answer'],new=new['answer'],reason=new['reason'],
                        central_fraction=[x['central_fraction'] for x in new['near_grip']]))
                restores=[f for f in fs if f['label']=='restored_test']
                retained=None if not restores else continuity(before,image(restores[0]),end='teal' if rid=='r1' else 'blue')
                challenges.append(dict(robot=rid,epoch=barrier['epoch'],attempt=start['attempt'],start_t=b['t'],
                    samples=samples,restored=retained,old_counts=dict(Counter(s['old'] for s in samples)),
                    new_counts=dict(Counter(s['new'] for s in samples))))
        align=[]
        if name.startswith('r12d'):
            undistort=load_vis3()[0].mp.undistort
            for ref in inputs:
                if ref['label'] not in ('realign_back','realign_final'):continue
                row=max((x for x in rows[ref['robot']] if x['t']<=ref['t']+1e-6),key=lambda x:x['t'])
                assert ref['t']-row['t']<.101
                pwm={int(k):v for k,v in row['pwm'].items()}
                feature=release14.line_features(undistort(image(ref)))
                step=release14.line_step(feature,Camera(),pwm)
                align.append(dict(t=ref['t'],pwm_ledger_t=row['t'],feature=feature,decision=step))
        runs.append(dict(name=name,source_sha=r['source_sha'],raw=str(p),challenges=challenges,line_replay=align,
            checked_input_jpegs=len(checked),input_sha256=checked,
            first_runner_divergence=dict(world_t=next(x['t'] for x in rows['r1'] if x['teacher_phase']=='observe_back'),
                action='stationary own-RGB panorama BEFORE rear motion; input at this new view not in old run'),
            input_payload_sha256=payloads,manifest_verified=True))
    return dict(schema='ugrp.release14.offline.v1',profile=release14.PROFILE,runs=runs,
        scope='saved inputs at old states; NOT a closed-loop counterfactual trajectory',
        physical_effect='unverified',new_physical_runs=0,simulator_render_calls=0,
        denominator='development seeds only; no gate/generalization denominator',
        truth_inputs_to_new_decisions=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=replay(a.raw_root)
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(runs=len(result['runs']),jpeg_hashes=sum(r['checked_input_jpegs'] for r in result['runs']),
        line_inputs=sum(len(r['line_replay']) for r in result['runs']),physical_effect='unverified')))
if __name__=='__main__':main()
