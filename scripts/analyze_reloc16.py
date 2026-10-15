"""gcp2 original-file recount; all truth reads are evaluator-only."""
import argparse,collections,hashlib,json,math,platform
from pathlib import Path
import numpy as np
from scripts.analyze_reloc11_selfmap import obj,rows
from scripts.analyze_reloc14 import selfmap


def wrap(x):return math.atan2(math.sin(x),math.cos(x))

def dist(xs):
    return dict(N=len(xs),p50=float(np.percentile(xs,50)),p95=float(np.percentile(xs,95)),max=max(xs)) if xs else dict(N=0)


def verify(raw):
    p=raw/'artifacts.sha256.json'
    if p.exists() or Path(str(p)+'.zst').exists():manifest=obj(p);kind='selfmap'
    elif (raw/'manifest.json').exists() or (raw/'manifest.json.zst').exists():manifest=obj(raw/'manifest.json');kind='carry'
    else:return dict(verified=False,reason='manifest_missing',files=0)
    missing=[];bad=[]
    for name,value in manifest.items():
        f=raw/name
        if not f.is_file():missing.append(name);continue
        expected=value if isinstance(value,str) else value['sha256']
        if hashlib.sha256(f.read_bytes()).hexdigest()!=expected:bad.append(name)
    return dict(verified=not missing and not bad,files=len(manifest),missing=missing,bad=bad,kind=kind)


def carry(folder,result):
    raw=folder/'raw';cmd=rows(raw/'teacher-commands.jsonl');ev=rows(raw/'eval-only.jsonl')
    by={round(e['t'],5):e for e in ev};commands={round(c['t'],5):c for c in cmd}
    view_times=[e['t'] for e in result.get('lookaround',{}).get('localizer',{}).get('events',[]) if e.get('event')=='view']
    times=np.array([c['t'] for c in cmd]);unsafe=set()
    for at in view_times:
        i=int(np.searchsorted(times,at-1e-8))
        if i<len(times):unsafe.add(round(times[i],5))
    def actual(at):
        k=round(at,5);e=by.get(k);c=commands.get(k)
        if e is None or c is None:return None
        if 'base_yaw_rad' in e:return e['base_yaw_rad']
        if k in unsafe:return None
        if e.get('map_pose_error_yaw_rad') is None:return None
        return wrap(c['map_pose']['pose_estimate'][2]-e['map_pose_error_yaw_rad'])
    heading={};phases=collections.Counter()
    for c in cmd:
        h=c.get('map_pose',{}).get('reloc15_heading',{})
        if h.get('exposure_sim_t') is not None:heading[round(h['exposure_sim_t'],5)]=h
        phases[c['phase']]+=1
    statuses=collections.Counter(h.get('status','unknown') for h in heading.values())
    admissions=[];eligible=[];increments=[]
    for at,h in sorted(heading.items()):
        if h.get('status')!='accepted':continue
        c=commands.get(at,{});e=by.get(at,{});truth=actual(at)
        row=dict(t=at,phase=c.get('phase'),command_closed=c.get('command',{}).get('pwm',{}).get('1',2000)<=1600,
                 observed_yaw_rad=h['observed_yaw_rad'],actual_yaw_rad=truth,
                 abs_error_deg=None if truth is None else abs(math.degrees(wrap(h['observed_yaw_rad']-truth))),
                 confidence_bound_deg=math.degrees(h['uncertainty_bound_rad']))
        admissions.append(row)
        if truth is not None:eligible.append(row)
        oldat=round(h.get('confirmation_exposure_t',-100.),5);old=heading.get(oldat);oldtruth=actual(oldat)
        if old is not None and old.get('observed_yaw_rad') is not None and truth is not None and oldtruth is not None:
            error=wrap(wrap(h['observed_yaw_rad']-old['observed_yaw_rad'])-wrap(truth-oldtruth))
            increments.append(dict(t0=oldat,t1=at,error_deg=math.degrees(error)))
    audit=result.get('input_audit',{});physical=result.get('physical_success')
    original_errors=[e for e in ev if e.get('map_pose_error_yaw_rad') is not None]
    return dict(source_sha=result.get('source_sha'),status=result.get('status'),sim_s=result.get('sim_s'),
        termination_category=result.get('termination_category'),termination_reason=result.get('termination_reason'),
        first30=result.get('first30'),place_verified=physical is True,physical_success=physical,
        heading=dict(exposures=len(heading),statuses=dict(statuses),accepted=len(admissions),scorable_absolute=len(eligible),
            excluded_absolute=len(admissions)-len(eligible),absolute_false_over5_N=sum(r['abs_error_deg']>5 for r in eligible),
            absolute_error_deg=dist([r['abs_error_deg'] for r in eligible]),scorable_delta=len(increments),
            delta_false_over5_N=sum(abs(r['error_deg'])>5 for r in increments),delta_error_deg=dist([abs(r['error_deg']) for r in increments]),
            accepted_while_command_closed=sum(r['command_closed'] for r in admissions),
            truth_scope='direct evaluator base yaw if present; R1 reconstruction excludes simultaneous lookaround capture ticks',
            admissions=admissions,increments=increments),
        all_pose_error=dict(xy_m=dist([e['map_pose_error_xy_m'] for e in original_errors]),yaw_deg=dist([abs(math.degrees(e['map_pose_error_yaw_rad'])) for e in original_errors])),
        input_audit=audit,phases=dict(phases),recovery=result.get('teacher',{}).get('result'))


def main(round_no):
    if not platform.node().startswith('ugrp-sim-gcp2'):raise RuntimeError('gcp2 only')
    root=Path('/home/ugrp/ugrp-sim/runs');batch=root/f'reloc16-round{round_no}';queue=obj(batch/'queue.json');reports=[];funnel=[]
    for task in queue['runs']:
        folder=root/task['name'];raw=folder/'raw';result=obj(raw/'result.json')
        report=dict(run=task['name'],kind=task['kind'],seed=task['seed'],scene=task['scene'],raw=str(raw),source_sha=task['source_sha'],host_retry_of=task.get('host_retry_of'))
        if result.get('status') not in ('running',None):
            report['integrity']=verify(raw)
        if task['kind']=='selfmap' and result.get('frames',0):
            s=selfmap(folder);(folder/'analysis.json').write_text(json.dumps(s,indent=2)+'\n')
            report.update(status=result['status'],termination=result.get('termination_category'),first30=s['first30'],
                registration=s['registration_frame_funnel'],known_mode=s['known_mode_measurement_funnel'],
                registration_events=s['registration_events'],false_registration_events=s['false_registration_events'],
                funnel=s['funnel'],registered_errors=s['registered_errors'],drive_errors=s['drive_errors'],input_audit=result.get('input_audit'))
            funnel.append(dict(run=task['name'],raw=str(raw),cumulative=s['registration_frame_funnel']['cumulative'],rejections=s['registration_frame_funnel']['first_rejections']))
        elif task['kind']=='carry' and result.get('status')=='complete':
            report.update(carry(folder,result));h=report['heading']
            funnel.append(dict(run=task['name'],raw=str(raw),cumulative=dict(exposures=h['exposures'],accepted=h['accepted'],scorable=h['scorable_absolute'],correct=h['scorable_absolute']-h['absolute_false_over5_N']),
                rejections=[dict(category=k,N=n,blocked_object='own_rgb_static_background',minimum_gap_m=None,gap_status='not_applicable_localization_gate') for k,n in h['statuses'].items() if k!='accepted']))
        else:
            report.update(status=result.get('status','UNRETRIEVED'),failure=result.get('failure'),physical_frames=result.get('frames',0))
            funnel.append(dict(run=task['name'],raw=str(raw),cumulative=dict(frames=result.get('frames',0)),rejections=[dict(category='HOST_ERROR' if result.get('status')=='HOST_ERROR' else 'INCOMPLETE',N=1,blocked_object='execution_environment',minimum_gap_m=None,gap_status='not_applicable_host_error',reason=result.get('failure') or result.get('error') or 'result not terminal')]))
        reports.append(report)
    write=lambda p,v:p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
    write(batch/'summary.json',dict(round=round_no,status='MEASURED' if all(r['status'] not in ('running','UNRETRIEVED') for r in reports) else 'INCOMPLETE',runs=reports,analysis_host='gcp2'))
    write(batch/'rejection-table.json',dict(round=round_no,unit='ordered frames/events; not independent trial success rate',runs=funnel,source_queue=str(batch/'queue.json'),reproduction=f'PYTHONPATH=. python -m scripts.analyze_reloc16 --round {round_no}'))
    print(json.dumps([dict(run=r['run'],status=r['status'],drive=r.get('drive_errors'),heading=None if 'heading' not in r else {k:v for k,v in r['heading'].items() if k not in ('admissions','increments')},failure=r.get('failure')) for r in reports]))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--round',type=int,choices=(1,2,3),required=True);a=p.parse_args();main(a.round)
