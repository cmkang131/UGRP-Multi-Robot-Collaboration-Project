"""v171: active-phase heartbeat; own executor terminal events close the lease."""
from scripts import run_s4_pair_live7 as previous
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure

ROOT = previous.ROOT
RECORD = previous.RECORD
BUNDLE_ID = 'zone-s4-pair-live-v171'
VERSION = '7.64.0'
WORKFLOW = 'configs/simulation_workflows.d/s4_pair_live_v171.json'
PLAN_FILE = 'plan-r2.json'
RENEWAL_MODE = previous.hs.ACTIVE_PHASE_HEARTBEAT


def bundle(source_sha, condition, renewal='off', drop_guard='off'):
    b = bind(previous.bundle, BUNDLE_ID=BUNDLE_ID, VERSION=VERSION, WORKFLOW=WORKFLOW,
        RENEWAL_MODE=RENEWAL_MODE)(source_sha, condition, renewal, drop_guard)
    b.update(schema='ugrp.s4_pair_live.v171', phase_lifetime='own executor terminal event; no truth inputs')
    paths=set(source_closure(ROOT, ['scripts/run_s4_pair_live7_r2.py']))
    paths.add(RECORD+'/'+PLAN_FILE)
    b['source_sha256'].update({p:previous.base.old.sha(ROOT/p) for p in paths})
    return b


def main(argv=None):
    return bind(previous.main, bundle=bundle, BUNDLE_ID=BUNDLE_ID, RENEWAL_MODE=RENEWAL_MODE)(argv)


if __name__ == '__main__':raise SystemExit(main())
