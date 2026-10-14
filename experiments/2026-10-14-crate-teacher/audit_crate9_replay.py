"""Recorded visible-input replay; never steps or renders physics."""
import json,sys,importlib.util
from pathlib import Path
from harness.grasp_act_visible_world import VisibleWorld
from sim.cargo_teacher_profile import CRATE
from sim.crate_antipodal import visible_grasp
from sim.crate_lift_pose import CARTESIAN_OPTION,ANTIPODAL_OPTION
exp=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('audit9',exp/'audit_crate9.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
spec=importlib.util.spec_from_file_location('audit8',exp/'audit_crate8.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
rows=[];cases=[]
for seed in range(77960,77970):
 p=a.RAW/f'crate-diag-{seed}-5644e3dd/raw';ev=a.lines(p/'eval-only.jsonl.zst');g=[x for x in ev if x['stage']=='grasp'];labs={r:a.lines(p/f'teacher-{r}.jsonl.zst')[:len(g)] for r in ('r1','r2')};result=json.loads(a.read(p/'result.json'));roles=result['prefix']['assigned'];models={r:VisibleWorld(r,e,profile=CRATE) for r,e in roles.items()};done=set()
 for i,row in enumerate(g):
  for rid in roles:
   world=models[rid].observe(row['visible_measurements'][rid],row['t']);models[rid].issue(labs[rid][i]['applied_command'])
   if labs[rid][i]['teacher_phase']=='pick' and rid not in done:
    done.add(rid);report=visible_grasp(world,rid,roles[rid]);small={k:world[k] for k in ('t','robots','beam','visibility','objects','walls')}
    cases.append({'seed':seed,'rid':rid,'end':roles[rid],'world':small,'valid':report['valid'],'input_source':a.ref(p/'eval-only.jsonl.zst'),'tick':i});print(seed,rid,report['valid'],report.get('samples',[{}])[-1])
 base,_,_=old.replay(g,labs,roles,CARTESIAN_OPTION);assert base['first_divergence'] is None,(seed,base)
 new,_,_=old.replay(g,labs,roles,ANTIPODAL_OPTION);rows.append({'seed':seed,'baseline':base,'candidate':new})
(exp/'crate9-replay.json').write_text(json.dumps({'runs':rows,'baseline_ticks':sum(x['baseline']['compared_robot_ticks'] for x in rows)},indent=2)+'\n')
Path('tests/fixtures/crate9-visible-picks.json').write_text(json.dumps({'source_sha':result['source_sha'],'scope':'visible inputs only; evaluation excluded','cases':cases},separators=(',',':'))+'\n')
print('replay',sum(x['baseline']['compared_robot_ticks'] for x in rows),[(r['seed'],r['candidate']['compared_robot_ticks'],r['candidate']['first_divergence'] is None) for r in rows])
