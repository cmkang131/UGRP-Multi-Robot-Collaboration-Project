"""v176: unchanged S3 calibrated reinspection + bounded GO retry/terminal censor."""
import argparse
import json
import os
from pathlib import Path
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure
from harness.s4_pair_recovery import Driver
from scripts import run_s4_pair_live8 as old

ROOT = old.ROOT
RECORD = 'experiments/2026-10-06-s4-llm/s4live9'
PLAN = RECORD+'/README.md'
BUNDLE_ID = 'zone-s4-pair-live-v176'
VERSION = '7.69.0'
WORKFLOW = 'configs/simulation_workflows.d/s4_pair_live_v176.json'


def configure(rid, ep, now, inspect=False):
    old.configure(rid, ep, now)
    if inspect:
        from harness.zone_s3_route_resume import attach, Options
        from harness.zone_s3_reacquire import attach as reacquire, Options as Reacquire
        attach(ep, Options(inspect_before_look=True))
        # The existing inspect wrapper preserves pan. Use upstream's existing
        # canonical pan adapter too, without altering S3 source/calibration.
        reacquire(ep, Reacquire(canonical_pan=True))


def bundle(sha, condition, seed=601, *, inspect=False, retry=False, censor=False):
    if any(type(v) is not bool for v in (inspect,retry,censor)):
        raise ValueError('S4 recovery switches must be bool')
    b=bind(old.bundle,RECORD=RECORD,PLAN=PLAN,BUNDLE_ID=BUNDLE_ID,VERSION=VERSION,
        WORKFLOW=WORKFLOW)(sha,condition,seed,old.RENEWAL_MODE)
    b.update(schema='ugrp.s4_pair_live.v176',case_cap_s=600.,wall_cap_s=3000.,
        inspect_before_look=inspect,canonical_pan=inspect,go_ack_retry=retry,terminal_censor=censor,
        stage_scope='uninterrupted existing eight-leg beam route; judge restart and full goal separately',
        calls_per_actor=300,calls_total=900,token_cap=18000000,utterances_per_actor=160,utterances_total=320,
        termination='own pair executors terminal, pair/physical/HOST failure, or finite horizon; never second-leg success')
    paths=set(source_closure(ROOT,['scripts/run_s4_pair_live9.py','scripts/submit_s4_live9.py',
        'scripts/evaluate_s4_live9.py'])) | {WORKFLOW,PLAN,RECORD+'/plan.json',RECORD+'/release.json'}
    b['source_sha256'].update({p:old.admission.old.sha(ROOT/p) for p in paths})
    return b


class Extension(old.Extension):
    def __init__(self, out, renewal, *, inspect=False, retry=False):
        super().__init__(out,renewal)
        self.inspect,self.retry=inspect,retry
        self.terminal_since=None
        self.last_now=0.

    def driver(self, host, runtime):
        self.pair_driver=Driver(host,runtime,go_ack_retry=self.retry,
            on_admit=lambda r,e,t:configure(r,e,t,self.inspect))
        return self.pair_driver

    def terminal(self):
        terminal=bool(len(self.pair_driver.endpoints)==2 and all(
            e.terminal for e in self.pair_driver.endpoints.values()))
        if terminal and self.terminal_since is None:self.terminal_since=self.last_now
        # A fixed own-software terminal settle; no contact/success feedback.
        return bool(terminal and self.last_now-self.terminal_since>=.6-1e-8)

    def record_states(self,runtime,now):
        self.last_now=now
        return super().record_states(runtime,now)

    def health(self, backend, runtime, host, causal, rel, result=None):
        if result is not None and result.get('status')=='HOST_ERROR':
            # Physics has already stopped and held all robots. Let the finite
            # command-free finalizer preserve the manifest before EXIT/fetch.
            result={**result,'status':'TERMINAL_FINALIZING'}
        return super().health(backend,runtime,host,causal,rel,result=result)


def run(b,out,receipt):
    extensions=[]
    def extension(out,renewal):
        e=Extension(out,renewal,inspect=b['inspect_before_look'],retry=b['go_ack_retry'])
        extensions.append(e);return e
    result=bind(old.run,Extension=extension,PLAN=PLAN)(b,out,receipt)
    for e in extensions:
        old.live.write(out/'reinspection.json',{r:{k:getattr(ep.controller,k,None)
            for k in ('s3_route_resume','s3_reacquire')}
            for r,ep in getattr(getattr(e,'pair_driver',None),'endpoints',{}).items()})
        old.live.write(out/'go-ack-retries.json',getattr(getattr(e,'pair_driver',None),'retry_events',[]))
    old.live.artifact_manifest(out)
    return result


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--condition',choices=old.live.stage.CONDITIONS,required=True)
    p.add_argument('--seed',type=int,choices=(601,602),default=601)
    for flag in ('inspect-before-look','go-ack-retry','terminal-censor'):p.add_argument('--'+flag,action='store_true')
    p.add_argument('--relay-receipt',type=Path,required=True);p.add_argument('--execute',action='store_true')
    a=p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False,bundle_id=BUNDLE_ID,seed=a.seed,
            inspect_before_look=a.inspect_before_look,go_ack_retry=a.go_ack_retry,terminal_censor=a.terminal_censor)));return 0
    old.persistent_output(a.output);old.live.previous.archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    old.live.write(a.output.parent/'driver.json',dict(pid=os.getpid(),pgid=os.getpgid(0),job=a.output.parent.name,source_sha=a.expected_source_sha))
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:
        result=run(bundle(a.expected_source_sha,a.condition,a.seed,inspect=a.inspect_before_look,
            retry=a.go_ack_retry,censor=a.terminal_censor),a.output,a.relay_receipt)
    finally:undo()
    print(json.dumps(result));return int(result['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
