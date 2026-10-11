"""Saved-raw metadata/qpos analysis only, no physics step, no renderer/control."""
import argparse,json,math,hashlib,platform,xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np


def read(p):return json.loads(p.read_text())
def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def diagnose(raw):
    manifest=read(raw/'artifacts.sha256.json')
    wanted=['scene.xml','stage-states.json','robots/r1/commands.jsonl','robots/r2/commands.jsonl',
            'eval_only/r1/trajectory.jsonl','eval_only/r2/trajectory.jsonl',
            'eval_only/r1/render_camera.jsonl','eval_only/contacts.jsonl','eval_only/referee_truth.jsonl']
    for p in wanted:
        if digest(raw/p)!=manifest[p]:raise ValueError('raw changed '+p)
    states=read(raw/'stage-states.json');start=next((r['t'] for r in states if all(r['robots'][x]['state']=='carry' for x in ('r1','r2'))),None)
    if start is None:return dict(case=raw.parent.name,carry_entry=None)
    end=next(r['t'] for r in states if r['t']>start and any(r['robots'][x]['state']!='carry' for x in ('r1','r2')))
    tree=ET.fromstring((raw/'scene.xml').read_text());adr={};index=0
    for j in tree.find('worldbody').iter():
        if j.tag not in ('joint','freejoint'):continue
        adr[j.get('name')]=index
        index+=7 if j.tag=='freejoint' or j.get('type')=='free' else 4 if j.get('type')=='ball' else 1
    cameras=[r for r in rows(raw/'eval_only/r1/render_camera.jsonl') if start<=r['t']<=end]
    contacts=[r for r in rows(raw/'eval_only/contacts.jsonl') if start<=r['t']<=end]
    truth=[r['items']['beam_1'] for r in rows(raw/'eval_only/referee_truth.jsonl') if start<=r['t']<=end]
    result=dict(case=raw.parent.name,source_sha=read(raw/'bundle.json')['source_sha'],host='oracle-x86',
        carry_entry=start,carry_exit=end,duration_s=end-start,robots={},
        beam_excursion_m=max(math.dist((t['x'],t['y']),(truth[0]['x'],truth[0]['y'])) for t in truth),
        beam_min_z_m=min(t['z'] for t in truth),force_n=None,
        force_limitation='v162 stored geom pairs/distances but no constraint force/qvel/ctrl; exact force cannot be reconstructed from qpos alone',
        feedback_to_controller=False)
    cmd={}
    for rid in ('r1','r2'):
        cmd[rid]=[r for r in rows(raw/f'robots/{rid}/commands.jsonl') if start<=r['t']<end and r['kind'] in ('mecanum','drive')]
        moving=[r for r in cmd[rid] if any(r.get(k,0) for k in ('forward','left','turn'))]
        traj=[r for r in rows(raw/f'eval_only/{rid}/trajectory.jsonl') if start<=r['t']<=end]
        path=sum(math.dist(a['robot_xyz_m'][:2],b['robot_xyz_m'][:2]) for a,b in zip(traj,traj[1:]))
        q=np.array([[r['joint_qpos'][adr[f'{rid}__wheel_{w}_joint']] for w in ('fl','fr','rl','rr')] for r in cameras])
        dq=np.abs(np.diff(q,axis=0));wheel_path=.0325*float(dq.sum(axis=0).mean())
        touched=[]
        for r in contacts:
            names={c[k] for c in r['contacts'] if 'cargo_beam_1' in c['geom1'] or 'cargo_beam_1' in c['geom2'] for k in ('geom1','geom2')}
            touched.append(all(rid+'__'+s+'_finger' in names for s in ('left','right')))
        result['robots'][rid]=dict(commands=len(cmd[rid]),neutral=len(cmd[rid])-len(moving),moving=len(moving),
            unique_nonzero=list({(r.get('forward',0),r.get('left',0),r.get('turn',0),r['duration_s']) for r in moving}),
            first_motion=None if not moving else moving[0]['t'],last_motion=None if not moving else moving[-1]['t'],
            chassis_path_m=path,chassis_excursion_m=max(math.dist(r['robot_xyz_m'][:2],traj[0]['robot_xyz_m'][:2]) for r in traj),
            wheel_surface_path_proxy_m=wheel_path,wheel_total_abs_rad=dq.sum(axis=0).tolist(),
            slip_proxy=1-path/wheel_path if wheel_path>1e-5 else None,
            slip_scope='absolute wheel rim path proxy, includes passive tiny settling; not a contact-point slip ratio',
            both_fingers_samples=sum(touched),contact_samples=len(touched))
    result['matched_command_ticks']=len(cmd['r1'])==len(cmd['r2']) and all(abs(a['t']-b['t'])<1e-8 and all(abs(a.get(k,0)+b.get(k,0))<1e-8 for k in ('forward','left','turn')) for a,b in zip(cmd['r1'],cmd['r2']))
    result['one_sided_wait_ticks']=sum(bool(any(a.get(k,0) for k in ('forward','left','turn')))!=bool(any(b.get(k,0) for k in ('forward','left','turn'))) for a,b in zip(cmd['r1'],cmd['r2']))
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('x86 saved replay only')
    a.output.mkdir(parents=True,exist_ok=False)
    result=[diagnose(a.cohort/f's3fix16-pair-c{i}-r1/raw') for i in range(6)]
    (a.output/'summary.json').write_text(json.dumps(dict(host='oracle-x86',physics_steps=0,runs=result),indent=2,allow_nan=False)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
