"""gcp6-only fixed primitive extraction; no physics parameter retuning."""
import argparse
import json
from pathlib import Path
import shutil

from scripts.warpfit import dump,digest,host,load


def clear_drive(root):
    """Reuse PR564's demonstrated setup intervention, no mj_step or tuning."""
    import numpy as np
    import mujoco
    from types import SimpleNamespace
    src=root/'primitive-v1/drive';dst=root/'primitive-v1/drive-clear-v1';dst.mkdir()
    m,d,archive,meta,xml,_=load(SimpleNamespace(fixture=src,profile='baseline_noslip10',engine='cpu'))
    for name in ('scene.xml','actuator312.json','geometry312.npz','geometry312.npz.json'):
        shutil.copyfile(src/name,dst/name)
    names=['forward-0.1','left-0.06','turn-0.1']
    state=('qpos','qvel','ctrl','qacc_warmstart','tree_sleep_policy','cam_pos','cam_quat',
           'cam_resolution','cam_sensorsize','cam_intrinsic')
    arrays={k:archive[k].copy() for k in (*state,*names) if k in archive.files}
    base=m.geom('r1__base_lower_collision').id;box=m.geom('cargo_box_00_geom').id
    # Exact measured cause intervention from PR564 drivecheck.py178..189:
    # twice original XY bounding-radius sum, direction away from the base.
    shift=2*(np.linalg.norm(m.geom_size[base,:2])+np.linalg.norm(m.geom_size[box,:2]))
    direction=1 if d.geom_xpos[box,1]>=d.geom_xpos[base,1] else -1
    adr=int(m.jnt_qposadr[m.body_jntadr[m.geom_bodyid[box]]])
    before=arrays['qpos'].copy();arrays['qpos'][adr+1]+=direction*shift
    def pair_gap():
        values=[float(c.dist) for c in d.contact if set(map(int,c.geom))=={base,box}]
        return dict(minimum_gap_m=min(values) if values else None,
                    gap_status='contact_distance' if values else 'pair_absent_from_contact_array; positive separation not measured')
    original_gap=pair_gap();d.qpos[:]=arrays['qpos'];mujoco.mj_forward(m,d);new_gap=pair_gap()
    if new_gap['minimum_gap_m'] is not None and new_gap['minimum_gap_m']<0:
        raise ValueError('verified setup intervention did not clear the observed pair')
    changed=np.flatnonzero(before!=arrays['qpos']).tolist()
    if changed!=[adr+1]:raise ValueError('only blocker lateral coordinate may change')
    length=max(len(arrays[k]) for k in names)
    arrays['clear3']=np.stack([np.concatenate([arrays[k],np.tile(arrays[k][-1],(length-len(arrays[k]),1))]) for k in names],axis=1)
    assert all(np.array_equal(arrays['clear3'][:len(arrays[k]),i],archive[k]) for i,k in enumerate(names))
    meta.update(groups={'clear3':names},cases=[v for v in meta['cases'] if v['id'] in names],
        fixture_ablation=dict(name='drivecheck-clear-overlap-v1',object='cargo_box_00',
            lateral_shift_m=float(direction*shift),changed_qpos_indices=changed,
            before_xyz=before[adr:adr+3].tolist(),after_xyz=arrays['qpos'][adr:adr+3].tolist(),
            before_gap=original_gap,after_gap=new_gap,
            basis='PR564 measured initial overlap and clearance intervention; 2*(original XY bounding radii sum)',
            production_fix=False,physics_steps=0),
        extraction='same three registered drivecheck short pulses; original tape bytes; setup-only known blocker relocation')
    np.savez_compressed(dst/'fixture.npz',**arrays);dump(dst/'fixture.json',meta)
    dump(dst/'SHA256.json',{p.name:digest(p) for p in dst.iterdir() if p.is_file()})
    cap=json.loads((root/'inputs/drivecheck-capacity-reference-v2.json').read_text())
    dump(root/'drive-clear-capacity-reference.json',dict(max_ncon=cap['max_ncon'],max_nefc=cap['max_nefc'],
        basis='observed PR564 every-step maxima, allocation only; actual import also included; no result pooling',
        source=cap,source_sha256=digest(root/'inputs/drivecheck-capacity-reference-v2.json')))
    print(json.dumps(meta['fixture_ablation']))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--drive-clear-v1',action='store_true')
    a=p.parse_args()
    if not a.enabled:p.error('--enabled required')
    host()
    import numpy as np
    root=a.root.resolve()
    if a.drive_clear_v1:clear_drive(root);return
    out=root/'primitive-v1';out.mkdir()
    for kind in ('box','beam','drive'):
        src=root/kind;dst=out/kind;dst.mkdir()
        for name in ('scene.xml','actuator312.json','geometry312.npz','geometry312.npz.json'):
            shutil.copyfile(src/name,dst/name)
        archive=np.load(src/'fixture.npz');arrays={k:archive[k] for k in archive.files}
        meta=json.loads((src/'fixture.json').read_text());meta['protocol']='primitive-v1'
        meta['original_fixture_sha256']=digest(src/'fixture.npz')
        # Box: original close1.2s + lift1.5s + first3s lift_settle. These
        # durations are frozen teacher phases, not new acceptance constants.
        if kind=='box':
            arrays['tape']=arrays['tape'][:22800]  # 5.7 SIM s at unchanged250us.
            meta.update(hold_start_s=2.7,phases=meta['phases'][:57],
                extraction='original fixed tape prefix: close12 + lift15 + loaded_settle30 rows')
        elif kind=='beam':
            # Saved issued tape closes r1 at2.8s, r2 at3.8s; start2.7s
            # immediately before either closure, then retain both lifts.
            sfile=root/'R1-Cref/beam-tape-baseline_noslip10/states.npz'
            states=np.load(sfile);index=int(np.flatnonzero(np.abs(states['t']-2.7)<1e-8)[0])
            arrays['qpos']=states['qpos'][index,0];arrays['qvel']=states['qvel'][index,0]
            arrays['tape']=arrays['tape'][10800:];arrays['ctrl']=arrays['tape'][0]
            arrays['qacc_warmstart']=np.zeros_like(arrays['qvel'])
            meta.update(hold_start_s=3.0,source_state_sha256=digest(sfile),source_state_t=2.7,
                extraction='C reference common pre-close setup at2.7s; unchanged issued tape2.7..6s; no subsequent truth feedback')
        else:
            # Preserve every original pulse byte. N16 main16 + two shortest
            # tail cases requires6+2.1s; N64 all18 requires one6s batch.
            names=[r['id'] for r in meta['cases']]
            tail=['left-0.06','turn-0.1'];main=[n for n in names if n not in tail]
            groups={'group16':main,'tail2':tail,'group64':names}
            for name,ids in groups.items():
                length=max(len(arrays[k]) for k in ids)
                arrays[name]=np.stack([np.concatenate([arrays[k],np.tile(arrays[k][-1],(length-len(arrays[k]),1))]) for k in ids],axis=1)
                assert all(np.array_equal(arrays[name][:len(arrays[k]),i],arrays[k]) for i,k in enumerate(ids))
            meta['groups']=groups;meta['extraction']='packing only; all18 original pulses byte-identical'
        np.savez_compressed(dst/'fixture.npz',**arrays)
        dump(dst/'fixture.json',meta)
    dump(out/'SHA256.json',{str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file()})
    print(out)


if __name__=='__main__':main()
