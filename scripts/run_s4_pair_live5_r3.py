"""v168: unchanged v167 plant/history with asynchronous GO polling fixed."""
from scripts import run_s4_pair_live5_r2 as previous
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure

BUNDLE_ID='zone-s4-pair-live-v168'
VERSION='7.61.0'
WORKFLOW='configs/simulation_workflows.d/s4_pair_live_v168.json'


def bundle(source_sha,condition):
    b=previous.bundle(source_sha,condition)
    b.update(schema='ugrp.s4_pair_live.v168',execution_bundle_id=BUNDLE_ID,workflow_version=VERSION)
    paths=set(source_closure(previous.ROOT,['scripts/run_s4_pair_live5_r3.py']))
    paths.update((WORKFLOW,previous.RECORD+'/plan-r3.json'))
    b['source_sha256'].update({p:previous.old.sha(previous.ROOT/p) for p in paths})
    return b


def main(argv=None):return bind(previous.main,bundle=bundle,BUNDLE_ID=BUNDLE_ID)(argv)
if __name__=='__main__':raise SystemExit(main())
