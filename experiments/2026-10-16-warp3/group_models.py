"""Exact pinned-API compatibility groups, no model approximation or rollout."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--references',type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(a.source/'scripts'))
    from simalt_host import gcp2_identity
    host=gcp2_identity()
    from simalt_compiled_compat import apply_reference,apply_geometry
    from warp_act_core import runtime_sleep_policy
    import mujoco
    import numpy as np
    import warp as wp
    import mujoco_warp as mjw
    rows=json.loads((a.references/'inventory.json').read_text());groups={};audits=[]
    for row in rows:
        xml=Path(row['actuator']).parent/'world-000/scene.xml'
        m=mujoco.MjModel.from_xml_string(xml.read_text())
        apply_geometry(m,xml,Path(row['geometry']));apply_reference(m,xml,Path(row['actuator']))
        e=mujoco.mjtSleepPolicy
        m.tree_sleep_policy[:]=runtime_sleep_policy(m.tree_sleep_policy,auto=int(e.mjSLEEP_AUTO),auto_never=int(e.mjSLEEP_AUTO_NEVER),
            auto_allowed=int(e.mjSLEEP_AUTO_ALLOWED),never=int(e.mjSLEEP_NEVER),allowed=int(e.mjSLEEP_ALLOWED))
        converted=mjw.put_model(m);digest=hashlib.sha256();static=[];batched=[]
        def visit(obj,prefix=''):
            for f in dataclasses.fields(obj):
                value=getattr(obj,f.name);name=prefix+f.name
                if dataclasses.is_dataclass(value):visit(value,name+'.')
                elif isinstance(value,wp.array):
                    v=value.numpy()
                    if name=='dof_length' or getattr(f.type,'shape',())[:1]==('*',):batched.append(name)
                    else:
                        digest.update(name.encode()+repr((v.shape,v.dtype.str)).encode()+v.tobytes());static.append(name)
                elif isinstance(value,(int,float,bool,str,type(None))):digest.update(repr((name,value)).encode())
        visit(converted);key=digest.hexdigest();groups.setdefault(key,[]).append(row['index'])
        audits.append(dict(index=row['index'],seed=row['seed'],group=key,model_counts=row['model_counts'],
            dof_length_sha256=hashlib.sha256(m.dof_length.tobytes()).hexdigest()))
        del converted,m
    report=dict(host=host,groups=[dict(key=k,indices=v) for k,v in groups.items()],rows=audits,
        exact_shared_fields=static,world_batchable_fields=batched,scope='all unbatchable arrays/scalars exact; dof_length preserved by versioned world-indexed sleep adapter')
    (a.references/'model-groups.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(cases=len(rows),groups=[v for v in groups.values()])))


if __name__=='__main__':main()
