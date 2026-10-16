"""Offline restart + complete route judgment; truth never enters control."""
import argparse
import json
import math
from pathlib import Path
from scripts.evaluate_s4_live8 import evaluate as previous
from scripts.evaluate_s4_live5 import read,rows
from scripts.evaluate_s4_live6 import support


def goal_metrics(route, states, epochs, truth, contacts, handshake):
    cc={round(r['t'],8):support(r) for r in contacts}
    ss={round(r['t'],8):r['robots'] for r in states}
    ee={round(r['t'],8):r['robots'] for r in epochs}
    held_segments=set();final=None;goal_distance=None;excursions={};last=None;start=None
    for row in truth:
        t=row['t'];key=round(t,8);beam=row['items']['beam_1'];touch=cc.get(key,{})
        rs=ss.get(key,{});es=ee.get(key,{})
        rs={r:rs.get(r) or es.get(r) for r in ('r1','r2')}
        if len(rs)!=2 or len(es)!=2:continue
        segs={v['seg'] for v in es.values()}
        if len(segs)!=1:continue
        seg=next(iter(segs))
        permitted=any(p['epoch']==es['r1']['grip_epoch']*1000+seg==es['r2']['grip_epoch']*1000+seg
            for p in handshake['permits'])
        if touch.get('bilateral') and beam['z']>.06 and permitted and all(v and v['state']=='carry' for v in rs.values()):
            xy=(beam['x'],beam['y'])
            if not last or seg!=last[1] or t-last[0]>.051:start=xy
            excursions[seg]=max(excursions.get(seg,0.),math.dist(start,xy))
            if excursions[seg]>=.020:held_segments.add(seg)
            last=(t,seg)
        else:last=start=None
        goal_distance=math.dist([beam['x'],beam['y']],route[-1])
        if seg!=len(route)-2 or not all(v and v['state'] in ('released','done') for v in rs.values()):continue
        tail=[v for v in truth if t<=v['t']<=t+.5+1e-8]
        if (goal_distance<=.020 and tail and tail[-1]['t']-t>=.5-1e-8
                and all(cc.get(round(v['t'],8),{}).get('floor')
                    and not cc.get(round(v['t'],8),{}).get('fingers')
                    and v['items']['beam_1']['speed']<=.03 for v in tail)
                and max(v['items']['beam_1']['z'] for v in tail)-min(v['items']['beam_1']['z'] for v in tail)<=.005):
            final=t;break
    return dict(n=int(final is not None and held_segments==set(range(len(route)-1))),N=1,
        planned_segments=len(route)-1,held_segments=sorted(held_segments),final_floor_release_t=final,
        contact_supported_segment_excursion_m=excursions,
        goal_distance_m=goal_distance,scope='existing synthetic beam alignment entrance to goal; no navigation/E2E study success')


def evaluate(raw):
    value=previous(raw)
    result=read(raw/'result.json');routes=read(raw/'pair-route.json') if (raw/'pair-route.json').exists() else {}
    if set(routes)=={'r1','r2'} and routes['r1']['route']==routes['r2']['route']:
        value['goal_route']=goal_metrics(routes['r1']['route'],rows(raw/'pair-controller-states.jsonl'),
            rows(raw/'pair-grip-epochs.jsonl'),rows(raw/'eval_only/referee_truth.jsonl'),
            rows(raw/'eval_only/contacts.jsonl'),read(raw/'pair-handshake.json'))
    else:value['goal_route']=dict(n=0,N=1,reason='no matching admitted routes')
    value.update(reinspection=read(raw/'reinspection.json'),go_ack_retries=read(raw/'go-ack-retries.json'),
        terminal_settlement=result.get('terminal_settlement'),channel=read(raw/'llm/channel.json'),
        outstanding=sum(r['status']=='outstanding' for r in read(raw/'llm/scheduler_ledger.json').values()))
    return value


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv)
    if a.output.exists():raise FileExistsError(a.output)
    values=[evaluate(a.raw_root/r['name']/'raw') for r in read(a.plan)['runs']]
    a.output.write_text(json.dumps(values,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:dict(n=sum(v[k]['n'] for v in values),N=len(values)) for k in
        ('reobserve','regrasp','fresh_go_ack','fresh_go_ack_continue','goal_route')}))


if __name__=='__main__':raise SystemExit(main())
