"""Post-run full-outline/segment judge; source truth never goes to control."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from scripts.evaluate_s3_synchronized_carry import read, rows, sustained
from scripts.evaluate_s3_route_resume import events


def footprint_inside(point, center=(4.6,-2.1), half=(.4,.7), beam_half=(.3,.0205)):
    c,s=abs(math.cos(point['yaw'])),abs(math.sin(point['yaw']))
    extent=[c*beam_half[0]+s*beam_half[1],s*beam_half[0]+c*beam_half[1]]
    margin=[half[i]-abs(point[k]-center[i])-extent[i] for i,k in enumerate(('x','y'))]
    return min(margin)>=0.,margin


def file_sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def evaluate(raw):
    b=read(raw/'bundle.json');r=read(raw/'result.json')
    manifest=read(raw/'artifacts.sha256.json')
    for path,h in manifest.items():
        if file_sha(raw/path)!=h:raise ValueError('RAW_HASH_MISMATCH:'+path)
    base=dict(status=r['status'],seed=b['seed'],source_sha=b['source_sha'],source='test_route_provider',
        entrance=b.get('test_entrance','off'),
        E2E_success=False,research_result=False,wall_s=r['wall_s'],sim_s=r.get('check_sim_s',0.),
        failure=r.get('failure'),initial_check=read(raw.parent/'initial-check.json'),
        raw_path=str(raw),manifest_sha256=file_sha(raw/'artifacts.sha256.json'),
        verified_files=len(manifest),all_sha256_match=True,model_calls=0)
    if not (raw/'ownroute-s3-plan.json').exists():
        return dict(**base,S3_route_success=False,B_setdown=False,drops=0,legs=[],cause='before_route_plan')
    plan=read(raw/'ownroute-s3-plan.json');ss=read(raw/'stage-states.json')
    tt=rows(raw/'eval_only/referee_truth.jsonl');cc=rows(raw/'eval_only/contacts.jsonl')
    held=set()
    for x in cc:
        touched={c[k] for c in x['contacts'] if 'cargo_beam_1' in c['geom1'] or 'cargo_beam_1' in c['geom2']
                 for k in ('geom1','geom2')}
        if all(rid+'__'+side+'_finger' in touched for rid in ('r1','r2') for side in ('left','right')):
            held.add(round(x['t'],6))
    ev=list({json.dumps(e,sort_keys=True):e for e in events(read(raw/'student_record.json'))}.values())
    legs=[]
    for leg in plan['legs']:
        seg=leg['seg']
        active=[s['t'] for s in ss if all(v['seg']==seg and v['state']=='carry' for v in s['robots'].values())]
        times=[x for x in tt if active and active[0]<=x['t']<=active[-1]+.051]
        pts=[x['items']['beam_1'] for x in times if round(x['t'],6) in held and x['items']['beam_1']['z']>.06]
        transported=max((math.dist([p['x'],p['y']],[pts[0]['x'],pts[0]['y']]) for p in pts),default=0.)
        end=next((s['t'] for s in ss if active and s['t']>active[-1] and any(v['seg']==seg and v['state']!='carry' for v in s['robots'].values())),None)
        point=times[-1]['items']['beam_1'] if times else None
        error=math.dist([point['x'],point['y']],leg['end']) if point else None
        legs.append(dict(seg=seg,axis=leg['axis'],planned_m=leg['distance_m'],actual_contact_transport_m=transported,
            end_sim_s=end,endpoint_error_m=error,completed=end is not None,
            carried=end is not None and transported>=max(.02,leg['distance_m']-.10)))
    releases=[c['t'] for rid in ('r1','r2') for c in rows(raw/f'robots/{rid}/commands.jsonl')
              if c.get('servo_id')==1 and c.get('pulse')==2000]
    final_release=max(releases) if releases else None
    floor=[x['t'] for x in rows(raw/'eval_only/setdown.jsonl') if final_release is not None and x['t']>=final_release
        and x['floor_normal_n']>=.1 and x['cargo_z_m']<=.025 and abs(x['vertical_speed_m_s'])<=.02 and x['cargo_tilt_deg']<10.]
    tail=[x for x in rows(raw/'eval_only/beam-outline.jsonl') if final_release is not None and x['t']>=final_release]
    margins=[min(x['min_xyz_m'][0]-4.2,5.-x['max_xyz_m'][0],
                 x['min_xyz_m'][1]+2.8,-1.4-x['max_xyz_m'][1]) for x in tail]
    inside=bool(tail) and all(m>=0 for m in margins)
    finished=r.get('stage_end')=='final_route_release_commanded'
    B_setdown=finished and inside and sustained(floor,minimum=1.) is not None
    drops=int('LOAD_DROP' in (r.get('failure') or ''))
    tilt=int('TILT_LIMIT' in (r.get('failure') or ''))
    door=any(x['items']['beam_1']['x']-.3>2.225 for x in tt)
    final=tt[-1]['items']['beam_1']
    success=len(legs)==len(plan['legs']) and all(l['carried'] for l in legs) and B_setdown and not drops and not tilt and door
    return dict(**base,route_hash=plan['route_hash'],plan_hash=plan['plan_hash'],length_m=plan['length_m'],
        legs=legs,planned_segments=len(plan['legs']),B_setdown=B_setdown,B_whole_outline_inside=inside,
        B_min_margin_m=min(margins) if margins else None,final_xy_m=[final['x'],final['y']],
        final_yaw_rad=final['yaw'],door_crossed=door,final_release_sim_s=final_release,drops=drops,tilt_aborts=tilt,
        S3_route_success=success,cause=None if success else 'host_error' if r['status']=='HOST_ERROR' else 'S3_route_or_setdown_incomplete',
        controller_failures={rid:v['failure'] for rid,v in r.get('final',{}).items() if v['failure']},
        scopes=dict(carriers='synthetic S3 alignment entrance',route='test_route_provider',
            legacy_guard_provider=True,ownmap_admitted=False,dialogue_live=False),
        correction_events=sum(e['event']=='checkpoint_carry_command_plan' for e in ev))


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=evaluate(a.raw);a.output.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k not in ('initial_check','legs','failure','scopes')}))


if __name__=='__main__':raise SystemExit(main())
