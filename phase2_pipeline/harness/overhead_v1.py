"""Ceiling cameras that measure where every robot is (user decision 2026-11-15).

One camera above the middle of the arena, looking straight down (there is one camera; user, 2026-11-15). Each robot carries a flat number card on
the top of its rear cage. A camera picture is read with an ArUco detector; the card centre is cut at its known height
and the card's top edge gives the heading. The same reading runs on a rendered picture in the simulation and on a
real ceiling camera picture: only the camera intrinsics and placement change (measured once when installing).

Who may use it: the motion code (driving, door passing, stopping before another robot). The LLM planner gets only its
own rough position. Boxes are never read from the ceiling.
"""
import json
import math
import xml.etree.ElementTree as ET

import numpy as np

import os
HEIGHT_M = float(os.environ.get('UGRP_OVERHEAD_H', '2.5'))
WIDTH, HEIGHT = int(os.environ.get('UGRP_OVERHEAD_W', '1280')), int(os.environ.get('UGRP_OVERHEAD_HH', '960'))
CARD_M = float(os.environ.get('UGRP_OVERHEAD_CARD', '0.085'))   # the rear cage top is 8.9 x 9.4 cm                      # card side; the marker is the inner 75 %
CARD_AT = (-0.041, 0.0, float(os.environ.get('UGRP_OVERHEAD_CARD_Z', '0.30')))    # card centre in the robot base frame: on a thin mast above the rear cage, higher than the
                                    # raised arm (flat on the cage the arm hid it whenever the robot faced the camera: 2/438 reads)
MAST_HALF = (0.003, max(0.01, (CARD_AT[2] - 0.0685) / 2))          # mast radius and half length, from the cage top (z 0.0685) up to the card
BASE_Z = 0.0325                     # base frame origin height on a flat floor
TOP_ID0 = 40                        # card number = 39 + robot number
ARENA_SHORT_HALF_M = float(os.environ.get('UGRP_OVERHEAD_HALF', '2.75'))          # about 95 deg vertical view at 2.5 m (a wide lens; the real camera is not known yet)
CAMERAS = (('top', (2.175, -0.85)),)
YAW_OFFSET = 0.0                    # the marker top edge runs along the robot heading (checked against the simulator, 2026-11-15)
N_TOP = 9                           # card numbers TOP_ID0 .. TOP_ID0 + N_TOP - 1 mean a robot
DICTIONARY = 'DICT_4X4_50'


def camera_tiles(bounds, edge_m=0.20):
    """Ceiling camera centres that cover an arena with the SAME optics as the one camera of the old arena (so a card is as many pixels as
    before): tiles of the old footprint, enough of them that every robot centre (at least edge_m inside the walls) puts its card, with a
    little margin, inside one tile, and neighbouring tiles overlap. One tile at the centre when the old footprint is enough (the old arena)."""
    depth = HEIGHT_M - (BASE_Z + CARD_AT[2])
    half_y = depth * ARENA_SHORT_HALF_M / HEIGHT_M          # the picture's vertical half span at the card height
    half_x = half_y * WIDTH / HEIGHT
    margin = CARD_M / 2 + 0.02
    out = []
    for lo, hi, half in ((bounds[0], bounds[1], half_x), (bounds[2], bounds[3], half_y)):
        u, span = half - margin, hi - lo - 2 * edge_m          # a card centre within u of a tile centre is fully in that picture
        if span <= 2 * u:
            out.append([(lo + hi) / 2])
        else:
            n = max(2, math.ceil((span - 2 * u) / (1.8 * u)) + 1)      # centre step <= 1.8 u: neighbouring usable areas overlap by 10 %
            out.append([lo + edge_m + u + i * (span - 2 * u) / (n - 1) for i in range(n)])
    return [(x, y) for y in out[1] for x in out[0]]


# Generated map scenes (harness/map_scene_v1.py, DEFAULT off): UGRP_MAP_SCENE names the JSON file of the bridge; unset = the old arena above
_MAP = None
if os.environ.get('UGRP_MAP_SCENE'):
    with open(os.environ['UGRP_MAP_SCENE']) as _fh:
        _MAP = json.load(_fh)
if _MAP is not None:
    TOP_ID0, N_TOP, DICTIONARY = _MAP['markers']['robot_top_id0'], _MAP['markers']['n_robots'], _MAP['markers']['dictionary']
    CAMERAS = tuple(('top' if k == 0 else 'top_%d' % k, (round(x, 3), round(y, 3))) for k, (x, y) in enumerate(camera_tiles(_MAP['bounds'])))


def fovy_deg():
    return 2 * math.degrees(math.atan(ARENA_SHORT_HALF_M / HEIGHT_M))


def focal_px():
    return (HEIGHT / 2) / math.tan(math.radians(fovy_deg()) / 2)


def add_to_scene(xml, robots, textures):
    """Top cards on the robots, the ceiling cameras, and a render buffer large enough for them."""
    root = ET.fromstring(xml)
    asset, world = root.find('asset'), root.find('worldbody')
    vis = root.find('visual') if root.find('visual') is not None else ET.SubElement(root, 'visual')
    glob = vis.find('global') if vis.find('global') is not None else ET.SubElement(vis, 'global')
    glob.set('offwidth', str(max(WIDTH, int(glob.get('offwidth', 0) or 0))))
    glob.set('offheight', str(max(HEIGHT, int(glob.get('offheight', 0) or 0))))
    for rid in robots:
        n = TOP_ID0 - 1 + int(rid[1:])
        body = next((b for b in root.iter('body') if b.get('name') == rid + '__robot'), None)
        if body is None:
            continue
        ET.SubElement(asset, 'texture', name='robot_top_%d' % n, type='2d', file=textures[(n, 'n')])
        ET.SubElement(asset, 'material', name='robot_top_%d' % n, texture='robot_top_%d' % n, specular='0', shininess='0')
        ET.SubElement(body, 'geom', name=rid + '__tag_top', type='box', size='%.4f %.4f 0.0005' % (CARD_M / 2, CARD_M / 2),
                      pos='%.4f %.4f %.4f' % CARD_AT, material='robot_top_%d' % n, contype='0', conaffinity='0', mass='0')
        ET.SubElement(body, 'geom', name=rid + '__tag_mast', type='cylinder', size='%.4f %.4f' % MAST_HALF,
                      pos='%.4f %.4f %.4f' % (CARD_AT[0], CARD_AT[1], CARD_AT[2] - MAST_HALF[1] - 0.001),
                      rgba='.2 .2 .2 1', contype='0', conaffinity='0', mass='0')
    for name, (x, y) in CAMERAS:
        ET.SubElement(world, 'camera', name=name, pos='%.3f %.3f %.3f' % (x, y, HEIGHT_M), xyaxes='1 0 0 0 1 0',
                      fovy='%.3f' % fovy_deg())
    return ET.tostring(root, encoding='unicode')


def card_numbers(robots=('r1', 'r2', 'r3')):
    return [TOP_ID0 - 1 + int(r[1:]) for r in robots]


class OverheadReader:
    """Pictures of the ceiling cameras -> {robot: (x, y, yaw)} in the arena frame (metres, radians)."""
    def __init__(self):
        import cv2
        self.detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY)),
                                                cv2.aruco.DetectorParameters())
        self.f = focal_px()
        # camera axes (installed looking down, image x along the arena +x, image y along the arena -y)
        self.right, self.down = np.array([1., 0., 0.]), np.array([0., -1., 0.])

    def read(self, pictures):
        import cv2
        out = {}
        for name, (cx, cy) in CAMERAS:
            img = pictures.get(name)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
            corners, ids, _ = self.detector.detectMarkers(gray)
            for q, n in zip(corners, [] if ids is None else ids.ravel().tolist()):
                if not TOP_ID0 <= n < TOP_ID0 + N_TOP:
                    continue
                q = q.reshape(4, 2)
                c = q.mean(axis=0)
                depth = HEIGHT_M - (BASE_Z + CARD_AT[2])
                ground = np.array([cx, cy]) + depth / self.f * ((c[0] - WIDTH / 2) * self.right[:2] + (c[1] - HEIGHT / 2) * self.down[:2])
                top = q[1] - q[0]                       # the marker's top edge, left to right, in the picture
                v = top[0] * self.right[:2] + top[1] * self.down[:2]
                yaw = math.atan2(v[1], v[0]) + YAW_OFFSET
                yaw = math.atan2(math.sin(yaw), math.cos(yaw))
                # the card sits behind the base origin: move to the base origin along the heading
                x = ground[0] - CARD_AT[0] * math.cos(yaw)
                y = ground[1] - CARD_AT[0] * math.sin(yaw)
                side = float(np.mean([np.linalg.norm(q[i] - q[(i + 1) % 4]) for i in range(4)]))
                rid = 'r%d' % (n - TOP_ID0 + 1)
                if rid not in out or side > out[rid][3]:
                    out[rid] = (float(x), float(y), float(yaw), side, name)
        return {r: v[:3] for r, v in out.items()}


def to_frame(pose, frame):
    """A pose in the arena frame -> the frame of `frame` (an arena pose: its origin and heading)."""
    dx, dy = pose[0] - frame[0], pose[1] - frame[1]
    c, s = math.cos(frame[2]), math.sin(frame[2])
    yaw = pose[2] - frame[2] if len(pose) > 2 else 0.
    return (dx * c + dy * s, -dx * s + dy * c, math.atan2(math.sin(yaw), math.cos(yaw)))


def rough_place(x, y):
    """What the LLM planner is told about its own position (room level)."""
    if x < 2.2:
        where = 'in the box room'
    else:
        where = 'in the destination room'
    if abs(x - 2.2) < 0.9 and abs(y - 0.05) < 0.9:
        where += ', near the door'
    return where


def arena_from_model(model, prefix='zone_wall'):
    """Walls and doors of the arena, from the wall boxes of the scene (arena frame). A door is a gap between two
    collinear interior walls. Returns ({'walls': [(x0, y0, x1, y1)], 'doors': [{'x','y','left','right','width_m'}]})."""
    walls = []
    for g in range(model.ngeom):
        name = model.geom(g).name or ''
        if name.startswith(prefix):
            (x, y, _), (hx, hy, _) = model.geom_pos[g], model.geom_size[g]
            walls.append((name, float(x - hx), float(y - hy), float(x + hx), float(y + hy)))
    doors = []
    inner = [w for w in walls if 'divider' in w[0]]
    for a in inner:
        for b in inner:
            if a is b:
                continue
            ax, bx = .5 * (a[1] + a[3]), .5 * (b[1] + b[3])
            if abs(ax - bx) < 1e-3 and a[4] < b[2]:                 # same x, a below b: the gap between them
                if not any(c is not a and c is not b and abs(.5 * (c[1] + c[3]) - ax) < 1e-3 and a[4] <= c[2] < b[2] for c in inner):
                    doors.append({'x': ax, 'y': .5 * (a[4] + b[2]), 'left': [ax, b[2]], 'right': [ax, a[4]], 'width_m': b[2] - a[4]})
    # destination sign positions are not part of it (user decision 2026-11-15): robots find signs with their own camera
    return {'walls': [w[1:] for w in walls], 'doors': doors}


def wall_points(walls, step=0.10):
    """Points every `step` m along the centre line of each wall box."""
    pts = []
    for x0, y0, x1, y1 in walls:
        cx, cy = .5 * (x0 + x1), .5 * (y0 + y1)
        if x1 - x0 >= y1 - y0:
            pts += [(x, cy) for x in np.arange(x0, x1 + 1e-9, step)]
        else:
            pts += [(cx, y) for y in np.arange(y0, y1 + 1e-9, step)]
    return pts
