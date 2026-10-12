"""v185: bounded own RGB -> GoalRoute -> S4 dialogue -> S3 Azure execution."""
import argparse
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import time
import traceback
from harness.zone_study_contract import digest
from harness.s4_event_policy import Options

ROOT=Path(__file__).resolve().parents[1]
BUNDLE_ID='e2e-ownmap-live-v185'
RECORD='experiments/2026-10-11-e2e-azure-first'
WORKFLOW='configs/simulation_workflows.d/e2e_ownmap_live_v185.json'
PROFILES=('study_gemma4_31b_v1','main_study_gemini_v1')
PORTS=dict(zip(PROFILES,(18393,18391)))


def relay_url(profile, decider='off'):
    # Paired Gemma/Jev uses the existing second loopback relay independently.
    port = 18391 if decider == 'jev_v1' else PORTS[profile]
    return f'http://127.0.0.1:{port}/v1/chat/completions'


from harness.e2e_result_writer import write, Finalizer

WALL_CAP_MAX_S = 25200.  # 7 h finite ceiling; default --wall-cap-s remains 12600

def bundle(sha,seed,profile,*,enabled=False,relook='off',options=Options(),decider='off',exploration_progress='off',pose_fix='off',path_follow='off',dev_light=False,wall_cap_s=12600.,stall_odometry='off',stall_recovery='off',stall_noise='off',stall_bundle=False,mapping_budget='off',exact_speedups=None,speed_bundle=False,boundary_views='off',b_marker_detect='off',runtime_registration='off',speed2_bundle=False,ultrasonic_front='off',vo_floor_mask='off',vo_rotation_policy='off',explore_deadlock='off',boundary_association='off',boundary_retry='off',boundary_coverage='off',speed3='off',speed4=None,b_partial_accept='off',speed5='off'):
    # E2E17 broad is candidate-only; preserve every older bundle's seed scope.
    registered_seeds = range(61001,61013) if b_partial_accept != 'off' else range(61001, 61010) if explore_deadlock == 'replan_v1' else range(61001, 61005)
    if profile not in PROFILES or seed not in registered_seeds:raise ValueError('REGISTERED_MODEL_SEED_REQUIRED')
    if relook not in ('off','on_v1'):raise ValueError('UNKNOWN_RELOOK_TOGGLE')
    if decider not in ('off','jev_v1'):raise ValueError('UNKNOWN_DECIDER')
    if decider!='off' and profile!='study_gemma4_31b_v1':raise ValueError('JEV_GEMMA_REQUIRED')
    if exploration_progress not in ('off','frontier_progress_v1'):raise ValueError('UNKNOWN_EXPLORATION_PROGRESS')
    if pose_fix not in ('off','innovation'):raise ValueError('UNKNOWN_E2E_POSE_FIX')
    if path_follow not in ('off','rpp_v1'):raise ValueError('UNKNOWN_PATH_FOLLOW')
    # Finite ceiling 7 h (E2E14): the old 12600 s (3.5 h) ceiling stopped case_cap_s=1800
    # SIM runs at ~12-15 wall/SIM before the case cap. Default stays 12600 s.
    if not 0 < wall_cap_s <= WALL_CAP_MAX_S:raise ValueError('FINITE_WALL_CAP_REQUIRED')
    from harness.e2e_boundary_views import OPTIONS as VIEWS_OPTIONS
    from harness.e2e_rgb_gate import MARKER_OPTIONS
    if boundary_views not in ('off',*VIEWS_OPTIONS):raise ValueError('UNKNOWN_B_BOUNDARY_VIEWS')
    if b_marker_detect not in ('off',*MARKER_OPTIONS):raise ValueError('UNKNOWN_B_MARKER_DETECT')
    if boundary_views!='off' and exploration_progress=='off':raise ValueError('FRONTIER_PROGRESS_V1_REQUIRED_BEFORE_VIEWS')
    if mapping_budget not in ('off','case_cap_v1'):raise ValueError('UNKNOWN_MAPPING_BUDGET')
    from harness.e2e_stall_odometry import Options as StallOptions
    stall=StallOptions(stall_odometry,stall_recovery,stall_noise)
    if stall.stall_odometry=='rgb_vo_v2' and boundary_views=='off' and b_marker_detect=='off':
        # Registered only inside the E2E14 composition bundle (v205); never fall back to v198/v201.
        raise ValueError('RGB_VO_V2_HAS_NO_STANDALONE_BUNDLE')
    from harness.ultrasonic_input import normalize_sensors, bundle_record
    sensors = normalize_sensors({'ultrasonic_front': ultrasonic_front})
    us_on = stall.stall_odometry == 'rgb_vo_us_v1'
    if us_on != bool(sensors):raise ValueError('US_STALL_REQUIRES_SENSOR_ON_AND_CONSUMER')
    if us_on and (boundary_views not in VIEWS_OPTIONS or b_marker_detect not in MARKER_OPTIONS):
        raise ValueError('US_STALL_REQUIRES_V205_COMPOSITION')
    mask_on = vo_floor_mask != 'off' or vo_rotation_policy != 'off'
    if mask_on and (not us_on or (vo_floor_mask, vo_rotation_policy) != ('homography_v1', 'no_ransac_v1')):
        raise ValueError('VO_MASK_BUNDLE_REQUIRES_V206_AND_SELECTED_TURN_POLICY')
    from harness.e2e_exact_speedups import Options as SpeedOptions
    speed=SpeedOptions(**(exact_speedups or {}))
    from harness.e2e_exact_speedups import ROUND2_FIELDS
    # Round-2 toggles are only part of the v203 bundle; v200 bytes stay unchanged.
    speed2=speed2_bundle or any(getattr(speed,k) for k in ROUND2_FIELDS)
    from harness.zone_study_llm_driver import load_registry
    b=json.loads((ROOT/'configs/e2e_s3_test_runtime_v1.json').read_text())
    # The template contributes physical/calibration constants only. Its authored
    # runtime config is never passed into the own-map controller.
    b.update(schema='ugrp.e2e_ownmap_live.v185',execution_bundle_id=BUNDLE_ID,workflow_version='7.78.0',
        source_sha=sha,seed=seed,scenario_id='e2e_one_beam_ownmap',map_id='zone_wide_door_e2e_b80_v1',
        case='pair',check='ownmap-live',host='azure',condition='peer_en',research_result=False,
        route_source='own_map',fixture_restore=False,weld=False,case_cap_s=1800.,wall_cap_s=12600.,
        initial_health_wall_s=240.,contact_profile='cargo_noslip_v1',
        pair_drop_guard='contact_com_v1',final_release_guard='supported_phase',
        driver_profile=profile,driver_profile_sha256=digest(load_registry()['driver_profiles'][profile]),
        study_options=dataclasses.asdict(options),
        e2e_options=dict(enabled=enabled,own_inputs='on_v1' if enabled else 'off',dialogue='on_v1' if enabled else 'off',
            pulse_budget='fractional_duration_v1' if enabled else 'off',
            own_route='goal_route_v1' if enabled else 'off',arrival_gate='rgb_geometry_v1' if enabled else 'off',
            goal_geometry='e2e_b80_v1' if enabled else 'off',
            covariance_inflation='nees_frozen_v1' if enabled else 'off',
            setdown_reobserve='boundary_reobserve_v1' if enabled else 'off',setdown_only_when_relook=relook))
    b['e2e_options'].update(decider=decider,exploration_progress=exploration_progress,pose_fix=pose_fix)
    if path_follow!='off' or dev_light:
        b['e2e_options'].update(path_follow=path_follow,dev_light=dev_light)
    b['wall_cap_s']=wall_cap_s
    if decider=='jev_v1':
        b.update(schema='ugrp.e2e_ownmap_live.v192',execution_bundle_id='e2e-ownmap-jev-v192',workflow_version='7.85.0')
    if exploration_progress!='off' or pose_fix!='off':
        b.update(schema='ugrp.e2e_ownmap_live.v194',execution_bundle_id='e2e-explore-posefix-v194',workflow_version='7.87.0')
    if path_follow!='off' or dev_light:
        b.update(schema='ugrp.e2e_ownmap_live.v197',execution_bundle_id='e2e-rpp-lookahead-v197',workflow_version='7.90.0')
    if stall.enabled or stall_bundle:
        b['e2e_options'].update(dataclasses.asdict(stall))
        b.update(schema='ugrp.e2e_ownmap_live.v198',execution_bundle_id='e2e-stall-odometry-v198',workflow_version='7.91.0')
    if mapping_budget!='off':
        b['e2e_options'].update(mapping_budget=mapping_budget,mapping_budget_s=b['case_cap_s'])
        b.update(schema='ugrp.e2e_ownmap_live.v199',execution_bundle_id='e2e-stall-budget-v199',workflow_version='7.92.0')
    if speed_bundle or any(vars(speed).values()):
        b['e2e_options']['exact_speedups']={k:v for k,v in dataclasses.asdict(speed).items() if k not in ROUND2_FIELDS}
        b.update(schema='ugrp.e2e_ownmap_live.v200',execution_bundle_id='e2e-exact-speed-v200',workflow_version='7.93.0')
    if speed2:
        b['e2e_options']['exact_speedups']=dataclasses.asdict(speed)
        b.update(schema='ugrp.e2e_ownmap_live.v203',execution_bundle_id='e2e-exact-speed2-v203',workflow_version='7.96.0')
    if stall.stall_odometry=='rgb_vo_v1':
        b.update(schema='ugrp.e2e_ownmap_live.v201',execution_bundle_id='e2e-rgb-vo-v201',workflow_version='7.94.0')
    combo=boundary_views!='off' or b_marker_detect!='off'
    if combo:
        # E2E14 composition: B confirmation views / B mark contrast (#443) on the same
        # runner; keys are added only when on so older bundles stay byte-identical.
        b['e2e_options'].update(boundary_views=boundary_views,b_marker_detect=b_marker_detect)
        # v202 (source e4fc8354) crashed in rgb_vo_v1 ground() on 0 floor points; v204 carries the guard.
        b.update(schema='ugrp.e2e_ownmap_live.v204',execution_bundle_id='e2e-combo14-v204',workflow_version='7.97.0')
        if stall.stall_odometry=='rgb_vo_v2':
            # v205 = v204 composition with rgb_vo_v2 (VO, then pulse-gate stall fallback, then command).
            b.update(schema='ugrp.e2e_ownmap_live.v205',execution_bundle_id='e2e-combo14-vo2-v205',workflow_version='7.98.0')
    if us_on:
        from harness.e2e_us_stall import PARAMS as US_PARAMS
        b.update(schema='ugrp.e2e_ownmap_live.v206',execution_bundle_id='e2e-usstall-v206',workflow_version='7.99.0')
        b['sensors'] = bundle_record(sensors)
        b['sensors']['ultrasonic_front']['controller_use'] = 'rgb_vo_us_v1: own forward increment ZUPT hypothesis'
        b['sensors'].pop('sha256')
        b['sensors']['sha256'] = digest(b['sensors'])
        b['us_stall'] = dict(params=US_PARAMS, clock='episode_since_reset',poll_interval_s=.05,effective_period_s=.10)
    if mask_on:
        b.update(schema='ugrp.e2e_ownmap_live.v207',execution_bundle_id='e2e-vomask-turn-v207',workflow_version='7.100.0')
        b['e2e_options'].update(vo_floor_mask=vo_floor_mask,vo_rotation_policy=vo_rotation_policy)
        b['vo_mask_scope']='RANSAC only on non-turn intervals; authored map projection unavailable, not enabled'
    from harness.e2e_explore_deadlock import OPTION as DEADLOCK, PARAMS as DEADLOCK_PARAMS
    if explore_deadlock not in ('off',DEADLOCK):raise ValueError('UNKNOWN_EXPLORE_DEADLOCK')
    if explore_deadlock != 'off':
        if not mask_on or exploration_progress == 'off':raise ValueError('V207_REQUIRED_BEFORE_DEADLOCK')
        b.update(schema='ugrp.e2e_ownmap_live.v208',execution_bundle_id='e2e-explore-deadlock-v208',workflow_version='7.101.0')
        b['e2e_options']['explore_deadlock']=explore_deadlock
        b['explore_deadlock']=dict(params=DEADLOCK_PARAMS,scope='own issued zero-motion commands; local goal suppression only')
    from harness.e2e_boundary_association import OPTION as ASSOC, PARAMS as ASSOC_PARAMS
    from harness.e2e_boundary_views import RETRY_OPTION, MAX_NAVIGATION_FAILURES
    if boundary_association not in ('off',ASSOC):raise ValueError('UNKNOWN_BOUNDARY_ASSOCIATION')
    if boundary_retry not in ('off',RETRY_OPTION):raise ValueError('UNKNOWN_BOUNDARY_RETRY')
    if boundary_association != 'off' or boundary_retry != 'off':
        if explore_deadlock != DEADLOCK:raise ValueError('V208_REQUIRED_BEFORE_BOUNDARY_REPAIR')
        b.update(schema='ugrp.e2e_ownmap_live.v212',execution_bundle_id='e2e-boundary-repair-v212',workflow_version='7.105.0')
        b['e2e_options'].update(boundary_association=boundary_association,boundary_retry=boundary_retry)
        b['boundary_repair']=dict(association=ASSOC_PARAMS,max_navigation_failures=MAX_NAVIGATION_FAILURES)
    from harness.e2e_boundary_views import COVERAGE_OPTION
    if boundary_coverage not in ('off',COVERAGE_OPTION):raise ValueError('UNKNOWN_BOUNDARY_COVERAGE')
    if boundary_coverage != 'off':
        if not dev_light or boundary_association != ASSOC:raise ValueError('DEV_V211_ASSOCIATION_REQUIRED_BEFORE_NATIVE_COVERAGE')
        b.update(schema='ugrp.e2e_ownmap_live.v213',execution_bundle_id='e2e-boundary-native-v213',workflow_version='7.106.0')
        b['e2e_options']['boundary_coverage']=boundary_coverage
        b['boundary_coverage_scope']='DEV existing native unknown tracking; extra fully observed sweep is diagnostic, no observation fabrication'
    from harness.e2e_runtime_registration import register
    if boundary_coverage != 'off':runtime_registration='reviewed_v1'
    runtime_assets=register(b,runtime_registration)
    from harness.e2e_speed3 import compose
    speed3_assets=compose(b,speed3)
    from harness.python_source_closure import source_closure
    paths=set(source_closure(ROOT,['scripts/run_e2e_ownmap_live.py','sim/e2e_ownmap_live.py',
        'harness/e2e_live_transport.py','harness/e2e_live_mapping.py','harness/e2e_s4_live.py',
        'scripts/s4_proxy_relay.py','scripts/s4_reverse_tunnel.py','scripts/e2e_gemini_keychain.py',
        'scripts/evaluate_e2e_ownmap_live.py']))
    paths.update((WORKFLOW,RECORD+'/azure-plan.json','configs/e2e_s3_test_runtime_v1.json',
        'configs/s2_v133_full_template.json','configs/e2e_nees_egomap70_dev_v1.json',
        'configs/zone_study_dev/e2e_one_beam_ownmap.json'))
    if decider=='jev_v1':paths.add('configs/simulation_workflows.d/e2e_ownmap_jev_v192.json')
    if exploration_progress!='off' or pose_fix!='off':
        paths.add('configs/simulation_workflows.d/e2e_explore_posefix_v194.json')
    if path_follow!='off' or dev_light:
        paths.add('configs/simulation_workflows.d/e2e_rpp_lookahead_v197.json')
    if stall.enabled or stall_bundle:paths.add('configs/simulation_workflows.d/e2e_stall_odometry_v198.json')
    if mapping_budget!='off':paths.add('configs/simulation_workflows.d/e2e_stall_budget_v199.json')
    if speed_bundle or any(vars(speed).values()):paths.add('configs/simulation_workflows.d/e2e_exact_speed_v200.json')
    if stall.stall_odometry=='rgb_vo_v1':paths.add('configs/simulation_workflows.d/e2e_rgb_vo_v201.json')
    if combo:paths.add('configs/simulation_workflows.d/e2e_combo14_v204.json' if stall.stall_odometry!='rgb_vo_v2' else
                       'configs/simulation_workflows.d/e2e_combo14_vo2_v205.json')
    if us_on:
        paths.update(source_closure(ROOT, ['sim/e2e_us_input.py','harness/e2e_us_stall.py']))
        paths.add('configs/simulation_workflows.d/e2e_usstall_v206.json')
    if mask_on:
        paths.add('configs/simulation_workflows.d/e2e_vomask_turn_v207.json')
        paths.add('experiments/2026-10-12-e2e-vomask-registration/registration.json')
        paths.add('experiments/2026-10-12-e2e-vomask-registration/bundle-decision.json')
    if explore_deadlock != 'off':paths.add('configs/simulation_workflows.d/e2e_explore_deadlock_v208.json')
    if boundary_association != 'off' or boundary_retry != 'off':paths.add('configs/simulation_workflows.d/e2e_boundary_repair_v212.json')
    if speed2:paths.update(('configs/simulation_workflows.d/e2e_exact_speed2_v203.json','scripts/e2e_speed_measure.py'))
    paths.update(runtime_assets)
    paths.update(speed3_assets)
    if boundary_coverage != 'off':paths.add('configs/simulation_workflows.d/e2e_boundary_native_v213.json')
    from harness.e2e_speed4 import Options as Speed4Options, record as speed4_record
    candidate = Speed4Options(**(speed4 or {}))
    if candidate.enabled:
        if not dev_light:raise ValueError('SPEED4_DEV_COHORT_REQUIRED')
        b['speed4']=dataclasses.asdict(candidate)
        b['speed4_record']=speed4_record(candidate)
    if b_partial_accept not in ('off','on_v1'):raise ValueError('UNKNOWN_B_PARTIAL_ACCEPT')
    if b_partial_accept != 'off':
        from harness.e2e18_bundle import compose as compose18
        paths.update(compose18(b, b_partial_accept))
    from harness.e2e_speed5 import OPTIONS as SPEED5_OPTIONS, STATIC, INPUTS
    if speed5 not in ('off',*SPEED5_OPTIONS):raise ValueError('UNKNOWN_SPEED5')
    if speed5 != 'off':
        if b['execution_bundle_id']!='e2e18-v216':raise ValueError('SPEED5_REQUIRES_E2E18')
        b['e2e_options']['speed5']=speed5
        b.update(schema='ugrp.e2e_ownmap_live.v217',execution_bundle_id='e2e18-v217',workflow_version='7.110.0')
        paths.update((STATIC,*INPUTS,'configs/simulation_workflows.d/e2e18_v217.json'))
        if speed5 in ('lean_v2','lean_v3'):
            b.update(schema='ugrp.e2e_ownmap_live.v218',execution_bundle_id='e2e18-v218',workflow_version='7.111.0')
            b['opencv_threads']=1
            paths.add('configs/simulation_workflows.d/e2e18_v218.json')
        if speed5=='lean_v3':
            b.update(schema='ugrp.e2e_ownmap_live.v219',execution_bundle_id='e2e18-v219',workflow_version='7.112.0')
            b['coarse_grid_dtype']='float32'
            paths.add('configs/simulation_workflows.d/e2e18_v219.json')
    b['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
    return b


def ownmap_record(robot, obs, trace, now):
    """Persist both accepted and rejected own-input association diagnostics."""
    return dict(t=now,frame_id=obs['frame_id'],sha256=obs['sha256'],
        pose_own_m=robot.goal.explorer.local_pose.tolist(),
        remembered_B=robot.goal.entities.get('B'),stage=robot.goal.stage,command=robot.nav_command,
        pose_continuity=trace.get('pose_continuity'),exploration=trace.get('exploration'),
        navigation_status=trace.get('status'),pulse=trace.get('pulse'),stall_odometry=trace.get('stall_odometry'),
        **{k:trace[k] for k in ('boundary_view','boundary_diagnostics','explore_deadlock','boundary_association') if k in trace})


def health(robots,host,transport,sim_s,wall_s,frames):
    from harness.llm_completion import normal_completion
    ledger=host.trial.send_ledger.entries if host else []
    normal=[e for e in ledger if normal_completion(e.get('completion'))]
    r1=robots.get('r1')
    generated=bool(r1 and r1.goal.entities.get('B'))
    return dict(wall_s=wall_s,sim_s=sim_s,frames=frames,model_attempts=len(ledger),
        first_model_response=bool(normal),own_map_B_generated=generated,
        own_B_boundary_remembered=bool(r1 and 'B' in r1.goal.e2e_gate.references),
        own_route_generated=bool(r1 and r1.packet is not None),
        phase=transport.state if transport else 'boot',setdowns=transport.setdowns if transport else 0,
        robots={r:dict(pose_own_m=v.goal.explorer.local_pose.tolist(),stage=v.goal.stage,
            map_frames=len(v.goal.e2e_observed),command=v.nav_command,
            translation_commands=v.translation_commands) for r,v in robots.items()},
        latest_route_wait=transport.last_route_error if transport else None)


def startup_decision(progress, b):
    ok=progress['first_model_response'] and progress['own_map_B_generated']
    if b['e2e_options'].get('exploration_progress','off')!='off':
        ok=progress['first_model_response'] and all(
            progress['robots'][r]['map_frames']>1 and progress['robots'][r]['translation_commands']>0
            for r in ('r1','r2'))
    failed=progress['wall_s']>=b['initial_health_wall_s'] and not ok
    return dict(passed=bool(ok),would_stop=bool(failed),
                stop=bool(failed and not b['e2e_options'].get('dev_light',False)))


def run(b,out,receipt,*,backend_factory=None):
    if not b['e2e_options']['enabled']:raise ValueError('E2E_LIVE_TOGGLE_OFF')
    from harness.e2e_runtime_registration import require_current
    require_current(b,ROOT)
    from harness.e2e_live_mapping import Robot,Link
    from harness.e2e_exact_speedups import Options as SpeedOptions
    from harness.e2e_stall_odometry import Options as StallOptions
    from harness.e2e_live_transport import Transport
    from harness.e2e_s4_live import Host
    from harness.s4_tunnel_recovery import RecoveryLedger
    from harness.zone_study_llm_driver import load_registry,client_factory
    from harness.zone_study_integration import ModelAdapter
    from harness.zone_main_budget import MainStudyBudget
    from harness.zone_environment_registry import load_scenario,bundle_for
    from harness.zone_event_scheduler import CallPolicy
    from harness.zone_study_decisions import DecisionLimits
    from harness.active_camera import SEARCH
    from sim.e2e_ownmap_live import PhysicsBackend
    out.mkdir(parents=True,exist_ok=False);write(out/'bundle.json',b)
    result=dict(status='HOST_ERROR',source_sha=b['source_sha'],seed=b['seed'],model=b['driver_profile'],
        condition=b['condition'],options=b['e2e_options'],LLM_operated=False,own_map_completed=False,
        start_to_finish_transport=False,E2E_success=False,setdowns=0,model_calls=0,
        physical_hardware=False,route_source='own_map',host='azure',class_='dev',
        pr=json.loads((out.parent/'RUN_META.json').read_text()).get('pr') if (out.parent/'RUN_META.json').exists() else None)
    started=time.monotonic();backend=host=transport=None;robots={};frames_seen=0;origin=0.
    milestones={};initial_recorded=False
    finalizer=Finalizer(out,result)
    finalizer.install()
    try:
        for p,sha in b['source_sha256'].items():
            if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha:raise ValueError('SOURCE_HASH_MISMATCH:'+p)
        if b.get('opencv_threads')==1:
            import cv2
            cv2.setNumThreads(1)
        options=Options(**b['study_options'])
        from harness.e2e_speed4 import Options as Speed4Options, processing_due
        speed4=Speed4Options(**b.get('speed4',{}))
        if speed4.enabled:write(out/'speed4.json',b['speed4_record'])
        cov=json.loads((ROOT/'configs/e2e_nees_egomap70_dev_v1.json').read_text())
        robots={r:Robot(r,b['seed']+i,cov,options,speed4=speed4,speed5=b['e2e_options'].get('speed5','off'),relook=b['e2e_options']['setdown_only_when_relook'],
                        goal_geometry=b['e2e_options']['goal_geometry'],
                        exploration_progress=b['e2e_options'].get('exploration_progress','off'),
                        pose_fix=b['e2e_options'].get('pose_fix','off'),
                        path_follow=b['e2e_options'].get('path_follow','off'),
                        stall_options=StallOptions(**{k:b['e2e_options'].get(k,'off') for k in ('stall_odometry','stall_recovery','stall_noise')}),
                        explore_deadlock=b['e2e_options'].get('explore_deadlock','off'),
                        boundary_association=b['e2e_options'].get('boundary_association','off'),
                        boundary_retry=b['e2e_options'].get('boundary_retry','off'),
                        boundary_coverage=b['e2e_options'].get('boundary_coverage','off'),
                        vo_floor_mask=b['e2e_options'].get('vo_floor_mask','off'),
                        vo_rotation_policy=b['e2e_options'].get('vo_rotation_policy','off'),
                        mapping_budget_s=b['e2e_options'].get('mapping_budget_s'),
                        boundary_views=b['e2e_options'].get('boundary_views','off'),
                        b_marker_detect=b['e2e_options'].get('b_marker_detect','off'),
                        b_partial_accept=b['e2e_options'].get('b_partial_accept','off'),
                        exact_speedups=SpeedOptions(**b['e2e_options'].get('exact_speedups',{})))
                for i,r in enumerate(('r1','r2','r3'))}
        for robot in robots.values():robot.decider=b['e2e_options'].get('decider','off')
        offered=json.loads(receipt.read_text())
        if offered.get('decider','off')!=b['e2e_options'].get('decider','off'):
            raise ValueError('RELAY_DECIDER_MISMATCH')
        backend=(backend_factory or PhysicsBackend)(b,out,seed=b['seed'])
        backend.reset(b['reset_cap_s']);origin=backend.now
        backend.set_deadline(origin+b['case_cap_s'])
        if b.get('sensors'):
            from sim.e2e_us_input import attach as attach_sonar
            attach_sonar(backend, robots, seed=b['seed'], out=out)
        for rid,robot in robots.items():
            for sid,pwm in SEARCH.items():
                a=dict(kind='look',pan_pulse=pwm) if sid==6 else dict(kind='arm',servo_id=sid,pulse=pwm)
                backend.issue(rid,a);robot.commanded(a,0.)
        profile=copy.deepcopy(load_registry()['driver_profiles'][b['driver_profile']])
        if digest(profile)!=b['driver_profile_sha256']:raise ValueError('MODEL_PROFILE_HASH_MISMATCH')
        profile.update(profile_id=b['driver_profile'],proxy_url=relay_url(b['driver_profile'],b['e2e_options'].get('decider','off')))
        profile['sha256']=digest(profile)
        budget=MainStudyBudget.create(out/'budget.sqlite');key=out.parent.name
        budget.register_cohort(key,token_cap=800000,unknown_usage_charge_tokens=16000,
            prereg_sha256=b['source_sha256'][RECORD+'/azure-plan.json'],source={'source_sha':b['source_sha']})
        budget.start_run(key,cohort_id=key,bundle_id=b['execution_bundle_id'],bundle_sha256=digest(b),record={'research_result':False})
        ledger=RecoveryLedger(receipt=receipt,remote_url=profile['proxy_url'],store_dir=out/'wire',budget=budget,
            run_key=key,profile=profile,tunnel_recovery=True,retry_429=True)
        ledger.retry_snapshot=lambda:dict(sim_s=backend.now,frames=backend.frame)
        scenario=load_scenario('e2e_one_beam_ownmap')
        host=Host(scenario,condition='peer_en',links={r:Link.build(v,'peer_en') for r,v in robots.items()},
            seed=b['seed'],map_bundle=bundle_for(scenario),horizon_s=b['case_cap_s'],
            model_adapter=ModelAdapter(client_factory(profile),ledger),code_sha=b['source_sha'],
            e2e_own_inputs_v1='on_v1',e2e_dialogue_v1='on_v1',
            policy=CallPolicy(max_calls_per_actor=120,max_http_attempts_per_actor=120,max_attempts_total=300,max_retries=0),
            decision_limits=DecisionLimits(max_calls_total=300,max_utterances_per_actor=80,max_utterances_total=160))
        profiles=json.loads((ROOT/'configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']
        transport=Transport(robots,host.trial.dialogue,profiles,pulse_budget=b['e2e_options']['pulse_budget'],
                            setdown_only_when_relook=b['e2e_options']['setdown_only_when_relook'],
                            dev_light=b['e2e_options'].get('dev_light',False))
        host.trial.dialogue.motion_connected=True
        host.trial.provenance.update(provider=offered.get('upstream',host.trial.provenance['provider']),
            decider=b['e2e_options'].get('decider','off'))
        backend.authorize_pulse=lambda rid,a,t:transport.authorize(rid,a,round(t-origin,8))
        backend.final_segment_getter=lambda:bool(transport.plan and transport.seg==len(transport.plan['own_route']['legs'])-1)
        observation_ticks=round(b.get('speed3_profile',{}).get('observation_period_s',.2)/.05)
        for tick in range(round(b['case_cap_s']/.05)):
            now=round(backend.now-origin,8)
            if time.monotonic()-started>b['wall_cap_s']:raise TimeoutError('E2E_WALL_CAP')
            backend.eval_sample()
            if tick%observation_ticks==0:
                raw=backend.capture()
                for rid,robot in robots.items():
                    if not processing_due(robot,now,transport.state):
                        backend._append(f'robots/{rid}/speed4-skips.jsonl',dict(t=now,reason='moving_observation_stride'))
                        continue
                    obs,rgb=raw[rid]
                    own_obs={k:obs[k] for k in ('frame_id','sim_time','sha256','image')}
                    own_obs['sim_time']=round(obs['sim_time']-origin,8)
                    trace=robot.receive(own_obs,rgb)
                    backend._append(f'robots/{rid}/ownmap.jsonl',ownmap_record(robot,obs,trace,now))
                frames_seen+=1
                if not host.started:
                    write(out/'e2e-progress.json',health(robots,host,transport,now,time.monotonic()-started,frames_seen))
                    backend.flush()
                    host.begin(now)
            if not host.started:continue
            if tick%20==0:
                write(out/'e2e-progress.json',health(robots,host,transport,now,time.monotonic()-started,frames_seen))
                backend.flush()
            host.step_to(now)
            commands=transport.step(now)
            if tick%4==0 and transport.state=='mapping':
                commands += [(r,v.nav_command) for r,v in robots.items() if r!='r3' and v.packet is None]
            for rid,action in commands:
                backend.issue(rid,action);robots[rid].commanded(action,now)
            if tick%20==0:
                p=health(robots,host,transport,now,time.monotonic()-started,frames_seen)
                write(out/'e2e-progress.json',p);backend.flush()
                print(json.dumps(p,ensure_ascii=False),flush=True)
                decision=startup_decision(p,b)
                if not initial_recorded and (decision['would_stop'] or decision['passed'] and now>=10):
                    write(out/'initial-check.json',{**p,**decision})
                    initial_recorded=True
                if decision['stop']:raise RuntimeError('INITIAL_HEALTH_FAILED')
                for stage,reached in dict(LLM=p['first_model_response'],B_boundary=p['own_B_boundary_remembered'],
                        route=p['own_route_generated'],**{transport.state:True}).items():
                    if reached and stage not in milestones:
                        milestones[stage]=dict(sim_s=now,wall_s=p['wall_s'])
                        write(out/'stage-milestones.json',milestones)
            if transport.failure:result['status']='CONTROLLER_STOP';break
            if transport.done:result['status']='FINISHED';break
            backend.advance_to(origin+(tick+1)*.05)
        else:result['status']='SIM_BUDGET_EXHAUSTED'
    except (Exception,KeyboardInterrupt) as exc:
        result.update(status='EARLY_STOP' if isinstance(exc,KeyboardInterrupt) or str(exc)=='INITIAL_HEALTH_FAILED' else
            'PHYSICAL_STOP' if type(exc).__name__=='PhysicalStop' else 'HOST_ERROR',failure_type=type(exc).__name__,
            failure=str(exc),traceback=traceback.format_exc())
        if host is not None:host.failed=exc
    finally:
        finalizer.finalizing=True
        result.update(wall_s=time.monotonic()-started,frames=frames_seen,stage_milestones=milestones)
        if backend is not None:result['sim_s']=backend.now-origin
        finalizer.checkpoint()
        if transport is not None:
            result.update(setdowns=transport.setdowns,controller_failure=transport.failure,
                own_map_completed=any(e['event']=='own_map_B_route_generated' for e in transport.events))
            finalizer.attempt('transport',lambda:write(out/'transport-trace.json',transport.events))
        if host is not None:
            from harness.llm_completion import normal_completion
            result.update(model_calls=len(host.trial.send_ledger.entries),
                LLM_operated=any(normal_completion(r.get('completion')) for r in host.trial.send_ledger.entries))
            def save_host():
                saved=host.save(out/'llm')
                result.update(model_usage=saved['model_usage'],response_wall_s=saved['response_wall_s'])
                write(out/'jev-guard-events.json',host.trial.jev_guard_events)
            finalizer.attempt('llm',save_host)
        for rid,robot in robots.items():
            finalizer.attempt(rid+'-map',lambda:write(out/f'{rid}-ownmap-final.json',robot.goal.snapshot()))
            finalizer.attempt(rid+'-relook',lambda:write(out/f'{rid}-relook.json',robot.goal.e2e_relook.events))
        if backend is not None:
            for rid in robots:
                finalizer.attempt(rid+'-hold',lambda:backend.issue(rid,dict(kind='hold')))
            finalizer.attempt('backend-close',backend.close)
            def evaluate_result():
                from scripts.evaluate_e2e_ownmap_live import evaluate
                evaluation=evaluate(out,{**result,'start_to_finish_transport':bool(transport and transport.done)},
                                    transport.events if transport else [],origin)
                write(out/'evaluation.json',evaluation)
                result['start_to_finish_transport']=evaluation['start_to_finish_transport']
                result['drops']=evaluation['drops']
            finalizer.attempt('evaluation',evaluate_result)
        result['E2E_success']=not result['finalization_errors'] and all(
            result[k] for k in ('LLM_operated','own_map_completed','start_to_finish_transport'))
        finalizer.finish()
        hashes={}
        for p in out.rglob('*'):
            if p.is_file() and p.name!='artifacts.sha256.json':
                with p.open('rb') as stream:hashes[str(p.relative_to(out))]=hashlib.file_digest(stream,'sha256').hexdigest()
        write(out/'artifacts.sha256.json',hashes)
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--driver-profile',choices=PROFILES,required=True);p.add_argument('--relay-receipt',type=Path,required=True)
    p.add_argument('--e2e-live',action='store_true');p.add_argument('--event-driven-llm',action='store_true')
    p.add_argument('--compact-prompt',action='store_true');p.add_argument('--setdown-only-when-relook',choices=('off','on_v1'),default='off')
    p.add_argument('--decider',choices=('off','jev_v1'),default='off')
    p.add_argument('--exploration-progress',choices=('off','frontier_progress_v1'),default='off')
    p.add_argument('--explore-deadlock',choices=('off','replan_v1'),default='off')
    p.add_argument('--boundary-association',choices=('off','extent_v1'),default='off')
    p.add_argument('--boundary-retry',choices=('off','navigation_v1'),default='off')
    p.add_argument('--boundary-coverage',choices=('off','native_v1'),default='off')
    p.add_argument('--pose-fix',choices=('off','innovation'),default='off')
    p.add_argument('--path-follow',choices=('off','rpp_v1'),default='off')
    p.add_argument('--stall-odometry',choices=('off','rgb_gate_v1','rgb_pulse_gate_v1','rgb_vo_v1','rgb_vo_v2','rgb_vo_us_v1'),default='off')
    p.add_argument('--ultrasonic-front',choices=('off','on_v1'),default='off')
    p.add_argument('--vo-floor-mask',choices=('off','homography_v1'),default='off')
    p.add_argument('--vo-rotation-policy',choices=('off','no_ransac_v1'),default='off')
    p.add_argument('--stall-recovery',choices=('off','backup_replan_v1'),default='off')
    p.add_argument('--stall-noise',choices=('off','amcl_alpha_v1'),default='off')
    p.add_argument('--stall-bundle',action='store_true')
    p.add_argument('--mapping-budget',choices=('off','case_cap_v1'),default='off')
    p.add_argument('--dev-light',action='store_true')
    p.add_argument('--boundary-views',choices=('off','candidate_views_v1','standoff_fullquad_v1'),default='off')
    p.add_argument('--b-marker-detect',choices=('off','contrast_v1','contrast_v2','partial_known_size_v1'),default='off')
    p.add_argument('--b-partial-accept',choices=('off','on_v1'),default='off')
    p.add_argument('--wall-cap-s',type=float,default=12600.)
    p.add_argument('--exact-provenance-index',action='store_true')
    p.add_argument('--exact-sha-cache',action='store_true')
    p.add_argument('--exact-omit-copy',action='store_true')
    p.add_argument('--exact-scalar-cells',action='store_true')
    p.add_argument('--exact-geometry-cache',action='store_true')
    p.add_argument('--exact-speed-bundle',action='store_true')
    p.add_argument('--exact-vector-rays',action='store_true')
    p.add_argument('--exact-shared-wall-frontend',action='store_true')
    p.add_argument('--exact-lazy-scan-path',action='store_true')
    p.add_argument('--exact-vector-costmap-writes',action='store_true')
    p.add_argument('--exact-track-cell-tuples',action='store_true')
    p.add_argument('--exact-speed2-bundle',action='store_true')
    p.add_argument('--rbpf-audit-hash',choices=('off','binary_v1','both_v1','none','final_v1'),default='off',
                   help='Measurement-only RBPF audit digest (with --measure-sim-s); off = legacy JSON digest')
    p.add_argument('--measure-sim-s',type=float,default=0.,help='External measurement stop; bundle horizon unchanged')
    p.add_argument('--measure-profile',action='store_true')
    p.add_argument('--speed3',choices=('off','dt1_v1','dt2_v1','adaptive_v1'),default='off')
    p.add_argument('--speed5',choices=('off','cache_v1','lean_v1','lean_v2','lean_v3'),default='off')
    p.add_argument('--speed4',type=json.loads,default=None,help='DEV compute budget JSON; all fields default off')
    p.add_argument('--runtime-registration',choices=('off','reviewed_v1'),default='off')
    p.add_argument('--expected-workflow-id')
    p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    b=bundle(a.expected_source_sha,a.seed,a.driver_profile,enabled=a.e2e_live,relook=a.setdown_only_when_relook,
             options=Options(a.event_driven_llm,a.compact_prompt,'en'),decider=a.decider,
             exploration_progress=a.exploration_progress,pose_fix=a.pose_fix,
             path_follow=a.path_follow,dev_light=a.dev_light,wall_cap_s=a.wall_cap_s,
             stall_odometry=a.stall_odometry,stall_recovery=a.stall_recovery,stall_noise=a.stall_noise,stall_bundle=a.stall_bundle,mapping_budget=a.mapping_budget,
             exact_speedups=dict(provenance_index=a.exact_provenance_index,sha_validation_cache=a.exact_sha_cache,omit_discarded_copy=a.exact_omit_copy,scalar_cells=a.exact_scalar_cells,geometry_cache=a.exact_geometry_cache,
                 vector_rays=a.exact_vector_rays,shared_wall_frontend=a.exact_shared_wall_frontend,lazy_scan_path=a.exact_lazy_scan_path,
                 vector_costmap_writes=a.exact_vector_costmap_writes,track_cell_tuples=a.exact_track_cell_tuples),
             speed_bundle=a.exact_speed_bundle,speed2_bundle=a.exact_speed2_bundle,boundary_views=a.boundary_views,b_marker_detect=a.b_marker_detect,runtime_registration=a.runtime_registration,ultrasonic_front=a.ultrasonic_front,vo_floor_mask=a.vo_floor_mask,vo_rotation_policy=a.vo_rotation_policy,explore_deadlock=a.explore_deadlock,boundary_association=a.boundary_association,boundary_retry=a.boundary_retry,boundary_coverage=a.boundary_coverage,speed3=a.speed3,speed4=a.speed4,b_partial_accept=a.b_partial_accept,speed5=a.speed5)
    if a.rbpf_audit_hash!='off' and not a.measure_sim_s:raise ValueError('RBPF_AUDIT_HASH_REQUIRES_MEASUREMENT')
    if a.expected_workflow_id is not None and a.expected_workflow_id!=b['execution_bundle_id']:
        raise ValueError('WORKFLOW_BUNDLE_ID_MISMATCH')
    if not a.execute:print(json.dumps(b));return
    if platform.system()!='Linux' or platform.machine()!='x86_64' or os.environ.get('MUJOCO_GL')!='osmesa':
        raise ValueError('AZURE_X86_OSMESA_ONLY')
    if not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs'):raise ValueError('PERSISTENT_RUN_REQUIRED')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=a.expected_source_sha:raise ValueError('COMMITTED_SHA_REQUIRED')
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:
        if a.measure_sim_s:
            from scripts.e2e_speed_measure import measured_run
            r=measured_run(run,b,a.output,a.relay_receipt,a.measure_sim_s,a.measure_profile,
                'final_v1' if a.speed3!='off' and a.rbpf_audit_hash=='off' else a.rbpf_audit_hash)
        else:r=run(b,a.output,a.relay_receipt)
    finally:undo()
    print(json.dumps(r));return int(r['status']!='FINISHED')


if __name__=='__main__':raise SystemExit(main())
