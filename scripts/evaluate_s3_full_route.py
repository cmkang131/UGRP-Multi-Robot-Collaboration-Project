"""Complete-route saved-raw evaluator; all live truth is evaluation only."""
import argparse
import json
import math
from pathlib import Path
from scripts.evaluate_s3_route_resume import evaluate as previous, events
from scripts.evaluate_s3_synchronized_carry import read, rows, sustained


def evaluate(raw):
    r=previous(raw)
    b=read(raw/'bundle.json')
    truth=rows(raw/'eval_only/referee_truth.jsonl')
    contacts=rows(raw/'eval_only/contacts.jsonl')
    held=set()
    for x in contacts:
        touched={c[k] for c in x['contacts'] if 'cargo_beam_1' in c['geom1']
            or 'cargo_beam_1' in c['geom2'] for k in ('geom1','geom2')}
        if all(rid+'__'+side+'_finger' in touched for rid in ('r1','r2')
               for side in ('left','right')):
            held.add(round(x['t'],6))
    # Use the same contact-qualified actual carry evidence as the sealed parent.
    for leg in r['legs']:
        start,end=leg['start_sim_s'],leg['end_sim_s']
        points=[x['items']['beam_1'] for x in truth if start<=x['t']<=
                (end if end is not None else truth[-1]['t'])
                and round(x['t'],6) in held and x['items']['beam_1']['z']>.06]
        leg['actual_transport_m']=max((math.dist([p['x'],p['y']],
            [points[0]['x'],points[0]['y']]) for p in points),default=0.)
        leg['transport_reached']=end is not None and leg['actual_transport_m']>=.020
    final_seg=r['planned_legs']-1
    states=read(raw/'stage-states.json')
    last=next((l for l in r['legs'] if l['seg']==final_seg),None)
    lower=next((s['t'] for s in states if last and last['end_sim_s'] is not None
        and s['t']>=last['end_sim_s'] and all(v['state']=='lower' for v in s['robots'].values())),None)
    opens={rid:next((c['t'] for c in rows(raw/f'robots/{rid}/commands.jsonl')
        if lower is not None and c['t']>=lower and c.get('servo_id')==1 and c.get('pulse')==2000),None)
        for rid in ('r1','r2')}
    released=max(opens.values()) if all(v is not None for v in opens.values()) else None
    stable=[x['t'] for x in rows(raw/'eval_only/setdown.jsonl') if released is not None
        and x['t']>=released and x['floor_normal_n']>=.1 and x['cargo_z_m']<=.025
        and abs(x['vertical_speed_m_s'])<=.02 and x['cargo_tilt_deg']<10.]
    point=truth[-1]['items']['beam_1']
    complete=r['status']=='DEV_STAGE_FINISHED' and not r['controller_failures']
    r.update(candidate=b['reacquire']['candidate'],final_release_sim_s=released,
        final_setdown=complete and sustained(stable) is not None,
        final_endpoint_error_m=math.dist([point['x'],point['y']],b['registered_route'][-1]),
        reacquire=read(raw/'reacquire.json'))
    r['full_route_success']=(len(r['legs'])==r['planned_legs']
        and all(l['endpoint_reached'] and l['transport_reached'] for l in r['legs'])
        and r['final_setdown'] and r['final_endpoint_error_m']<=.020
        and not r['drop_aborts'] and not r['tilt_aborts'])
    return r


def main():
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    cc=read(a.cohort/'cohort.json');assert len(cc)==6
    rr=[dict(name=c['name'],**evaluate(a.cohort/c['name']/'raw')) for c in cc]
    summary=dict(host='oracle-x86',n=6,runs=rr,
        full_route_success=sum(r['full_route_success'] for r in rr),
        final_setdown=sum(r['final_setdown'] for r in rr),
        host_errors=sum(r['status']=='HOST_ERROR' for r in rr),
        drop_aborts=sum(r['drop_aborts'] for r in rr),tilt_aborts=sum(r['tilt_aborts'] for r in rr),
        initial_checks_healthy=sum(r['initial_check']['healthy'] for r in rr),
        legs={str(i):dict(n=sum(r['planned_legs']>i for r in rr),
            transported=sum(any(l['seg']==i and l['transport_reached'] for l in r['legs']) for r in rr),
            endpoint_reached=sum(any(l['seg']==i and l['endpoint_reached'] for l in r['legs']) for r in rr))
            for i in range(3)},scope='unbroken synthetic alignment-to-final-release registered routes; not dock-to-B E2E')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'}))


if __name__=='__main__':raise SystemExit(main())
