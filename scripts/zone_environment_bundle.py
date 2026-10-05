"""Legacy static preview plus an explicit v84 environment check bundle CLI.

The v6e runner stays byte-identical. Reuse its non-physical bundle helpers,
with explicit map routing and environment inputs for a future registration.
This preview cannot inherit its base runner's execution bundle ID/admission.
The v84 check bundle is DRAFT and uses its separately registered workflow;
it does not seal or make a legacy student preregistration runnable.
"""
import json
from pathlib import Path

from scripts import run_zone_study_integration as legacy
from scripts.run_zone_study_integration import (
    ROOT, zi, zo, llm, zr, ROBOTS, MAIN_CONDITIONS, OwnCamTeamHost,
    digest, host_spec, evaluation_top_config, _StubLink,
)
from harness.zone_environment_candidate import candidate_contract, source_files


def runtime_files(prereg, provider, map_id):
    from harness.python_source_closure import source_closure
    # Include all statically selected environment inputs even on tagged maps.
    return source_closure(ROOT, (*legacy.runtime_files(prereg, provider),
                                'scripts/zone_environment_bundle.py', *source_files(map_id)))


def run_bundle(prereg, episode, *, model_adapter=None, driver=None):
    """Everything that identifies this execution, hashed (docs/execution_versioning.md)."""
    from harness.zone_study_scenarios import bundle_for, validate
    from harness.zone_environment_registry import maps_dir_for, provider_binding
    from sim.zone_environment_scene_provider import scene_static_map
    scenario = json.loads((ROOT / episode['scenario']).read_text())
    if scenario['map_id'] != episode['map']:
        raise SystemExit('scenario map_id differs from episode map')
    maps_dir = maps_dir_for(episode['map'])
    provider = zi.pose_provider_spec(prereg['pose_provider'], map_id=episode['map'])
    try:
        environment = provider_binding(episode['map'], provider, prereg['student']['calibration'],
                                       robot_model=episode.get('robot_model'),
                                       static_map_sha256=episode.get('static_map_sha256'))
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if not provider['uses_landmark_tags'] and scenario.get('landmark_detail') != 'none':
        raise SystemExit('geometry provider requires explicit landmark_detail=none')
    report = validate(scenario, maps_dir=maps_dir)
    if not report.ok:
        raise SystemExit(f'scenario {episode["scenario"]} fails validation: {report.checks}')
    map_bundle = bundle_for(scenario, maps_dir=maps_dir)
    static = json.loads(Path(map_bundle['map_file']).read_text())
    if environment is not None and episode['base_map'] != static['base_map']['map_id']:
        raise SystemExit('episode base_map differs from registered environment')
    if static != scene_static_map(episode['map']):
        raise SystemExit('the map file the robots read differs from the static map the scene builds')
    spec = host_spec(scenario, episode, map_bundle)
    from scripts.zone_pair_dev_contract import profile_contract
    # Record the calibration actually passed to the executor/provider, including
    # the M2 loop-v2 calibration. Never label it with the registry's M1 default.
    provider['calibration'] = prereg['student']['calibration']
    stub = {r: _StubLink(r) for r in ROBOTS}
    limits, caps = llm.speech_caps_for(prereg)
    trial = zi.IntegratedTrial(scenario, condition=MAIN_CONDITIONS[0], seed=episode['trial_seed'], links=stub,
                               horizon_s=prereg['horizon_s'], map_bundle=map_bundle,
                               policy=zo.CallPolicy(**prereg.get('call_policy', {})),
                               decision_limits=limits,
                               pose_label=zi.provider_record(provider)['label'])
    invariant = zi.condition_invariant_config(trial.study_config())
    if driver is not None:
        model_adapter = zi.ModelAdapter(driver.client_factory, None)
    if model_adapter is not None:
        invariant.update(zi.model_config('gemini_proxy', model_adapter.client_factory))
    from harness.owncam_memory_time import TIME_CONTRACT
    bundle = {'execution_bundle_id': None, 'schema': 'ugrp.zone_environment_candidate_bundle.v1',
              'base_execution_bundle_id': zi.EXECUTION_BUNDLE_ID,
              'status': 'DRAFT_UNSEALED', 'runnable': False, 'research_result': False,
              'memory_time_contract': TIME_CONTRACT,
              'runtime_files_sha256': {f: zi.file_sha256(ROOT / f) for f in runtime_files(prereg, provider, episode['map'])},
              'scenario': episode['scenario'], 'scenario_sha256': zi.file_sha256(ROOT / episode['scenario']),
              'map_id': episode['map'], 'map_file_sha256': map_bundle['map_file_sha256'],
              'public_map_sha256': map_bundle['public_map_sha256'], 'scene_static_map_sha256': digest(scene_static_map(episode['map'])),
              'physical': {k: episode[k] for k in ('base_map', 'layout_seed', 'goal', 'extra_boxes',
                                                    'contact_profile', 'job_sim_limit_s')},
              'actor': 'gemini_proxy' if model_adapter else zi.FIXTURE_ACTOR,
              'model_settings_sha256': digest(model_adapter.client_factory.settings) if model_adapter else None,
              'host_spec': spec, 'contact_profile_expected': profile_contract(),
              'perception_delay_s': zi.PERCEPTION_DELAY_S,
              'weld': 'off', 'sync_sim': True, 'frame_period_s': OwnCamTeamHost.FRAME_S,
              'executor_tick_s': zi.QUANTUM_S, 'student': dict(prereg['student']),
              'student_calibration_sha256': zi.file_sha256(ROOT / prereg['student']['calibration']),
              'pose_provider': zi.provider_record(provider),
              'eval_top_camera': evaluation_top_config(static),
              'referee': zr.profile(), 'hidden_events': zr.HiddenEventSchedule(scenario).config(),
              'study_invariant': invariant,
              'conditions': list(MAIN_CONDITIONS), 'horizon_s': prereg['horizon_s'],
              'speech_caps': caps, 'llm_driver': driver.bundle_record() if driver is not None else None}
    bundle['environment_contract'] = candidate_contract({}, episode['map'])
    if environment is not None:
        bundle['environment_binding'] = environment
    return bundle, scenario, map_bundle, provider


def main(argv=None):
    import argparse
    from harness.zone_final_environment import bundle
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map-id', required=True)
    parser.add_argument('--check', choices=('p01', 'calibration', 'p03'), default='p01')
    args = parser.parse_args(argv)
    print(json.dumps(bundle(args.map_id, check=args.check), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
