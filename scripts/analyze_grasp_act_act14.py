"""gcp1-only saved-output recount and six-frame own-camera evidence extraction."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil

import numpy as np
from PIL import Image, ImageDraw

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_json, read_rows, sha256, write_json
from harness.grasp_act_rollout import LiftScore
from scripts.grasp_act_training_guard import require_gcp


def existing(path):
    return path if path.exists() else path.with_suffix(path.suffix+'.zst')


def recount(rows):
    score=LiftScore(); first={};counts=Counter()
    for row in rows:
        counts['evaluation_frames']+=1
        score.add(row['t'],**{k:row[k] for k in ('clearance','tilt','forces','weld')})
        # Same frozen ACT11 boundaries as the evaluator; evaluation never feeds
        # commands. These are descriptive gates, not new adoption criteria.
        tests=[('approach',row['station_error_m']<=.08),
               ('alignment',row['station_error_m']<=.008 and row['yaw_error_rad']<=.04),
               ('grasp',min(row['forces'])>=.5),('lift_confirmation',score.record()['lift_success'])]
        prior=True
        for stage,ok in tests:
            if prior and ok:
                counts[stage]+=1;first.setdefault(stage,row['t'])
            prior=stage in first
    return {'counts':dict(counts),'first_pass_sim_t':first,**score.record(),
            'cumulative_run_pass':{s:int(s in first) for s in ('approach','alignment','grasp','lift_confirmation')}}


def analyze(root,output):
    raw=root/'raw' if (root/'raw').exists() else root
    summary=read_json(existing(raw/'summary.json'))
    output.mkdir(parents=True,exist_ok=False)
    records=read_rows(existing(raw/'student-inputs.jsonl')) if existing(raw/'student-inputs.jsonl').exists() else []
    for row in records:c.validate_observation(row)
    evaluations=read_rows(existing(raw/'eval-only.jsonl')) if existing(raw/'eval-only.jsonl').exists() else []
    funnel=recount(evaluations)
    stages=('approach','alignment','grasp','lift_confirmation')
    failed=next((s for s in stages if not funnel['cumulative_run_pass'][s]),None)
    rejection=None if failed is None else {'category':failed+'_not_passed','blocking_object':'none_observed',
        'target_object':read_json(raw/'plan.json')['item_id'],
        'minimum_gap_m':min((r['target_finger_min_gap_m'] for r in evaluations),default=None),
        'scope':'target finger gap; no collision cause inferred'}
    frames=[]; tiles=[]
    if records:
        for j,index in enumerate(np.linspace(0,len(records)-1,min(6,len(records)),dtype=int)):
            row=records[index]; ref=row['rgb'][-1]; source=raw/ref['path']
            if sha256(source)!=ref['sha256']:raise ValueError('own RGB hash mismatch')
            target=output/f'frame-{j:02d}.jpg';shutil.copyfile(source,target)
            frames.append({'t':row['t'],'path':str(target),'source':str(source),'sha256':ref['sha256']})
            with Image.open(target) as im:tile=im.convert('RGB').resize((320,240))
            ImageDraw.Draw(tile).text((4,4),f'{root.name} t={row["t"]:.1f}',fill='white',stroke_width=1,stroke_fill='black');tiles.append(tile)
        montage=Image.new('RGB',(960,480))
        for j,tile in enumerate(tiles):montage.paste(tile,((j%3)*320,(j//3)*240))
        montage.save(output/'montage.jpg')
    artifacts={str(p.relative_to(raw)):sha256(p) for p in raw.rglob('*') if p.is_file()}
    report={'run':root.name,'raw':str(raw),'summary':summary,'failure_stage':failed,
        'cap_end':summary.get('cap_end'),'funnel':funnel,'rejection':rejection,'own_frames':frames,
        'strict_input_rows':len(records),'top_frames':len(list(raw.rglob('*top*'))),
        'raw_sha256':artifacts,'reproduce':'python -m scripts.analyze_grasp_act_act14 --root '+str(root)+' --output NEW_DIR',
        'independent_haiku_recount':'pending; automated evaluator only'}
    write_json(output/'analysis.json',report)
    write_json(output/'funnel.json',{'counts':funnel,'rejection':rejection,'raw':str(raw),
        'reproduce':report['reproduce'],'raw_sha256':{k:v for k,v in artifacts.items() if 'eval-only' in k or 'commands' in k or 'student-inputs' in k}})
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path);a=p.parse_args();require_gcp(training=False)
    result=analyze(a.root,a.output or a.root.parent/(a.root.name+'-analysis'))
    print(json.dumps({k:result[k] for k in ('run','failure_stage','cap_end','strict_input_rows')}))


if __name__=='__main__':main()
