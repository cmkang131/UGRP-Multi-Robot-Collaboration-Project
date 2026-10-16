"""gcp6-only fixed primitive extraction; no physics parameter retuning."""
import argparse
import json
from pathlib import Path
import shutil

from scripts.warpfit import dump,digest,host


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--enabled',action='store_true')
    a=p.parse_args()
    if not a.enabled:p.error('--enabled required')
    host()
    import numpy as np
    root=a.root.resolve();out=root/'primitive-v1';out.mkdir()
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
