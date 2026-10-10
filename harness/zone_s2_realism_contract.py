"""Explicit camera-v3/drive-v7 S2 integration; all earlier bundles stay frozen."""
from harness import zone_solo_cyan_contract_v106 as old
from harness.python_source_closure import source_closure
from sim import masterpi_camera_review_v3 as camera

ROOT = old.ROOT
BUNDLE_ID = 'zone-s2-realism-v109'
WORKFLOW_VERSION = '7.2.0'
WORKFLOW = 'configs/simulation_workflows.d/s2_realism_v109.json'
PLAN = 'experiments/2026-10-06-s2-realism/registration.json'
OPTIONS = dict(camera_profile=camera.PROFILE_ID, drive_profile='masterpi_drive_friction_v7',
               setdown_relook='off', grasp_check='pickup_site_v1')
SAFETY = dict(robot_tilt_limit_deg=10., lift_z_m=.06, grip_lost_s=.3,
              drop_floor_m=.005, sample_s=.05,
              scope='external abort only; no GT returned to controller; normal release excluded')


def bundle(source_sha, *, seed, stage_probe, pickup_slot):
    plan = old.hp.base.read(ROOT/PLAN)
    if not any(r['seed'] == seed and r['stage'] == stage_probe and r['slot'] == pickup_slot
               for r in plan['runs']):
        raise ValueError('unregistered seed/stage/slot')
    # Reuse static-map/calibration vocabulary validation without expanding old admission.
    out = old.bundle(source_sha, seed=911, pickup_slot=pickup_slot, stage_probe=stage_probe)
    paths = set(out['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s2_realism_contract.py', 'scripts/run_s2_realism.py', 'sim/s2_realism.py']))
    paths.update((WORKFLOW, PLAN, 'experiments/2026-10-06-s2-realism/launch_dev.zsh',
                  'sim/assets/masterpi_drive_friction_v2/fuji_roller.stl',
                  'sim/assets/masterpi_drive_friction_v2/source.json'))
    out.update(schema='ugrp.s2_realism_bundle.v109', execution_bundle_id=BUNDLE_ID,
               workflow_version=WORKFLOW_VERSION, check='s2-realism-dev', options=dict(OPTIONS),
               supervisor=dict(SAFETY), in_run_drop_tilt_contact_detection=True,
               speedups='v98-exact-v6; legacy build_world/drive kernel unused',
               camera_v3=camera.record(), motion_calibration='inherited, NOT identified on drive v7',
               source_sha256={p: old.hp.base.sha(ROOT/p) for p in sorted(paths)})
    out['task']['seed'] = seed
    out['bundle_sha256'] = old.hp.base.digest(out)
    return out
