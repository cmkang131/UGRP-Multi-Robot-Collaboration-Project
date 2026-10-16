"""v178: own epoch recovery + evaluation-only cyan supervision to route termination."""
import argparse,json,os
from pathlib import Path
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure
from harness import s4_pair_epochs as epoch
from scripts import run_s4_pair_live9 as old

ROOT=old.ROOT
RECORD='experiments/2026-10-06-s4-llm/s4live10'
PLAN=RECORD+'/README.md'
BUNDLE_ID='zone-s4-pair-live-v178'
VERSION='7.71.0'
WORKFLOW='configs/simulation_workflows.d/s4_pair_live_v178.json'


def bundle(sha,condition,seed=601,*,reconnect=False,rounds=False,cyan=False):
    if any(type(v) is not bool for v in (reconnect,rounds,cyan)):raise ValueError('recovery switches must be bool')
    b=bind(old.bundle,RECORD=RECORD,PLAN=PLAN,BUNDLE_ID=BUNDLE_ID,VERSION=VERSION,WORKFLOW=WORKFLOW)(
        sha,condition,seed,inspect=True,retry=True,censor=True)
    b.update(schema='ugrp.s4_pair_live.v178',case_cap_s=900.,wall_cap_s=10800.,
        calls_per_actor=450,calls_total=1350,token_cap=27000000,utterances_per_actor=240,utterances_total=480,
        raw_budget_bytes=2*1024**3,epoch_reconnect=reconnect,go_ack_rounds=rounds,
        cyan_drop_supervisor='contact_com_v1' if cyan else 'off',
        handshake_deadline_s={'GO':20.,'ACK':20.} if rounds else 20.,
        stage_scope='complete existing eight-leg beam route to goal; no partial-distance success')
    paths=set(source_closure(ROOT,['scripts/run_s4_pair_live10.py','scripts/submit_s4_live10.py',
        'scripts/evaluate_s4_live10.py']))|{WORKFLOW,PLAN,RECORD+'/plan.json',RECORD+'/release.json'}
    b['source_sha256'].update({p:old.old.admission.old.sha(ROOT/p) for p in paths});return b


class Extension(old.Extension):
    def __init__(self,out,b):
        super().__init__(out,b['carry_lease_renewal'],inspect=True,retry=True);self.b=b
    def components(self):
        return epoch.base.Link,epoch.Host,{'handshake':epoch.Handshake(
            carry_lease_renewal=self.renewal,epoch_reconnect=self.b['epoch_reconnect'],go_ack_rounds=self.b['go_ack_rounds'])}
    def driver(self,host,runtime):
        self.pair_driver=epoch.Driver(host,runtime,go_ack_retry=True,
            on_admit=lambda r,e,t:old.configure(r,e,t,True));return self.pair_driver


def run(b,out,receipt):
    from sim.s4_cyan_supervisor import PhysicsBackend
    e=Extension(out,b)
    def backend(*args,**kwargs):
        value=PhysicsBackend(*args,**kwargs)
        value.states_getter=lambda:{r:p.controller.state for r,p in
            getattr(getattr(e,'pair_driver',None),'endpoints',{}).items()};return value
    def setup(scenario):
        from sim.s3_stage_origin import initialize
        return initialize(old.old.live.setup_record(scenario),'pair',b['stage_origin']['public_start_xy_m'],b['stage_origin']['option'])
    result=bind(old.old.live.run,PLAN=PLAN,setup_record=setup)(b,out,receipt,pair_extension=e,backend_factory=backend)
    old.old.live.write(out/'reinspection.json',{r:{k:getattr(ep.controller,k,None)
        for k in ('s3_route_resume','s3_reacquire')} for r,ep in getattr(e.pair_driver,'endpoints',{}).items()})
    old.old.live.write(out/'go-ack-retries.json',e.pair_driver.retry_events)
    old.old.live.write(out/'epoch-reconnections.json',e.pair_driver.epoch_transitions)
    old.old.live.artifact_manifest(out);return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',choices=old.old.live.stage.CONDITIONS,required=True);p.add_argument('--seed',type=int,choices=(601,602),default=601)
    for flag in ('epoch-reconnect','go-ack-rounds','cyan-supervisor'):p.add_argument('--'+flag,action='store_true')
    p.add_argument('--relay-receipt',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:
        print(json.dumps({'execution_started':False,'bundle_id':BUNDLE_ID,'seed':a.seed,
            'epoch_reconnect':a.epoch_reconnect,'go_ack_rounds':a.go_ack_rounds,'cyan_supervisor':a.cyan_supervisor}));return 0
    old.old.persistent_output(a.output);old.old.live.previous.archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    old.old.live.write(a.output.parent/'driver.json',{'pid':os.getpid(),'pgid':os.getpgid(0),'job':a.output.parent.name,'source_sha':a.expected_source_sha})
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.condition,a.seed,reconnect=a.epoch_reconnect,
        rounds=a.go_ack_rounds,cyan=a.cyan_supervisor),a.output,a.relay_receipt)
    finally:undo()
    print(json.dumps(r));return int(r['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
