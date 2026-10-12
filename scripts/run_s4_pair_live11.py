"""v182: bounded synchronous 429 recovery, full reply examples and existing S3 backoff."""
import argparse,json,os
from pathlib import Path
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure
from scripts import run_s4_pair_live10c as prior
from scripts import run_s4_pair_live10 as old
from harness import s4_reply_contract as reply
from harness.s4_call_recovery import RetryLedger
ROOT=old.ROOT
RECORD='experiments/2026-10-06-s4-llm/s4live11'
PLAN=RECORD+'/README.md'
BUNDLE_ID='zone-s4-pair-live-v182'
VERSION='7.75.0'
WORKFLOW='configs/simulation_workflows.d/s4_pair_live_v182.json'


def bundle(sha,condition,seed=601,*,reconnect=False,rounds=False,cyan=False,floor=False,feedback=False,retry_429=False,reply_contract=False,clipped_backoff=False):
    if any(type(v) is not bool for v in (floor,feedback,retry_429,reply_contract,clipped_backoff)):raise ValueError('recovery toggles must be bool')
    b=bind(old.bundle,RECORD=RECORD,PLAN=PLAN,BUNDLE_ID=BUNDLE_ID,VERSION=VERSION,WORKFLOW=WORKFLOW)(
        sha,condition,seed,reconnect=reconnect,rounds=rounds,cyan=cyan)
    b.update(schema='ugrp.s4_pair_live.v182',cyan_floor_support=floor,carry_protocol_feedback=feedback,
        retry_429=retry_429,reply_contract=reply_contract,clipped_backoff=clipped_backoff,
        retry_policy={"max_retries":6,"max_wall_s_per_call":300,"backoff_base_s":2,"backoff_cap_s":60,"jitter_fraction":.2},
        wall_cap_s=10800.)
    paths=set(source_closure(ROOT,['scripts/run_s4_pair_live11.py','scripts/submit_s4_live11.py']))|{WORKFLOW,PLAN,RECORD+'/plan.json'}
    b['source_sha256'].update({p:old.old.old.admission.old.sha(ROOT/p) for p in paths});return b


class Extension(prior.Extension):
    def components(self):
        link,_,extra=super().components();h=extra['handshake']
        h.retry_429=self.b['retry_429'];h.reply_contract=self.b['reply_contract']
        return link,reply.Host,extra
    def driver(self,host,runtime):
        def configure(rid,ep,now):
            old.old.old.configure(rid,ep,now)
            from harness.zone_s3_route_resume import attach,Options
            from harness.zone_s3_reacquire import attach as reacquire,Options as Reacquire
            attach(ep,Options(inspect_before_look=True))
            reacquire(ep,Reacquire(canonical_pan=True,clipped_backoff=self.b['clipped_backoff']))
        self.pair_driver=old.epoch.Driver(host,runtime,go_ack_retry=True,on_admit=configure)
        return self.pair_driver


def run(b,out,receipt):
    from sim.s4_cyan_supervisor import PhysicsBackend
    from scripts import run_s4_live as live
    e=Extension(out,b); held={'issued_commands':0}
    def backend(*args,**kwargs):
        value=PhysicsBackend(*args,**kwargs)
        value.states_getter=lambda:{r:p.controller.state for r,p in
            getattr(getattr(e,'pair_driver',None),'endpoints',{}).items()}
        held['backend']=value
        original_issue=value.issue
        def issue(*args,**kwargs):
            held['issued_commands']+=1
            return original_issue(*args,**kwargs)
        value.issue=issue
        return value
    def setup(scenario):
        from sim.s3_stage_origin import initialize
        return initialize(live.setup_record(scenario),'pair',b['stage_origin']['public_start_xy_m'],b['stage_origin']['option'])
    def ledger(**kwargs):
        value=RetryLedger(retry_429=b['retry_429'],**kwargs)
        value.retry_snapshot=lambda:dict(sim_s=held['backend'].now,
            frame=held['backend'].frame,issued_commands=held['issued_commands'])
        return value
    result=bind(live.run,PLAN=PLAN,setup_record=setup,TunnelLedger=ledger)(b,out,receipt,pair_extension=e,backend_factory=backend)
    live.write(out/'reinspection.json',{r:{k:getattr(ep.controller,k,None)
        for k in ('s3_route_resume','s3_reacquire')} for r,ep in getattr(e.pair_driver,'endpoints',{}).items()})
    live.write(out/'go-ack-retries.json',e.pair_driver.retry_events)
    live.write(out/'epoch-reconnections.json',e.pair_driver.epoch_transitions)
    live.artifact_manifest(out);return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',choices=old.old.old.live.stage.CONDITIONS,required=True);p.add_argument('--seed',type=int,choices=(601,602),default=601)
    for flag in ('epoch-reconnect','go-ack-rounds','cyan-supervisor','cyan-floor-support','carry-protocol-feedback','retry-429','reply-contract','clipped-backoff'):p.add_argument('--'+flag,action='store_true')
    p.add_argument('--relay-receipt',type=Path,required=True);p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:print(json.dumps({'execution_started':False,'cyan_floor_support':a.cyan_floor_support,'carry_protocol_feedback':a.carry_protocol_feedback}));return 0
    old.old.old.persistent_output(a.output);old.old.old.live.previous.archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    old.old.old.live.write(a.output.parent/'driver.json',{'pid':os.getpid(),'pgid':os.getpgid(0),'job':a.output.parent.name,'source_sha':a.expected_source_sha})
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.condition,a.seed,reconnect=a.epoch_reconnect,rounds=a.go_ack_rounds,
        cyan=a.cyan_supervisor,floor=a.cyan_floor_support,feedback=a.carry_protocol_feedback,retry_429=a.retry_429,reply_contract=a.reply_contract,
        clipped_backoff=a.clipped_backoff),a.output,a.relay_receipt)
    finally:undo()
    print(json.dumps(r));return int(r['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
