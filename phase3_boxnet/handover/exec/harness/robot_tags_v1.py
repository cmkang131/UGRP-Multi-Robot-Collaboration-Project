"""Number tags on the robots (task-definition option, DEFAULT off) and how a robot reads them.

Each robot carries four flat tag cards on its body (back, left, right of the rear cage, and a small one on the front
bumper), so its number can be read from any side. A tag is an ArUco 4x4 marker; its number tells the robot and
the side. It is a name plate on the robot body, not a marker for finding one's own position, and it is only
drawn: it has no mass and touches nothing.

Reading (robot side): from the robot's own picture only. A tag gives the other robot's number, its bearing and its
distance (from the known tag size).
"""
import json
import math
import os
import xml.etree.ElementTree as ET

import numpy as np

# Generated map scenes (harness/map_scene_v1.py, DEFAULT off): the bridge writes a small JSON file and points UGRP_MAP_SCENE at it. This
# module is loaded by file path in more than one place (the runner and harness/place_memory_v1.py each load their own copy), so the choice
# is made at import from the environment, not by a call. Unset = the constants of the one old arena below, byte for byte.
_MAP = None
if os.environ.get('UGRP_MAP_SCENE'):
    with open(os.environ['UGRP_MAP_SCENE']) as _fh:
        _MAP = json.load(_fh)

# Where the tags sit, thinking of the real robot: flat cards on the outside of the rear cage (the box that holds the
# controller board), one on its back and one on each side, standing a little above the wheels, and a small one on the
# front bumper plate (the arm leaves no room for more at the front). Nothing floats above the robot.
# side -> (index, card centre in the base frame, half width, half height, rotation, drawing that reads right from outside)
SIDES = {'back': (0, (-0.0861, 0., 0.043), 0.024, 0.024, '0 1.5708 0', 'h'),
         'left': (1, (-0.041, 0.0478, 0.043), 0.024, 0.024, '1.5708 0 0', 'h'),
         'right': (2, (-0.041, -0.0478, 0.043), 0.024, 0.024, '1.5708 0 0', 'n'),
         'front': (3, (0.0933, 0., 0.0009), 0.014, 0.014, '0 1.5708 0', 'n')}
# Card sizes follow the faces they sit on (2026-11-15): the rear cage side faces are 5.1 cm tall, so the back and side
# cards are 4.8 cm and stay inside them; nothing sticks up past the cage top, where the ceiling card lies.
INNER = 0.75                       # the marker is the inner 75 % of a card, the rest is its white border
ROBOT_ID0 = 20                     # tag number = 20 + 4 * (robot number - 1) + side index; 11..19 are destination signs
N_TAG_ROBOTS = 9                   # tag numbers ROBOT_ID0 .. ROBOT_ID0 + 4 * N_TAG_ROBOTS - 1 mean a robot side
DICTIONARY = 'DICT_4X4_50'
if _MAP is not None:
    ROBOT_ID0, N_TAG_ROBOTS, DICTIONARY = _MAP['markers']['robot_side_id0'], _MAP['markers']['n_robots'], _MAP['markers']['dictionary']


def tag_number(robot_number, side):
    return ROBOT_ID0 + 4 * (robot_number - 1) + SIDES[side][0]


def tag_meaning(number):
    """-> ('r2', 'left', marker side in metres) or None"""
    if not ROBOT_ID0 <= number < ROBOT_ID0 + 4 * N_TAG_ROBOTS:
        return None
    side = next(k for k, v in SIDES.items() if v[0] == (number - ROBOT_ID0) % 4)
    return 'r%d' % ((number - ROBOT_ID0) // 4 + 1), side, 2. * SIDES[side][2] * INNER


def _dictionary():
    import cv2
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICTIONARY))


def write_textures(folder, numbers):
    """PNG drawings of the tags (white border around the marker), plain and mirrored. Returns {(number, variant): path}."""
    import cv2
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for n in numbers:
        marker = cv2.aruco.generateImageMarker(_dictionary(), n, 240)
        img = np.full((320, 320), 255, np.uint8)
        img[40:280, 40:280] = marker
        for variant, picture in (('n', img), ('h', cv2.flip(img, 1))):
            path = folder / ('tag_%d_%s.png' % (n, variant))
            cv2.imwrite(str(path), cv2.cvtColor(picture, cv2.COLOR_GRAY2BGR))
            out[(n, variant)] = str(path.resolve())
    return out


def add_to_scene(xml, robots, textures):
    """Put the four tag cards on each robot body of the scene description. robots: e.g. ('r1', 'r2', 'r3')."""
    root = ET.fromstring(xml)
    asset = root.find('asset')
    for rid in robots:
        body = next((b for b in root.iter('body') if b.get('name') == rid + '__robot'), None)
        if body is None:
            continue
        for side, (_, centre, half_w, half_h, euler, variant) in SIDES.items():
            n = tag_number(int(rid[1:]), side)
            name = 'robot_tag_%d' % n
            ET.SubElement(asset, 'texture', name=name, type='2d', file=textures[(n, variant)])
            ET.SubElement(asset, 'material', name=name, texture=name, specular='0', shininess='0')
            ET.SubElement(body, 'geom', name='%s__tag_%s' % (rid, side), type='box', size='%.4f %.4f 0.0005' % (half_h, half_w),
                          pos='%.4f %.4f %.4f' % centre, euler=euler, material=name, contype='0', conaffinity='0', mass='0')
    return ET.tostring(root, encoding='unicode')


def robot_tag_numbers(robots=(1, 2, 3)):
    return [tag_number(r, side) for r in robots for side in SIDES]


# Destination signs (user decision 2026-11-15): a place to put boxes is marked by a number sign on a wall, and the box
# goes on the floor in front of that sign. These are destination labels, not position markers: the robot does not
# use them to work out where it is.
SIGN_M = 0.25
SIGN_MARKER_M = INNER * SIGN_M
SIGN_CENTRE_Z = 0.5 * SIGN_M + 0.005
# number -> (centre x, y on the wall face, which way the wall faces the room: '-x' east wall, '+y' south wall)
SIGNS = {11: (5.372, 0.40, '-x'), 12: (5.372, -2.10, '-x'), 13: (3.40, -3.122, '+y')}
# where a box counts as delivered to a sign: the floor within 0.65 m in front of it and 0.5 m to each side
SIGN_AREA = {11: (4.72, 5.375, -0.10, 0.90), 12: (4.72, 5.375, -2.60, -1.60), 13: (2.90, 3.90, -3.125, -2.47)}
if _MAP is not None:
    SIGNS = {int(k): (v['pos'][0], v['pos'][1], v['facing']) for k, v in _MAP['signs'].items()}
    SIGN_AREA = {int(k): tuple(v['area']) for k, v in _MAP['signs'].items()}
# the picture of a sign for each facing (the wall face it stands on looks toward this direction): two are the old arena's and verified by
# runs; '+x' and '-y' are those two turned by 180 degrees about the vertical axis (a quaternion; not checked in a picture)
SIGN_EULER = {'-x': '0 1.5708 0', '+y': '1.5708 0 0'}
SIGN_QUAT = {'+x': '0.000000 -0.707107 0.000000 0.707107', '-y': '0.000000 0.000000 0.707107 0.707107'}     # = harness/map_scene_v1.sign_orientation


def add_signs(xml, textures, numbers=None):
    """Stand the destination signs against the walls of the scene description (default: every sign of the scene: 11, 12, 13 in the
    old arena)."""
    root = ET.fromstring(xml)
    asset, world = root.find('asset'), root.find('worldbody')
    for n in (sorted(SIGNS) if numbers is None else numbers):
        x, y, facing = SIGNS[n]
        name = 'sign_tag_%d' % n      # both wall faces used here are seen from the side where the mirrored drawing reads right
        ET.SubElement(asset, 'texture', name=name, type='2d', file=textures[(n, 'h')])
        ET.SubElement(asset, 'material', name=name, texture=name, specular='0', shininess='0')
        # attribute order as before (the old arena's XML text must stay the same)
        attrs = dict(name='destination_sign_%d' % n, type='box', size='%.4f %.4f 0.001' % (0.5 * SIGN_M, 0.5 * SIGN_M),
                     pos='%.4f %.4f %.4f' % (x, y, SIGN_CENTRE_Z))
        attrs.update({'euler': SIGN_EULER[facing]} if facing in SIGN_EULER else {'quat': SIGN_QUAT[facing]})
        attrs.update(material=name, contype='0', conaffinity='0')
        ET.SubElement(world, 'geom', **attrs)
    return ET.tostring(root, encoding='unicode')


class TagReader:
    """Reads robot number tags in one own picture. K, D: the camera matrix and fisheye coefficients the robot knows."""
    def __init__(self, K, D):
        import cv2
        self.K = np.asarray(K, float)
        self.D = np.asarray(D, float).reshape(4, 1)
        self.raw_detector = None          # --sign-raw-read: made on first use
        self.maps = cv2.fisheye.initUndistortRectifyMap(self.K, np.asarray(D, float).reshape(4, 1), np.eye(3), self.K,
                                                         (640, 480), cv2.CV_32FC1)
        self.detector = cv2.aruco.ArucoDetector(_dictionary(), cv2.aruco.DetectorParameters())

    def read(self, jpeg):
        """-> [{'robot': 'r2', 'bearing_rad': +left, 'distance_m': along the view ray, 'side_px': tag size in the picture}]"""
        import cv2
        bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None or bgr.shape[:2] != (480, 640):
            raise ValueError('own RGB frame must decode to 640x480')
        gray = cv2.cvtColor(cv2.remap(bgr, self.maps[0], self.maps[1], cv2.INTER_LINEAR), cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.detector.detectMarkers(gray)
        out = []
        for quad, n in zip(corners, [] if ids is None else ids.ravel().tolist()):
            q = quad.reshape(4, 2)
            side = float(np.mean([np.linalg.norm(q[i] - q[(i + 1) % 4]) for i in range(4)]))
            if n in SIGNS:
                out.append({'sign': n, 'corners_px': [[float(v) for v in c_] for c_ in q], 'side_px': side})
                continue
            meaning = tag_meaning(n)
            if meaning is None:
                continue
            cx, cy = q.mean(axis=0)
            x, y = (cx - self.K[0, 2]) / self.K[0, 0], (cy - self.K[1, 2]) / self.K[1, 1]
            depth = self.K[0, 0] * meaning[2] / max(side, 1e-6)          # along the optical axis, card roughly facing
            out.append({'robot': meaning[0], 'side_seen': meaning[1], 'corners_px': [[float(v) for v in c_] for c_ in q],
                        'bearing_rad': -math.atan(x),
                        'distance_m': float(depth * math.sqrt(1. + x * x + y * y)), 'side_px': side})
        return out

    def read_signs_raw(self, jpeg):
        """Destination signs found in the RAW picture, their code corners mapped into the rectified 640 x 480 view (the corners `read` returns for a sign).
        -> [{'sign': 12, 'corners_px': 4 x 2 rectified pixels, 'side_px': mean side of the mapped code}]

        `read` looks for the codes in the rectified picture. A carrying robot's camera is 0.23 m high and looks 18 degrees down, so a card 2.4-2.7 m away stands at
        the very top of that picture (its top border at y = 0-5 px), and the rectified picture cuts it there: FIN-P2_N03_S10 r1 stood twice in front of sign 12 (frames 4421-4423
        and 4440-4442; the card whole and clear in the raw picture, upper right / upper left, 0.5 m from the top edge of the camera picture) and the rectified picture
        gave no code in any of the 24 look frames; the raw picture of the same frames gives the code in all of them (seen in the remapped frames: the card touches the top
        edge there). Over the 900 frames of that run the raw picture found the sign in 380, the rectified one in 240 (every one of those 240 among the 380), the mapped
        corners differing from the rectified ones by 0.8 px (median) and 2 px at most, the bearing of the sign from the mapped corners within 0.3 degree of the true one.
        Only codes with a sign number are returned."""
        import cv2
        bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None or bgr.shape[:2] != (480, 640):
            raise ValueError('own RGB frame must decode to 640x480')
        if self.raw_detector is None:
            self.raw_detector = cv2.aruco.ArucoDetector(_dictionary(), cv2.aruco.DetectorParameters())
        corners, ids, _ = self.raw_detector.detectMarkers(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
        out = []
        for quad, n in zip(corners, [] if ids is None else ids.ravel().tolist()):
            if n not in SIGNS:
                continue
            q = cv2.fisheye.undistortPoints(quad.reshape(1, 4, 2).astype(np.float64), self.K, self.D, P=self.K)[0]
            side = float(np.mean([np.linalg.norm(q[i] - q[(i + 1) % 4]) for i in range(4)]))
            out.append({'sign': n, 'corners_px': [[float(v) for v in c_] for c_ in q], 'side_px': side})
        return out


def card_corners(reading):
    """The card's white border corners (4 x 2, rectified 640 x 480 pixels), projected from the four decoded code corners."""
    import cv2
    square = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]], np.float32)
    quad = np.asarray(reading['corners_px'], np.float32)
    transform = cv2.getPerspectiveTransform(square * INNER, quad)
    return cv2.perspectiveTransform(square[None], transform)[0]


def whole_sign_in_frame(reading):
    """Project the card's white border from the four decoded code corners in the rectified 640 x 480 view."""
    card = card_corners(reading)
    return bool(np.all((card > 0) & (card < (639, 479))))


TOP_CLIP_MARGIN_PX = 3.0


def sign_in_frame_top_clipped(reading, margin=TOP_CLIP_MARGIN_PX):
    """--zone-close-fix: a close look accepts a card whose top border is cut off by the picture edge. The four decoded code corners
    lie inside the rectified 640 x 480 view by `margin` pixels, and the white border is whole at the left, the right and the bottom. A carrying
    robot's camera (0.23 m high, 18 degrees down) sees the top of the 0.255 m high card at the top edge of the picture at every distance, so the
    whole-border rule alone rejected the sign at the distance the approach stands (measured: SPD-P2_N03_S01 r2)."""
    quad = np.asarray(reading['corners_px'], float)
    if not np.all((quad[:, 0] > margin) & (quad[:, 0] < 639 - margin) & (quad[:, 1] > margin) & (quad[:, 1] < 479 - margin)):
        return False
    card = card_corners(reading)
    bottom = card[np.argsort(card[:, 1])[2:]]
    return bool(np.all((card[:, 0] > 0) & (card[:, 0] < 639)) and np.all((bottom[:, 1] > 0) & (bottom[:, 1] < 479)))


def sign_on_floor(reading, posture, camera_extrinsics, K):
    """Where a sign stands, from one reading and the camera posture the robot commanded (body frame, metres).

    The sign's centre height is known, so the view ray through its centre is cut at that height; the same for its
    two lower corners gives the direction of the wall. Returns {'x', 'y', 'normal': unit vector from the wall
    toward the robot} or None when the rays do not reach that height in front of the camera.
    """
    origin, axes = camera_extrinsics(posture)
    q = np.asarray(reading['corners_px'], float)

    def at_height(pixel, z):
        ray = np.array([(pixel[0] - K[0, 2]) / K[0, 0], (pixel[1] - K[1, 2]) / K[1, 1], 1.]) @ axes
        if abs(ray[2]) < 1e-6:
            return None
        k = (z - origin[2]) / ray[2]
        return None if k <= 0.05 else origin[:2] + k * ray[:2]
    centre = at_height(q.mean(axis=0), SIGN_CENTRE_Z)
    low = q[np.argsort(q[:, 1])[2:]]
    a, b = (at_height(p_, SIGN_CENTRE_Z - 0.5 * SIGN_MARKER_M) for p_ in low)
    if centre is None or a is None or b is None or np.linalg.norm(a - b) < 1e-3:
        return None
    along = (a - b) / np.linalg.norm(a - b)
    normal = np.array([-along[1], along[0]])
    if normal @ (-centre) < 0:          # toward the robot (the body origin)
        normal = -normal
    return {'x': float(centre[0]), 'y': float(centre[1]), 'normal': [float(normal[0]), float(normal[1])]}


BASE_Z = 0.0325          # the robot base sits this high (its body frame origin); card heights are above it


def robot_on_floor(reading, posture, camera_extrinsics, K):
    """Where the other robot is, in the reader's body frame: the view ray through the card centre cut at the card's
    known height, then moved half a body width inward along the ray (the card is on the outside of the robot).
    Returns (x, y) or None."""
    _, centre, half_w, half_h, _, _ = SIDES[reading['side_seen']]
    origin, axes = camera_extrinsics(posture)
    q = np.asarray(reading['corners_px'], float).mean(axis=0)
    ray = np.array([(q[0] - K[0, 2]) / K[0, 0], (q[1] - K[1, 2]) / K[1, 1], 1.]) @ axes
    if abs(ray[2]) < 1e-6:
        return None
    k = (BASE_Z + centre[2] - origin[2]) / ray[2]
    if k <= .05:
        return None
    flat = ray[:2] / max(np.linalg.norm(ray[:2]), 1e-6)
    at = origin[:2] + k * ray[:2] + 0.06 * flat
    return float(at[0]), float(at[1])
