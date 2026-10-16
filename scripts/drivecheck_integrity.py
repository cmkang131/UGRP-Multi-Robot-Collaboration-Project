"""gcp2-only raw hash, clock-grid, initial-placement and paired-model audit."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if not os.uname().nodename.startswith('ugrp-sim-gcp2'):raise ValueError('gcp2 only')
    import numpy as np
    import mujoco
    os.chdir('/home/ugrp/ugrp-sim/src/drivecheck-renderer-5974a181')
    fixture=a.raw/'fixture-v3';f=np.load(fixture/'fixture.npz')
    m=mujoco.MjModel.from_xml_string((fixture/'scene.xml').read_text());d=mujoco.MjData(m)
    base=m.geom('r1__base_lower_collision').id;box=m.geom('cargo_box_00_geom').id
    floor=m.geom('floor').id;boxadr=int(m.jnt_qposadr[m.body_jntadr[m.geom_bodyid[box]]])
    rollers={name:{g for g in range(m.ngeom) if (m.geom(g).name or '').startswith('r1__v3_wheel_'+name+'_roller_')
        and (m.geom(g).name or '').endswith('_body_contact')} for name in ('fl','fr','rl','rr')}
    records=[];errors=[];initial=[]
    for path in sorted(a.raw.glob('*/result.json')):
        folder=path.parent;r=json.loads(path.read_text());bad=[]
        manifest=folder/'SHA256SUMS.json'
        if manifest.is_file():
            for name,digest in json.loads(manifest.read_text()).items():
                file=folder/name
                if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
                    bad.append(dict(category='RAW_HASH_MISMATCH',reason='recorded original bytes differ or missing',blocked_object=name,minimum_gap_m=None,gap_status='not_applicable'))
        iscomplete=r.get('planned_tape_complete') and r['status']=='cap_end'
        if iscomplete:
            s=np.load(folder/'states.npz');c=np.load(folder/'contacts.npz')['records'];dt=r['dt']
            expected=f['qpos'].copy()
            if r.get('fixture_ablation'):
                expected[boxadr:boxadr+3]=r['fixture_ablation']['after_xyz']
            expected=expected.astype(s['qpos'].dtype)
            for ci,case in enumerate(r['cases']):
                ids=np.flatnonzero(s['case']==ci);ticks=np.rint(s['t'][ids]/dt).astype(int)
                end=round((case['settle_s']+case['duration_s']+case['tail_s'])/dt)
                required=set(range(0,end+1,round(.1/dt)))|{0,end,round(case['settle_s']/dt),round((case['settle_s']+case['duration_s'])/dt)}
                if not required.issubset(set(ticks)):
                    bad.append(dict(category='RECORDING_GRID_MISSING',reason='10Hz or exact pulse boundary missing',blocked_object=case['id'],minimum_gap_m=None,gap_status='not_applicable'))
                if not np.array_equal(s['qpos'][ids[0]],expected):
                    bad.append(dict(category='INITIAL_STATE_MISMATCH',reason='recorded tick0 differs from frozen fixture cast to engine dtype',blocked_object=case['id'],minimum_gap_m=None,gap_status='not_applicable'))
                first=ids[0];d.qpos[:]=s['qpos'][first];mujoco.mj_kinematics(m,d)
                # m.stat.extent supplies the scene-scale distance query limit;
                # zero is the geometric non-intersection boundary, not a fitted tolerance.
                gap=float(mujoco.mj_geomDistance(m,d,base,box,float(m.stat.extent),None))
                rows=c[(c[:,0]==ci)&(np.rint(c[:,1]/dt).astype(int)==round(case['settle_s']/dt))]
                counts=[];forces=[]
                for name,gs in rollers.items():
                    wheelrows=rows[np.array([(int(x[2])==floor and int(x[3]) in gs) or
                        (int(x[3])==floor and int(x[2]) in gs) for x in rows],dtype=bool)]
                    counts.append(len(wheelrows));forces.append(float(wheelrows[:,17].sum()))
                initial.append(dict(run=folder.name,case=case['id'],initial_base_box_gap_m=gap,
                    nonoverlap=gap>=0,settled_wheel_floor_contacts_fl_fr_rl_rr=counts,
                    settled_wheel_floor_normal_N_fl_fr_rl_rr=forces,geometry_evaluator='C312 box-box geometry on recorded state; contact counts/forces from actual engine'))
            if not np.isfinite(s['qpos']).all() or not np.isfinite(s['qvel']).all() or not np.isfinite(c).all():
                bad.append(dict(category='NONFINITE_RAW',reason='state/contact contains nonfinite values',blocked_object=folder.name,minimum_gap_m=None,gap_status='not_applicable'))
        records.append(dict(run=folder.name,status=r['status'],planned_tape_complete=bool(iscomplete),
            completed_cases=r.get('completed_cases',0),raw_hash_manifest_checked=manifest.is_file(),errors=bad))
        errors.extend(bad)
    paired={}
    if (a.raw/'warp-baseline-v2/result.json').is_file():
        c=json.loads((a.raw/'cpu316-v2/result.json').read_text());w=json.loads((a.raw/'warp-baseline-v2/result.json').read_text())
        paired=dict(C316_Warp_physics_hashes_equal=c['physics_hashes']==w['physics_hashes'],
            fixture_equal=c['fixture_sha256']==w['fixture_sha256'],xml_equal=c['xml_sha256']==w['xml_sha256'])
    v1=np.load(a.raw/'cpu312-v1/states.npz');v2=np.load(a.raw/'cpu312-v2/states.npz')
    recording_path_invariant={key:np.array_equal(v1[key],v2[key]) for key in v1.files}
    a.out.mkdir(parents=True,exist_ok=True)
    (a.out/'integrity.json').write_text(json.dumps(dict(records=records,errors=errors,paired=paired,
        C312_recorder_correction_arrays_equal=recording_path_invariant,weld_active0_count=int(np.count_nonzero(m.eq_active0)),
        raw=str(a.raw),reproduce=list(__import__('sys').argv)),indent=2,allow_nan=False)+'\n')
    (a.out/'initial-contact-audit.json').write_text(json.dumps(dict(rows=initial),separators=(',',':'),allow_nan=False)+'\n')
    print(json.dumps(dict(runs=len(records),complete=sum(x['planned_tape_complete'] for x in records),
        cases=len(initial),errors=len(errors),paired=paired,C312_recording_invariant=recording_path_invariant)))
    if errors:raise SystemExit('raw integrity failures')


if __name__=='__main__':main()
