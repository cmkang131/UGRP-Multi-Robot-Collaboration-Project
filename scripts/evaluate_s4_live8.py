"""Offline release/reobservation/regrasp/fresh handshake evidence; never control inputs."""
import argparse
import json
import math
from pathlib import Path
from scripts.evaluate_s4_live5 import read,rows
from scripts.evaluate_s4_live6 import support
from scripts.evaluate_s4_live7 import evaluate as previous


def restart_metrics(states,contacts,truth,epochs,handshake,commands,inputs,origin):
    ss={round(r['t'],8):r['robots'] for r in states}
    cc={round(r['t'],8):support(r) for r in contacts}
    ee={round(r['t'],8):r['robots'] for r in epochs}
    samples=[]
    for row in truth:
        t=row['t'];key=round(t,8)
        samples.append((t,row['items']['beam_1'],cc.get(key,{}),ss.get(key,{}),ee.get(key,{})))
    lower_at={}
    for row in states:
        for rid,state in row['robots'].items():
            if state and state['state']=='lower':lower_at.setdefault(rid,row['t'])
    lower_start=max(lower_at.values()) if len(lower_at)==2 else None
    released=None
    for i,(t,c,touch,_,_) in enumerate(samples):
        if lower_start is None or t<lower_start:continue
        tail=[v for v in samples[i:] if v[0]<=t+.5+1e-8]
        if (tail and tail[-1][0]-t>=.5-1e-8 and all(v[2].get('floor') and not v[2].get('fingers') and v[1]['speed']<=.03 for v in tail)
                and max(v[1]['z'] for v in tail)-min(v[1]['z'] for v in tail)<=.005):
            released=t;break
    looks={}
    if released is not None:
        for rid in ('r1','r2'):
            looks[rid]=next((v for v in inputs.get(rid,[]) if v['sim_s']>released and
                v['phase'] in ('align','align_relook','align_relook_return','refix_look','refix_post_look','grasp_relook')
                and len(v.get('sha256',''))==64),None)
    reobserved=len(looks)==2 and all(looks.values())
    regrasp=None
    if reobserved:
        after=max(v['sim_s'] for v in looks.values())
        for t,c,touch,_,es in samples:
            if t>after and touch.get('bilateral') and c['z']>.06 and len(es)==2 and all(e['grip_epoch']>1 for e in es.values()):
                regrasp=t;break
    decisions=handshake.get('decisions',[]);fresh=[]
    if regrasp is not None:
        for p in handshake.get('permits',[]):
            if origin+p['at']<regrasp-1e-8:continue
            valid=all(any(d['robot_id']==r and d['call_id']==p[key][r] and d['accepted'] and
                d['action']['choice']==choice and d['action']['epoch']==p['epoch'] for d in decisions)
                for r in ('r1','r2') for key,choice in (('go_calls','go'),('ack_calls','ack_go')))
            moved=all(any(c['robot_id']==r and c.get('pair_permit')==p and c['t']>=origin+p['at']-1e-8 and
                c['action']['kind'] in ('drive','mecanum') and (c['action'].get('forward',0) or c['action'].get('left',0)) for c in commands) for r in ('r1','r2'))
            if valid and moved:fresh.append(p)
    last=None;start=None;distance=path=0.
    for t,c,touch,rs,es in samples:
        permit=next((p for p in reversed(fresh) if origin+p['at']<=t and len(es)==2 and
            all(e['grip_epoch']*1000+e['seg']==p['epoch'] for e in es.values())),None)
        loaded=bool(permit and touch.get('bilateral') and c['z']>.06 and len(rs)==2 and all(r and r['state']=='carry' for r in rs.values()))
        if not loaded:last=start=None;continue
        xy=(c['x'],c['y']);connected=last and t-last[0]<=.051 and permit['epoch']==last[2]
        if not connected:start=xy
        else:path+=math.dist(last[1],xy)
        distance=max(distance,math.dist(start,xy));last=(t,xy,permit['epoch'])
    return dict(release_start_t=released,reobserve=dict(n=int(reobserved),N=1,own_frame_receipts=looks),
        regrasp=dict(n=int(regrasp is not None),N=1,first_supported_t=regrasp),
        fresh_go_ack=dict(n=int(bool(fresh)),N=1,permits=fresh),
        fresh_go_ack_continue=dict(n=int(distance>=.020),N=1,additional_distance_m=distance,additional_path_m=path))


def evaluate(raw):
    value=previous(raw,'all_active_phase_rgb_heartbeat_v3')
    student=read(raw/'student_record.json')
    sessions=student['pair']['pair']
    inputs={r:[v for s in sessions for v in s['robots'].get(r,{}).get('inputs',[])] for r in ('r1','r2')}
    stage=read(raw/'stage-states.json');origin=stage[0]['t']-stage[0]['relative_sim_s']
    value.update(restart_metrics(rows(raw/'pair-controller-states.jsonl'),rows(raw/'eval_only/contacts.jsonl'),
        rows(raw/'eval_only/referee_truth.jsonl'),rows(raw/'pair-grip-epochs.jsonl'),read(raw/'pair-handshake.json'),
        read(raw/'decision-command-links.json'),inputs,origin),seed=read(raw/'bundle.json')['seed'],
        s3_failures=student['failures'])
    return value


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv)
    if a.output.exists():raise FileExistsError(a.output)
    result=[evaluate(a.raw_root/r['name']/'raw') for r in read(a.plan)['runs']]
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps([{k:r[k] for k in ('condition','seed','status','lowering','reobserve','regrasp','fresh_go_ack_continue','s3_failures')} for r in result]))


if __name__=='__main__':raise SystemExit(main())
