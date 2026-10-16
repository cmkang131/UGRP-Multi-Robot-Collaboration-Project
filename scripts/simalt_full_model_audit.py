"""gcp2 zero-step audit of every numeric compiled MjModel array and option."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--name',required=True)
    p.add_argument('--compiled312',action='store_true')
    a=p.parse_args()
    from simalt_host import gcp2_identity
    host=gcp2_identity()
    import mujoco
    import numpy as np
    from simalt_compiled_compat import apply_reference,apply_geometry
    xml=a.fixture/'scene.xml'
    m=mujoco.MjModel.from_xml_path(str(xml))
    if a.compiled312:
        apply_reference(m,xml,a.root/'compiled-312.json')
        apply_geometry(m,xml,a.root/'compiled-geometry312.npz')
    arrays={k:getattr(m,k).copy() for k in dir(m) if not k.startswith('_')
            and isinstance(getattr(m,k),np.ndarray) and getattr(m,k).dtype.kind!='O'}
    path=a.root/('full-model-'+a.name+'.npz')
    with path.open('xb') as stream:np.savez_compressed(stream,**arrays)
    options={}
    for k in dir(m.opt):
        if k.startswith('_'):continue
        value=getattr(m.opt,k)
        if isinstance(value,np.ndarray):options[k]=value.tolist()
        elif isinstance(value,(int,float,bool)):options[k]=value
        elif not callable(value):
            try:options[k]=int(value)
            except (TypeError,ValueError):pass
    record={'host':host,'mujoco':mujoco.__version__,'physics_steps':0,
        'compiled312':a.compiled312,'arrays':len(arrays),'options':options,
        'npz_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'xml_sha256':hashlib.sha256(xml.read_bytes()).hexdigest()}
    Path(str(path)+'.json').write_text(json.dumps(record,indent=2)+'\n')
    if a.name!='C312':
        reference=np.load(a.root/'full-model-C312.npz',allow_pickle=False)
        rmeta=json.loads((a.root/'full-model-C312.npz.json').read_text())
        different=[]
        for k in sorted(set(reference.files)&set(arrays)):
            rv,cv=reference[k],arrays[k]
            if rv.shape!=cv.shape:different.append({'array':k,'shape_C312':list(rv.shape),'shape_candidate':list(cv.shape)});continue
            if not np.array_equal(rv,cv):
                mask=rv!=cv;indices=np.argwhere(mask)
                different.append({'array':k,'entries':int(mask.sum()),
                    'max_abs':float(np.max(np.abs(rv.astype(float)-cv.astype(float)))),
                    'first_entries':[{'index':i.tolist(),'C312':float(rv[tuple(i)]),'candidate':float(cv[tuple(i)])} for i in indices[:5]]})
        result={'candidate':a.name,'common_arrays':len(set(reference.files)&set(arrays)),
            'C312_only':sorted(set(reference.files)-set(arrays)),
            'candidate_only':sorted(set(arrays)-set(reference.files)),'different':different,
            'option_differences':{k:{'C312':rmeta['options'].get(k),'candidate':options.get(k)}
                for k in sorted(set(rmeta['options'])|set(options)) if rmeta['options'].get(k)!=options.get(k)}}
        (a.root/('full-model-differences-'+a.name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'common_arrays':result['common_arrays'],'different':[(x['array'],x.get('entries')) for x in different],
                          'option_differences':result['option_differences']},indent=2))


if __name__=='__main__':main()
