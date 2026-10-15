"""VM-only raw recount, candidate/event/frame funnels and failed own frames."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
from scripts.analyze_grasp_act_search24 import analyze,read
from scripts.analyze_grasp_act_search25 import funnel


def recount(root,out):
    summary=analyze(root,out);episodes=[];gate_totals=Counter()
    for raw in sorted(root.glob('diagnostic*/episode-*/raw')):
        data=read(raw/'result.json');res=json.loads(data);plan=json.loads(read(raw/'plan.json'))
        events=Counter();frames=Counter();terminal=Counter()
        for t in res.get('teachers',{}).values():
            for e in t.get('search22_log',[]):
                rows=e.get('candidates',[])
                events['candidate_events']+=1;events['nonempty']+=bool(rows)
                events['any_endpoint_pass']+=any(c['reason'] in ('endpoint_feasible','feasible') or c['reason'].startswith('connector') for c in rows)
                events['any_full_pass']+=any(c['reason']=='feasible' for c in rows)
                terminal.update(c['reason'] for c in rows)
        labels={r:[json.loads(x) for x in (read(raw/f'teacher-{r}.jsonl') or b'').splitlines()] for r in plan['roles']}
        for i,line in enumerate((read(raw/'eval-only.jsonl') or b'').splitlines()):
            e=json.loads(line)
            for rid,end in plan['roles'].items():
                frames['robot_input_frames']+=1
                if i>=len(labels[rid]):frames['interrupted_before_label']+=1;continue
                frames['label_written']+=1
                if labels[rid][i]['teacher_phase'] not in ('approach','align','ready'):continue
                frames['approach_align_ready']+=1
                if e['visibility'][rid]['visible_probes']<5:continue
                frames['assigned_band_visible']+=1
                if any(m['id']=='band_'+end for m in e.get('visible_measurements',{}).get(rid,[])):
                    frames['assigned_band_measurement_admitted']+=1
        for values,key,order in ((frames,'frame_funnel',['robot_input_frames','label_written','approach_align_ready','assigned_band_visible','assigned_band_measurement_admitted']),
                                 (events,'event_funnel',['candidate_events','nonempty','any_endpoint_pass','any_full_pass'])):
            previous=None;steps=[]
            for gate in order:
                passed=values[gate];steps.append({'gate':gate,'cumulative_pass':passed,
                                                 'rejected_here':None if previous is None else previous-passed});previous=passed
            if key=='frame_funnel':frame_steps=steps
            else:event_steps=steps
        row={'episode':raw.parent.name,'raw':str(raw),'raw_result_decoded_sha256':hashlib.sha256(data).hexdigest(),
             'candidate_populations':funnel(res),'frame_funnel':frame_steps,'event_funnel':event_steps,
             'incomplete_input_frames':frames['interrupted_before_label'],'review_jpeg_N':len(list((raw/'eval-own').glob('*/*.jpg'))),
             'status':res['status'],'cap_end':res.get('cap_end',False),'input_audit':res.get('input_audit')}
        episodes.append(row);gate_totals.update(terminal)
    report={'schema':'ugrp.search25.rejection_table.v2','source_sha':summary['source_sha'],
            'analysis_source_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'raw_root':str(root),'reproduce':f'.venv-sim/bin/python -m scripts.recount_grasp_act_search25 {root} --out {out}',
            'categories':summary['rejections'],'reason_counts':dict(gate_totals),'episodes':episodes,
            'scope':'raw rows; endpoint/full kept separate; budget unknown stage excluded from proven passes; frame/event populations are separate'}
    (out/'rejection_table.json').write_text(json.dumps(report,indent=2)+'\n')
    summary['rejection_table']=str(out/'rejection_table.json')
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();recount(a.root,a.out)
