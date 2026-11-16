"""Number tags on the robots (task-definition option, DEFAULT off) and how a robot reads them.

Each robot carries four flat tag cards on its body (back, left, right of the rear cage, and a small one on the front
bumper), so its number can be read from any side. A tag is an ArUco 4x4 marker; its number tells the robot and
the side. It is a name plate on the robot body, not a marker for finding one's own position, and it is only
drawn: it has no mass and touches nothing.

Reading (robot side): from the robot's own picture only. A tag gives the other robot's number, its bearing and its
distance (from the known tag size).
"""
import math
import xml.etree.ElementTree as ET

import numpy as np

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


def tag_number(robot_number, side):
    return ROBOT_ID0 + 4 * (robot_number - 1) + SIDES[side][0]


def tag_meaning(number):
    """-> ('r2', 'left', marker side in metres) or None"""
    if not ROBOT_ID0 <= number < ROBOT_ID0 + 36:
        return None
    side = next(k for k, v in SIDES.items() if v[0] == (number - ROBOT_ID0) % 4)
    return 'r%d' % ((number - ROBOT_ID0) // 4 + 1), side, 2. * SIDES[side][2] * INNER


def _dictionary():
    import cv2
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


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


def add_signs(xml, textures, numbers=(11, 12, 13)):
    """Stand the destination signs against the walls of the scene description."""
    root = ET.fromstring(xml)
    asset, world = root.find('asset'), root.find('worldbody')
    for n in numbers:
        x, y, facing = SIGNS[n]
        name = 'sign_tag_%d' % n      # both wall faces used here are seen from the side where the mirrored drawing reads right
        ET.SubElement(asset, 'texture', name=name, type='2d', file=textures[(n, 'h')])
        ET.SubElement(asset, 'material', name=name, texture=name, specular='0', shininess='0')
        ET.SubElement(world, 'geom', name='destination_sign_%d' % n, type='box', size='%.4f %.4f 0.001' % (0.5 * SIGN_M, 0.5 * SIGN_M),
                      pos='%.4f %.4f %.4f' % (x, y, SIGN_CENTRE_Z), euler='0 1.5708 0' if facing == '-x' else '1.5708 0 0',
                      material=name, contype='0', conaffinity='0')
    return ET.tostring(root, encoding='unicode')


class TagReader:
    """Reads robot number tags in one own picture. K, D: the camera matrix and fisheye coefficients the robot knows."""
    def __init__(self, K, D):
        import cv2
        self.K = np.asarray(K, float)
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
