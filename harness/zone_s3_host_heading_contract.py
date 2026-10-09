"""One new host-corrected S3 smoke; never reseal the v142 execution."""
from harness import zone_s3_no_prior_contract as old
from harness.python_source_closure import source_closure

ROOT = old.ROOT
BUNDLE_ID = 'zone-s3-host-heading-v144'
WORKFLOW_VERSION = '7.37.0'
SEEDS = (14201,)
PLAN = 'experiments/2026-10-09-s3-no-prior/s3next/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/s3_host_heading_v144.json'


def inputs():
    return old.inputs()


hp = old.hp


def bundle(sha, *, seed=14201, speedups='v98-exact-v6'):
    b = old.bundle(sha, seed=seed, speedups=speedups)
    b['controller_config']['options'].update(
        heading_mode='path_tangent_v1', localization_certification='posterior_consensus_v1')
    b.update(schema='ugrp.s3_host_heading_bundle.v144', execution_bundle_id=BUNDLE_ID,
        workflow_version=WORKFLOW_VERSION, options=b['controller_config']['options'],
        s3_camera_binding='v3_persistent_v1', eval_render_camera=True,
        raw_budget_bytes=3*1024**3,
        preregistration=hp.base.read(ROOT/PLAN),
        parent_bundles=[*b['parent_bundles'], old.BUNDLE_ID],
        replay_extrinsic_synthesis=False, research_result=False,
        convergence_thresholds_changed=False, particle_recovery_changed=False)
    paths = set(b['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s3_host_heading_contract.py', 'scripts/run_s3_host_heading.py']))
    paths.update((PLAN, WORKFLOW))
    b['source_sha256'] = {p: hp.base.sha(ROOT/p) for p in sorted(paths)}
    return b


def verify(value):
    if value != bundle(value['source_sha'], seed=value['seed'], speedups=value['speedups']):
        raise ValueError('S3 host-heading source/config mismatch')
