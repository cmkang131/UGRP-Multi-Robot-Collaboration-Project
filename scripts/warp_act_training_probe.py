"""Finite training-only critic lane probe, without an actor or RL update."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled',action='store_true')
    for key in ('physics-python','api-source','qualified-source','teacher-source','qualification',
                'references','compiled-reference','compiled-geometry','plans','out'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if not a.enabled or sys.platform!='linux':p.error('default OFF, Linux gcp2 only')
    sys.path.insert(0,str(a.api_source/'scripts'))
    from warp_act_rpc import Client
    options={k:getattr(a,k) for k in ('qualified_source','teacher_source','qualification','references',
                                    'compiled_reference','compiled_geometry')}
    plans=json.loads(a.plans.read_text())['episodes'][:1]
    client=Client(python=a.physics_python,out=a.out,nworld=1,enabled=True,training=True,**options)
    report=dict(status='running',passed=False,scope='training critic lane wiring only; no RL update or task gate',
                probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    try:
        client.reset(plans)
        before=client.read_actor(0)
        truth,critic=client.read_training(0)
        if client.read_actor(0)!=before:raise RuntimeError('critic read mutated public actor')
        obs,_=before
        client.step([dict(command=dict(obs['issued'][-1],t=obs['t'],wheels=[0.]*4,duration_s=[0.]*4),done=False)])
        after=client.read_actor(0)
        next_truth,next_critic=client.read_training(0)
        # Owner and client both validate the fixed observation schema. No
        # privileged fields are added to public observations after critic reads.
        if client.read_actor(0)!=after:raise RuntimeError('critic read mutated stepped public actor')
        if truth.target_xy is not None or next_truth.target_xy is not None:
            raise RuntimeError('unsupported centre annotation was supplied')
        if not critic or len(critic)!=len(next_critic):raise RuntimeError('unstable critic shape')
        report.update(status='complete',passed=True,actor_unchanged_by_critic=True,
                      actor_fields=sorted(after[0]),critic_length=len(critic),
                      truth_fields=sorted(vars(truth)),centre_mask_annotation_supported=False,
                      private_truth_before=vars(truth),private_truth_after=vars(next_truth))
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error));raise
    finally:
        try:client.close('probe_control_budget_end')
        except BaseException as error:report.update(status='HOST_ERROR',passed=False,close_error=repr(error))
        report['raw_sha256']={str(x.relative_to(a.out)):hashlib.sha256(x.read_bytes()).hexdigest()
                              for x in a.out.rglob('*') if x.is_file()}
        (a.out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
