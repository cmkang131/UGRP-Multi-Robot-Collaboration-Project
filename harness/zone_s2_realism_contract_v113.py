"""Explicit camera-v3/drive-v7 S2 integration; all earlier bundles stay frozen."""
from harness import zone_solo_cyan_contract_v106 as old
from harness.python_source_closure import source_closure
from sim import masterpi_camera_review_v3 as camera

ROOT = old.ROOT
BUNDLE_ID = 'zone-s2-realism-v113'
WORKFLOW_VERSION = '7.6.0'
WORKFLOW = 'configs/simulation_workflows.d/s2_realism_v113.json'
PLAN = 'experiments/2026-10-06-s2-realism/registration-v113.json'
OPTIONS = dict(camera_profile=camera.PROFILE_ID, drive_profile='masterpi_drive_friction_v7',
               setdown_relook='off', grasp_check='pickup_site_v1')
SAFETY = dict(robot_tilt_limit_deg=10., lift_z_m=.06, grip_lost_s=.3,
              drop_floor_m=.005, sample_s=.05,
              scope='external abort only; no GT returned to controller; normal release excluded')


NEW_OPTIONS=dict(min_wheel_cmd='real_v1',dead_reckoning='v7_diag_v1',stagnation_watch='window120_v1')
MOTION_MODEL='configs/s2_motion_v7_diag_v1.json'

def bundle(source_sha, *, seed, stage_probe, pickup_slot, min_wheel_cmd='off', dead_reckoning='off', stagnation_watch='off'):
    plan = old.hp.base.read(ROOT/PLAN)
    if not any(r['seed'] == seed and r['stage'] == stage_probe and r['slot'] == pickup_slot
               for r in plan['runs']):
        raise ValueError('unregistered seed/stage/slot')
    # Reuse static-map/calibration vocabulary validation without expanding old admission.
    out = old.bundle(source_sha, seed=911, pickup_slot=pickup_slot, stage_probe=stage_probe)
    paths = set(out['source_sha256']) | set(source_closure(ROOT, [
        'harness/zone_s2_realism_contract_v113.py', 'scripts/run_s2_realism_v113.py', 'sim/s2_real_output.py', 'harness/zone_solo_cyan_v7_motion.py']))
    paths.update((WORKFLOW, PLAN, MOTION_MODEL, 'experiments/2026-10-06-s2-realism/run_cohort_v113.py', 'experiments/2026-10-06-s2-realism/launch_v113.zsh',
                  'sim/assets/masterpi_drive_friction_v2/fuji_roller.stl',
                  'sim/assets/masterpi_drive_friction_v2/source.json'))
    out.update(schema='ugrp.s2_realism_bundle.v113', execution_bundle_id=BUNDLE_ID,
               workflow_version=WORKFLOW_VERSION, check='s2-realism-dev', options=dict(OPTIONS),
               supervisor=dict(SAFETY), in_run_drop_tilt_contact_detection=True,
               speedups='v98-exact-v6; legacy build_world/drive kernel unused',
               camera_v3=camera.record(), motion_calibration='inherited, NOT identified on drive v7',
               source_sha256={p: old.hp.base.sha(ROOT/p) for p in sorted(paths)})
    requested=dict(min_wheel_cmd=min_wheel_cmd,dead_reckoning=dead_reckoning,stagnation_watch=stagnation_watch)
    for key,value in requested.items():
        if value not in ('off',NEW_OPTIONS[key]):raise ValueError('unsupported '+key)
    if dead_reckoning!='off' and min_wheel_cmd=='off':raise ValueError('v7 motion requires real output')
    out['options'].update(requested)
    if old.hp.base.sha(ROOT/MOTION_MODEL)!=plan['motion_model_sha256']:raise ValueError('motion model differs from registration')
    out['motion_model']=old.hp.base.read(ROOT/MOTION_MODEL) if dead_reckoning!='off' else None
    out['motion_calibration']='v7 three-pulse exploratory fit; loaded/reverse transfer unqualified' if dead_reckoning!='off' else 'inherited, not v7 identified'
    out['supervisor']['stagnation']=dict(option=stagnation_watch,window_sim_s=120.,position_envelope_m=.01,scope='eval-only abort')
    out['task']['seed'] = seed
    out['bundle_sha256'] = old.hp.base.digest(out)
    return out
