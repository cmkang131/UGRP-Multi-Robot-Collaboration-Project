"""Two-pass own-RGB prediction then evaluation-only contact join; no physics."""
import argparse
import base64
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from harness.s4_grip_visual import Config, GripMonitor, OPTION
from scripts.run_s4_grip_dataset import PLAN, ROOT, RECORD


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def readlines(path):return [json.loads(x) for x in path.read_text().splitlines()]


def score(labels, predictions):
    if len(labels)!=len(predictions):raise ValueError('label/prediction length mismatch')
    if not labels:raise ValueError('empty episode')
    for a,b in zip(labels,predictions):
        if abs(a['sim_time']-b['sim_time'])>1e-8:raise ValueError('timestamp mismatch')
    start_held=len(labels)>=5 and all(r['label']=='held' for r in labels[:5])
    onset=next((i for i in range(5,len(labels)-2) if all(r['label']=='zero' for r in labels[i:i+3])),None) if start_held else None
    alarm=next((i for i,r in enumerate(predictions) if r['state']=='grip_lost'),None)
    counts=Counter(); states=Counter(r['state'] for r in predictions)
    for i,(a,b) in enumerate(zip(labels,predictions)):
        label='lost' if a['label']=='zero' and onset is not None and i>=onset else a['label']
        state=b['state']
        counts['label_'+label]+=1
        if label=='held':counts['held_unknown' if state=='unknown' else 'false_positive' if state=='grip_lost' else 'true_negative']+=1
        if label=='lost':counts['lost_unknown' if state=='unknown' else 'true_positive' if state=='grip_lost' else 'false_negative']+=1
    detected=start_held and onset is not None and alarm is not None and alarm>=onset
    return dict(start_held=start_held,actual_loss=onset is not None,onset_frame=onset,alarm_frame=alarm,
                detected=detected,false_alarm=start_held and alarm is not None and (onset is None or alarm<onset),
                delay_frames=alarm-onset if detected else None,
                delay_sim_s=round(labels[alarm]['sim_time']-labels[onset]['sim_time'],8) if detected else None,
                frame_counts=dict(counts),prediction_counts=dict(states))


def evaluate(raw_root,split,output):
    freeze=json.loads((ROOT/RECORD/'detector-freeze.json').read_text())
    for path,digest in freeze['sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('detector changed after preregistered freeze')
    if freeze['config']!=asdict(Config()):raise ValueError('config mismatch')
    output.mkdir(parents=True,exist_ok=False)
    episodes=[];sources={};unique=Counter()
    for job in json.loads(PLAN.read_text())['runs']:
        rid=job['robot_id']
        for case in job['cases']:
            if case['split']!=split:continue
            raw=raw_root/job['name']/'raw'/case['id']
            result=json.loads((raw/'result.json').read_text())
            entry=dict(job=job['name'],robot_id=rid,case=case,raw=str(raw),status=result['status'])
            if result['status']!='COLLECTED':episodes.append(entry);continue
            frames=readlines(raw/f'robots/{rid}/frames.jsonl')
            sensor=GripMonitor('cyan' if rid=='r3' else 'long_beam',mode=OPTION)
            predictions=[];legacy=[]
            # This loop cannot see evaluation labels or perturbation schedule.
            for f in frames:
                path=raw/f['path'];digest=sha(path)
                if digest!=f['sha256']:raise ValueError('RGB hash mismatch')
                unique[digest]+=1
                encoded=base64.b64encode(path.read_bytes()).decode()
                prediction=sensor.observe(encoded,f['sim_time'],f['commanded_servo'])
                predictions.append(dict(**prediction,sim_time=f['sim_time'],image_sha256=digest))
                if rid!='r3':
                    q=GripMonitor().observe(encoded,f['sim_time'],f['commanded_servo'])
                    legacy.append(dict(sim_time=f['sim_time'],state='held' if q['ok'] else 'grip_lost',original=q))
            # Label access begins only after every prediction of this episode.
            labels=readlines(raw/'eval_only/labels.jsonl')
            for path in (raw/'result.json',raw/'bundle.json',raw/f'robots/{rid}/frames.jsonl',raw/'eval_only/labels.jsonl'):
                sources[str(path)]=sha(path)
            entry['candidate']=score(labels,predictions)
            entry['legacy']=score(labels,legacy) if legacy else None
            name=job['name']+'-'+case['id']
            with (output/(name+'.jsonl')).open('x') as f:
                for a,b in zip(labels,predictions):f.write(json.dumps(dict(prediction=b,evaluation_only=a))+'\n')
            episodes.append(entry)
    report=dict(schema='ugrp.s4grip2.offline.v1',research_result=False,split=split,detector=OPTION,
                freeze=freeze,episodes=episodes,sources_sha256=sources,total_frames=sum(unique.values()),unique_image_sha256=len(unique),
                model_calls=0,mac_physics_runs=0,mac_render_calls=0)
    report['by_robot']={r:aggregate([e for e in episodes if e['robot_id']==r]) for r in ('r1','r2','r3')}
    report['all']=aggregate(episodes)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def aggregate(episodes):
    valid=[e['candidate'] for e in episodes if e.get('candidate',{}).get('start_held')]
    loss=[e for e in valid if e['actual_loss']];hold=[e for e in valid if not e['actual_loss']]
    frames=Counter()
    for e in valid:frames.update(e['frame_counts'])
    return dict(planned=len(episodes),collected=sum(e['status']=='COLLECTED' for e in episodes),start_held=len(valid),
        true_positive_episodes=sum(e['detected'] for e in loss),actual_loss_episodes=len(loss),
        false_positive_hold_episodes=sum(e['false_alarm'] for e in hold),actual_hold_episodes=len(hold),
        premature_loss_alarms=sum(e['false_alarm'] for e in loss),
        delays_frames=[e['delay_frames'] for e in loss if e['detected']],delays_sim_s=[e['delay_sim_s'] for e in loss if e['detected']],frame_counts=dict(frames))


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True)
    p.add_argument('--split',choices=['explore','confirm'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    r=evaluate(a.raw_root,a.split,a.output);print(json.dumps(r['all']))


if __name__=='__main__':raise SystemExit(main())
