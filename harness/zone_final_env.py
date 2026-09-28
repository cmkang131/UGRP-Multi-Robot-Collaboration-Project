"""Final study environment (#218, main-study prereg blocker B5): walls_v3, zero tags, scenario v2.

User decisions (2026-09-26/28): the final environment is the environment-v3 wall
profile ``walls_v3`` (every wall 0.40 m) with **no** AprilTag and nothing designed
around tags. The six study scenarios ``configs/zone_study_scenarios/s1..s6`` pin
``*_tags_v1`` maps; this module moves them onto tag-free walls_v3 maps as NEW
files (scenario v2) and leaves every v1 file byte-identical.

Reuse (REUSE FIRST, 2026-09-26):

* Map recipe: ``maps/zones/zone_wide_door_geometry_v2.json`` (PR #240 family,
  ``sim/zone_geometry_scene.py``) is already a tag-free walls_v3 map, built as
  ``sim.zone_arena.authored_map(base)`` + ``apply_wall_profile(.., 'walls_v3')`` +
  ``map_id``/``version 4``/``base_map`` link, written with ``json.dumps(indent=2)``.
  The door scenarios reuse that file unchanged. ``final_map`` reproduces it byte
  for byte (tested), and the same recipe builds the two missing maps
  (``zone_wide_two_doors`` / ``zone_wide_corridor``) under ``maps/zones_final/``.
  ``maps/zones/*`` is owned by other work, so new files do not go there.
* Scenario checks: ``harness.zone_study_scenarios.validate`` (contract, order
  sheet, placements, hidden events, leader rotation) with ``maps_dir``.
* Map schema and projection: ``harness.zone_map_schematic.load_map`` /
  ``public_map``; obstacle rectangles: ``harness.static_keepouts.keepout_rects``;
  robot disc radii: ``harness.zone_scenario_feasibility`` (teacher values).

Static checks here (no MuJoCo, no scene, no model, no simulator state):
``check_map`` (schema, no tag field, walls 0.40 m, 2-D geometry identical to the
base map), ``passage_widths`` (measured wall gap equals the declared 0.50 / 1.00 m),
``reachability`` (grid flood fill of the disc-inflated free space: every order's
pickup slot and destination zone exist and are connected) and ``scenario_diff``
(v2 differs from v1 only in the map pin). Formation-level carry routes stay with
``harness.zone_scenario_feasibility.evaluate``; physics (contact, own-camera
localisation, completion) is not checked here and must not be reported as such.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import deque
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from harness.static_keepouts import keepout_rects
from harness.zone_map_schematic import MAP_DIR, load_map, pickup_bays, public_map
from harness.zone_scenario_feasibility import CARRY_RADIUS_M, ROBOT_RADIUS_M
from harness.zone_study_contract import ZONE_IDS

ROOT = Path(__file__).resolve().parents[1]
ENV_ID = 'zone_final_env_v1'
CATALOG_SCHEMA = 'ugrp.zone_final_env_catalog.v1'
WALL_PROFILE = 'walls_v3'
MAP_VERSION = 4                      # same as the reused zone_wide_door_geometry_v2
FINAL_MAP_DIR = ROOT / 'maps' / 'zones_final'
V1_SCENARIO_DIR = ROOT / 'configs' / 'zone_study_scenarios'
V2_SCENARIO_DIR = ROOT / 'configs' / 'zone_study_scenarios_v2'
CATALOG_PATH = FINAL_MAP_DIR / 'catalog.json'
# final map id -> (base map, directory of the file). The door map is the existing file.
FINAL_MAPS = {
    'zone_wide_door_geometry_v2': ('zone_wide_door', MAP_DIR),
    'zone_wide_two_doors_final_v1': ('zone_wide_two_doors', FINAL_MAP_DIR),
    'zone_wide_corridor_final_v1': ('zone_wide_corridor', FINAL_MAP_DIR),
}
# v1 tag map pinned by the v1 scenarios -> tag-free final map on the same base.
V1_MAP_TO_FINAL = {
    'zone_wide_door_tags_v1': 'zone_wide_door_geometry_v2',
    'zone_wide_two_doors_tags_v1': 'zone_wide_two_doors_final_v1',
    'zone_wide_corridor_tags_v1': 'zone_wide_corridor_final_v1',
}
V2_SUFFIX = '_v2'
# The only paths a v2 scenario may change relative to its v1 source. landmark_detail
# 'none' is what scripts/run_zone_study_integration.py demands for a tag-free provider.
ALLOWED_DIFF = ('scenario_id', 'map_id', 'landmark_detail', 'eval.setup.map_file_sha256')
LANDMARK_DETAIL = 'none'
# Keys/values that would mean a tag field survived (case-insensitive).
TAG_PATTERN = re.compile(r'(april\s*tag|\btags?\b|tag36h11|aruco|landmark|fiducial|marker)', re.I)
GRID_M = .02
EPS = 1e-6


class FinalEnvError(ValueError):
    """A final-environment map or scenario that breaks the B5 contract."""


# ---------------------------------------------------------------------------
# Maps

def _dump(value: object) -> str:
    return json.dumps(value, indent=2, allow_nan=False) + '\n'


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def final_map_path(map_id: str) -> Path:
    if map_id not in FINAL_MAPS:
        raise FinalEnvError(f'unknown final map: {map_id!r} (known: {sorted(FINAL_MAPS)})')
    return FINAL_MAPS[map_id][1] / (map_id + '.json')


def maps_dir_for(map_id: str) -> Path:
    return final_map_path(map_id).parent


def final_map(map_id: str) -> dict:
    """Definition of a final map: base map + walls_v3 + id/version + base-map link (no landmarks)."""
    from sim.research_dispatch_arena import digest
    from sim.zone_arena import apply_wall_profile, authored_map
    if map_id not in FINAL_MAPS:
        raise FinalEnvError(f'unknown final map: {map_id!r}')
    source = authored_map(FINAL_MAPS[map_id][0])
    value = apply_wall_profile(source, WALL_PROFILE)
    value.update(map_id=map_id, version=MAP_VERSION,
                 base_map={'map_id': source['map_id'], 'version': source['version'],
                           'static_map_sha256': digest(source)})
    return value


def write_maps() -> dict:
    """Write missing final maps; refuse to change any existing file (returns id -> sha256)."""
    out = {}
    for map_id in FINAL_MAPS:
        path, text = final_map_path(map_id), _dump(final_map(map_id))
        if path.exists():
            if path.read_text() != text:
                raise FinalEnvError(f'{path} differs from its definition; publish a new version instead')
        else:
            if path.parent == MAP_DIR:
                raise FinalEnvError(f'{path} must already exist: maps/zones is not written here')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        out[map_id] = sha256_bytes(path.read_bytes())
    return out


def tag_hits(value: object, path: str = '') -> list[str]:
    """Every key or string value that names a tag/landmark/marker (recursive)."""
    hits = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            where = f'{path}.{key}' if path else str(key)
            if TAG_PATTERN.search(str(key)):
                hits.append(where)
            hits += tag_hits(item, where)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            hits += tag_hits(item, f'{path}[{index}]')
    elif isinstance(value, str) and TAG_PATTERN.search(value):
        hits.append(f'{path}={value!r}')
    return hits


def _footprints(data: Mapping) -> list:
    return [(o['id'], o.get('kind'), o['center_m'], o['half_extents_m'], o.get('yaw_rad', 0.))
            for o in data['obstacles']]


def check_map(map_id: str) -> list[str]:
    """Schema, definition, zero tag fields, 0.40 m walls and base-identical 2-D geometry."""
    from sim.zone_arena import authored_map, wall_profile_record
    try:
        path = final_map_path(map_id)
        data, _ = load_map(map_id, maps_dir=path.parent)
    except (OSError, ValueError) as error:          # FinalEnvError is a ValueError
        return [f'{map_id}: cannot load: {error}']
    out = []
    if path.read_text() != _dump(final_map(map_id)):
        out.append(f'{map_id}: file differs from base map + {WALL_PROFILE} + base_map link')
    hits = tag_hits(data)
    if hits:
        out.append(f'{map_id}: tag field(s) remain: {hits[:5]}')
    if data.get('wall_profile') != wall_profile_record(WALL_PROFILE):
        out.append(f'{map_id}: wall_profile is not the registered {WALL_PROFILE} record')
    height = wall_profile_record(WALL_PROFILE)['height_m']
    low = [o['id'] for o in data['obstacles'] if o.get('kind') == 'wall' and o.get('height_m') != height]
    if low:
        out.append(f'{map_id}: wall(s) not at {height} m: {low}')
    base = authored_map(FINAL_MAPS[map_id][0])
    if _footprints(data) != _footprints(base):
        out.append(f'{map_id}: wall footprints differ from {base["map_id"]}')
    for key in ('bounds_m', 'frame', 'regions', 'zone_slots', 'passages', 'terrain', 'box_kinds',
                'approach_convention', 'top_cameras'):
        if data.get(key) != base.get(key):
            out.append(f'{map_id}: {key} differs from {base["map_id"]}')
    extra = sorted(set(data) - set(base) - {'wall_profile', 'base_map'})
    if extra:
        out.append(f'{map_id}: unexpected key(s) {extra}')
    if 'landmarks' in public_map(data, landmark_detail=LANDMARK_DETAIL):
        out.append(f'{map_id}: the robot projection still carries landmarks')
    return out


# ---------------------------------------------------------------------------
# Passage widths (declared vs measured wall gap)

def _finite(values: Sequence) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def measured_gap_m(data: Mapping, passage: Mapping, samples: int = 9) -> float:
    """Smallest free gap across ``passage`` between wall rectangles (and bounds), over its length."""
    centre, half = passage['center_m'], passage['half_extents_m']
    if not (_finite(centre) and _finite(half)) or len(centre) != 2 or len(half) != 2:
        raise FinalEnvError(f'passage {passage.get("id")!r}: center_m/half_extents_m must be 2 finite numbers')
    along = 0 if passage.get('axis', 'x') == 'x' else 1     # axis x: crossed along x, opens along y
    across = 1 - along
    lo_b, hi_b = data['bounds_m'][2 * across], data['bounds_m'][2 * across + 1]
    rects = keepout_rects(data, perimeter=True)
    if any(r[4] for r in rects):
        raise FinalEnvError('rotated walls are not supported by the gap measurement')
    best = math.inf
    for k in range(samples):
        s = centre[along] - half[along] + 2. * half[along] * (k + .5) / samples
        low, high = lo_b, hi_b
        for rect in rects:
            c, h = (rect[0], rect[1]), (rect[2], rect[3])
            if abs(s - c[along]) >= h[along]:
                continue
            a, b = c[across] - h[across], c[across] + h[across]
            if b <= centre[across] + EPS:
                low = max(low, b)
            elif a >= centre[across] - EPS:
                high = min(high, a)
            else:
                return 0.                              # a wall stands in the opening
        best = min(best, high - low)
    return round(best, 6)


def passage_widths(data: Mapping) -> tuple[list[dict], list[str]]:
    """(rows, problems): doors are 0.50 m / 1 lane or 1.00 m / 2 lanes; corridors 0.50 m / 1 lane."""
    from sim.zone_arena import NARROW_DOOR_M, WIDE_DOOR_M
    allowed = {'door': {NARROW_DOOR_M: 1, WIDE_DOOR_M: 2}, 'corridor': {NARROW_DOOR_M: 1}}
    rows, out = [], []
    passages = data.get('passages')
    if not isinstance(passages, list) or not passages:
        return rows, ['the map declares no passage']
    for passage in passages:
        kind = passage.get('kind') if isinstance(passage, Mapping) else None
        if kind not in allowed:
            continue                                   # passing_bay: a waiting area, no width
        width, lanes = passage.get('width_m'), passage.get('lanes')
        try:
            measured = measured_gap_m(data, passage)
        except (FinalEnvError, KeyError, TypeError, IndexError) as error:
            out.append(f'{passage.get("id")}: {error}')
            continue
        rows.append({'id': passage['id'], 'kind': kind, 'declared_m': width, 'lanes': lanes,
                     'measured_m': measured})
        if not _finite([width]) or allowed[kind].get(width) != lanes:
            out.append(f'{passage["id"]}: {kind} must be one of {allowed[kind]} (width -> lanes), '
                       f'got {width!r} / {lanes!r}')
        elif abs(measured - width) > 1e-4:
            out.append(f'{passage["id"]}: measured wall gap {measured} m differs from declared {width} m')
    return rows, out


# ---------------------------------------------------------------------------
# Reachability on the static map graph (disc-inflated free space, 4-connected grid)

def free_grid(data: Mapping, radius_m: float, *, extra_rects: Sequence = (), grid_m: float = GRID_M):
    """(free bool array [ny, nx], x0, y0, grid) for a disc robot of ``radius_m``."""
    if not _finite([radius_m, grid_m]) or radius_m < 0 or grid_m <= 0:
        raise FinalEnvError(f'radius/grid must be finite, radius >= 0 and grid > 0, got {radius_m!r}/{grid_m!r}')
    x0, x1, y0, y1 = (float(v) for v in data['bounds_m'])
    xs = np.arange(x0 + grid_m / 2, x1, grid_m)
    ys = np.arange(y0 + grid_m / 2, y1, grid_m)
    gx, gy = np.meshgrid(xs, ys)
    free = (gx - x0 > radius_m) & (x1 - gx > radius_m) & (gy - y0 > radius_m) & (y1 - gy > radius_m)
    for cx, cy, hx, hy, yaw in tuple(keepout_rects(data, perimeter=True)) + tuple(extra_rects):
        if yaw:
            raise FinalEnvError('rotated obstacles are not supported by the grid check')
        dx = np.maximum(np.abs(gx - cx) - hx, 0.)
        dy = np.maximum(np.abs(gy - cy) - hy, 0.)
        free &= np.hypot(dx, dy) > radius_m
    return free, x0, y0, grid_m


def _labels(free: np.ndarray) -> np.ndarray:
    labels = np.zeros(free.shape, dtype=np.int32)
    ny, nx = free.shape
    current = 0
    for j0, i0 in zip(*np.nonzero(free)):
        if labels[j0, i0]:
            continue
        current += 1
        labels[j0, i0] = current
        queue = deque([(j0, i0)])
        while queue:
            j, i = queue.popleft()
            for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = j + dj, i + di
                if 0 <= a < ny and 0 <= b < nx and free[a, b] and not labels[a, b]:
                    labels[a, b] = current
                    queue.append((a, b))
    return labels


def _rect_labels(labels, x0, y0, grid, centre, half) -> set[int]:
    ny, nx = labels.shape
    i0 = max(int(math.floor((centre[0] - half[0] - x0) / grid)), 0)
    i1 = min(int(math.ceil((centre[0] + half[0] - x0) / grid)), nx)
    j0 = max(int(math.floor((centre[1] - half[1] - y0) / grid)), 0)
    j1 = min(int(math.ceil((centre[1] + half[1] - y0) / grid)), ny)
    patch = labels[j0:j1, i0:i1]
    return {int(v) for v in np.unique(patch) if v}


def reachability(data: Mapping, orders: Sequence, *, radius_m: float = CARRY_RADIUS_M,
                 extra_rects: Sequence = ()) -> tuple[dict, list[str]]:
    """(graph, problems): each order's pickup slot/bay and destination zone exist and are connected.

    A disc of ``radius_m`` (default: the teacher's loaded radius) whose centre lies in
    the slot/zone rectangle. Formation footprints of two-robot items are
    ``harness.zone_scenario_feasibility``'s job, not this graph's.
    """
    if not isinstance(orders, Sequence) or isinstance(orders, (str, bytes)) or not orders:
        return {}, ['orders must be a non-empty list']
    free, x0, y0, grid = free_grid(data, radius_m, extra_rects=extra_rects)
    labels = _labels(free)
    bays = {b['bay_id']: b for b in pickup_bays(data)}
    slots = {s['slot_id']: s for b in bays.values() for s in b['slots']}
    zones = {z: set().union(*[_rect_labels(labels, x0, y0, grid, s['center_m'], s['half_extents_m'])
                              for s in data['zone_slots'][z]] or [set()]) for z in ZONE_IDS}
    passages = {p['id']: _rect_labels(labels, x0, y0, grid, p['center_m'], p['half_extents_m'])
                for p in data.get('passages', ()) if p.get('kind') in ('door', 'corridor')}
    graph = {'radius_m': radius_m, 'grid_m': grid, 'components': int(labels.max()),
             'zones': {z: sorted(v) for z, v in zones.items()},
             'passages': {k: sorted(v) for k, v in passages.items()}, 'orders': {}}
    out = []
    for index, order in enumerate(orders):
        if not isinstance(order, Mapping):
            out.append(f'orders[{index}] must be an object')
            continue
        oid = order.get('order_id', f'orders[{index}]')
        location = order.get('initial_location')
        zone = order.get('destination_zone')
        if not isinstance(location, Mapping):
            out.append(f'{oid}: initial_location must be an object')
            continue
        target = slots.get(location.get('slot')) or (None if location.get('slot') else
                                                     bays.get(location.get('pickup_bay')))
        if target is None:
            out.append(f'{oid}: pickup {location!r} is not a slot/bay of {data["map_id"]}')
            continue
        if zone not in ZONE_IDS:
            out.append(f'{oid}: destination_zone {zone!r} is not one of {ZONE_IDS}')
            continue
        start = _rect_labels(labels, x0, y0, grid, target['center_m'], target['half_extents_m'])
        shared = start & zones[zone]
        via = sorted(p for p, comp in passages.items() if comp & shared)
        graph['orders'][oid] = {'pickup': location.get('slot') or location.get('pickup_bay'),
                                'zone': zone, 'reachable': bool(shared), 'via': via}
        if not start:
            out.append(f'{oid}: no free cell for a {radius_m} m disc in pickup {target.get("slot_id") or target["bay_id"]}')
        elif not shared:
            out.append(f'{oid}: pickup and zone {zone} are not connected for a {radius_m} m disc')
    return graph, out


# ---------------------------------------------------------------------------
# Scenario v2

def v2_id(v1_id: str) -> str:
    return v1_id + V2_SUFFIX


def scenario_v2(v1: Mapping) -> dict:
    """The v2 config: v1 with the tag-free map pin only (ids, map, detail, map file hash)."""
    if not isinstance(v1, Mapping) or v1.get('map_id') not in V1_MAP_TO_FINAL:
        raise FinalEnvError(f'not a v1 tag-map scenario: map_id {getattr(v1, "get", lambda k: None)("map_id")!r}')
    map_id = V1_MAP_TO_FINAL[v1['map_id']]
    value = copy.deepcopy(dict(v1))
    value['scenario_id'] = v2_id(v1['scenario_id'])
    value['map_id'] = map_id
    value['landmark_detail'] = LANDMARK_DETAIL
    value['eval']['setup']['map_file_sha256'] = sha256_bytes(final_map_path(map_id).read_bytes())
    return value


def diff_paths(a: object, b: object, path: str = '') -> list[str]:
    """Dotted paths where two JSON values differ (lists compared by index)."""
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        out = []
        for key in list(dict.fromkeys([*a, *b])):
            where = f'{path}.{key}' if path else str(key)
            if key not in a or key not in b:
                out.append(where)
            else:
                out += diff_paths(a[key], b[key], where)
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b)) for p in diff_paths(x, y, f'{path}[{i}]')]
    return [] if (type(a) is type(b) and a == b) else [path]


def scenario_diff(v1: Mapping, v2: Mapping) -> list[str]:
    """Problems if v2 changes anything but ALLOWED_DIFF, or does not change the map pin."""
    changed = diff_paths(v1, v2)
    out = [f'{v2.get("scenario_id")}: {p} differs from v1' for p in changed if p not in ALLOWED_DIFF]
    if 'map_id' not in changed:
        out.append(f'{v2.get("scenario_id")}: map_id was not moved off the tag map')
    return out


def write_scenarios() -> dict:
    """Write missing v2 configs next to nothing else; refuse to change an existing one."""
    V2_SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for path in sorted(V1_SCENARIO_DIR.glob('*.json')):
        v2 = scenario_v2(json.loads(path.read_text()))
        target = V2_SCENARIO_DIR / (v2['scenario_id'] + '.json')
        text = json.dumps(v2, ensure_ascii=False, indent=2) + '\n'
        if target.exists():
            if json.loads(target.read_text()) != v2:
                raise FinalEnvError(f'{target} differs from its v1 source + map pin; publish a new version')
        else:
            target.write_text(text)
        out[v2['scenario_id']] = sha256_bytes(target.read_bytes())
    return out


def _rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(ROOT))


def catalog() -> dict:
    """Maps and scenarios of the final environment with every hash (docs/execution_versioning.md)."""
    from sim.research_dispatch_arena import digest
    maps = {}
    for map_id, (base, _) in FINAL_MAPS.items():
        path = final_map_path(map_id)
        data = json.loads(path.read_text())
        maps[map_id] = {'file': _rel(path), 'file_sha256': sha256_bytes(path.read_bytes()),
                        'static_map_sha256': digest(data), 'base_map': data['base_map'],
                        'wall_profile': {'id': data['wall_profile']['id'],
                                         'sha256': data['wall_profile']['sha256']},
                        'public_map_sha256': digest(public_map(data, landmark_detail=LANDMARK_DETAIL)),
                        'reused_existing_file': path.parent == MAP_DIR}
    scenarios = {}
    for path in sorted(V1_SCENARIO_DIR.glob('*.json')):
        v1 = json.loads(path.read_text())
        target = V2_SCENARIO_DIR / (v2_id(v1['scenario_id']) + '.json')
        v2 = json.loads(target.read_text())
        scenarios[v2['scenario_id']] = {
            'file': _rel(target), 'file_sha256': sha256_bytes(target.read_bytes()),
            'map_id': v2['map_id'], 'landmark_detail': v2['landmark_detail'],
            'map_file_sha256': v2['eval']['setup']['map_file_sha256'],
            'v1': {'file': _rel(path), 'file_sha256': sha256_bytes(path.read_bytes()), 'map_id': v1['map_id'],
                   'map_file_sha256': v1['eval']['setup']['map_file_sha256']},
            'changed_paths': diff_paths(v1, v2)}
    return {'schema': CATALOG_SCHEMA, 'env_id': ENV_ID, 'wall_profile': WALL_PROFILE, 'tags': 0,
            'maps': maps, 'scenarios': scenarios,
            'not_verified': ['physics: no-LLM 3-robot smoke on this environment (B8)',
                             'M1/M2 skill re-validation on walls_v3 (#219)',
                             'scene builders for the two new maps (sim/zone_geometry_scene.MAP_IDS lists the door '
                             'map only)', 'own-camera localisation without tags (VIS6, B3)']}


def write_catalog() -> str:
    text = json.dumps(catalog(), ensure_ascii=False, indent=2) + '\n'
    if CATALOG_PATH.exists() and CATALOG_PATH.read_text() != text:
        raise FinalEnvError(f'{CATALOG_PATH} differs from the current files; publish a new env version')
    CATALOG_PATH.write_text(text)
    return sha256_bytes(text.encode())


def check_all() -> dict:
    """Every static check over the final maps and the v2 scenarios: id -> list of problems."""
    from harness.zone_study_scenarios import validate
    report = {}
    for map_id in FINAL_MAPS:
        problems = check_map(map_id)
        data, _ = load_map(map_id, maps_dir=maps_dir_for(map_id))
        problems += passage_widths(data)[1]
        report[map_id] = problems
    for path in sorted(V1_SCENARIO_DIR.glob('*.json')):
        v1 = json.loads(path.read_text())
        target = V2_SCENARIO_DIR / (v2_id(v1['scenario_id']) + '.json')
        if not target.exists():
            report[target.stem] = ['missing v2 config']
            continue
        v2 = json.loads(target.read_text())
        problems = scenario_diff(v1, v2) + validate(v2, maps_dir=maps_dir_for(v2['map_id'])).problems
        problems += [f'tag field: {h}' for h in tag_hits(v2) if h != f'landmark_detail={LANDMARK_DETAIL!r}'
                     and h != 'landmark_detail']
        data, _ = load_map(v2['map_id'], maps_dir=maps_dir_for(v2['map_id']))
        for radius in (ROBOT_RADIUS_M, CARRY_RADIUS_M):
            problems += reachability(data, v2['orders'], radius_m=radius)[1]
        report[v2['scenario_id']] = problems
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m harness.zone_final_env [--write]`` -- (write missing files, then) check everything."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--write', action='store_true', help='write missing maps/v2 configs/catalog (never overwrite)')
    args = parser.parse_args(argv)
    if args.write:
        write_maps()
        write_scenarios()
        write_catalog()
    report = check_all()
    for key, problems in report.items():
        print(f'{"ok  " if not problems else "FAIL"} {key}')
        for problem in problems:
            print(f'       {problem}')
    bad = sum(1 for p in report.values() if p)
    print(f'{len(report) - bad}/{len(report)} final-environment item(s) pass the static checks')
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
