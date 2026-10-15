"""Terminal GCP2 round summary with invalid/withheld runs kept explicitly."""
import argparse,collections,hashlib,json,math,platform,subprocess
from pathlib import Path
import numpy as np
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def load(p):return p.read_text() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'],text=True)
def obj(p):return json.loads(load(p))
def rows(p):return [json.loads(s) for s in load(p).splitlines()]
def dist(x):return dict(N=len(x),p50=float(np.percentile(x,50)),p95=float(np.percentile(x,95)),end=float(x[-1])) if x else dict(N=0)
def main(n):
    assert platform.node().startswith('ugrp-sim-gcp2')
    batch=RUNS/f'reloc18-round{n}';queue=obj(batch/'queue.json');reports=[]
    for task in queue['runs']:
        raw=Path(task['raw']);folder=raw.parent
        r={k:task[k] for k in ('name','kind','condition','seed','source_sha','raw')}
        invalid=folder/'INVALID_CONTROL.json';withheld=folder/'WITHHELD.json'
        if withheld.exists():r.update(status='WITHHELD',reason=obj(withheld));reports.append(r);continue
        if not (folder/'EXIT').exists():raise RuntimeError('RUNNING '+task['name'])
        d=obj(raw/'result.json');r.update(status=d.get('status'),termination=d.get('termination_category'),valid_for_comparison=not invalid.exists(),exit_code=(folder/'EXIT').read_text().strip())
        if invalid.exists():r.update(invalid_reason=obj(invalid))
        r['source_hashes']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (folder/'task.json',raw/'result.json',raw/'result.json.zst',raw/'manifest.json',raw/'manifest.json.zst',raw/'artifacts.sha256.json',raw/'artifacts.sha256.json.zst') if p.is_file()}
        if task['kind']=='selfmap':
            from scripts.analyze_reloc14 import selfmap
            s=selfmap(folder)
            for k in ('drive_errors','registered_errors','registration_frame_funnel','known_mode_measurement_funnel','input_audit','drift','first30'):r[k]=s[k]
            trace=rows(raw/'trace.jsonl');admissions=[x.get('correction_admission') for x in trace if x.get('correction_admission')]
            r['gate_reasons']=dict(collections.Counter(x['reason'] for x in admissions))
            r['gate_cumulative']=dict(candidates=len(admissions),accepted=sum(x['accepted'] for x in admissions))
        else:
            c=rows(raw/'teacher-commands.jsonl');ev=rows(raw/'eval-only.jsonl');by={round(x['t'],5):x for x in ev if 'base_xyz' in x};scored=[];trackers={};headings={}
            for x in c:
                e=by.get(round(x['t'],5))
                if e is None:continue
                m=x['map_pose'];pose=np.asarray(m['pose_estimate']);truth=np.array([*e['base_xyz'][:2],e['base_yaw_rad']])
                def err(p):
                    delta=p-truth;return float(np.linalg.norm(delta[:2])),abs(math.degrees(math.atan2(math.sin(delta[2]),math.cos(delta[2]))))
                shadow=m.get('reloc18_command_shadow');a=err(pose);b=err(np.asarray(shadow)) if shadow is not None else (None,None)
                scored.append(dict(t=x['t'],elapsed=x['t']-c[0]['t'],phase=x['phase'],xy=a[0],yaw=a[1],command_xy=b[0],command_yaw=b[1]))
                h=m.get('reloc14_tracking',{});key=h.get('sensor_updates')
                if h.get('updated') and key not in trackers:
                    observed=err(np.asarray(h['pose']));trackers[key]=dict(t=x['t'],accepted=bool(h.get('accepted')) and task['condition']!='command_only',raw_error_xy=observed[0],raw_error_yaw=observed[1],applied_error_xy=a[0],applied_error_yaw=a[1],reason=h.get('reloc18_innovation',{}).get('reason','legacy_without_innovation'))
                h=m.get('reloc15_heading',{});key=h.get('exposure_sim_t')
                if key is not None and key not in headings:
                    gt=by.get(round(key,5));observed=h.get('observed_yaw_rad')
                    de=None if gt is None or observed is None else observed-gt['base_yaw_rad']
                    he=None if de is None else abs(math.degrees(math.atan2(math.sin(de),math.cos(de))))
                    headings[key]=dict(t=key,status=h.get('status'),decision=h.get('reloc18_innovation'),error_yaw_deg=he)
            phases=collections.Counter(x['phase'] for x in c);teacher=d.get('teacher',{});carry=teacher.get('carry',{})
            reasons=collections.Counter(e.get('reason',e.get('event','missing_original_reason')) for e in carry.get('recovery_events',[]))
            final=next((e for e in reversed(ev) if 'footprint_xy' in e),{})
            region=obj(raw/'carry-static-map.json')['regions']['zone_'+d.get('destination_zone',obj(raw/'plan.json')['destination_zone'])]
            cx,cy=region['center_m'];hx,hy=region['half_extents_m']
            margin=min((min(hx-abs(x-cx),hy-abs(y-cy)) for x,y in final.get('footprint_xy',[])),default=None)
            r.update(place_success=d.get('zone_placement_success') is True,lift=d.get('lift_success'),phase=teacher.get('phase'),sim_s=d.get('sim_s'),first30=d.get('first30'),
                input_audit=d.get('input_audit'),phases=dict(phases),gate_reasons=dict(reasons),
                gate_cumulative=dict(started=1,lift_success=int(d.get('lift_success') is True),travel_entered=int(phases['carry_to_zone']>0),
                    authored_arrival=int(carry.get('map_arrival_estimated_t') is not None),place_view=int(phases['zone_place_view']>0),
                    place_advance=int(phases['zone_place_advance']>0),lower=int(phases['lower']>0),open=int(phases['open']>0),place_success=int(d.get('zone_placement_success') is True)),
                errors={k:dist([x[k] for x in scored if x[k] is not None]) for k in ('xy','yaw','command_xy','command_yaw')},
                drift_bins=[dict(sim_interval=[lo,hi],errors={k:dist([x[k] for x in scored if x[k] is not None and lo<=x['elapsed']<hi]) for k in ('xy','yaw','command_xy','command_yaw')}) for lo,hi in ((0,50),(50,100),(100,150),(150,200),(200,250),(250,300))],
                tracker=dict(candidates=len(trackers),accepted=sum(x['accepted'] for x in trackers.values()),accepted_raw_yaw_over5=sum(x['accepted'] and x['raw_error_yaw']>5 for x in trackers.values()),accepted_applied_yaw_over5=sum(x['accepted'] and x['applied_error_yaw']>5 for x in trackers.values()),reasons=dict(collections.Counter(x['reason'] for x in trackers.values()))),
                heading_statuses=dict(collections.Counter(x['status'] for x in headings.values())),
                heading=dict(accepted=sum(x['status']=='accepted' for x in headings.values()),
                    accepted_yaw_over5=sum(x['status']=='accepted' and x['error_yaw_deg'] is not None and x['error_yaw_deg']>5 for x in headings.values()),
                    unscorable=sum(x['status']=='accepted' and x['error_yaw_deg'] is None for x in headings.values())),
                final_evaluator=dict(t=final.get('t'),zone_margin_min_m=margin,
                    clearance_m=final['min_z']-final['support_z'] if final else None,tilt_deg=final.get('tilt_deg'),speed_m_s=final.get('speed'),
                    open_issued=final.get('open_issued'),finger_contacts=final.get('finger_contacts'),xy_error_m=final.get('map_pose_error_xy_m'),
                    footprint_inside=d.get('final_footprint_inside_zone'),release_success=d.get('release_success'),
                    scope='evaluator only; predicates may be false because final place was never reached'),
                would_stop_pose_budget=carry.get('would_stop_pose_budget'),
                criteria=d.get('criteria'),failure=carry.get('failure'))
        reports.append(r)
    result=dict(round=n,analysis_host='gcp2',runs=reports,reproduce=f'PYTHONPATH=. python {__file__} --round {n}',scope='DEV; invalid and predetermined failure-window diagnostics excluded from adoption')
    (batch/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    rejection=dict(source_queue=str(batch/'queue.json'),reproduce=result['reproduce'],runs=[dict(run=r['name'],raw=r['raw'],valid=r.get('valid_for_comparison',False),cumulative=r.get('gate_cumulative',r.get('registration_frame_funnel')),rejections=[dict(category=k,N=v,blocked_object='pose_or_route_gate',minimum_gap_m=None,gap_scope='not_applicable_localization_or_original_gap_missing') for k,v in r.get('gate_reasons',{}).items()]) for r in reports])
    (batch/'rejection-table.json').write_text(json.dumps(rejection,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in r.items() if k in ('name','status','termination','valid_for_comparison','phase','sim_s','place_success','errors','tracker','drive_errors')} for r in reports],indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,required=True);a=p.parse_args();main(a.round)
