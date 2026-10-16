"""Evaluation-only contact/command audit; no simulator or controller feedback."""
import hashlib,json,math
from pathlib import Path
import cv2
import numpy as np

RAW=Path('/Users/changmin/projects/ugrp/outputs/s2-realism-c26e9afd-s1051-P1-2-place')
OUT=Path('/Users/changmin/projects/ugrp/outputs/s2-blocked-pulse-20261007')
TIMES=(107.35,108.30,109.25,110.20,111.15,113.70)

def main():
    read=lambda p:json.loads((RAW/p).read_text())
    lines=lambda p:[json.loads(l) for l in (RAW/p).read_text().splitlines()]
    record=read('student_record.json');contacts=lines('eval_only/contacts.jsonl')
    supervisor=lines('eval_only/supervisor.jsonl');frames=lines('robots/r3/frames.jsonl')
    drift=json.loads(Path('/Users/changmin/projects/ugrp/outputs/s2-load-height-20261007/drift-decomposition.json').read_text())
    rows=[];sheet=[]
    for t in TIMES:
        d=next(r for r in drift['rows'] if abs(r['t']-t)<1e-6)
        cmd=next(r for r in record['pulse_motion_model']['transformations'] if abs(r['t']-t)<1e-6)
        pose=max((r for r in record['poses'] if r['t']<=t+1e-7),key=lambda r:r['t'])
        interval=[r for r in contacts if t-1e-7<=r['t']<=t+.75+1e-7]
        categories={k:[] for k in ('wall_wheel','wall_cargo','divider_robot_or_cargo','other_wall_robot')}
        for r in interval:
            for c in r['contacts']:
                names=[c['geom1'],c['geom2']];joined=' '.join(names)
                if 'zone_wall_north' in names and 'r3__' in joined:
                    key='wall_wheel' if 'wheel_' in joined else 'other_wall_robot'
                elif 'zone_wall_north' in names and 'cargo_box_00_geom' in names:key='wall_cargo'
                elif ('divider' in joined or 'door' in joined) and ('r3__' in joined or 'cargo_box_00_geom' in names):key='divider_robot_or_cargo'
                else:continue
                categories[key].append(dict(t=r['t'],**c))
        detail={k:dict(samples=len({x['t'] for x in v}),contacts=len(v),
            first_t=min((x['t'] for x in v),default=None),last_t=max((x['t'] for x in v),default=None),
            min_distance_m=min((x['dist_m'] for x in v),default=None),
            geom_pairs=sorted(set(tuple(sorted([x['geom1'],x['geom2']])) for x in v))) for k,v in categories.items()}
        sup=[r for r in supervisor if t-1e-7<=r['t']<=t+.75+1e-7]
        pair=[];image_records=[]
        for when in (t,t+.75):
            f=min(frames,key=lambda r:abs(r['sim_time']-when));p=RAW/f['path'];data=p.read_bytes()
            assert hashlib.sha256(data).hexdigest()==f['sha256']
            im=cv2.imdecode(np.frombuffer(data,np.uint8),1)
            cv2.putText(im,f"{t:.2f}s / frame {f['sim_time']:.2f}s",(15,30),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,255),2)
            pair.append(im);image_records.append(dict(t=f['sim_time'],path=str(p),sha256=f['sha256']))
        sheet.append(np.hstack(pair))
        rows.append(dict(t=t,horizon_s=.75,controller=cmd,estimate=pose,evaluation=d,
            contacts=detail,contact_samples=len(interval),finger_both_count=sum(all(r['finger_contacts']) for r in sup),
            supervisor_samples=len(sup),max_tilt_deg=max(r['robot_tilt_deg'] for r in sup),
            weld_count=max(len(r['active_weld_ids']) for r in interval),frames=image_records))
    target=OUT/'six-pulses.json';assert not target.exists()
    result=dict(schema='ugrp.s2.blocked_pulse.audit.v1',source_raw=str(RAW),physics_runs=0,model_calls=0,
        gt_scope='evaluation only; never imported by candidate/replay',rows=rows,
        source_hashes={p:hashlib.sha256((RAW/p).read_bytes()).hexdigest() for p in
            ('student_record.json','eval_only/contacts.jsonl','eval_only/supervisor.jsonl','eval_only/trajectory.jsonl','robots/r3/frames.jsonl')})
    target.write_text(json.dumps(result,indent=2)+'\n')
    cv2.imwrite(str(OUT/'six-before-after.jpg'),np.vstack(sheet))
    for r in rows:print(json.dumps({k:v for k,v in r.items() if k not in ('estimate','controller','evaluation','frames')}))

if __name__=='__main__':main()
