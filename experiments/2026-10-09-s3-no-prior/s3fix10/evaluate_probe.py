"""Oracle-side, post-run evaluation only; never imported by control."""
import argparse,bisect,hashlib,json,subprocess,sys
from pathlib import Path
import numpy as np

p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
old=Path(__file__).parents[1]/'s3fix8'
subprocess.run([sys.executable,str(old/'evaluate_probe.py'),'--raw',str(a.raw),'--output',str(a.output/'basic')],check=True)
read=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(s) for s in p.read_text().splitlines()]
r=read(a.output/'basic/report.json');raw=read(a.raw/'result.json');b=read(a.raw/'bundle.json')
r.update(host=raw['host'],alignment_entry=raw['alignment_entry'],stage_scope=raw['stage_scope'],
    physical_stop=raw.get('physical_stop'),comparison_scope=b['comparison_scope'])
r['alignment_entry_audit']=read(a.raw/'alignment-entry.json')
if raw['status']=='PHYSICAL_STOP':r['all_stage_pass']=False;r['exit_reason']='physical_stop'
states=read(a.raw/'stage-states.json')
for rid,value in r['robots'].items():
 selected=[(s['t'],s['robots'][rid]['state']) for s in states if rid in s['robots']]
 for name in ('lift','carry','lower','released','done'):
  value[name]=next((t for t,state in selected if state==name),None)
if raw['case']=='cyan':
 q=rows(a.raw/'eval_only/r3/physical-supervisor.jsonl')
 truth=rows(a.raw/'eval_only/referee_truth.jsonl')
 contact={x['t']:x for x in q}
 item=next(k for k,v in truth[0]['items'].items() if v['kind']=='cyan')
 valid=[(x['t'],x['items'][item]) for x in truth if x['t'] in contact and all(contact[x['t']]['finger_contacts']) and contact[x['t']]['cyan_z_m']>.06]
 positions=np.array([[v['x'],v['y']] for _,v in valid])
 r['cyan_physics']=dict(lift_threshold_m=.06,lift_with_both_fingers_samples=len(valid),
    first_contact_lift_t=valid[0][0] if valid else None,
    max_xy_displacement_while_contact_lifted_m=float(np.linalg.norm(positions-positions[0],axis=1).max()) if valid else 0.,
    max_com_z_m=max(x['cyan_z_m'] for x in q),
    qualification='actual two-finger contact and lift; continuous cargo displacement is reported, no new success threshold')
 # Authored destination is evaluation only; stage restoration is not an E2E success.
 from harness.zone_s3_recovery_contract import inputs,hp
 from harness.zone_study_referee import Referee
 from harness.zone_evidence_key import key_for
 key=key_for(dict(run_id='oracle-stage-'+b['source_sha'][:12],trial_id='oracle-stage-cyan',condition='no_comm',seed=b['seed'],attempt=1))
 referee=Referee(inputs()[2]['orders'],hp.resolve(b['map_id'])[0],evidence_key=key)
 for x in truth:referee.observe(x['t'],x['items'])
 r['stage_destination_referee']=referee.record()
subprocess.run([sys.executable,str(old/'analyze_probe_frames.py'),'--raw',str(a.raw),'--output',str(a.output/'frames')],check=True)
r['frame_analysis']=read(a.output/'frames/summary.json')
(a.output/'report.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:r[k] for k in ('host','status','all_stage_pass','exit_reason','wall_s','sim_s')}))
