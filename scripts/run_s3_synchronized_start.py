"""v165: shared two-control-tick carry publication before first pulse."""
import hashlib
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure
from scripts import run_s3_synchronized_carry as previous
BUNDLE_ID='zone-s3-synchronized-start-v165'
WORKFLOW_VERSION='7.58.0'
WORKFLOW='configs/simulation_workflows.d/s3_synchronized_start_v165.json'


def bundle(*args,**kwargs):
    b=previous.bundle(*args,**kwargs)
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version=WORKFLOW_VERSION,
        schema='ugrp.s3_synchronized_start.v165')
    paths=set(source_closure(previous.stage.ROOT,['scripts/run_s3_synchronized_start.py']))
    paths.update((WORKFLOW,'experiments/2026-10-10-s3-synchronized-carry/batch-plan-r2.json'))
    b['source_sha256'].update({p:hashlib.sha256((previous.stage.ROOT/p).read_bytes()).hexdigest() for p in paths})
    return b


def main():return bind(previous.main,bundle=bundle,BUNDLE_ID=BUNDLE_ID)()
if __name__=='__main__':raise SystemExit(main())
