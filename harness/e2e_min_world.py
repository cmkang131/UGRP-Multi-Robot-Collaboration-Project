"""E2E-min world builder helpers (pure; used by scripts/e2e_warp_physics.build_context).

Default OFF: ``build_context(..., nav_cubes=None)`` keeps the nav gate world
exactly as before (no cargo).  With ``nav_cubes`` the nav world keeps only the
named colour boxes of the nav scenario (``s7_pair_with_solo_v7``: ``cyan_1``,
``red_1``; the long beam stays removed) at caller-given setup-only xy.  No
cube position is defaulted here: the prereg must freeze them ([확인 필요]).

The builder never asserts that the finger/cargo contact pairs equal the ACT
owner's (unverified); it records them (``cargo_pair_audit``) so the run shows
which pairs exist.
"""
from __future__ import annotations

import copy
import math
import xml.etree.ElementTree as ET

SCHEMA = 'ugrp.e2e_min.world.v1'
ROBOTS = ('r1', 'r2')
#: Colour boxes authored in configs/zone_study_scenarios_v7/s7_pair_with_solo_v7.json.
NAV_SCENARIO_BOXES = ('cyan_1', 'red_1')
#: Design proposal only (DESIGN.md §3.1): lane spawn + ~0.85 m east, bearing 0.
#: NOT used unless a caller passes it explicitly; prereg freezes the real values.
PROPOSED_CUBE_XY = {'r1': ('cyan_1', (-0.05, -2.375)), 'r2': ('red_1', (-0.05, -2.875))}


class E2EWorldError(ValueError):
    pass


def validate_cubes(nav_cubes):
    """``{robot: {'item_id': str, 'xy': [x, y]}}`` for exactly r1+r2, distinct items."""
    if not isinstance(nav_cubes, dict) or set(nav_cubes) != set(ROBOTS):
        raise E2EWorldError('E2E_CUBES_REQUIRE_R1_R2')
    items = []
    out = {}
    for robot in ROBOTS:
        spec = nav_cubes[robot]
        if not isinstance(spec, dict) or set(spec) != {'item_id', 'xy'}:
            raise E2EWorldError('E2E_CUBE_SPEC_FIELDS:' + robot)
        xy = [float(v) for v in spec['xy']]
        if len(xy) != 2 or not all(math.isfinite(v) for v in xy):
            raise E2EWorldError('E2E_CUBE_XY_INVALID:' + robot)
        items.append(spec['item_id'])
        out[robot] = dict(item_id=str(spec['item_id']), xy=xy)
    if len(set(items)) != len(items):
        raise E2EWorldError('E2E_CUBE_ITEMS_NOT_DISTINCT')
    return out


def select_cube_objects(objects, nav_cubes):
    """Keep only the requested setup-only colour boxes, moved to the given xy."""
    cubes = validate_cubes(nav_cubes)
    keep = {}
    for robot in ROBOTS:
        item = cubes[robot]['item_id']
        if item not in (objects or {}):
            raise E2EWorldError('E2E_CUBE_UNKNOWN_ITEM:' + item)
        row = copy.deepcopy(objects[item])
        z = float(row['position_m'][2])
        row['position_m'] = [*cubes[robot]['xy'], z]
        row['carried_by'] = robot
        keep[item] = row
    return keep


def cargo_bodies(xml):
    root = ET.fromstring(xml)
    return sorted(b.get('name') for b in root.iter('body')
                  if str(b.get('name') or '').startswith('cargo_'))


def audit_cube_bodies(xml, nav_cubes):
    """Fail closed unless the XML holds exactly the requested cargo bodies."""
    cubes = validate_cubes(nav_cubes)
    expected = sorted('cargo_' + cubes[r]['item_id'] for r in ROBOTS)
    found = cargo_bodies(xml)
    if found != expected:
        raise E2EWorldError(f'E2E_CUBE_BODIES_MISMATCH: expected {expected}, found {found}')
    return found


def cargo_pair_audit(xml):
    """Explicit <pair> contacts that involve a cargo geom (recorded, not asserted)."""
    root = ET.fromstring(xml)
    cargo_geoms = set()
    for body in root.iter('body'):
        if str(body.get('name') or '').startswith('cargo_'):
            for geom in body.iter('geom'):
                if geom.get('name'):
                    cargo_geoms.add(geom.get('name'))
    pairs = []
    for pair in root.iter('pair'):
        g1, g2 = pair.get('geom1'), pair.get('geom2')
        if g1 in cargo_geoms or g2 in cargo_geoms:
            pairs.append(dict(geom1=g1, geom2=g2,
                              **{k: pair.get(k) for k in ('condim', 'friction', 'solref',
                                                         'solreffriction', 'solimp')
                                 if pair.get(k) is not None}))
    return dict(cargo_geoms=sorted(cargo_geoms), pairs=pairs, pair_n=len(pairs),
                finger_pair_n=sum(1 for p in pairs
                                  if 'finger' in str(p['geom1']) or 'finger' in str(p['geom2'])),
                asserted_equal_to_act_owner=False)


def cube_geometry(model, nav_cubes, objects):
    """Eval-only cube rows for eval-geometry.json (qpos address, half size)."""
    cubes = validate_cubes(nav_cubes)
    adr, half, items = {}, {}, {}
    for robot in ROBOTS:
        item = cubes[robot]['item_id']
        row = objects[item]
        jid = model.joint(row['joint_name']).id
        adr[robot] = int(model.jnt_qposadr[jid])
        half[robot] = [float(v) for v in row['half_extents_m']]
        items[robot] = dict(item_id=item, kind=row['kind'], body_name=row['body_name'])
    halves_z = {h[2] for h in half.values()}
    if len(halves_z) != 1:
        raise E2EWorldError('E2E_CUBE_HALF_Z_DIFFERS')
    return dict(cube_qpos_adr=adr, cube_half_m=halves_z.pop(), cube_half_extents_m=half,
                cube_items=items, eval_only=True)


def arm_pwm(nav_arm_pwm, robot, search):
    """Initial servo PWM for a robot: SEARCH unless an explicit setup pose is given."""
    if nav_arm_pwm is None or robot not in nav_arm_pwm:
        return dict(search)
    pwm = {int(k): int(v) for k, v in nav_arm_pwm[robot].items()}
    if set(pwm) != {int(k) for k in search} or any(not 500 <= v <= 2500 for v in pwm.values()):
        raise E2EWorldError('E2E_ARM_PWM_INVALID:' + robot)
    return pwm
