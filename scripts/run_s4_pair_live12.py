"""v183 transport recovery adapter. Own-map E2E admission remains closed.

The inherited S3 runtime consumes an authored B route. It may only be used with
an explicit legacy-route DEV diagnostic flag, never labelled own-map E2E.
"""
import argparse
import json
from pathlib import Path

from harness.s4_tunnel_recovery import RecoveryLedger
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure

ROOT=Path(__file__).resolve().parents[1]
RECORD='experiments/2026-10-06-s4-llm/s4live12'
PLAN=RECORD+'/README.md'
BUNDLE_ID='zone-s4-pair-live-v183'
VERSION='7.76.0'
WORKFLOW='configs/simulation_workflows.d/s4_pair_live_v183.json'


def bundle(sha,condition,seed=601,*,tunnel_recovery=False,**kwargs):
    from scripts import run_s4_pair_live11 as prior
    if type(tunnel_recovery) is not bool or seed not in (601,602,603):
        raise ValueError('registered toggle and seed required')
    b=bind(prior.bundle,RECORD=RECORD,PLAN=PLAN,BUNDLE_ID=BUNDLE_ID,VERSION=VERSION,
           WORKFLOW=WORKFLOW)(sha,condition,seed if seed in (601,602) else 601,**kwargs)
    # The old pure template admits only 601/602. Seed affects these runtime
    # fields only; no scene, RNG, model or simulation is instantiated here.
    b.update(seed=seed,provider_seeds={r:seed+i for i,r in enumerate(b['provider_seeds'])})
    b.update(schema='ugrp.s4_pair_live.v183',tunnel_recovery=tunnel_recovery,
        e2e_eligible=False,own_map_transport_connected=False,
        tunnel_policy=dict(max_retries=6,max_wall_s=600,same_request_id=True,
            physics='synchronous hold',exhaustion='HOST_ERROR'),
        stage_scope='legacy-route DEV only; own-map E2E and goal correction not connected')
    paths=set(source_closure(ROOT,['scripts/run_s4_pair_live12.py','scripts/s4_proxy_relay.py',
        'scripts/s4_reverse_tunnel.py','scripts/s4_deadline_run.py']))|{WORKFLOW,PLAN,RECORD+'/plan.json'}
    b['source_sha256'].update({p:prior.old.old.old.admission.old.sha(ROOT/p) for p in paths})
    return b


def run(b,out,receipt,*,legacy_route_dev=False):
    # Fail before importing/constructing a world, ledger, network or renderer.
    if not legacy_route_dev:
        raise ValueError('OWN_MAP_TRANSPORT_NOT_CONNECTED: authored B route forbidden for E2E')
    from scripts import run_s4_pair_live11 as prior
    def ledger(**kwargs):
        value=RecoveryLedger(tunnel_recovery=b['tunnel_recovery'],**kwargs)
        (out/'tunnel-toggle.json').write_text(json.dumps(dict(
            tunnel_recovery=b['tunnel_recovery'], relay_receipt_sha256=value.receipt_sha256,
            idempotent_response_journal=value.receipt.get('idempotent_response_journal',False),
            same_request_id=True, exhaustion='HOST_ERROR', physics='synchronous hold'))+'\n')
        return value
    result=bind(prior.run,RetryLedger=ledger,PLAN=PLAN)(b,out,receipt)
    result.update(e2e_eligible=False,legacy_route_dev=True)
    prior.old.old.old.live.write(out/'result.json',result)
    prior.old.old.old.live.artifact_manifest(out)
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--relay-receipt',type=Path,required=True)
    p.add_argument('--condition',choices=('no_comm','peer_ko','leader_ko','structured'),required=True)
    p.add_argument('--seed',type=int,choices=(601,602,603),required=True)
    p.add_argument('--tunnel-recovery',action='store_true');p.add_argument('--legacy-route-dev',action='store_true')
    p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:
        print(json.dumps(dict(execution_started=False,tunnel_recovery=a.tunnel_recovery,
            own_map_transport_connected=False,e2e_eligible=False)));return 0
    if not a.legacy_route_dev:
        raise ValueError('OWN_MAP_TRANSPORT_NOT_CONNECTED: no physical/model execution admitted')
    # Existing source/host/output gates stay in place for a separately authorized
    # diagnostic. This option is deliberately absent from the s4live12 plan.
    import os
    from scripts import run_s4_pair_live11 as prior
    prior.old.old.old.persistent_output(a.output)
    prior.old.old.old.live.previous.archive_guard(a.expected_source_sha,a.output)
    if os.environ.get('LP_NUM_THREADS')!='4':raise ValueError('LP_NUM_THREADS=4 required')
    prior.old.old.old.live.write(a.output.parent/'driver.json',dict(pid=os.getpid(),pgid=os.getpgid(0),
        job=a.output.parent.name,source_sha=a.expected_source_sha))
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:
        result=run(bundle(a.expected_source_sha,a.condition,a.seed,tunnel_recovery=a.tunnel_recovery,
            reconnect=True,rounds=True,cyan=True,floor=True,feedback=True,retry_429=True,
            reply_contract=True,clipped_backoff=True),a.output,a.relay_receipt,legacy_route_dev=True)
    finally:undo()
    print(json.dumps(result));return int(result['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
