"""Post-run evaluation only; no controller imports or feedback."""
import argparse,bisect,collections,hashlib,importlib.util,json,math
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();R=a.raw;O=a.output;O.mkdir(parents=True,exist_ok=False)
def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result=read(R/'result.json');bundle=read(R/'bundle.json');student=read(R/'student_record.json');states=read(R/'stage-states.json');pair=student.get('pair',{})
report=dict(raw=str(R),source_sha=result['source_sha'],case=result['case'],option=result['servo_option'],status=result['status'],
    wall_s=result['wall_s'],sim_s=result.get('check_sim_s'),actual_stop=result.get('failure'),robots={},thresholds_changed=False,
    setup=read(R/'eval_only/stage-setup.json'),gt_use='post-run evaluation only; setup is separately labelled reconstruction',
    input_hashes={n:sha(R/n) for n in ('result.json','bundle.json','stage-states.json','student_record.json')})
for rid in (('r1','r2') if result['case']=='pair' else ('r3',)):
    selected=[(r['t'],r['robots'][rid]) for r in states if rid in r['robots']]
    timeline=[]
    for t,v in selected:
        key=(v['state'],v.get('blind_phase'))
        if not timeline or key!=(timeline[-1]['state'],timeline[-1].get('blind_phase')):timeline.append(dict(t=t,**v))
    first=lambda f:next((t for t,v in selected if f(v)),None)
    hover=first(lambda v:v['state']=='hover' or v.get('blind_phase')=='hover')
    descent=first(lambda v:v['state']=='blind_descent' or v.get('blind_phase')=='descend')
    close=first(lambda v:v['servo'].get('1',v['servo'].get(1,2000))<=1600)
    cmds=rows(R/f'robots/{rid}/commands.jsonl');moving=[c for c in cmds if c['kind']=='mecanum' and any(c.get(k,0) for k in ('forward','left','turn'))]
    failures=[v['failure'] for t,v in selected if v.get('failure')]
    events=[e for session in pair.get('pair',[]) for e in session.get('robots',{}).get(rid,{}).get('events',[])]
    report['robots'][rid]=dict(hover=hover,descent=descent,close=close,timeline=timeline,
        stage_pass=all(t is not None for t in (hover,descent,close)) and hover<=descent<=close and not failures,
        failure=failures[-1] if failures else 'probe_horizon' if close is None else None,
        moving_commands=len(moving),short_commands=sum(c['duration_s']<.1 for c in moving),
        mixed_commands=sum(sum(c.get(k,0)!=0 for k in ('forward','left','turn'))>1 for c in moving),
        beam_observations=sum(e.get('event')=='beam_obs' for e in events),
        beam_visible=sum(e.get('event')=='beam_obs' and e.get('visible',False) for e in events),
        last_beam=next((e for e in reversed(events) if e.get('event')=='beam_obs'),None),
        local_would_stop=student['localizers'][rid].get('dev_light_would_stop',{}))
report['pair_would_stop']=pair.get('s3_dev_light',{})
truth=rows(R/'eval_only/referee_truth.jsonl');report['cargo']={item:dict(held_samples=sum(t['items'][item]['held'] for t in truth),
    max_com_z_m=max(t['items'][item]['z'] for t in truth),samples=len(truth)) for item in truth[0]['items']}
report['frame_command_mismatches']={rid:sum(f['actuator_state']['servo_pulses']!=f['commanded_servo'] for f in rows(R/f'robots/{rid}/frames.jsonl')) for rid in ('r1','r2','r3')}
report['input_contract_valid']=not any(report['frame_command_mismatches'].values())
contacts=rows(R/'eval_only/contacts.jsonl')
report['finger_contacts_eval_only']={}
for rid,rob in report['robots'].items():
    item='cargo_cyan_1' if rid=='r3' else 'cargo_beam_1'
    counts=dict(left=0,right=0,both=0,both_after_close=0,last_both=False)
    for row in contacts:
        touched={c[k] for c in row['contacts'] if item in c['geom1'] or item in c['geom2'] for k in ('geom1','geom2')}
        left=rid+'__left_finger' in touched;right=rid+'__right_finger' in touched
        counts['left']+=int(left);counts['right']+=int(right);counts['both']+=int(left and right)
        counts['both_after_close']+=int(left and right and rob['close'] is not None and row['t']>=rob['close'])
        counts['last_both']=left and right
    report['finger_contacts_eval_only'][rid]=counts
report['exit_reason']='host_error' if result['status']=='HOST_ERROR' else ('controller_failure' if any(r['failure'] not in (None,'probe_horizon') for r in report['robots'].values()) else 'commanded_close_settled' if (result.get('close_settle_s') or 0)>=1.-1e-8 else 'probe_horizon')
report['all_stage_pass']=report['input_contract_valid'] and bool(report['robots']) and all(r['stage_pass'] for r in report['robots'].values()) and result['status']!='HOST_ERROR'
manifest=read(R/'artifacts.sha256.json');report['artifact_verification']=dict(files=len(manifest),all_hashes_match=all(sha(R/f)==h for f,h in manifest.items()),manifest_sha256=sha(R/'artifacts.sha256.json'))
save(O/'report.json',report)
print(json.dumps({k:v for k,v in report.items() if k in ('status','wall_s','sim_s','all_stage_pass','actual_stop','cargo')}))
print(json.dumps(report['robots'],ensure_ascii=False))
