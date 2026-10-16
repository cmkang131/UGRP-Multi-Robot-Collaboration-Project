"""v181: default-off floor support and own protocol-feedback recovery."""
import argparse,json,os
from pathlib import Path
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure
from scripts import run_s4_pair_live10 as old
ROOT=old.ROOT
RECORD='experiments/2026-10-06-s4-llm/s4live10-r3'
PLAN=RECORD+'/README.md'
BUNDLE_ID='zone-s4-pair-live-v181'
VERSION='7.74.0'
WORKFLOW='configs/simulation_workflows.d/s4_pair_live_v181.json'


def bundle(sha,condition,seed=601,*,reconnect=False,rounds=False,cyan=False,floor=False,feedback=False):
    if any(type(v) is not bool for v in (floor,feedback)):raise ValueError('recovery toggles must be bool')
    b=bind(old.bundle,RECORD=RECORD,PLAN=PLAN,BUNDLE_ID=BUNDLE_ID,VERSION=VERSION,WORKFLOW=WORKFLOW)(
        sha,condition,seed,reconnect=reconnect,rounds=rounds,cyan=cyan)
    b.update(schema='ugrp.s4_pair_live.v181',cyan_floor_support=floor,carry_protocol_feedback=feedback)
    paths=set(source_closure(ROOT,['scripts/run_s4_pair_live10c.py','scripts/submit_s4_live10c.py']))|{WORKFLOW,PLAN,RECORD+'/plan.json'}
    b['source_sha256'].update({p:old.old.old.admission.old.sha(ROOT/p) for p in paths});return b


class Extension(old.Extension):
    def components(self):
        return old.epoch.base.Link,old.epoch.Host,{'handshake':old.epoch.Handshake(
            carry_lease_renewal=self.renewal,epoch_reconnect=self.b['epoch_reconnect'],
            go_ack_rounds=self.b['go_ack_rounds'],carry_protocol_feedback=self.b['carry_protocol_feedback'])}


def run(b,out,receipt):return bind(old.run,Extension=Extension,PLAN=PLAN)(b,out,receipt)


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',choices=old.old.old.live.stage.CONDITIONS,required=True);p.add_argument('--seed',type=int,choices=(601,602),default=601)
    for flag in ('epoch-reconnect','go-ack-rounds','cyan-supervisor','cyan-floor-support','carry-protocol-feedback'):p.add_argument('--'+flag,action='store_true')
    p.add_argument('--relay-receipt',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:print(json.dumps({'execution_started':False,'cyan_floor_support':a.cyan_floor_support,'carry_protocol_feedback':a.carry_protocol_feedback}));return 0
    old.old.old.persistent_output(a.output);old.old.old.live.previous.archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    old.old.old.live.write(a.output.parent/'driver.json',{'pid':os.getpid(),'pgid':os.getpgid(0),'job':a.output.parent.name,'source_sha':a.expected_source_sha})
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.condition,a.seed,reconnect=a.epoch_reconnect,rounds=a.go_ack_rounds,
        cyan=a.cyan_supervisor,floor=a.cyan_floor_support,feedback=a.carry_protocol_feedback),a.output,a.relay_receipt)
    finally:undo()
    print(json.dumps(r));return int(r['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
