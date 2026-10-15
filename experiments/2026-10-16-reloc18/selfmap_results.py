"""Terminal-only selfmap comparison, keeping local and map-absolute errors apart."""
import json,platform,sys,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def main(source_root,round_no=2):
    assert platform.node().startswith('ugrp-sim-gcp2')
    sys.path.insert(0,str(Path(source_root)/'experiments/2026-10-16-reloc17'))
    from analyze import analysis
    from scripts.analyze_reloc14 import selfmap
    q=json.loads((RUNS/f'reloc18-round{round_no}/queue.json').read_text());out=[]
    for t in q['runs']:
        if t['kind']!='selfmap':continue
        folder=Path(t['raw']).parent
        if not (folder/'EXIT').is_file():continue
        base=selfmap(folder);extra=analysis(folder)
        report=dict(run=t['name'],raw=t['raw'],source_sha=t['source_sha'],
            local_command=extra['command_only_replay'],local_candidate=extra['local_execution_drift'],
            absolute_drive=base['drive_errors'],absolute_registered=base['registered_errors'],
            static_admissions=base['drift']['fixes'],funnel=base['registration_frame_funnel'],
            input_audit=base['input_audit'])
        if round_no==3:
            import numpy as np
            from harness.natural_floor_slam import compose,wrap
            from harness.selfmap4_geometry import inverse
            from scripts.analyze_reloc11_selfmap import rows
            from scripts.analyze_reloc13 import distribution
            raw=Path(t['raw']);trace=rows(raw/'trace.jsonl');truth={round(x['t'],6):x for x in rows(raw/'eval_only/trajectory.jsonl')}
            scored=[];anchor=None;fixes=[];reasons={};local_diffs=[]
            for r in trace:
                reg=r['static_registration'];m=reg.get('map_odom');p=reg.get('reloc12',{}).get('replay',{}).get('own_odometry_pose');gt=truth.get(round(r['t'],6))
                if m is None or p is None or gt is None:continue
                local_diffs.append([float(np.linalg.norm(np.asarray(r['pose'])[:2]-np.asarray(p)[:2])),abs(math.degrees(wrap(r['pose'][2]-p[2])))])
                if anchor is None:anchor=compose(m['world_pose'],inverse(p));start=r['t']
                actual=np.array([*gt['robot_xyz_m'][:2],gt['robot_yaw_rad']])
                def err(x):return [float(np.linalg.norm(np.asarray(x)[:2]-actual[:2])),abs(math.degrees(wrap(x[2]-actual[2])))]
                c,e=err(compose(anchor,p)),err(m['world_pose']);d=m['decision'];reasons[d['reason']]=reasons.get(d['reason'],0)+1
                scored.append(dict(t=r['t'],elapsed=r['t']-start,command=c,candidate=e))
                if d.get('accepted') and d.get('nis') is not None:fixes.append(dict(t=r['t'],raw=err(reg['world_pose']),applied=e,nis=d['nis']))
            def stats(values):return dict(N=len(values),xy_m=distribution([x[0] for x in values]),yaw_deg=distribution([x[1] for x in values]))
            report['global_same_trajectory']=dict(scope='same executed commands, command-only world anchor fixed from first RGB registration; no evaluator alignment fed to control',
                command=stats([x['command'] for x in scored]),candidate=stats([x['candidate'] for x in scored]),
                bins=[dict(sim_interval=[lo,lo+30],command=stats([x['command'] for x in scored if lo<=x['elapsed']<lo+30]),candidate=stats([x['candidate'] for x in scored if lo<=x['elapsed']<lo+30])) for lo in range(0,180,30)],
                first_RGB_anchor=None if anchor is None else anchor.tolist(),gate_reasons=reasons,
                global_admissions=dict(N=len(fixes),raw_yaw_over5_N=sum(x['raw'][1]>5 for x in fixes),applied_yaw_over5_N=sum(x['applied'][1]>5 for x in fixes),raw_xy_over10cm_N=sum(x['raw'][0]>.1 for x in fixes)),
                local_vs_command=dict(N=len(local_diffs),max_xy_m=max((x[0] for x in local_diffs),default=None),max_yaw_deg=max((x[1] for x in local_diffs),default=None)))
            # Local error equality is reported through the identical local
            # distributions above; no privileged evaluation pose is a runtime input.
            (RUNS/f'reloc18-round{round_no}'/(t['name']+'-global-errors.json')).write_text(json.dumps(scored)+'\n')
        out.append(report)
    data=dict(status='COMPLETE' if len(out)==2 else 'INCOMPLETE',runs=out,
        scope='local drift aligned once at initial evaluator pose for scoring only; absolute map errors are separate; each command comparison uses the same executed trajectory',
        reproduce=f'PYTHONPATH=. python {__file__} {source_root} {round_no}')
    (RUNS/f'reloc18-round{round_no}/selfmap-results.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data,indent=2))
if __name__=='__main__':main(sys.argv[1],int(sys.argv[2]) if len(sys.argv)>2 else 2)
