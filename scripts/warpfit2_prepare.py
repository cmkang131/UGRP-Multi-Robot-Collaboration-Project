"""Own-gcp6-only warm pulse packing; no physics integration or retuning."""
import argparse
import json
from pathlib import Path
import shutil
from scripts.warpfit import host,dump,digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    a=p.parse_args();host()
    import numpy as np
    old=Path('/home/ugrp/ugrp-sim/runs/warpfit/primitive-v1')
    out=a.root/'fixtures';out.mkdir(parents=True)
    for kind in ('box','beam'):
        shutil.copytree(old/kind,out/kind)
    src=old/'drive-clear-v1';dst=out/'drive';shutil.copytree(src,dst)
    f=np.load(src/'fixture.npz');original=np.load(old/'drive/fixture.npz')
    arrays={k:f[k] for k in f.files if k in ('qpos','qvel','ctrl','qacc_warmstart','tree_sleep_policy',
        'cam_pos','cam_quat','cam_resolution','cam_sensorsize','cam_intrinsic')}
    meta=json.loads((src/'fixture.json').read_text())
    original_meta=json.loads((old/'drive/fixture.json').read_text())
    dt=.00025  # frozen original XML, unchanged
    forward=f['forward-0.1'];stop=forward[:4000];tail=forward[-4000:]
    cases=[];tapes={}
    for name in ('forward-0.1','left-0.06','left-0.4','turn-0.1'):
        source='left-0.5' if name=='left-0.4' else name
        row=dict(next(r for r in original_meta['cases'] if r['id']==source))
        if name=='left-0.4':
            # User requested a400ms diagnostic. Copy the original500ms tape's
            # first400ms powered segment, followed by its unchanged1s stop.
            # This does not extrapolate an odometry prediction or tune drive.
            tapes[name]=np.concatenate([original[source][:5600],original[source][-4000:]])
            row.update(id=name,duration_s=.4,v122=None,
                prediction_status='400ms unregistered; no extrapolation',source_tape=source)
        else:tapes[name]=original[name].copy()
        cases.append(row)
    for duration in (.06,.4):
        source=next(r for r in cases if r['id']==f'left-{duration:g}')
        name=f'warm-left-{duration:g}'
        # Exactly original forward100ms + original1s stop, then original
        # lateral pulse and1s stop. All 35% commands are copied, not inferred.
        lateral=tapes[source['id']][4000:]
        tapes[name]=np.concatenate([forward,lateral])
        cases.append(dict(source,id=name,settle_s=2.1,warm_forward_s=.1,warm_stop_s=1.,
            v122=None,prediction_status='warm state not registered; no extrapolation'))
    names=list(tapes);length=max(map(len,tapes.values()))
    arrays.update(tapes)
    arrays['warm6']=np.stack([np.concatenate([tapes[n],np.tile(tail[-1],(length-len(tapes[n]),1))]) for n in names],axis=1)
    for i,n in enumerate(names):assert np.array_equal(arrays['warm6'][:len(tapes[n]),i],tapes[n])
    meta.update(cases=cases,groups={'warm6':names},protocol='warpfit2-warm-v1',
        warm_basis='model-variant-plan: original100ms forward + original1s stop + original60/400ms lateral',
        source_fixture_sha256=digest(src/'fixture.npz'),original_drive_sha256=digest(old/'drive/fixture.npz'))
    np.savez_compressed(dst/'fixture.npz',**arrays);dump(dst/'fixture.json',meta)
    dump(a.root/'fixture-hashes.json',{str(x.relative_to(out)):digest(x) for x in out.rglob('*') if x.is_file()})


if __name__=='__main__':main()
