#!/usr/bin/env python3
"""PairTeam + OwnCamTeamHost dev adapter. Default: prepare only, no MuJoCo import.

Execution is deliberately explicit, source-pinned, managed, and lock-owned.
No model is called. Runtime GT and observer images live exclusively in eval_only/.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.zone_pair_dev_contract import PREVIOUS_PREREG, profile_contract, timing_contract, scene_contract

WORKFLOW = 'zone-pair-dev'
SCHEMA = 'ugrp.zone_pair_dev.v1'
LABELS = ['tags_temporary', 'dev', '연구 결과 아님']
PREREG = ROOT / 'experiments/2026-09-27-zone-pair-dev/prereg_v2_DRAFT.json'
PREREG_V3 = PREREG.with_name('prereg_v3.json')
PREREG_V4 = PREREG.with_name('prereg_v4.json')
PREREG_V5 = PREREG.with_name('prereg_v5.json')
PREREG_V5B = PREREG.with_name('prereg_v5b.json')
PREREG_V5C = PREREG.with_name('prereg_v5c.json')
PREREG_V5D = PREREG.with_name('prereg_v5d.json')
PREREG_V5E = PREREG.with_name('prereg_v5e.json')
PREREG_V5F = PREREG.with_name('prereg_v5f.json')
PREREG_V5G = PREREG.with_name('prereg_v5g.json')
PREREG_V5H = PREREG.with_name('prereg_v5h.json')
MAP = ROOT / 'maps/zones/zone_wide_door_tags_v2.json'
CALIBRATION = ROOT / 'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'
PARTICIPANTS = ('r1', 'r2')
PROFILE_CONTRACT = profile_contract()
EXPECTED = {'map': 'zone_wide_door_tags_v2', 'participants': list(PARTICIPANTS),
            'world_robots': ['r1', 'r2', 'r3'], 'cargo': [{'item_id': 'cargoX', 'kind': 'long_beam'}],
            'other_objects': 0, 'weld': False, 'contact_profile': 'cargo_noslip_v1',
            'noslip_iterations': PROFILE_CONTRACT['noslip_iterations'],
            'timestep_s': PROFILE_CONTRACT['timestep_s']}
ORDER = {'orders': [{'order_id': 'cargoX', 'kind': 'long_beam', 'count': 1, 'required_robots': 2,
                     'destination_zone': 'B', 'initial_location': {'pickup_bay': 'P2', 'slot': 'P2-3'}}]}


def registered_v3(prereg):
    # Registered successors retain the dock-v3 scene (not the old v3 DRAFT).
    return prereg.get('registration_version') in (3, 4, 5) and prereg.get('status') == 'REGISTERED'


def map_path(prereg):
    if prereg.get('registration_version') == 6:
        return ROOT / prereg['inputs']['map']['path']
    if registered_v3(prereg):
        from sim.zone_start_dock import MAP_ID
        return ROOT / f'maps/zones/{MAP_ID}.json'
    return MAP


def expected_environment(prereg):
    return {**EXPECTED, 'map': map_path(prereg).stem}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def primary_root():
    common = Path(git('rev-parse', '--git-common-dir'))
    return (ROOT / common).resolve().parent


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prereg', type=Path, default=PREREG)
    p.add_argument('--run-id', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true', help='explicit physical run; coordinator only')
    p.add_argument('--expected-source-sha', help='full clean committed HEAD required for --execute')
    p.add_argument('--lock-owner', choices=('claude', 'codex', 'kiro'))
    p.add_argument('--pair-policy', choices=('v5h','b-only','a+b'), help='must match the v6 registered case')
    return p


def load_config(args):
    prereg = json.loads(args.prereg.read_text())
    if prereg.get('registration_version') == 6:
        from scripts.zone_pair_v6_contract import load_config as load_v6
        return load_v6(args)
    if getattr(args,'pair_policy',None) not in (None,'v5h'):
        raise ValueError('v6 pair policy requires a v6 registration')
    expected = expected_environment(prereg)
    if prereg.get('schema') != SCHEMA or prereg.get('labels') != LABELS or prereg.get('environment') != expected:
        raise ValueError('unsupported or altered dev environment/labels')
    if (prereg.get('status') != 'DRAFT' and not registered_v3(prereg)) or prereg.get('research_result') is not False:
        raise ValueError('this driver is for preregistered dev only')
    version = prereg.get('registration_version')
    revision = prereg.get('registration_revision')
    if revision is not None and (version != 5 or revision not in ('v5b', 'v5c', 'v5d', 'v5e', 'v5f', 'v5g', 'v5h')):
        raise ValueError('unsupported prereg revision')
    from scripts.zone_pair_authorization import validate_authorization
    validate_authorization(prereg)
    if version not in (2, 3, 4, 5):
        raise ValueError('use prereg v2 or registered v3/v4/v5; preserve earlier versions')
    if version in (4, 5) and not registered_v3(prereg):
        raise ValueError('v4/v5 requires a registered grasp contract')
    if version == 3 and args.execute and not registered_v3(prereg):
        raise ValueError('v3 is prepare-only: coordinator startup/dock decision and implementation are pending')
    if registered_v3(prereg):
        if prereg.get('scene_contract') != scene_contract():
            raise ValueError('scene contract/hash mismatch')
        v2 = json.loads(PREREG.read_text())
        for key in ('criteria', 'planned_setdown', 'limits', 'safety_coverage'):
            if prereg.get(key) != v2[key]:
                raise ValueError(f'v3 must preserve v2 {key}')
        if {k: v for k, v in prereg['stage_rules'].items() if k != 'admission_diagnostics'} != v2['stage_rules']:
            raise ValueError('v3 must preserve v2 stage rules')
        readiness = prereg.get('execution_readiness', {})
        readiness_status = ('AWAITING_EXECUTION_AUTHORIZATION' if revision in ('v5f', 'v5g', 'v5h') else
                            'PREPARE_ONLY_REVIEW_HOLD' if revision in ('v5d', 'v5e') else 'READY_AFTER_SOURCE_FREEZE')
        if (readiness.get('status') != readiness_status
                or readiness.get('spawn_change_applied') is not True
                or readiness.get('startup_policy') != 'relocate_static_dock_x_minus_0_65'):
            raise ValueError('v3 dock decision/readiness missing')
        for old, new in zip(v2['runs'], prereg['runs'], strict=True):
            excluded = ('id', 'seed') if version in (4, 5) else ('id',)
            if {k: v for k, v in new.items() if k not in excluded} != {k: v for k, v in old.items() if k not in excluded}:
                raise ValueError('v3 must preserve v2 seeded cargo/order/intervention')
    if version in (4, 5):
        from scripts.zone_pair_grasp_contract import grasp_contract
        v3 = json.loads(PREREG_V3.read_text())
        for key in ('criteria', 'stage_rules', 'planned_setdown', 'limits', 'safety_coverage', 'timing', 'environment', 'inputs'):
            if prereg.get(key) != v3[key]:
                raise ValueError(f'v4 must preserve v3 {key}')
        if prereg.get('grasp_contract') != grasp_contract():
            raise ValueError('grasp contract/hash mismatch')
    if prereg.get('contact_profile_contract') != profile_contract():
        raise ValueError('contact profile contract/hash mismatch; freeze a new prereg before execution')
    previous_path = {2: PREVIOUS_PREREG, 3: PREREG, 4: PREREG_V3, 5: PREREG_V4}[version]
    if revision == 'v5b':
        previous_path = PREREG_V5  # unexecuted v5 remains byte-identical history
    elif revision == 'v5c':
        previous_path = PREREG_V5B  # executed dev09/10 remain immutable
    elif revision == 'v5d':
        previous_path = PREREG_V5C  # unexecuted registration preserved byte-for-byte
    elif revision == 'v5e':
        previous_path = PREREG_V5D  # constructor fix; same still-unexecuted dev11/12
    elif revision == 'v5f':
        previous_path = PREREG_V5E
    elif revision == 'v5g':
        previous_path = PREREG_V5F
    elif revision == 'v5h':
        previous_path = PREREG_V5G  # executed dev11/12 remain immutable
    previous = {'path': str(previous_path.relative_to(ROOT)), 'sha256': sha_file(previous_path)}
    if prereg.get('supersedes') != previous:
        raise ValueError('previous prereg hash mismatch')
    timing, frozen_limits = timing_contract(json.loads(PREVIOUS_PREREG.read_text()), EXPECTED['timestep_s'])
    if (prereg.get('timing') != timing or prereg['criteria'].get('gt_sample_period_s') != timing['gt_sample_period_s']
            or prereg['criteria']['max_sample_gap_s'] != timing['max_sample_gap_s']):
        raise ValueError('profile-derived sampling/step contract mismatch')
    rows = prereg['runs']
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('duplicate run ids')
    case = next((r for r in rows if r['id'] == args.run_id), None)
    if case is None:
        raise ValueError('run-id is not preregistered')
    if type(case['seed']) is not int or not 0 <= case['seed'] < 2**32:
        raise ValueError('seed must be a uint32 integer')
    expected_runs = {2: [('dev03', 901), ('dev04', 902)], 3: [('dev05', 901), ('dev06', 902)],
                     4: [('dev07', 903), ('dev08', 904)], 5: [('dev09', 905), ('dev10', 906)]}[version]
    if revision in ('v5c', 'v5d', 'v5e', 'v5f', 'v5g'):
        expected_runs = [('dev11', 907), ('dev12', 908)]
    elif revision == 'v5h':
        expected_runs = [('dev13', 909), ('dev14', 910)]
    if [(r['id'], r['seed']) for r in rows] != expected_runs:
        raise ValueError(f'v{version} fixes {expected_runs}; do not reuse prior IDs')
    limits = prereg['limits']
    for k in ('sim_s', 'wall_s', 'submit_at_s', 'post_terminal_s', 'outer_wall_timeout_s'):
        v = limits[k]
        if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
            raise ValueError(f'{k} must be positive and finite')
    if limits != frozen_limits:
        raise ValueError('dev budgets must match the profile-derived frozen v2 limits')
    if case.get('intervention') not in ('none', 'abort_after_carry_go'):
        raise ValueError('unsupported intervention')
    pose = case['setup_beam_xyyaw']
    if len(pose) != 3 or not all(type(x) in (int, float) and math.isfinite(x) for x in pose):
        raise ValueError('invalid setup beam pose')
    if not (.7 <= pose[0] <= 1.2 and abs(pose[1] - .05) <= .15 and abs(pose[2]) <= math.radians(10)):
        raise ValueError('beam outside supported M2 pickup envelope')
    # The same documented coarse quantization, without importing the frozen physical CLI.
    q = lambda v, g: round(round(v / g) * g, 6)
    sheet = {'beam_xyyaw': [q(pose[0], .1), q(pose[1], .1), q(pose[2], math.radians(10))],
             'grid': {'xy_m': .1, 'yaw_rad': round(math.radians(10), 6)},
             'source': 'coarse order sheet (setup pose rounded to the sheet grid; static, fixed before the run)'}
    if case['coarse_order_sheet'] != sheet:
        raise ValueError('predeclared coarse sheet does not match setup quantization')
    for name, path in [('map', map_path(prereg)), ('calibration', CALIBRATION)]:
        if (sha_file(path) != prereg['inputs'][name]['sha256']
                or prereg['inputs'][name]['path'] != str(path.relative_to(ROOT))):
            raise ValueError(f'{name} hash mismatch')
    if digest(ORDER) != prereg['inputs']['order_sheet_sha256']:
        raise ValueError('order sheet hash mismatch')
    if args.output.exists():
        raise ValueError('output must be new; originals are never overwritten')
    if args.execute:
        if not args.expected_source_sha or not re.fullmatch('[0-9a-f]{40}', args.expected_source_sha):
            raise ValueError('--execute requires full --expected-source-sha')
        if args.lock_owner is None:
            raise ValueError('--execute requires --lock-owner')
        if not args.output.is_absolute() or not args.output.resolve().is_relative_to(primary_root() / 'outputs'):
            raise ValueError('physical raw output must be absolute under primary checkout outputs/')
        validate_authorization(prereg, execute=True, expected_source_sha=args.expected_source_sha,
                               run_id=args.run_id)
    return prereg, copy.deepcopy(case)


def build_manifest(prereg, case, *, source, environment, prereg_path, applied=None):
    """No requested value is passed off as an actual model setting before construction."""
    return {'schema': SCHEMA, 'labels': LABELS, 'research_result': False, 'run_id': case['id'],
            'seed': case['seed'], 'intervention': case['intervention'], 'source': source,
            'environment': environment, 'requested': copy.deepcopy(prereg['environment']), 'applied': applied,
            'contact_profile_contract': copy.deepcopy(prereg.get('contact_profile_contract')),
            'scene_contract': copy.deepcopy(prereg.get('scene_contract')),
            'grasp_contract': copy.deepcopy(prereg.get('grasp_contract')),
            'timing': copy.deepcopy(prereg.get('timing')),
            'state': 'prepared_not_executed' if applied is None else 'running',
            'limits': prereg['limits'], 'prereg': {'path': str(prereg_path), 'sha256': sha_file(prereg_path)},
            'inputs': {**prereg['inputs'], 'coarse_order_sheet_sha256': digest(case['coarse_order_sheet'])},
            'input_contract': ['own wrist robot_cam RGB', 'own issued commands',
                               'static map/calibration/coarse order sheet', 'STATUS enums'],
            'pose_provider': {'implementation': 'harness.owncam_pose_source.OwnCamPoseSource',
                              'labels': LABELS, 'live_gt': False},
            'r3_policy': {'mode': 'idle_at_standard_seeded_spawn', 'task_api_calls': 0,
                          'normal_physics_preserved': True, 'noninterference': 'pending eval_only checks'},
            'execution_authorization': copy.deepcopy(prereg.get('execution_authorization')),
            'github_authorization': None,
            'pair_policy': case.get('pair_policy','v5h'),
            'v6_contract': copy.deepcopy(prereg.get('v6_contract')),
            'registration_sha256': prereg.get('registration_sha256'),
            'model_calls': 0, 'physical_success': None,
            'common_record': 'parent sim_cli workflow manifest links source/config/input/environment/result receipts'}


def applied_settings(host, *, validate=True, expected=None):
    expected = EXPECTED if expected is None else expected
    actual = {**EXPECTED, 'world_robots': list(host.world.robot_ids),
              'cargo': [{'item_id': c.item_id, 'kind': c.kind} for c in host.scene.cargo],
              'other_objects': len(host.scene.config['setup_only']['objects']),
              'weld': bool(any(host.world.data.eq_active)),
              'map': host.static['map_id'], 'contact_profile': host.contact_record['profile'],
              'noslip_iterations': int(host.world.model.opt.noslip_iterations),
              'timestep_s': float(host.world.model.opt.timestep)}
    if validate and actual != expected:
        raise ValueError(f'actual model settings differ: {actual}; expected: {expected}')
    if validate and 'start_dock' in host.static:
        from sim.zone_start_dock import static_spawn_keepouts
        records = [{**{k: v for k, v in d.items() if k != 'center_m'}, 'xy_m': d['center_m']}
                   for d in static_spawn_keepouts(host.static)]
        if host.keepout_records != records:
            raise ValueError('actual static spawn keepouts differ from map')
    from harness.zone_pair_executor import PairTeam
    if validate and not isinstance(host.pairs, PairTeam):
        raise ValueError('host is not using PairTeam')
    return actual


def validate_scene(prereg, scene):
    """Configuration receipt before world construction; never use settled/live poses."""
    if registered_v3(prereg):
        from sim.zone_start_dock import profile_record
        static = json.loads(map_path(prereg).read_text())
        spawns = scene.config['setup_only']['spawns']
        dock = profile_record()
        if (scene.config['static_map'] != static or set(spawns) != {'r1', 'r2', 'r3'}
                or any(p[0] != dock['spawn_x_m'] or p[3] != dock['spawn_yaw_rad'] for p in spawns.values())
                or sorted(p[1] for p in spawns.values()) != sorted(dock['spawn_rows_y_m'])):
            raise ValueError('actual scene configuration differs from dock prereg')
        cases = [r for r in prereg['runs'] if r['seed'] == scene.scene['seed']]
        if (len(cases) != 1 or scene.record()['resolved_sha256']
                != prereg['scene_instances'][cases[0]['id']]['resolved_sha256']):
            raise ValueError('resolved scene configuration hash mismatch')


class DevActor:
    """A fixed script for ONE robot; independent submissions, never peer state/GT.

    It first requests an own-camera look, then submits at/after the fixed SIM
    timestamp when its own look ends. Refusal is recorded, never retried for luck.
    """
    def __init__(self, robot_id, submit_at_s):
        self.robot_id, self.submit_at_s = robot_id, submit_at_s
        self.look_sent = self.submitted = False
        self.ack = None

    def tick(self, own, call, now):
        if not self.look_sent:
            self.look_sent = True
            call('look_around')
        if not self.submitted and now >= self.submit_at_s and own.job is None:
            self.submitted = True
            self.ack = call('pair_carry', 'cargoX', 'B', 'r2' if self.robot_id == 'r1' else 'r1')


class WallLimit(RuntimeError):
    pass


def execute(args, prereg, case, manifest):
    """Only entered after CLI admission; all simulator imports are below this line."""
    from scripts.zone_pair_dev_runtime import run_physical
    return run_physical(args, prereg, case, manifest)


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        prereg, case = load_config(args)
        from sim.workflow_manager import MANAGED_CHILD, environment_identity, git_identity, source_fingerprint
        source = {**git_identity(ROOT), 'execution_tree': source_fingerprint(ROOT)}
        if args.execute:
            from scripts import agent_lock
            if os.environ.get(MANAGED_CHILD) != '1':
                raise ValueError('execute via sim_cli workflow run zone-pair-dev for the common record')
            from scripts.zone_pair_authorization import verify_source
            verify_source(ROOT, args.prereg, prereg, args.expected_source_sha)
            held = agent_lock.status(primary_root() / 'outputs/agent-locks')
            if not held or not held['pid_alive'] or held['owner'] != args.lock_owner or held['branch'] != git('branch', '--show-current'):
                raise ValueError('live agent_lock matching owner and branch required')
            if git('branch', '--show-current') == 'main':
                raise ValueError('physical driver must run from its task worktree')
        args.output.mkdir(parents=True)
        environment = {**environment_identity(), 'loadavg_at_start': list(os.getloadavg())}
        manifest = build_manifest(prereg, case, source=source, environment=environment, prereg_path=args.prereg)
        prereg_bytes = args.prereg.read_bytes()
        if hashlib.sha256(prereg_bytes).hexdigest() != manifest['prereg']['sha256'] or json.loads(prereg_bytes) != prereg:
            raise ValueError('prereg changed during preparation')
        write_json(args.output / 'manifest.json', manifest)
        (args.output / 'prereg.json').write_bytes(prereg_bytes)
        # Setup-only values are saved apart from the static inputs actually supplied to actors.
        write_json(args.output / 'eval_only/setup.json', case)
        write_json(args.output / 'inputs/static.json', {'map': json.loads(map_path(prereg).read_text()),
                   'calibration': json.loads(CALIBRATION.read_text()), 'order_sheet': ORDER,
                   'coarse_order_sheet': case['coarse_order_sheet'], 'labels': LABELS})
        if not args.execute:
            print(json.dumps({'state': manifest['state'], 'manifest': str(args.output / 'manifest.json')}))
            return 0
        # Recheck the exact authorization bytes and source immediately before admission.
        if args.prereg.read_bytes() != prereg_bytes:
            raise ValueError('prereg changed after preparation')
        verify_source(ROOT, args.prereg, prereg, args.expected_source_sha)
        from scripts.zone_pair_authorization import verify_github_authorization
        verified = verify_github_authorization(prereg, args.expected_source_sha, args.run_id)
        # The network round trip must not open a source/envelope mutation window.
        if args.prereg.read_bytes() != prereg_bytes:
            raise ValueError('prereg changed during GitHub approval lookup')
        verify_source(ROOT, args.prereg, prereg, args.expected_source_sha)
        manifest['github_authorization'] = verified
        write_json(args.output / 'manifest.json', manifest)
        return execute(args, prereg, case, manifest)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        p.exit(2, f'{type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
