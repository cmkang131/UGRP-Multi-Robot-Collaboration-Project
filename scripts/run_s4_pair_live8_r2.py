"""v174: same latest S3 plant; correct the eight-job interpreter admission contract."""
from scripts import run_s4_pair_live8 as previous
from harness.zone_final_pair_binding import bind
from harness.python_source_closure import source_closure

ROOT=previous.ROOT
RECORD=previous.RECORD
BUNDLE_ID='zone-s4-pair-live-v174'
VERSION='7.67.0'
WORKFLOW='configs/simulation_workflows.d/s4_pair_live_v174.json'


def bundle(sha,condition,seed=601,renewal='off'):
    b=bind(previous.bundle,BUNDLE_ID=BUNDLE_ID,VERSION=VERSION,WORKFLOW=WORKFLOW,
        PLAN_FILE='plan-r2.json',RELEASE_FILE='release-r2.json')(sha,condition,seed,renewal)
    b['schema']='ugrp.s4_pair_live.v174'
    paths=source_closure(ROOT,['scripts/run_s4_pair_live8_r2.py','scripts/submit_s4_live8_r2.py'])
    b['source_sha256'].update({p:previous.admission.old.sha(ROOT/p) for p in paths})
    return b


def main(argv=None):return bind(previous.main,bundle=bundle,BUNDLE_ID=BUNDLE_ID)(argv)


if __name__=='__main__':raise SystemExit(main())
