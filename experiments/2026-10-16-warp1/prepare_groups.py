"""gcp2-only static model grouping preflight; all setup physics stays remote."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--teacher-source',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--indices',default='0,4');p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    sys.path.insert(0,str(a.source/'scripts'))
    from simalt_host import gcp2_identity
    host=gcp2_identity()
    sys.path.insert(0,str(a.teacher_source))
    from simalt_pilot import world_for
    from warp_act_core import model_key
    plans=json.loads(a.plan.read_text())['episodes'];rows=[]
    for i in map(int,a.indices.split(',')):
        world,scene=world_for(plans[i],False)
        try:
            rows.append(dict(index=i,seed=plans[i]['seed'],item=plans[i]['item_id'],
                model_key=model_key(world.scene_xml),xml_sha256=hashlib.sha256(world.scene_xml.encode()).hexdigest(),
                qpos_sha256=hashlib.sha256(world.data.qpos.tobytes()).hexdigest(),
                initial_sim_t=float(world.data.time),
                counts={k:int(getattr(world.model,k)) for k in ('nq','nv','nu','ngeom','nbody')}))
        finally:world.close()
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(dict(host=host,rows=rows,same_static_model=len({r['model_key'] for r in rows})==1,
        physics_scope='C setup only; no teacher rollout or gate',source=str(a.source),
        teacher_source=str(a.teacher_source),reproduce=sys.argv),indent=2)+'\n')
    print(a.out.read_text())


if __name__=='__main__':main()
