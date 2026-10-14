"""Offline comparison of saved GCP visible inputs; no dynamics or rendering.

Run from the project root with the existing Python environment. Source commands
are checked with 1e-12 tolerance for Mac/GCP floating-point differences. The two
counterfactual controllers are compared on the same host with exact equality.
Recorded commands, not counterfactual commands, advance the observed world;
after a divergence these are open-loop decisions, not predicted physical runs.
"""
import json, subprocess, pathlib, sys, hashlib, math, types
from copy import deepcopy
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness.grasp_act_visible_world import VisibleWorld
from sim.grasp_act_visible_route import constraints,free

def read(p):
    if p.exists():return p.read_bytes()
    return subprocess.check_output(['zstd','-dc',str(p)+'.zst'])
def rows(p):return [json.loads(s) for s in read(p).splitlines()]
def load(ref):
    ns={'__name__':'offline_'+ref}
    source=subprocess.check_output(['git','show',ref+':sim/grasp_act_teacher_v3.py'],cwd=ROOT).decode()
    if ref=='a3f3be78':
        name='offline_grasp_goals_a3f3be78'
        goals=types.ModuleType(name)
        exec(subprocess.check_output(['git','show',ref+':sim/grasp_act_goal_set.py'],cwd=ROOT),goals.__dict__)
        sys.modules[name]=goals
        source=source.replace('from sim.grasp_act_goal_set import',f'from {name} import')
    exec(source,ns)
    return ns['VisibleOnlyGraspTeacher']
CLASSES={r:load(r) for r in ('23a2a113','a3f3be78')}

def state(t,w,cmd):
    geometry=t._geometry(w) if w['beam'] else None
    return {'goal':geometry[3] if geometry else None,'heading':geometry[2] if geometry else None,
            'phase':t.phase,'folded_ready':t.folded_ready,'choice':getattr(t,'approach_choice',(0.,.203)),
            'path':deepcopy(t.path),'path_goal':t.path_goal,'planner_calls':t.planner_calls,
            'outcome':t.outcome,'command':cmd}

def audit():
    result=[];fixtures=[]
    for source in CLASSES:
      folder=pathlib.Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs/grasp-search-diagnostic-gcp-'+source)
      for raw in sorted(folder.glob('diagnostic/episode-*/raw')):
        plan=json.loads(read(raw/'plan.json'));ev=rows(raw/'eval-only.jsonl')
        record={'source':source,'episode':raw.parent.name,'seed':plan['seed'],'raw':str(raw),'robots':{},'roles':plan['roles'],
                'source_sha':(folder/'SOURCE_SHA').read_text().strip(),
                'plan_sha256':hashlib.sha256(read(raw/'plan.json')).hexdigest(),
                'eval_decoded_sha256':hashlib.sha256(read(raw/'eval-only.jsonl')).hexdigest()}
        for rid,end in plan['roles'].items():
          labels=rows(raw/f'teacher-{rid}.jsonl');pwm=labels[0]['applied_command']['pwm']
          kwargs=dict(bounds=(-20,20,-20,20),teacher_stability='align_relook_v1',teacher_search='search_body_scan_v2')
          ts={r:c(rid,end,pwm,**kwargs,**({'approach_goal_set':'approach_goal_set_v1'} if r=='a3f3be78' else {})) for r,c in CLASSES.items()}
          model=VisibleWorld(rid,end);out={'first_approach':{},'first_difference':None,'input_sha256':hashlib.sha256(read(raw/f'teacher-{rid}.jsonl')).hexdigest(),'source_command_mismatches':0,'source_command_material_mismatches':0,'source_command_max_abs_error':0.}
          for i,(e,label) in enumerate(zip(ev,labels)):
            now=e['t'];w=model.observe(e['visible_measurements'][rid],now)
            # Stored GO permission is used solely to replay this issued trace.
            permit=label['teacher_phase'] in ('pick','complete')
            states={}
            for r,t in ts.items():
              before=t.phase;calls=t.planner_calls
              t.prepare_signal(w,now)
              cmd,done=t.step(w,now,permit_pick=permit)
              states[r]=state(t,w,cmd)
              if r==source and cmd!=label['clean_teacher_command']:
                out['source_command_mismatches']+=1
                expected=label['clean_teacher_command']
                err=max(abs(a-b) for key in ('wheels','duration_s') for a,b in zip(cmd[key],expected[key]))
                out['source_command_max_abs_error']=max(out['source_command_max_abs_error'],err)
                out['source_command_material_mismatches']+=int(err>1e-12 or cmd['pwm']!=expected['pwm'] or cmd['t']!=expected['t'])
                if out['source_command_mismatches']==1:out['first_source_mismatch']={'sample':i,'command':cmd,'expected':label['clean_teacher_command']}
              t.remember_applied(label['applied_command'])
              if r not in out['first_approach'] and (t.planner_calls>calls or (before!='align' and t.phase=='align')):
                out['first_approach'][r]={'sample':i,'t':now,**states[r]}
                if r=='23a2a113':
                  fixtures.append({'source':source,'episode':raw.parent.name,'seed':plan['seed'],'rid':rid,'end':end,
                                   'sample':i,'world':deepcopy(w),'pwm':deepcopy(t.sink.pwm),
                                   'expected_goal':states[r]['goal']})
            if out['first_difference'] is None and states['23a2a113']['command']!=states['a3f3be78']['command']:
              out['first_difference']={'sample':i,'t':now,'states':states,'world':deepcopy(w)}
            model.issue(label['applied_command'])
          record['robots'][rid]=out
        result.append(record)
        print(source,record['episode'],plan['seed'],[(r,[(v,x['sample'],x['choice'],len(x['path'])) for v,x in d['first_approach'].items()],None if d['first_difference'] is None else d['first_difference']['sample'],d['source_command_mismatches']) for r,d in record['robots'].items()],flush=True)
    assert all(d['source_command_material_mismatches']==0 for row in result for d in row['robots'].values())
    out=ROOT/'experiments/2026-10-14-e2e18-grasp-rootcause'
    (out/'approach-regression-replay.json').write_text(json.dumps({'scope':'Recorded visible measurements and issued commands only; counterfactual open-loop decisions, no physics/rendering','sources':list(CLASSES),'rows':result},indent=2)+'\n')
    (out/'approach-regression-starts.json').write_text(json.dumps(fixtures,indent=2)+'\n')
if __name__=='__main__':audit()
