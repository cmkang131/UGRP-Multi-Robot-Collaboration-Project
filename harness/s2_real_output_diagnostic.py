"""Registered exploratory motion measurements, separate from S2 fresh probes."""
from harness import zone_s2_realism_contract_v110 as parent
from harness.python_source_closure import source_closure
ROOT=parent.ROOT
BUNDLE_ID='zone-s2-real-output-diag-v111'
WORKFLOW_VERSION='7.4.0'
PLAN='experiments/2026-10-06-s2-realism/registration-v111.json'
WORKFLOW='configs/simulation_workflows.d/s2_real_output_v111.json'


def bundle(source_sha, *, min_wheel_cmd='off'):
    if min_wheel_cmd not in ('off','real_v1'):
        raise ValueError('unsupported output option')
    b=parent.bundle(source_sha,seed=1033,stage_probe='pick',pickup_slot='P1-2')
    paths=set(b['source_sha256'])|set(source_closure(ROOT,['scripts/diagnose_s2_real_output.py']))
    paths.update((PLAN,WORKFLOW,'experiments/2026-10-06-s2-realism/launch_diag_v111.zsh',
                  'scripts/masterpi_control.py','scripts/red_block/primitive.py',
                  'scripts/red_block/physical_state_machine_reference.py'))
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version=WORKFLOW_VERSION,
             task=parent.old.hp.base.read(ROOT/PLAN),cohort_role='EXPLORATORY_MOTION_DIAGNOSTIC',
             source_sha256={p:parent.old.hp.base.sha(ROOT/p) for p in sorted(paths)})
    b['options'].update(min_wheel_cmd=min_wheel_cmd,dead_reckoning='off',stagnation_watch='off')
    b.pop('bundle_sha256',None);b['bundle_sha256']=parent.old.hp.base.digest(b)
    return b
