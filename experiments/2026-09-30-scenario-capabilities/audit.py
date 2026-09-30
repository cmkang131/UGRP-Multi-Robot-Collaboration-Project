"""P09 evaluation-only static audit. No scene, rendering, physics or model calls.

Run with the existing Python environment; this entry point takes the shared
host lock before geometry work or pytest. Outputs must be a NEW directory.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.abc
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
AUDIT_BASE = 'a8094cc14e098a55483f53a3c49bf6a0b116043d'
BRANCH = 'codex/scenario-capabilities'
SOURCES = (
    'harness/zone_scenario_feasibility.py', 'harness/zone_final_env.py',
    'harness/static_keepouts.py', 'harness/zone_team_footprint.py',
    'harness/zone_map_schematic.py', 'harness/zone_study_scenarios.py',
    'harness/zone_study_contract.py', 'harness/zone_study_inputs.py',
    'harness/zone_own_executor.py', 'harness/zone_pair_executor.py',
    'harness/zone_study_integration.py', 'scripts/run_zone_study_integration.py',
    'scripts/check_zone_scenarios.py', 'sim/zone_geometry_scene.py',
    'sim/zone_hidden_events.py', 'sim/zone_arena.py', 'sim/zone_cargo.py',
    'sim/research_dispatch_arena.py', 'tests/test_zone_scenario_feasibility.py',
    'tests/test_zone_final_env.py', 'harness/m1_owncam_delivery.py',
    'harness/pair_owncam_approach.py', 'harness/vision_pose_source.py',
    'sim/zone_own_scene_provider.py',
)
BLOCKED = ('mujoco', 'torch', 'tensorflow', 'cv2', 'openai', 'anthropic',
           'google.genai', 'google.generativeai', 'requests', 'httpx',
           'sim.session_scenes', 'sim.warehouse_mission')


class StaticOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == p or fullname.startswith(p + '.') for p in BLOCKED):
            raise RuntimeError('P09 static-only import boundary: ' + fullname)
        return None


def no_external_effect(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise RuntimeError('P09 static-only network boundary: ' + event)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def source_inventory():
    files = list(SOURCES) + ['maps/zones_final/catalog.json']
    catalog = json.loads((ROOT / files[-1]).read_text())
    files += [e['file'] for e in catalog['maps'].values()]
    for entry in catalog['scenarios'].values():
        files += [entry['file'], entry['v1']['file']]
    return {p: sha(ROOT / p) for p in sorted(set(files))}


def symbol_lines():
    out = {}
    for path in SOURCES:
        tree = ast.parse((ROOT / path).read_text())
        out[path] = {n.name: [n.lineno, n.end_lineno] for n in ast.walk(tree)
                     if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    return out


def passage_crossings(path, static):
    """Item reference crossing a passage centre plane, distinct from mouth visits.

    This supplements the evaluator's grown-mouth `passages_used` field. It does
    not claim clearance (the full formation sweep supplies that separately).
    """
    out = []
    for passage in static['passages']:
        if passage['kind'] == 'passing_bay':
            continue
        axis = 0 if passage['axis'] == 'x' else 1
        cross = 1 - axis
        plane = passage['center_m'][axis]
        lo = passage['center_m'][cross] - passage['half_extents_m'][cross]
        hi = passage['center_m'][cross] + passage['half_extents_m'][cross]
        # Require reference points on BOTH sides. Touching the plane and
        # retreating (or stopping on it) must not be counted as a passage.
        off_plane = [(i, p) for i, p in enumerate(path) if abs(p[axis] - plane) > 1e-9]
        for (ia, a), (ib, b) in zip(off_plane, off_plane[1:]):
            if (a[axis] - plane) * (b[axis] - plane) >= 0:
                continue
            direction = 1 if b[axis] > a[axis] else -1
            # The first segment reaches the plane; intermediate vertices may
            # lie on it. Full-footprint clearance remains a separate check.
            start, end = path[ia], path[ia + 1]
            fraction = (plane - start[axis]) / (end[axis] - start[axis])
            value = start[cross] + fraction * (end[cross] - start[cross])
            if lo <= value <= hi:
                labels = ('west_to_east', 'east_to_west') if axis == 0 else ('south_to_north', 'north_to_south')
                out.append({'passage': passage['id'], 'direction': labels[direction < 0],
                            'cross_coordinate_m': round(value, 6)})
    return out


def route_detail(route, static, item, obstacles=()):
    from harness.static_keepouts import keepout_rects
    from harness.zone_team_footprint import swept_clear
    path = route.path
    footprint = item.footprint(margin=route.margin_m or 0.)
    rects = tuple(keepout_rects(static, perimeter=True)) + tuple(obstacles)
    reverse = list(reversed(path))
    def swept(a, b):
        return swept_clear(a, b, footprint, rects, bounds=static['bounds_m'])
    return {
        **route.record(), 'authored_start_pose_m': list(item.pose),
        'path_m_rad': path,
        'passage_centre_crossings': passage_crossings(path, static),
        'reverse_passage_centre_crossings': passage_crossings(reverse, static),
        'translation_m': round(sum(math.dist(a[:2], b[:2]) for a, b in zip(path, path[1:])), 6),
        'yaw_travel_rad': round(sum(abs((b[2] - a[2] + math.pi) % (2 * math.pi) - math.pi)
                                    for a, b in zip(path, path[1:])), 6),
        'authored_start_to_lattice_swept': swept(item.pose, path[0]) if path else None,
        'reverse_same_path_swept': (all(swept(a, b) for a, b in zip(reverse, reverse[1:]))
                                    if path else None),
        'reverse_scope': 'same static obstacles, same formation and headings; no opposing traffic',
        'physical_passage': None, 'student_success': None,
    }


def extract(scenario, path, static):
    from harness.zone_scenario_feasibility import scenario_items
    from sim.zone_arena import layout
    placements = {p['item_id']: p for p in scenario['eval']['setup']['placements']}
    spec = layout(scenario['eval']['setup']['arena_variant'])
    # arena_default is a set of three spawn poses, NOT a fixed r1/r2/r3 mapping.
    # episode() shuffles after cargo sampling; no episode or scene is built here.
    spawns = [[spec['spawn_x'], y, 0.] for y in spec['spawn_rows_y']]
    items = []
    for item in scenario_items(scenario):
        x, y, yaw = item.pose
        c, s = math.cos(yaw), math.sin(yaw)
        stations = {}
        for role, (dx, dy, dyaw) in item.footprint(margin=0.).stations.items():
            pose = [x + c * dx - s * dy, y + s * dx + c * dy,
                    (yaw + dyaw + math.pi) % (2 * math.pi) - math.pi]
            stations[role] = {
                'base_xyyaw': [round(v, 6) for v in pose],
                'spawn_distance_lower_bounds_m': [round(math.dist(p[:2], pose[:2]), 6) for p in spawns],
                'collision_free_approach_path_m': None,
            }
        items.append({**item.record(), 'slot': placements[item.item_id]['slot'],
                      'source_pointer': f'/eval/setup/placements/{list(placements).index(item.item_id)}',
                      'catalogue_stations': stations})
    return {'scenario_id': scenario['scenario_id'], 'source_file': str(path.relative_to(ROOT)),
            'source_sha256': sha(path), 'map_id': scenario['map_id'], 'orders': scenario['orders'],
            'item_count': len(items), 'order_line_count': len(scenario['orders']), 'items': items,
            'robot_spawns': {'declaration': scenario['eval']['setup']['robot_spawns'],
                             'candidate_xyyaw': spawns, 'actor_assignment': None,
                             'reason': 'episode layout_seed and goal-dependent shuffle not bound by scenario'},
            'zones': {z: static['regions']['zone_' + z] for z in ('A', 'B', 'C')},
            'passages': static['passages'], 'hidden_events': scenario['eval']['hidden_events'],
            'seeds': scenario['seeds'], 'budget': scenario['eval']['budget'],
            'physical': {'success_rate': None, 'sim_seconds': None, 'command_count': None,
                         'model_calls': None, 'model_cost': None}}


def audit(output):
    from harness.zone_final_env import maps_dir_for, reachability
    from harness.zone_scenario_feasibility import evaluate, carry_route, ScenarioItem
    catalog = json.loads((ROOT / 'maps/zones_final/catalog.json').read_text())
    inventory, records = [], []
    for path in sorted((ROOT / 'configs/zone_study_scenarios_v2').glob('s*.json')):
        scenario = json.loads(path.read_text())
        map_path = maps_dir_for(scenario['map_id']) / (scenario['map_id'] + '.json')
        static = json.loads(map_path.read_text())
        assert sha(map_path) == scenario['eval']['setup']['map_file_sha256']
        assert sha(path) == catalog['scenarios'][scenario['scenario_id']]['file_sha256']
        inv = extract(scenario, path, static)
        inventory.append(inv)
        report = evaluate(scenario, maps_dir=maps_dir_for(scenario['map_id']))
        rec = report.record()
        rec['maps_dir'] = str(map_path.parent.relative_to(ROOT))
        rec['disc_reachability'] = {}
        for radius in (.17, .21):
            graph, problems = reachability(static, scenario['orders'], radius_m=radius)
            rec['disc_reachability'][str(radius)] = {'graph': graph, 'problems': problems}
        rec['routes'] = {item.item_id: route_detail(report.routes[item.item_id], static, item)
                         for item in report.items}
        # Preserve the actual after-event routes (evaluate records only kept/lost).
        # Same event-only obstacles as the existing evaluator, not cumulative time simulation.
        rec['event_routes'] = {}
        for event in report.events:
            if not event['checked']:
                continue
            changed = {}
            for item in report.items:
                obstacles = event.get('obstacle_rects', ())
                if event['kind'] == 'item_moved':
                    source = next(e for e in scenario['eval']['hidden_events']
                                  if e['event_id'] == event['event_id'])
                    if item.item_id == source['target']['item_id']:
                        item = ScenarioItem(item.item_id, item.kind, tuple(event['to_pose_m']),
                                            item.destination_zone, item.required_robots, item.order_id)
                        obstacles = ()
                route = carry_route(static, item, obstacles=obstacles)
                changed[item.item_id] = route_detail(route, static, item, obstacles)
            rec['event_routes'][event['event_id']] = changed
        records.append(rec)
        print(scenario['scenario_id'], report.verdict,
              [(f.code, f.item_id) for f in report.findings], flush=True)
    write(output / 'inventory.json', inventory)
    write(output / 'feasibility.json', records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tests', action='store_true')
    parser.add_argument('--lock-wait-s', type=int, default=0,
                        help='bounded wait for the same shared lock; never bypass it')
    args = parser.parse_args()
    if not 0 <= args.lock_wait_s <= 3600:
        parser.error('--lock-wait-s must be between 0 and 3600')
    # All git calls finish before installing the no-network hook.
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    if branch != BRANCH:
        raise SystemExit(f'wrong assigned branch: {branch}')
    from scripts.agent_lock import acquire, release, status, DEFAULT_ROOT
    args.output.mkdir(parents=True, exist_ok=False)
    before = source_inventory()
    base_equal = subprocess.run(['git', 'diff', '--quiet', AUDIT_BASE, '--', *before], cwd=ROOT).returncode == 0
    manifest = {'audit_base': AUDIT_BASE, 'source_head': head, 'branch': branch,
                'audit_script_sha256': sha(Path(__file__)), 'audit_base_inputs_equal': base_equal,
                'audit_tests_sha256': sha(Path(__file__).with_name('test_audit.py')),
                'python': platform.python_version(), 'platform': platform.platform(),
                'input_sha256': before, 'symbols': symbol_lines(), 'guard': list(BLOCKED),
                'scope': 'evaluation_only_static', 'physics_runs': 0, 'render_calls': 0,
                'model_calls': 0, 'student_trials': 0, 'started_unix': time.time()}
    wait_start = time.monotonic()
    while True:
        try:
            lock = acquire(DEFAULT_ROOT, owner='codex', branch=branch, purpose='P09 static audit and pytest only',
                           pid=os.getpid(), expected_minutes=10)
            break
        except RuntimeError as error:
            if not str(error).startswith('lock held:') or time.monotonic() - wait_start >= args.lock_wait_s:
                raise
            time.sleep(.2)
    manifest['lock_wait_wall_s'] = round(time.monotonic() - wait_start, 3)
    manifest['started_unix'] = time.time()
    manifest['lock'] = lock
    sys.meta_path.insert(0, StaticOnly())
    sys.addaudithook(no_external_effect)
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    exit_code = 0
    try:
        # Import inspection preceded this run. PIL is an import-only dependency;
        # fail loudly even for an accidental static schematic render.
        from harness import zone_map_schematic
        def no_render(*args, **kwargs):
            raise RuntimeError('P09: rendering forbidden')
        zone_map_schematic.render_schematic = no_render
        audit(args.output)
        if args.tests:
            import pytest
            exit_code = pytest.main(['-q', '-p', 'no:cacheprovider',
                                     'tests/test_zone_scenario_feasibility.py',
                                     'tests/test_zone_final_env.py',
                                     'experiments/2026-09-30-scenario-capabilities/test_audit.py'])
        assert source_inventory() == before, 'source/config drift during static audit'
        manifest['inputs_unchanged'] = True
        manifest['pytest_exit_code'] = int(exit_code) if args.tests else None
        manifest['forbidden_imports_loaded'] = [m for m in sys.modules
            if any(m == p or m.startswith(p + '.') for p in BLOCKED)]
        assert not manifest['forbidden_imports_loaded']
    finally:
        manifest['ended_unix'] = time.time()
        manifest['loadavg_end'] = os.getloadavg()
        held = status(DEFAULT_ROOT)
        if held and held['pid'] == os.getpid() and held['branch'] == branch:
            release(DEFAULT_ROOT, owner='codex')
            manifest['lock_released'] = True
        write(args.output / 'manifest.json', manifest)
    return int(exit_code)


if __name__ == '__main__':
    raise SystemExit(main())
