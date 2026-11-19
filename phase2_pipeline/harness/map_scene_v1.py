"""Generated map scenes (mapgen.scene.v1) for the real run code: task definition, DEFAULT off.

Without the switch nothing here is read and every run is unchanged. With it (the scene of `--scenes` / `--scene-id` of
scripts/run_team_carry.py has an `arena` key; there is no separate flag), the world is built from the scene: its walls, doors, wall signs, boxes and N robots (N up to 9) instead of
the one old arena of two rooms and three robots.

What this module is (standard library only; load it BY FILE PATH like harness/overhead_v1.py: inside dependency_modules() `import harness.x`
resolves to the frozen scene package, which has no such file):
  * config(scene) -> a small JSON dict (robots, bounds, rooms, walls, doors, signs, marker numbers). The bridge writes it to a file and sets
    the environment variable UGRP_MAP_SCENE to its path; harness/robot_tags_v1.py, harness/overhead_v1.py (and harness/place_memory_v1.py,
    which loads its own copy of robot_tags_v1) read it at import. Unset = the constants of the one old arena.
  * transform_xml(xml, cfg): the scene's XML after the frozen scene package built the old arena: the old walls and floor paint go, the
    scene's walls come, the floor and lights grow with the bounds, and the finger contact pairs of the robots r4..r9 are copied from
    robot r1's (the frozen contact profile only knows r1..r3). Boxes beyond the scene package's pool are not cloned here: listing them in
    setup_only.objects (cargo_items) makes the frozen zone builder create their bodies and contact pairs.
  * patch_frozen_world(ids): the frozen multi-robot world takes its robot ids from a module constant and builds three bodies; this swaps
    the ids (in this process only; dependency_modules() drops the patched module afterwards). Not applied without the switch.
  * door choice (choose_door): which door of the robot's own room it carries through. One rule, used by the motion code (from the
    robot's own measured place) and by the reference plan (from the box place), so both name the same door.
No signs positions go to the motion code (user decision 2026-11-15): the sign table below is the SCENE's (it draws the signs and scores the
boxes); the robot finds its sign with its own camera.
"""
import copy
import json
import math
import os
import re
import xml.etree.ElementTree as ET

ENV = 'UGRP_MAP_SCENE'
SCHEMA = 'ugrp.map_cfg.v1'
MAX_ROBOTS = 9        # the generated scenes have up to 9 robots (tag ids up to 65: DICT_4X4_250, which the scene's `markers` names)
WALL_HALF, WALL_H = 0.025, 0.40
SIGN_M = 0.25
# sign pictures: the two facings that exist in the old arena are verified by a run ('-x' east wall, '+y' south wall); the other two are
# those turned by 180 degrees about the vertical axis (a rigid motion keeps what is mirrored and what is up), NOT checked in a picture
SIGN_BASE_EULER = {'-x': '0 1.5708 0', '+y': '1.5708 0 0'}


def rid_number(rid):
    return int(re.fullmatch(r'r([0-9]+)', rid).group(1))


def natural_robots(robots):
    """r1, r2, ..., r9, r10 (plain string order puts 'r10' before 'r2')."""
    return sorted(robots, key=lambda r: (rid_number(r), r))


def world_robot_ids(n):
    """The bodies of the world: at least the three of the old world (an unused one is parked), up to the scene's N."""
    return tuple('r%d' % i for i in range(1, max(3, n) + 1))


def wall_rect(w):
    """Centre line a-b -> (centre, half extents); horizontal walls run one half thickness past both ends, vertical ones do not (the convention
    of maps/zones/zone_wide_door_geometry_v3.json, so the old arena is reproduced exactly)."""
    (ax, ay), (bx, by) = w['a'], w['b']
    if abs(ay - by) < 1e-9:
        return ((ax + bx) / 2, ay), (abs(bx - ax) / 2 + WALL_HALF, WALL_HALF)
    return (ax, (ay + by) / 2), (WALL_HALF, abs(by - ay) / 2)


def config(scene):
    """JSON-able description of the generated scene that the run code needs (no box positions, no oracle plan)."""
    a = scene['arena']
    rids = [r['rid'] for r in scene['robots']]
    n = len(rids)
    if not 2 <= n <= MAX_ROBOTS or rids != ['r%d' % (i + 1) for i in range(n)]:
        raise ValueError('a map scene needs the robots r1..rN with 2 <= N <= %d, got %s' % (MAX_ROBOTS, rids))
    mk = a['markers']
    signs = {}
    for s in a['signs']:
        signs[str(s['number'])] = {'pos': list(s['pos']), 'facing': s['facing'], 'area': list(s['area']), 'room': s['room']}
    sign_ids = [int(k) for k in signs]
    n_world = len(world_robot_ids(n))
    side0, top0 = int(mk['robot_side_id0']), int(mk['robot_top_id0'])
    size = int(mk.get('dictionary_size') or int(re.search(r'_([0-9]+)$', mk['dictionary']).group(1)))
    top_end = top0 + n_world
    if max(sign_ids) >= side0 or side0 + 4 * n_world > top0 or top_end > size:
        raise ValueError('marker numbers collide or leave the dictionary: signs %s, sides from %d, tops from %d (%d robots), %s'
                         % (sign_ids, side0, top0, n_world, mk['dictionary']))
    return {'schema': SCHEMA, 'scene_id': scene['id'], 'family': a.get('family'), 'robots': rids, 'world_robots': list(world_robot_ids(n)),
            'bounds': list(a['bounds']), 'wall_height': a.get('wall_height', WALL_H),
            'rooms': [{'id': r['id'], 'kind': r['kind'], 'name': r.get('name', r['kind']), 'rect': list(r['rect'])} for r in a['rooms']],
            'walls': [{'id': w['id'], 'a': list(w['a']), 'b': list(w['b']), 'kind': w.get('kind')} for w in a['walls']],
            'doors': [{'id': d['id'], 'centre': list(d['centre']), 'axis': d.get('axis', 'x'), 'width': d['width'], 'lanes': d.get('lanes', 1),
                       'rooms': list(d['rooms'])} for d in a['doors']],
            'signs': signs,
            'markers': {'dictionary': mk['dictionary'], 'robot_side_id0': side0, 'robot_top_id0': top0, 'n_robots': n_world},
            'boxes': [{'id': b['id'], 'colour': b['colour']} for b in scene['boxes']]}


_cache = {}


def active():
    """The config the environment points to (None = the old arena). Cached per file."""
    path = os.environ.get(ENV)
    if not path:
        return None
    key = (path, os.path.getmtime(path))
    if key not in _cache:
        with open(path) as fh:
            _cache[key] = json.load(fh)
    return _cache[key]


def write_config(scene, path):
    cfg = config(scene)
    with open(path, 'w') as fh:
        json.dump(cfg, fh, indent=1)
    return cfg


# -- sign table (what robot_tags_v1 draws and reads) ------------------------------------------------------------------------------

def sign_table(cfg):
    """{number: (x, y on the wall face, facing)} and {number: (x0, x1, y0, y1) delivery area}."""
    return ({int(k): (v['pos'][0], v['pos'][1], v['facing']) for k, v in cfg['signs'].items()},
            {int(k): tuple(v['area']) for k, v in cfg['signs'].items()})


def zone_tables(cfg):
    """Bridge side: the destination names of the planner ('sign11', ...) and the scoring rectangles."""
    zones = tuple('sign%d' % n for n in sorted(int(k) for k in cfg['signs']))
    return zones, {'sign%d' % int(k): tuple(v['area']) for k, v in cfg['signs'].items()}


def _qmul(p, q):
    return (p[0] * q[0] - p[1] * q[1] - p[2] * q[2] - p[3] * q[3], p[0] * q[1] + p[1] * q[0] + p[2] * q[3] - p[3] * q[2],
            p[0] * q[2] - p[1] * q[3] + p[2] * q[0] + p[3] * q[1], p[0] * q[3] + p[1] * q[2] - p[2] * q[1] + p[3] * q[0])


def sign_orientation(facing):
    """Geom attributes that stand a sign on a wall face looking toward `facing` (its outward normal): {'euler': ...} for the two facings
    of the old arena, {'quat': ...} (the verified one turned 180 degrees about the vertical axis) for '+x' and '-y'."""
    if facing in SIGN_BASE_EULER:
        return {'euler': SIGN_BASE_EULER[facing]}
    half = math.radians(90.) / 2
    base = {'+x': (math.cos(half), 0., math.sin(half), 0.), '-y': (math.cos(half), math.sin(half), 0., 0.)}   # '-x' = Ry(90), '+y' = Rx(90)
    # Rz(180 deg) = (0, 0, 0, 1) as a quaternion; '+x' = Rz(180) * Ry(90), '-y' = Rz(180) * Rx(90)
    q = _qmul((0., 0., 0., 1.), base[facing])
    return {'quat': '%.6f %.6f %.6f %.6f' % q}


# -- rooms, doors ------------------------------------------------------------------------------------------------------------------

def room_at(cfg, xy):
    """Id of the room whose rectangle holds the point (the nearest one when it is in a wall)."""
    best = None
    for r in cfg['rooms']:
        x0, x1, y0, y1 = r['rect']
        d = math.hypot(max(x0 - xy[0], 0., xy[0] - x1), max(y0 - xy[1], 0., xy[1] - y1))
        if best is None or d < best[0]:
            best = (d, r['id'])
    return best[1]


def choose_door(cfg, xy):
    """The door a robot at `xy` (arena frame) carries its box through: of the doors that lead out of the room it stands in, the one whose
    centre is nearest (the lower number on a tie). It needs the walls and the doors and the robot's own place, nothing about where the signs
    are. Families whose route crosses two doors or whose door depends on the destination (corridor, multidest) are not covered:
    check_supported() refuses them. Returns the door dict of the config."""
    room = room_at(cfg, xy)
    cands = [d for d in cfg['doors'] if room in d['rooms']]
    if not cands:
        raise ValueError('no door leaves the room %s' % room)
    return min(cands, key=lambda d: (round(math.hypot(d['centre'][0] - xy[0], d['centre'][1] - xy[1]), 6), d['id']))


def match_door(cfg, x, y, tol=0.06):
    """The config door whose centre is within `tol` of a door found in the model (arena_from_model), or None."""
    best = min(cfg['doors'], key=lambda d: math.hypot(d['centre'][0] - x, d['centre'][1] - y))
    return best if math.hypot(best['centre'][0] - x, best['centre'][1] - y) <= tol else None


def check_supported(cfg):
    """The motion code carries a box through ONE door of the robot's room into the room that holds the sign (it finds the sign by its
    own camera). Not covered here: a route of two doors (corridor) and a door that depends on the destination (several destination rooms
    behind different doors of one box room)."""
    kinds = {r['id']: r['kind'] for r in cfg['rooms']}
    if any(k == 'corridor' for k in kinds.values()):
        raise ValueError('map scene %s: a corridor needs two doors in a row (patch W6, not done): %s' % (cfg['scene_id'], cfg['family']))
    dest_rooms = {r['id'] for r in cfg['rooms'] if r['kind'] == 'dest'}
    for r in cfg['rooms']:
        if r['kind'] != 'box':
            continue
        reached = {x for d in cfg['doors'] if r['id'] in d['rooms'] for x in d['rooms'] if x != r['id']}
        if len(reached & dest_rooms) > 1:
            raise ValueError('map scene %s: the door out of %s depends on the destination room (several destination rooms; not done)'
                             % (cfg['scene_id'], r['id']))
    return True


def door_assignment(cfg, scene_robots_xy):
    """{rid: door id} the reference plan expects, from the robots' places (or the places of their boxes)."""
    return {rid: choose_door(cfg, xy)['id'] for rid, xy in scene_robots_xy.items()}


# -- the scene XML -----------------------------------------------------------------------------------------------------------------

def _f(v):
    return ('%.6f' % v).rstrip('0').rstrip('.') if abs(v) > 1e-9 else '0'


OLD_ARENA_PREFIXES = ('zone_wall_', 'zone_pickup', 'zone_zone_', 'zone_slot_')


def camera_height_light(xml_root):
    for lt in xml_root.find('worldbody').findall('light'):
        if lt.get('name') == 'dispatch_ceiling':
            return lt
    return None


def pool_of(objects):
    """The colour boxes the scene package built, from its `setup_only.objects`: {'blue': [body names], 'red': [...]} (blue boxes are cyan)."""
    have = {'blue': [], 'red': []}
    for o in objects.values():
        body = o.get('body_name') or ''
        if body.startswith('cargo_cyan_'):
            have['blue'].append(body)
        elif body.startswith(('cargo_red_', 'cargo_green_')):
            have['red'].append(body)
    return {k: sorted(v) for k, v in have.items()}


def extra_cargo(cfg, objects):
    """[(colour 'blue'|'red', new body name, template body name)]: the boxes the scene needs beyond the pool of the scene package. The
    template is the first pool body of the colour; new names continue its numbering (cargo_cyan_<k>, cargo_red_<k>)."""
    pool = pool_of(objects)
    need = {'blue': 0, 'red': 0}
    for b in cfg['boxes']:
        need['blue' if b['colour'] == 'blue' else 'red'] += 1
    out = []
    for colour, kind in (('blue', 'cyan'), ('red', 'red')):
        if not pool[colour]:
            raise ValueError('the scene package has no %s box to copy' % colour)
        numbers = [int(n.rsplit('_', 1)[1]) for n in pool[colour] if n.startswith('cargo_%s_' % kind)]
        k = max(numbers + [0]) + 1
        for _ in range(max(0, need[colour] - len(pool[colour]))):
            out.append((colour, 'cargo_%s_%d' % (kind, k), pool[colour][0]))
            k += 1
    return out


def transform_xml(xml, cfg, light_centres=()):
    """Old arena out, the scene's arena in (see the module text). Returns the new XML text."""
    root = ET.fromstring(xml)
    world = root.find('worldbody')
    walls_old = [g for g in world.findall('geom') if (g.get('name') or '').startswith('zone_wall_')]
    if not walls_old:
        raise ValueError('the scene XML has no zone_wall_* geom to take the wall appearance from')
    template = walls_old[0]
    insert_at = list(world).index(template)
    for g in list(world.findall('geom')):
        if (g.get('name') or '').startswith(OLD_ARENA_PREFIXES):
            world.remove(g)
    x0, x1, y0, y1 = cfg['bounds']
    h = cfg.get('wall_height', WALL_H)
    new = []
    for w in cfg['walls']:
        (cx, cy), (hx, hy) = wall_rect(w)
        attrs = {k: v for k, v in template.attrib.items() if k not in ('name', 'pos', 'size')}
        g = ET.Element('geom', dict(attrs, name='zone_' + w['id'], pos='%s %s %s' % (_f(cx), _f(cy), _f(h / 2)),
                                    size='%s %s %s' % (_f(hx), _f(hy), _f(h / 2))))
        new.append(g)
    for k, g in enumerate(new):
        world.insert(insert_at + k, g)
    # floor: the plane is centred on the arena and reaches 2 m past the walls; the checker keeps its tile size
    floor = next(g for g in world.findall('geom') if g.get('name') == 'floor')
    old_half = float(floor.get('size').split()[0])
    new_hx, new_hy = (x1 - x0) / 2 + 2., (y1 - y0) / 2 + 2.
    floor.set('pos', '%s %s 0' % (_f((x0 + x1) / 2), _f((y0 + y1) / 2)))
    floor.set('size', '%s %s %s' % (_f(new_hx), _f(new_hy), floor.get('size').split()[2]))
    mat = next((m for m in root.find('asset').findall('material') if m.get('name') == floor.get('material')), None)
    if mat is not None and mat.get('texrepeat'):
        u, v = (float(t) for t in mat.get('texrepeat').split())
        mat.set('texrepeat', '%s %s' % (_f(u * new_hx / old_half), _f(v * new_hy / old_half)))
    # lights: one copy of the ceiling light above each ceiling-camera tile (the old one stays; a tile it already stands above gets no copy, so the
    # one-tile arena of the old size is lit as before)
    light = camera_height_light(root)
    if light is not None:
        px, py, pz = (float(t) for t in light.get('pos').split())
        k = 0
        for lx, ly in light_centres:
            if abs(lx - px) < 1e-3 and abs(ly - py) < 1e-3:
                continue
            k += 1
            copy_ = copy.deepcopy(light)
            copy_.set('name', 'dispatch_ceiling_%d' % k)
            copy_.set('pos', '%s %s %s' % (_f(lx), _f(ly), _f(pz)))
            world.insert(list(world).index(light) + k, copy_)
    # boxes beyond the pool: the scene package builds a replica body (and its finger contact pairs for r1..r3) for every entry of
    # setup_only.objects, so they only have to be listed there (cargo_items); nothing is cloned here
    contact = root.find('contact')
    # robots beyond the third: finger contact pairs like robot r1's (the frozen profile writes them for r1..r3 only)
    if contact is not None:
        pairs = list(contact.findall('pair'))
        have = {p.get('geom1') for p in pairs}
        for rid in cfg['world_robots'][3:]:
            for p in pairs:
                g1 = p.get('geom1') or ''
                if g1.startswith('r1__'):
                    q = copy.deepcopy(p)
                    q.set('geom1', rid + g1[2:])
                    if q.get('geom1') not in have:
                        contact.append(q)
    return ET.tostring(root, encoding='unicode')


def cargo_items(cfg, objects):
    """`setup_only.objects` entries of the cloned boxes (the scene package lists its own pool only): {item id: entry}."""
    out = {}
    for colour, name, _ in extra_cargo(cfg, objects):
        out[name[len('cargo_'):]] = {'kind': 'cyan' if colour == 'blue' else 'red', 'body_name': name, 'joint_name': name + '_free',
                                     'position_m': [-60., -60., 0.016], 'half_extents_m': [0.017, 0.020, 0.016]}
    return out


# -- the frozen world --------------------------------------------------------------------------------------------------------------

def patch_frozen_world(ids):
    """Let the frozen multi-robot world (sim.multi_masterpi_production) build the robots `ids` instead of r1..r3. Call it inside
    dependency_modules(), BEFORE the runner imports from those modules (a name imported earlier keeps the old function): the bridge does it
    before the first robot step. Returns what was changed (for the record)."""
    import importlib
    mp = importlib.import_module('sim.multi_masterpi_production')
    ids = tuple(ids)
    old = tuple(mp.ROBOT_IDS)
    if ids[:len(old)] != old:
        raise ValueError('robot ids must start with %s' % (old,))
    original = mp.build_multi_robot_xml

    def build_multi_robot_xml(hardware=None, *, robot_ids=None, **kw):
        return original(hardware, robot_ids=ids if robot_ids is None or tuple(robot_ids) == old else robot_ids, **kw)
    mp.build_multi_robot_xml = build_multi_robot_xml
    mp.ROBOT_IDS = ids
    mp.MultiMasterPiProductionV2.robot_ids = ids
    # the world's own reset places every robot at a default spawn (the scene setup moves them to the scene's starts right after): r4.. need one.
    # Same dict object the world holds (warehouse_spawns), so it is extended in place; spaced 0.42 m along y like r1..r3, inside the old arena size
    for k, rid in enumerate(ids[len(old):]):
        mp.DEFAULT_SPAWNS.setdefault(rid, (-0.18, -0.84 - 0.42 * k, mp.WHEEL_RADIUS_M, 0.0))
    # the servo stiffness transform names the robots it accepts (r1..r3); its work is the same for any robot's actuators
    ss = importlib.import_module('sim.s2_servo_stiffness')
    original_ss = ss.transform_xml

    def transform_xml(xml, *, servo_stiffness='off', robot_id='r3'):
        if servo_stiffness == 'off' or robot_id in old:
            return original_ss(xml, servo_stiffness=servo_stiffness, robot_id=robot_id)
        if servo_stiffness != ss.OPTION or robot_id not in ids:
            raise ValueError('unsupported servo stiffness / robot')
        root = ET.fromstring(xml)
        option = root.find('option')
        if option is None or option.get('integrator') != 'implicitfast':
            raise ValueError('stiff servo requires existing implicitfast integrator')
        for name, spec in ss.parameters().items():
            nodes = root.findall("actuator/position[@name='%s__servo_%s']" % (robot_id, name))
            if len(nodes) != 1:
                raise ValueError('expected one named position actuator: ' + name)
            actuator = nodes[0]
            actuator.attrib.pop('kv', None)
            actuator.set('kp', repr(spec['kp']))
            actuator.set('dampratio', '1')
            actuator.set('forcelimited', 'true')
            torque = spec['torque_limit_nm']
            actuator.set('forcerange', '%s %s' % (-torque, torque))
        return ET.tostring(root, encoding='unicode')
    ss.transform_xml = transform_xml
    return {'robot_ids': list(ids), 'was': list(old), 'patched': ['multi_masterpi_production.ROBOT_IDS/robot_ids/build_multi_robot_xml',
                                                                     's2_servo_stiffness.transform_xml']}
