"""Offline raw evaluation; no inputs flow back to the controller."""
import argparse
import json
import math
from pathlib import Path
from scripts.evaluate_s4_live5 import evaluate as old_evaluate, read, rows
from scripts.evaluate_s4_live6 import physical_metrics, support
from scripts.run_s4_pair_live7 import ROOT, RECORD


def distances(states, contacts, truth):
    states={round(r['t'],8):r['robots'] for r in states}
    contacts={round(r['t'],8):support(r) for r in contacts}
    lengths={};excursions={};last=None;chain_start=None
    for row in truth:
        t=row['t'];key=round(t,8);c=row['items']['beam_1'];rs=states.get(key,{})
        pair=[rs.get(r) for r in ('r1','r2')]
        loaded=(all(r and r['state']=='carry' for r in pair)
            and pair[0]['seg']==pair[1]['seg'] and contacts.get(key,{}).get('bilateral') and c['z']>.06)
        if not loaded:last=None;chain_start=None;continue
        seg=pair[0]['seg'];xy=(c['x'],c['y'])
        connected=bool(last and seg==last[1] and t-last[0]<=.051)
        if not connected:chain_start=xy
        excursions[seg]=max(excursions.get(seg,0.),math.dist(chain_start,xy))
        lengths.setdefault(seg,0.)
        if connected:lengths[seg]+=math.dist(last[2],xy)
        last=(t,seg,xy)
    return dict(contact_supported_path_m=sum(lengths.values()),
        continued_transport_path_m=sum(v for k,v in lengths.items() if k>0),
        continued_transport_distance_m=max((v for k,v in excursions.items() if k>0),default=0.),
        segment_path_m=lengths,segment_excursion_m=excursions,
        definition='carry state on both robots, same segment, bilateral four-finger contact, COM>.06m; no gaps bridged')


def evaluate(raw,variant):
    value=old_evaluate(raw);states=rows(raw/'pair-controller-states.jsonl')
    contacts=rows(raw/'eval_only/contacts.jsonl');truth=rows(raw/'eval_only/referee_truth.jsonl')
    routes=list(read(raw/'pair-route.json').values()) if (raw/'pair-route.json').exists() else []
    route=routes[0]['route'] if len(routes)==2 else None
    if route and routes[1]['route']!=route:raise ValueError('route mismatch')
    h=read(raw/'pair-handshake.json');dispatch=read(raw/'llm/dispatch.json')
    released={d['call_id']:d for d in dispatch};accepted=[r for r in h.get('renewals',[]) if r['accepted']]
    for row in accepted:
        d=released[row['call_id']]
        if not(d['actor']==row['robot_id'] and d['action']==row['action']
                and d.get('carry_lease_renewal')==row):raise ValueError('unreleased heartbeat')
    distance=distances(states,contacts,truth)
    physical=physical_metrics(states,contacts,truth,route)
    physical['continue_transport']['n']=int(distance['continued_transport_distance_m']>=.020)
    value.update(variant=variant,**physical,
        distance=distance,heartbeats=dict(n=len(accepted),
            by_phase={phase:sum(r.get('own_executor_phase')==phase for r in accepted)
                for phase in sorted({r.get('own_executor_phase') or 'unspecified' for r in accepted})},
            rejected_commands_with_live_heartbeat=sum(not r['command_accepted'] for r in accepted)),
        renewal_rejections=[r for r in h.get('renewals',[]) if not r['accepted']])
    return value


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv)
    if a.output.exists():raise FileExistsError(a.output)
    results=[evaluate(a.raw_root/r['name']/'raw',r['variant']) for r in read(ROOT/RECORD/'plan.json')['runs']]
    a.output.write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps([{k:r[k] for k in ('condition','variant','status','continue_transport','goal_transport','lowering','distance','heartbeats')} for r in results]))


if __name__=='__main__':raise SystemExit(main())
