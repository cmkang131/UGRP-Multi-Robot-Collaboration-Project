"""Offline only: frozen criteria, command/response causality and physics labels."""
import argparse
import json
import math
from pathlib import Path
from scripts.evaluate_s4_live5 import evaluate as old_evaluate, read, rows, sha


def support(row):
    contacts = [c for c in row['contacts'] if any('cargo_beam_1' in c[k] for k in ('geom1','geom2'))]
    geoms = {c[k] for c in contacts for k in ('geom1','geom2')}
    fingers = {r+'__'+side+'_finger' for r in ('r1','r2') for side in ('left','right')}
    return dict(bilateral=fingers.issubset(geoms), fingers=bool(fingers & geoms), floor='floor' in geoms)


def physical_metrics(states, contacts, truth, route):
    states = {round(r['t'],8):r['robots'] for r in states}
    contacts = {round(r['t'],8):support(r) for r in contacts}
    points = {}; lower_at = {}; goal_errors = []; samples = []
    for row in truth:
        t = row['t']; robots = states.get(round(t,8),{})
        cargo = row['items']['beam_1']; touch = contacts.get(round(t,8),dict(bilateral=False,fingers=False,floor=False))
        for rid, state in robots.items():
            if state and state['state'] == 'lower':lower_at.setdefault(rid,t)
        vals = [robots.get(r) for r in ('r1','r2')]
        loaded = (all(v and v['state']=='carry' for v in vals)
            and len({v['seg'] for v in vals if v})==1 and touch['bilateral'] and cargo['z']>.06)
        if loaded:
            points.setdefault(vals[0]['seg'],[]).append((t,cargo['x'],cargo['y']))
            if route:goal_errors.append(math.dist((cargo['x'],cargo['y']),route[-1]))
        samples.append((t,cargo,touch))
    excursions = {seg:max((math.dist(p[1:],ps[0][1:]) for p in ps),default=0.) for seg,ps in points.items()}
    later = {seg:value for seg,value in excursions.items() if seg>0}
    lower_start = max(lower_at.values()) if len(lower_at)==2 else None
    drop_at = []; free_z = None; prev = None
    relevant = [r for r in samples if lower_start is not None and r[0]>=lower_start]
    for t,cargo,touch in relevant:
        if not touch['fingers'] and not touch['floor']:
            if free_z is None:free_z=prev[1]['z'] if prev else cargo['z']
            vz=(cargo['z']-prev[1]['z'])/(t-prev[0]) if prev and t>prev[0] else 0.
            if free_z-cargo['z']>=.020 and vz<-.10:drop_at.append(t)
        else:free_z=None
        prev=(t,cargo,touch)
    # Require a complete half-second of floor support without any fingers.
    stable=False
    for i,(t,cargo,touch) in enumerate(relevant):
        tail=[r for r in relevant[i:] if r[0]<=t+.5+1e-8]
        if (tail and tail[-1][0]-t>=.5-1e-8 and all(r[2]['floor'] and not r[2]['fingers']
                and r[1]['speed']<=.03 for r in tail)
                and max(r[1]['z'] for r in tail)-min(r[1]['z'] for r in tail)<=.005):
            stable=True;break
    return dict(continue_transport=dict(n=int(any(d>=.020 for d in later.values())),N=1,
                    contact_supported_segment_excursion_m=excursions),
        goal_transport=dict(n=int(bool(goal_errors) and min(goal_errors)<=.020),N=1,
            goal_xy_m=None if not route else route[-1], minimum_error_m=min(goal_errors,default=None)),
        lowering=dict(n=int(stable and not drop_at),N=1,entered=int(lower_start is not None),
            stable_floor_placement=stable,drop=bool(drop_at),drop_first_t=next(iter(drop_at),None)))


def evaluate(raw, variant):
    value=old_evaluate(raw)
    states=rows(raw/'pair-controller-states.jsonl')
    routes=read(raw/'pair-route.json') if (raw/'pair-route.json').exists() else {}
    registered=[r['route'] for r in routes.values()]
    if len(registered)==2 and registered[0]!=registered[1]:raise ValueError('pair route mismatch')
    route=registered[0] if len(registered)==2 else None
    physical=physical_metrics(states,rows(raw/'eval_only/contacts.jsonl'),
        rows(raw/'eval_only/referee_truth.jsonl'),route)
    h=read(raw/'pair-handshake.json')
    accepted=[r for r in h.get('renewals',[]) if r['accepted']]
    dispatch=read(raw/'llm/dispatch.json')
    linked=all(any(d['call_id']==r['call_id'] and d['actor']==r['robot_id']
        and d.get('ack',{}).get('accepted') and d['action']==r['action']
        and d.get('carry_lease_renewal')==r for d in dispatch) for r in accepted)
    if not linked:raise ValueError('lease renewal does not match admitted model command')
    value.update(variant=variant,**physical,lease_renewals=len(accepted),
        renewal_rejections=[r for r in h.get('renewals',[]) if not r['accepted']],
        carry_command_rejections=[dict(call_id=d['call_id'],actor=d['actor'],reason=d['ack']['rejected_reason'])
            for d in dispatch if d['action']['kind']=='carry_decision' and d.get('ack') and not d['ack']['accepted']])
    return value


def main(argv=None):
    from scripts.run_s4_pair_live6 import ROOT,RECORD
    p=argparse.ArgumentParser();p.add_argument('--raw-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    if a.output.exists():raise FileExistsError(a.output)
    results=[]
    for run in read(ROOT/RECORD/'plan.json')['runs']:
        results.append(evaluate(a.raw_root/run['name']/'raw',run['variant']))
    a.output.write_text(json.dumps(results,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps([{k:r[k] for k in ('condition','variant','status','continue_transport','goal_transport','lowering')}
        for r in results]))


if __name__=='__main__':raise SystemExit(main())
