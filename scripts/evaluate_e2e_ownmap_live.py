"""Post-close only: full-outline B, floor support, drop and carried segments.

Only this evaluator reads scene coordinates and physics logs. It produces no
commands and is never passed to the own-map/controller/model objects.
"""
import json
import math


def rows(path):
    if not path.exists():return []
    with path.open() as stream:return [json.loads(line) for line in stream if line.strip()]


def evaluate(raw,result,events,origin):
    outlines=rows(raw/'eval_only/beam-outline.jsonl')
    supports=rows(raw/'eval_only/setdown.jsonl')
    truth=rows(raw/'eval_only/referee_truth.jsonl')
    commanded_releases=[e['t']+origin for e in events if e['event']=='phase' and e['state']=='relook_camera']
    last=commanded_releases[-1] if commanded_releases else None
    tail=[r for r in outlines if last is not None and r['t']>=last]
    margins=[min(r['min_xyz_m'][0]-4.2,5.-r['max_xyz_m'][0],
                 r['min_xyz_m'][1]+2.8,-1.4-r['max_xyz_m'][1]) for r in tail]
    inside=bool(margins) and min(margins)>=0.
    floor=[r['t'] for r in supports if last is not None and r['t']>=last and r['floor_normal_n']>=.1
           and r['cargo_z_m']<=.025 and abs(r['vertical_speed_m_s'])<=.02 and r['cargo_tilt_deg']<10.]
    from scripts.evaluate_s3_synchronized_carry import sustained
    stable=sustained(floor,minimum=1.) is not None
    drop_rows=rows(raw/'eval_only/beam-drop-guard.jsonl')
    drops=sum(bool(r.get('drop')) for r in drop_rows)
    if 'LOAD_DROP' in result.get('failure','') and not drops:drops=1
    legs=[]
    for e in events:
        if e['event']!='s3_synchronized_segment':continue
        end=next((x['t'] for x in events if x['event']=='phase' and x['t']>e['t'] and x['state']!='carry'),None)
        observed=[x['items']['beam_1'] for x in truth if end is not None and e['t']+origin<=x['t']<=end+origin]
        travel=max((math.dist([p['x'],p['y']],[observed[0]['x'],observed[0]['y']]) for p in observed),default=0.)
        held=[r for r in supports if end is not None and e['t']+origin<=r['t']<=end+origin
              and r['cargo_z_m']>.06 and all(len(r['fingers'].get(rid,[]))==2 and
                    all(r['fingers'][rid]) for rid in ('r1','r2'))]
        legs.append(dict(key=e['key'],planned_m=e['planned_m'],actual_displacement_m=travel,
            held_samples=len(held),completed=end is not None,
            carried=end is not None and len(held)>0 and travel>=max(.02,e['planned_m']-.10)))
    complete=bool(result['start_to_finish_transport'] and legs and all(l['carried'] for l in legs)
                  and inside and stable and not drops)
    return dict(start_to_finish_transport=complete,B_whole_outline_inside=inside,
        B_min_margin_m=min(margins) if margins else None,floor_stable=stable,drops=drops,legs=legs,
        feedback_to_controller=False,scope='post_run_full_outline_and_contact_evaluation')
