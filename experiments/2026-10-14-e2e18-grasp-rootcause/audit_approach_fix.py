"""Compare fixed decisions to baseline on all 13 stored visible-input traces.

Offline only: stored applied commands advance VisibleWorld, never dynamics.
Requires the locally retrieved raw files and baseline Git object.
"""
import hashlib
import json
from pathlib import Path
from audit_approach_regression import CLASSES, ROOT, read, rows
from harness.grasp_act_visible_world import VisibleWorld
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher


def audit():
    output=[]
    for source in CLASSES:
        folder=Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-diagnostic-gcp-'+source)
        for raw in sorted(folder.glob('diagnostic/episode-*/raw')):
            plan=json.loads(read(raw/'plan.json'));ev=rows(raw/'eval-only.jsonl')
            result={'source':source,'episode':raw.parent.name,'seed':plan['seed'],'robots':{}}
            for rid,end in plan['roles'].items():
                labels=rows(raw/f'teacher-{rid}.jsonl');pwm=labels[0]['applied_command']['pwm']
                kwargs=dict(bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',teacher_search='search_body_scan_v2')
                old=CLASSES['23a2a113'](rid,end,pwm,**kwargs)
                new=VisibleOnlyGraspTeacher(rid,end,pwm,**kwargs,approach_goal_set='approach_goal_set_v1')
                model=VisibleWorld(rid,end);mismatches=[];first={};n=0
                for i,(e,label) in enumerate(zip(ev,labels)):
                    now=e['t'];w=model.observe(e['visible_measurements'][rid],now);commands=[]
                    for key,t in (('baseline',old),('fixed',new)):
                        before=t.phase;calls=t.planner_calls
                        t.prepare_signal(w,now)
                        cmd,_=t.step(w,now,permit_pick=label['teacher_phase'] in ('pick','complete'))
                        commands.append(cmd)
                        if key not in first and (t.planner_calls>calls or (before!='align' and t.phase=='align')):
                            first[key]={'sample':i,'goal':t._geometry(w)[3],'path':t.path.copy()}
                        t.remember_applied(label['applied_command'])
                    if commands[0]!=commands[1]:mismatches.append(i)
                    n+=1;model.issue(label['applied_command'])
                result['robots'][rid]={'samples':n,'command_mismatches':len(mismatches),'first_mismatch':next(iter(mismatches),None),'first_approach_equal':first.get('baseline')==first.get('fixed'),'fallback_selections':len(new.goal_set_log),'outcome':new.outcome,'input_decoded_sha256':hashlib.sha256(read(raw/f'teacher-{rid}.jsonl')).hexdigest()}
            output.append(result)
            print(source,result['episode'],result['robots'],flush=True)
    summary={'schema':'ugrp.approach_fix.offline.v1','scope':'13 saved visible-input/issued-command traces, exact same-host baseline vs fixed decisions; no physics/rendering/model calls. Counterfactual decisions after divergence are not physical results.','baseline_sha':'23a2a1137e3907073001ce079dd3294419fb5b1b','source_files':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('sim/grasp_act_teacher_v3.py','sim/grasp_act_goal_set.py')},'rows':output}
    (ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause/approach-fix-replay.json').write_text(json.dumps(summary,indent=2)+'\n')
    baseline=[r for r in output if r['source']=='23a2a113']
    assert len(baseline)==6
    assert all(d['command_mismatches']==0 and d['first_approach_equal'] for r in baseline for d in r['robots'].values())


if __name__=='__main__':audit()
