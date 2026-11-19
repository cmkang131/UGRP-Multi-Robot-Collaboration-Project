"""place_memory_v1: rough places the robot has seen, kept as points. Own RGB and own commanded posture only.

Not a wall map. Each remembered place is a point in the frame of the look-around list (the robot's body
frame at its first tick): the listed boxes live in approach_survey_v1; this module adds the door.

Door: per image column the lowest dark-green wall pixel is the wall base. A door is a run of columns whose
wall base sits higher in the image (farther away) than the wall on both sides, with tall green wall on both
sides and bright non-green pixels (floor beyond) inside. The two jamb base pixels are projected to the floor
with the same camera pose the box list uses. The gap rule is the earlier far-door rule of the movement-only
work (door_weak.weak_observe), copied here so that the student path has no outside dependency.

Measured on the look-around frames of 12 held-out scenes (offline, true door read for scoring only): found
in 11 (in the other one the door was outside the pan range), median position error 0.31 m at 2.3-4.0 m, all
within 0.5 m; the range is read 5-17 % too long, more so when farther.
"""
import math

import cv2
import numpy as np

NOTCH_FAR_PX = 12
MIN_GAP_PX = 40
PILLAR_RUN_PX = 25
INTERIOR_MIN = .60
THETA_FAR_DEG = (4., 40.)
WIDTH_M = (.30, .80)
MIN_OBSERVATIONS = 3
SIGN_BOX_M = 0.32      # a box for a wall sign is set down this far in front of the sign
SIGN_SNAP_MAX_M = 1.5  # a wall hit farther than this from the sign's own depth estimate is not used
ZONE_CLOSE_M = 2.0     # close confirmation: 0.9 m approach standoff, two 0.35 m backoffs and 0.32 m to the sign
ZONE_CLOSE_FAR_M = 3.3  # --zone-close-far: the same, with the first close look 2.3 m in front of the floor point
ZONE_CLOSE_FIX_M = 2.6  # --zone-close-fix: the same, read from farther (the sign stood 2.0-2.2 m from the second backoff view in SPD-P2_N03_S01 r2)
_MAPS = {}
# Floor ranges read from the raised camera come out long by about k d^2 (door centre in the look-around frames of
# 16 development scenes: +0.14 m at 2.3 m, +0.5 m at 4 m; median of (read - true) / true^2 = 0.029), as a camera
# pitch about 0.3 degrees off would give. Every floor point of this module is pulled back along its ray from the
# camera. On 10 held-out scenes the door range error went from a median of 0.29 m to 0.05 m (largest 0.13 m).
RANGE_BIAS_K = .029


def true_range(points, origin):
    """Floor points (N x 2, body frame) with the long reading taken out, along the ray from the camera."""
    pts = np.asarray(points, float).reshape(-1, 2)
    v = pts - np.asarray(origin[:2], float)
    r = np.hypot(v[:, 0], v[:, 1])
    fixed = (-1. + np.sqrt(1. + 4. * RANGE_BIAS_K * r)) / (2. * RANGE_BIAS_K)
    scale = np.where(r > 1e-6, fixed / np.maximum(r, 1e-6), 1.)
    return np.asarray(origin[:2], float) + v * scale[:, None]


def _undistort(bgr, projection):
    key = id(projection)
    if key not in _MAPS:
        _MAPS[key] = cv2.fisheye.initUndistortRectifyMap(
            projection.K, np.asarray(projection.D, float).reshape(4, 1), np.eye(3), projection.K, (640, 480), cv2.CV_32FC1)
    return cv2.remap(bgr, _MAPS[key][0], _MAPS[key][1], cv2.INTER_LINEAR)


def door_candidates(jpeg, posture, projection, ignore_below_row=None):
    """Door gaps in one own frame -> list of {'left', 'right'} floor points in the current body frame.

    ignore_below_row: image rows from this one down are not used (the held box shows there while carrying).
    """
    bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None or bgr.shape[:2] != (480, 640):
        raise ValueError('own RGB frame must decode to 640x480')
    und = _undistort(bgr, projection)
    if ignore_below_row is not None:
        und = und.copy()
        und[int(ignore_below_row):] = 0
    hsv = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)
    wall = (hsv[..., 0] >= 55) & (hsv[..., 0] <= 85) & (hsv[..., 1] > 110) & (hsv[..., 2] < 140)
    height, width = wall.shape
    valid = wall.sum(0) >= 4
    if valid.sum() < 50:
        return []
    base = np.where(valid, height - 1 - np.argmax(wall[::-1, :], axis=0), -1e9).astype(float)
    pad = 80
    padded = np.concatenate([np.full(pad, -1e9), base, np.full(pad, -1e9)])
    highest = np.array([padded[i:i + 2 * pad + 1].max() for i in range(width)])
    gap = valid & (base <= highest - NOTCH_FAR_PX)
    bright = (~wall) & (hsv[..., 2] >= 60)
    k_inv = np.linalg.inv(projection.K)
    fx, cx = projection.K[0, 0], projection.K[0, 2]
    origin, axes = projection.camera_extrinsics(posture)

    def floor(u, v):
        ray = (k_inv @ np.array([u, v, 1.])) @ axes
        if ray[2] >= -1e-6:
            return None
        return origin[:2] - origin[2] * ray[:2] / ray[2]

    out, u = [], 0
    while u < width:
        if not gap[u]:
            u += 1
            continue
        s = u
        while u < width and gap[u]:
            u += 1
        e = u - 1
        if e - s + 1 < MIN_GAP_PX or s < 11 or e > width - 12 or not (valid[s - 1] and valid[e + 1]):
            continue
        runs = []
        for cols, row in ((range(s - 1, s - 12, -1), base[s - 1]), (range(e + 1, e + 12), base[e + 1])):
            top = max(0, int(row) - 70)
            runs.append(max(int(wall[top:int(row) + 1, col].sum()) for col in cols))
        far = float(np.median(base[s:e + 1]))
        near = int(min(base[s - 1], base[e + 1]))
        inside = float(bright[int(far) + 3:near - 3, s:e + 1].mean()) if near - 3 > int(far) + 3 else 0.
        theta = math.degrees(math.atan((cx - (s - .5)) / fx) - math.atan((cx - (e + .5)) / fx))
        if min(runs) < PILLAR_RUN_PX or inside < INTERIOR_MIN or not THETA_FAR_DEG[0] <= theta <= THETA_FAR_DEG[1]:
            continue
        left, right = floor(s - .5, base[s - 1]), floor(e + .5, base[e + 1])
        if left is None or right is None:
            continue
        left, right = true_range([left, right], origin)
        out.append({'left': [float(left[0]), float(left[1])], 'right': [float(right[0]), float(right[1])]})
    return out


def open_distance(jpeg, posture, projection, ignore_below_row=None, cap_m=4.):
    """How far the floor runs straight ahead before the wall: the median floor range of the wall base over the
    central columns of one own frame (capped; columns without a wall base count as the cap)."""
    bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None or bgr.shape[:2] != (480, 640):
        raise ValueError('own RGB frame must decode to 640x480')
    und = _undistort(bgr, projection)
    if ignore_below_row is not None:
        und = und.copy()
        und[int(ignore_below_row):] = 0
    hsv = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)
    wall = (hsv[..., 0] >= 55) & (hsv[..., 0] <= 85) & (hsv[..., 1] > 110) & (hsv[..., 2] < 140)
    cols = np.arange(220, 420)
    has = wall[:, cols].sum(0) >= 4
    base = wall.shape[0] - 1 - np.argmax(wall[::-1, cols], axis=0)
    origin, axes = projection.camera_extrinsics(posture)
    rays = (np.column_stack([cols, base, np.ones(len(cols))]).astype(float) @ np.linalg.inv(projection.K).T) @ axes
    rng = np.full(len(cols), cap_m)
    ok = has & (rays[:, 2] < -1e-6)
    pts = origin[:2] - origin[2] * rays[ok, :2] / rays[ok, 2, None]
    rng[ok] = np.minimum(cap_m, np.hypot(pts[:, 0] - origin[0], pts[:, 1] - origin[1]))
    return float(np.median(rng))


OBSTACLE_SAT, OBSTACLE_MIN_PX, OBSTACLE_RANGE_M = 120, 40, (.30, 3.5)
# Paint hues as measured (orange 12-16, purple 143-144, blue 112-114), kept narrow: a far red box reads hue 3-5,
# the magenta tile 160 and the violet can 132, all with saturation near 170-185 when small in the picture.
PAINT_HUES = ((10, 18), (136, 152), (108, 118))
PAINT_MAX_SAT = 180
SAME_RAY_M, SAME_RAY_STEP_M = .06, .12
FAR_READ_M, CLEAR_RANGE_M, CLEAR_HALF_VIEW = 2.2, (.65, 1.9), math.radians(18)


def obstacle_points(jpeg, posture, projection, ignore_below_row=None):
    """Things standing on the floor, as floor points (current body frame): the bottom edge of every strongly
    coloured blob that is not wall green. Boxes, cans, tiles and bars in this arena are all strongly coloured;
    the floor (grey checker, faint blue tint up to saturation 93) is not. Floor paint of the zones is strongly
    coloured too, but thinly; blobs in a zone colour with paint-like saturation are left out (see below). Three
    development runs stopped in front of a free door because the edge of the purple zone behind it was read as a
    thing."""
    bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None or bgr.shape[:2] != (480, 640):
        raise ValueError('own RGB frame must decode to 640x480')
    hsv = cv2.cvtColor(_undistort(bgr, projection), cv2.COLOR_BGR2HSV)
    wall = (hsv[..., 0] >= 55) & (hsv[..., 0] <= 85) & (hsv[..., 1] > 110) & (hsv[..., 2] < 140)
    # nothing that stands on this floor is wall green; brightly lit wall ends fall outside the wall rule above and
    # were read as things beside the door opening
    green = (hsv[..., 0] >= 50) & (hsv[..., 0] <= 90)
    solid = ((~wall) & (~green) & (hsv[..., 1] >= OBSTACLE_SAT) & (hsv[..., 2] >= 50)).astype(np.uint8)
    solid[:40] = 0
    cut = int(ignore_below_row) if ignore_below_row is not None else 400
    solid[cut:] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    origin, axes = projection.camera_extrinsics(posture)
    k_inv = np.linalg.inv(projection.K)
    out = []
    for n in range(1, count):
        x, y, w, h, area = stats[n]
        if area < OBSTACLE_MIN_PX:
            continue
        if y + h >= cut - 1:
            continue        # runs into the hidden rows: its lower edge is the cut, not its foot (the held box's rim)
        part = labels[y:y + h, x:x + w] == n
        pix = []
        for col in range(0, w, 6):
            rows = np.flatnonzero(part[:, col])
            if len(rows):
                pix.append([x + col, y + rows[-1], 1.])
        rays = (np.array(pix) @ k_inv.T) @ axes
        down = rays[:, 2] < -1e-6
        if not down.any():
            continue
        pts = origin[:2] - origin[2] * rays[down, :2] / rays[down, 2, None]
        # floor paint of a zone is coloured too, but thinly: its saturation stays well below that of a solid thing
        # (paint medians 117-162; orange wheels 229, violet can 194, blue box 225). A blob in a zone colour with
        # paint-like saturation is paint, whatever its size: thin slivers of the purple zone seen past the door
        # jamb were small and narrow and still paint.
        hue = float(np.median(hsv[y:y + h, x:x + w, 0][part]))
        sat = float(np.median(hsv[y:y + h, x:x + w, 1][part]))
        zone_coloured = any(lo <= hue <= hi for lo, hi in PAINT_HUES) and sat < PAINT_MAX_SAT
        if zone_coloured:
            continue
        rng = np.hypot(pts[:, 0] - origin[0], pts[:, 1] - origin[1])
        out += true_range(pts[(rng >= OBSTACLE_RANGE_M[0]) & (rng <= OBSTACLE_RANGE_M[1])], origin).tolist()
    return out


TALL_MIN_PX, TALL_MIN_COLS = 8, 12


def _tall_thing_in_gap(hsv, wall, left, right, jamb_row, floor_point, jambs):
    """Something as tall as the camera stands behind the opening, and how far beyond the door line.

    Through the opening the far wall shows as a green band; a tall thing (another robot) covers part of that
    band, which floor paint and low things do not. Its distance comes from its foot: the lowest strongly
    coloured pixel under the covered columns, above the door line (the wheels of these robots are orange).
    Returns {'beyond_m', 'lateral_m'} (past the door line, and sideways from the door axis), or None when
    nothing covers the band or no foot is found.
    """
    margin = int(.15 * (right - left))
    first = left + margin
    cols = np.arange(first, right - margin + 1)
    if len(cols) < TALL_MIN_COLS:
        return None
    band = wall[:, cols]
    has = band.sum(0) >= 4
    if has.mean() < .5:
        return None                     # no far wall in the gap to judge against
    top = np.argmax(band, axis=0)
    base = band.shape[0] - 1 - np.argmax(band[::-1], axis=0)
    lo, hi = int(np.median(top[has])), int(np.median(base[has]))
    lit = hsv[:, cols, 2] > 12
    covered = ((lit[lo:hi + 1] & ~band[lo:hi + 1]).sum(axis=0) >= TALL_MIN_PX)
    best, run, end = 0, 0, 0
    for n, flag in enumerate(covered):
        run = run + 1 if flag else 0
        if run > best:
            best, end = run, n
    if best < TALL_MIN_COLS:
        return None
    c0, c1 = max(left + 2, first + end - best + 1 - 30), min(right - 2, first + end + 30)
    r0, r1 = hi + 1, int(jamb_row) - 2
    if r1 <= r0:
        return None
    patch = hsv[r0:r1, c0:c1 + 1]
    solid = (patch[..., 1] >= OBSTACLE_SAT) & (patch[..., 2] >= 50) & ~wall[r0:r1, c0:c1 + 1]
    rows = np.flatnonzero(solid.sum(axis=1) >= 3)
    if not len(rows):
        return None
    foot_row = r0 + int(rows[-1])
    foot_col = c0 + int(np.median(np.flatnonzero(solid[rows[-1]])))
    foot = floor_point(foot_col, foot_row)
    if foot is None:
        return None
    centre = .5 * (jambs[0] + jambs[1])
    along = (jambs[1] - jambs[0]) / np.linalg.norm(jambs[1] - jambs[0])
    normal = np.array([-along[1], along[0]])
    if normal @ centre < 0:
        normal = -normal                # away from the robot, which stands at the origin of this frame
    return {'beyond_m': float((foot - centre) @ normal), 'lateral_m': float((foot - centre) @ along)}


WALL_STEP_PX, WALL_MAX_RANGE_M = 16, 2.5


def wall_points(jpeg, posture, projection, ignore_below_row=None):
    """Where the wall meets the floor, as sparse floor points (current body frame, within WALL_MAX_RANGE_M).
    Not a wall map: a few points per look, so that a route does not run along a wall it has just seen. Two
    development runs touched the wall beside the door because routes knew only the things on the floor."""
    bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None or bgr.shape[:2] != (480, 640):
        raise ValueError('own RGB frame must decode to 640x480')
    und = _undistort(bgr, projection)
    if ignore_below_row is not None:
        und = und.copy()
        und[int(ignore_below_row):] = 0
    hsv = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)
    wall = (hsv[..., 0] >= 55) & (hsv[..., 0] <= 85) & (hsv[..., 1] > 110) & (hsv[..., 2] < 140)
    cols = np.arange(24, 616, WALL_STEP_PX)
    has = wall[:, cols].sum(0) >= 8
    base = wall.shape[0] - 1 - np.argmax(wall[::-1, cols], axis=0)
    origin, axes = projection.camera_extrinsics(posture)
    rays = (np.column_stack([cols, base, np.ones(len(cols))]).astype(float) @ np.linalg.inv(projection.K).T) @ axes
    ok = has & (rays[:, 2] < -1e-6)
    if not ok.any():
        return []
    pts = origin[:2] - origin[2] * rays[ok, :2] / rays[ok, 2, None]
    pts = true_range(pts, origin)
    rng = np.hypot(pts[:, 0] - origin[0], pts[:, 1] - origin[1])
    # a wall is continuous: a point with no neighbouring column within 0.25 m is something else that is green
    step = np.hypot(*(pts[1:] - pts[:-1]).T) if len(pts) > 1 else np.array([])
    lonely = np.ones(len(pts), bool)
    lonely[:-1] &= step > .25
    lonely[1:] &= step > .25
    return pts[(rng >= .30) & (rng <= WALL_MAX_RANGE_M) & ~lonely].tolist()


NEAR_JUMP_M = .40
NEAR_WIDTH_M = (.40, .62)
NEAR_MAX_RANGE_M = 2.2


def door_candidates_near(jpeg, posture, projection, ignore_below_row=None):
    """Door gaps within about 2 m, by range: every column's wall base is projected to the floor, and a door
    is a run of columns whose wall base is at least NEAR_JUMP_M farther than the wall on both sides (or has
    no wall at all), with the two jamb points NEAR_WIDTH_M apart. Same output as door_candidates."""
    bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None or bgr.shape[:2] != (480, 640):
        raise ValueError('own RGB frame must decode to 640x480')
    und = _undistort(bgr, projection)
    if ignore_below_row is not None:
        und = und.copy()
        und[int(ignore_below_row):] = 0
    hsv = cv2.cvtColor(und, cv2.COLOR_BGR2HSV)
    wall = (hsv[..., 0] >= 55) & (hsv[..., 0] <= 85) & (hsv[..., 1] > 110) & (hsv[..., 2] < 140)
    height, width = wall.shape
    has = wall.sum(0) >= 4
    base = height - 1 - np.argmax(wall[::-1, :], axis=0)
    origin, axes = projection.camera_extrinsics(posture)
    pix = np.column_stack([np.arange(width), base, np.ones(width)]).astype(float)
    rays = (pix @ np.linalg.inv(projection.K).T) @ axes
    down = rays[:, 2] < -1e-6
    pts = np.full((width, 2), np.nan)
    pts[down] = origin[:2] - origin[2] * rays[down, :2] / rays[down, 2, None]
    k_inv = np.linalg.inv(projection.K)

    def floor_point(u, v):
        ray = (k_inv @ np.array([u, v, 1.])) @ axes
        return None if ray[2] >= -1e-6 else origin[:2] - origin[2] * ray[:2] / ray[2]
    rng = np.where(has & down, np.hypot(pts[:, 0] - origin[0], pts[:, 1] - origin[1]), np.inf)
    # image columns lost to the lens border carry no information
    seen = und.max(axis=2).max(axis=0) > 12
    near = seen & np.isfinite(rng) & (rng <= NEAR_MAX_RANGE_M)
    out, u = [], 0
    cols = np.flatnonzero(seen)
    if len(cols) < 100:
        return out
    lo, hi = int(cols[0]) + 8, int(cols[-1]) - 8
    u = lo
    while u < hi:
        # a jamb on the left: a near wall column followed by a column that is much farther (or open)
        if not near[u] or not (rng[u + 1] - rng[u] >= NEAR_JUMP_M):
            u += 1
            continue
        left = u
        v = u + 1
        while v < hi and not (near[v] and rng[v] <= rng[left] + NEAR_JUMP_M + .4 and rng[v - 1] - rng[v] >= NEAR_JUMP_M):
            v += 1
        if v >= hi:
            break
        right = v
        gap = np.hypot(*(pts[left] - pts[right]))
        inside = rng[left + 1:right]
        if (NEAR_WIDTH_M[0] <= gap <= NEAR_WIDTH_M[1] and right - left >= 20
                and (inside >= min(rng[left], rng[right]) + NEAR_JUMP_M).mean() >= .9):
            jl, jr = true_range([pts[left], pts[right]], origin)
            out.append({'left': [float(jl[0]), float(jl[1])], 'right': [float(jr[0]), float(jr[1])],
                        'tall_thing': _tall_thing_in_gap(hsv, wall, left, right, min(base[left], base[right]),
                                                         lambda u, v: None if floor_point(u, v) is None else
                                                         true_range([floor_point(u, v)], origin)[0], (jl, jr))})
        u = right
    return out


# Floor-colour zones. Hue ranges (OpenCV H) are those of the earlier movement-only work; the saturation floors
# were read from one development run that looked around the next room (90725): orange paint median 146,
# purple 117-139, blue zone 122, while the faint blue tint of the pickup room floor stays at or below 93.
ZONE_RULE = {'orange': (5, 25, 80), 'purple': (130, 160, 80), 'blue': (100, 125, 105)}
ZONE_MIN_PX = 800
ZONE_MAX_RANGE_M = 3.5
# The held box, as the raised camera sees it at the bottom of the picture (it knows which kind it picked).
HELD_BOX_RULE = {'red': lambda h, s: ((h <= 4) | (h >= 175)) & (s >= 150), 'cyan': lambda h, s: (h >= 95) & (h <= 125) & (s >= 180)}
# Held check, lens-edge fix (--held-check-edge-fix, DEFAULT OFF). While the robot looks for the box it just lifted, the raised camera still sees
# the upper rim of that box as a thin coloured sliver lying along the curved black border of the lens (11-26 px high, 58-173 px wide, ends at
# rows 443-458, above the old 'reaches row 462' test). The check read that sliver as a box left on the floor 0.39 m ahead (a work
# record; offline replay of the stored held-look frames: scripts/held_edge_offline.py). A box that lies on the floor 0.6 m ahead
# stands at least 137 px above the border (stored real 'not held' cases). A blob counts as the box in the gripper when at least HELD_EDGE_COLUMNS of the columns
# it covers end within HELD_EDGE_PX rows of the lowest bright pixel (V >= 40) of that column. No height condition: the slivers are lower than
# any size that would separate them from a floor box (the diagnosis proposed 18 px; slivers are 11-26 px), the border distance alone does.
HELD_EDGE_PX, HELD_EDGE_COLUMNS = 6, 0.5


def last_bright_rows(value):
    """Per column the lowest row whose V is at least 40 (-1 when the column is black): where the lens border starts."""
    bright = value >= 40
    return np.where(bright.any(axis=0), bright.shape[0] - 1 - np.argmax(bright[::-1], axis=0), -1)


def lens_edge_share(blob, last_bright):
    """Share of the columns of one blob (bool mask) whose lowest blob pixel lies within HELD_EDGE_PX rows of the lens border (last_bright_rows)."""
    cols = np.flatnonzero(blob.any(axis=0))
    if not len(cols):
        return 0.
    bottom = blob.shape[0] - 1 - np.argmax(blob[::-1][:, cols], axis=0)
    return float(np.mean(last_bright[cols] - bottom <= HELD_EDGE_PX))


def held_box_top(hsv, kind):
    """Topmost image row of the held box: rows are followed upward from the bottom while at least 40 % of the
    central columns have the box colour. Returns 480 when no box shows."""
    rule = HELD_BOX_RULE.get(kind)
    if rule is None:
        return 480
    boxlike = rule(hsv[..., 0], hsv[..., 1])[:, 200:440].mean(axis=1) >= .40
    row, top = 445, 480
    while row >= 0 and not boxlike[row] and row > 400:
        row -= 1                      # the lens border at the very bottom
    while row >= 0 and boxlike[row]:
        top = row
        row -= 1
    return top


def zone_points(jpeg, posture, projection, colour, held_kind=None):
    """Floor points (current body frame) of the paint of one zone colour in one own frame, and its pixel count."""
    lo, hi, sat = ZONE_RULE[colour]
    bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None or bgr.shape[:2] != (480, 640):
        raise ValueError('own RGB frame must decode to 640x480')
    hsv = cv2.cvtColor(_undistort(bgr, projection), cv2.COLOR_BGR2HSV)
    wall = (hsv[..., 0] >= 55) & (hsv[..., 0] <= 85) & (hsv[..., 1] > 110) & (hsv[..., 2] < 140)
    paint = (~wall) & (hsv[..., 0] >= lo) & (hsv[..., 0] <= hi) & (hsv[..., 1] >= sat) & (hsv[..., 2] >= 40)
    paint[max(0, held_box_top(hsv, held_kind) - 6):] = False
    area = int(paint.sum())
    if area < ZONE_MIN_PX:
        return [], area
    rows, cols = np.nonzero(paint[::4, ::4])
    pix = np.column_stack([cols * 4, rows * 4, np.ones(len(rows))]).astype(float)
    origin, axes = projection.camera_extrinsics(posture)
    rays = (pix @ np.linalg.inv(projection.K).T) @ axes
    down = rays[:, 2] < -1e-6
    pts = origin[:2] - origin[2] * rays[down, :2] / rays[down, 2, None]
    near = np.hypot(pts[:, 0] - origin[0], pts[:, 1] - origin[1]) <= ZONE_MAX_RANGE_M
    return true_range(pts[near], origin).tolist(), area


def door_axes(door, came_from):
    """Unit vectors of the door frame in the list frame: forward (through the door, away from the side the
    robot came from) and left. came_from: a point on the side the robot started on."""
    tx, ty = door['right'][0] - door['left'][0], door['right'][1] - door['left'][1]
    n = math.hypot(tx, ty)
    fx, fy = -ty / n, tx / n
    if fx * (came_from[0] - door['x']) + fy * (came_from[1] - door['y']) > 0:
        fx, fy = -fx, -fy
    return (fx, fy), (-fy, fx)


def describe_from_door(point, door, came_from):
    """A place said the way a person would: so far past the door, so far to the left. Robots do not share a
    frame (each remembers in its own starting frame), but both can see the door."""
    (fx, fy), (lx, ly) = door_axes(door, came_from)
    dx, dy = point[0] - door['x'], point[1] - door['y']
    return {'forward_m': dx * fx + dy * fy, 'left_m': dx * lx + dy * ly}


def place_from_description(told, door, came_from):
    """The told place in the hearer's own list frame, from the hearer's own door."""
    (fx, fy), (lx, ly) = door_axes(door, came_from)
    return [door['x'] + told['forward_m'] * fx + told['left_m'] * lx, door['y'] + told['forward_m'] * fy + told['left_m'] * ly]


class PlaceMemory:
    """Door observations by phase ('look_around' while standing at the start, later phases while moving)."""

    def __init__(self, projection):
        self.projection = projection
        self.observations = []
        self.frames = {}
        self.zone_points = []   # (colour, phase, x, y) in the list frame
        self.walls = {}         # 5 cm cell -> (x, y, range it was seen from): sparse points where wall meets floor
        self.obstacles = {}     # 5 cm cell -> (x, y, range it was seen from, standpoint x, y) in the list frame
        self.zone_frames = {}

    def observe(self, jpeg, posture, pose=(0., 0., 0.), phase='look_around', ignore_below_row=None, near=False,
                held_kind=None):
        """pose: the robot's own estimate (x, y, yaw) in the list frame when the frame was taken.
        near: use the range rule (door within about 2 m) instead of the far rule."""
        self.frames[phase] = self.frames.get(phase, 0) + 1
        if held_kind is not None:
            # the held box can reach higher in the picture than the fixed row; it is neither wall nor obstacle
            bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            top = held_box_top(cv2.cvtColor(_undistort(bgr, self.projection), cv2.COLOR_BGR2HSV), held_kind)
            ignore_below_row = min(480 if ignore_below_row is None else ignore_below_row, top - 6)   # a tilted box: its rim rises to one side; blobs touching this row are dropped
        x, y, yaw = pose
        c, s = math.cos(yaw), math.sin(yaw)
        fresh = []
        for q in obstacle_points(jpeg, posture, self.projection, ignore_below_row):
            fresh.append((x + c * q[0] - s * q[1], y + s * q[0] + c * q[1], math.hypot(q[0], q[1])))
        for ox, oy, rng in fresh:
            # a thing seen from close by replaces what was read near the same spot from much farther away
            for key, old in list(self.obstacles.items()):
                if old[2] > 1.5 * rng and old[2] > 1.2 and math.hypot(old[0] - ox, old[1] - oy) < .35:
                    del self.obstacles[key]
        # A thing read from far away (a thin blob near the horizon: a few pixels are tenths of a metre) that should
        # now be in plain view at close range, with nothing seen near it, was misplaced: forget it. One development
        # scene kept a second, wrong row of a bar in front of the door and found no place to stand.
        pan = (float(posture.get(6, 1500)) - 1500.) * math.pi / 2000.
        for key, old in list(self.obstacles.items()):
            bx, by = (old[0] - x) * c + (old[1] - y) * s, -(old[0] - x) * s + (old[1] - y) * c
            now = math.hypot(bx, by)
            if (old[2] > FAR_READ_M and CLEAR_RANGE_M[0] <= now <= CLEAR_RANGE_M[1] and old[2] > 1.5 * now
                    and abs(math.atan2(by, bx) - pan) <= CLEAR_HALF_VIEW
                    and not any(math.hypot(old[0] - f[0], old[1] - f[1]) < .25 for f in fresh)):
                del self.obstacles[key]
        for ox, oy, rng in fresh:
            # From one standpoint, two points on the same line of sight are one thing: when the lit top of a low
            # thing is all that shows, its edge is read as a floor point farther along the ray (a bar 3 cm high
            # seen from 3 m gave a second row 0.4 m behind the real one). The nearer point is the foot.
            ux, uy = (ox - x) / max(rng, 1e-6), (oy - y) / max(rng, 1e-6)
            behind_another = False
            for key, old in list(self.obstacles.items()):
                if math.hypot(old[3] - x, old[4] - y) > .05:
                    continue                                  # seen from somewhere else
                along = (old[0] - x) * ux + (old[1] - y) * uy
                across = abs(-(old[0] - x) * uy + (old[1] - y) * ux)
                if across < SAME_RAY_M and along - rng > SAME_RAY_STEP_M:
                    del self.obstacles[key]                   # the old point lies behind the new one
                elif across < SAME_RAY_M and rng - along > SAME_RAY_STEP_M:
                    behind_another = True
            if behind_another:
                continue
            key = (round(ox / .05), round(oy / .05))
            if key not in self.obstacles or self.obstacles[key][2] > rng:
                self.obstacles[key] = (ox, oy, rng, x, y, phase)
        for q in wall_points(jpeg, posture, self.projection, ignore_below_row):
            wx, wy = x + c * q[0] - s * q[1], y + s * q[0] + c * q[1]
            key = (round(wx / .05), round(wy / .05))
            rng = math.hypot(q[0], q[1])
            if key not in self.walls or self.walls[key][2] > rng:
                self.walls[key] = (wx, wy, rng, phase)
        finder = door_candidates_near if near else door_candidates
        for cand in finder(jpeg, posture, self.projection, ignore_below_row):
            pts = [[x + c * p[0] - s * p[1], y + s * p[0] + c * p[1]] for p in (cand['left'], cand['right'])]
            width = math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
            if WIDTH_M[0] <= width <= WIDTH_M[1]:
                entry = {'phase': phase, 'left': pts[0], 'right': pts[1], 'width': width}
                if near:
                    entry['tall_thing'] = cand.get('tall_thing')
                self.observations.append(entry)

    def observe_zone(self, jpeg, posture, colour, pose=(0., 0., 0.), phase='zone_scan', held_kind=None, close=False):
        """Remember where the paint of one zone colour was seen (list frame).

        colour 'sign<n>': the destination is a number sign on a wall instead of floor paint. The remembered point
        is the floor SIGN_BOX_M in front of the sign, where the box goes. A close look accepts a whole card within
        ZONE_CLOSE_M, or floor paint within that range for a colour destination."""
        if colour.startswith('sign'):
            pts = self._sign_points(jpeg, posture, int(colour[4:]), pose, close=close, phase=phase)
            area = 1000 * len(pts)
        else:
            pts, area = zone_points(jpeg, posture, self.projection, colour, held_kind)
            if close:
                pts = [p for p in pts if math.hypot(*p) < ZONE_CLOSE_M]
        key = colour + '/' + phase
        entry = self.zone_frames.setdefault(key, {'frames': 0, 'frames_with_paint': 0, 'largest_px': 0})
        entry['frames'] += 1
        entry['frames_with_paint'] += int(bool(pts))
        entry['largest_px'] = max(entry['largest_px'], area)
        x, y, yaw = pose
        c, s = math.cos(yaw), math.sin(yaw)
        self.zone_points += [(colour, phase, x + c * p[0] - s * p[1], y + s * p[0] + c * p[1]) for p in pts]

    def _snap_to_wall(self, at, pose):
        """With the arena known (wall faces as list-frame segments): keep the sign's bearing from the picture, take its
        distance and facing from the wall face that the view ray meets. A sign read 3-4 m away at a slant had its depth
        and facing off by tenths of a metre (sign 12 set-down 0.5 m south in X04 and C01). Body frame in and out."""
        segs = getattr(self, 'known_wall_segments', None)
        if not segs:
            return at
        x, y, yaw = pose
        c, s_ = math.cos(yaw), math.sin(yaw)
        body = lambda p: ((p[0] - x) * c + (p[1] - y) * s_, -(p[0] - x) * s_ + (p[1] - y) * c)
        dx, dy = at['x'], at['y']
        n = math.hypot(dx, dy)
        if n < 1e-6:
            return at
        dx, dy = dx / n, dy / n
        best = None
        for a, b in segs:
            (ax, ay), (bx, by) = body(a), body(b)
            ex, ey = bx - ax, by - ay
            den = dx * ey - dy * ex
            if abs(den) < 1e-9:
                continue
            t = (ax * ey - ay * ex) / den            # along the ray
            u = (ax * dy - ay * dx) / den            # along the segment
            if t > 0.05 and -1e-6 <= u <= 1 + 1e-6 and (best is None or t < best[0]):
                nx, ny = -ey, ex
                if nx * -ax + ny * -ay < 0:
                    nx, ny = -nx, -ny
                k = math.hypot(nx, ny)
                best = (t, nx / k, ny / k)
        if best is None or abs(best[0] - n) > SIGN_SNAP_MAX_M:
            return at
        t, nx, ny = best
        return {'x': t * dx, 'y': t * dy, 'normal': [nx, ny], 'snapped': True}

    def _sign_points(self, jpeg, posture, number, pose=None, close=False, phase=None):
        if getattr(self, '_tags', None) is None:
            import importlib.util
            from pathlib import Path
            spec = importlib.util.spec_from_file_location('robot_tags_v1', str(Path(__file__).resolve().parent / 'robot_tags_v1.py'))
            self._tags = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self._tags)
            self._tag_reader = self._tags.TagReader(self.projection.K, self.projection.D)
        out = []
        fix = close and getattr(self, 'close_fix', False)            # --zone-close-fix (DEFAULT off)
        log = getattr(self, 'close_reads', None) if close else None   # a record of every close reading, kept with --zone-confirm-close
        limit = (ZONE_CLOSE_FAR_M if getattr(self, 'close_far', False) else ZONE_CLOSE_FIX_M) if fix else ZONE_CLOSE_M if close else 6.
        for reading in self._tag_reader.read(jpeg):
            if reading.get('sign') != number:
                if log is not None and 'sign' in reading:
                    log.append({'phase': phase, 'sign': reading['sign'], 'accepted': False, 'why': 'other_id'})
                continue
            row = None
            if log is not None:
                _q = reading['corners_px']
                _card = self._tags.card_corners(reading)
                row = {'phase': phase, 'sign': number, 'side_px': round(reading['side_px'], 1),
                       'marker_y': [round(min(c[1] for c in _q), 1), round(max(c[1] for c in _q), 1)],
                       'marker_x': [round(min(c[0] for c in _q), 1), round(max(c[0] for c in _q), 1)],
                       'card_y': [round(float(_card[:, 1].min()), 1), round(float(_card[:, 1].max()), 1)],
                       'card_x': [round(float(_card[:, 0].min()), 1), round(float(_card[:, 0].max()), 1)],
                       'whole': bool(self._tags.whole_sign_in_frame(reading)), 'accepted': False}
                log.append(row)
            if close and not (self._tags.sign_in_frame_top_clipped(reading) if fix else self._tags.whole_sign_in_frame(reading)):
                if row is not None:
                    row['why'] = 'not_in_frame'
                continue
            at = self._tags.sign_on_floor(reading, posture, self.projection.camera_extrinsics, self.projection.K)
            if row is not None:
                row['floor_xy'] = None if at is None else [round(at['x'], 3), round(at['y'], 3)]
            if at is not None and pose is not None:
                at = self._snap_to_wall(at, pose)
            if row is not None and at is not None:
                row['snapped_xy'] = [round(at['x'], 3), round(at['y'], 3)]
                row['dist_m'] = round(math.hypot(at['x'], at['y']), 3)
            if at is not None and math.hypot(at['x'], at['y']) < limit:
                # one reading counts as a full sighting (the paint rule asks for 30 points)
                out += [(at['x'] + SIGN_BOX_M * at['normal'][0], at['y'] + SIGN_BOX_M * at['normal'][1])] * 30
                if row is not None:
                    row['accepted'] = True
            elif row is not None:
                row['why'] = 'no_floor' if at is None else 'too_far'
        return out

    def zone(self, colour, phase=None):
        """Rough place of a zone: the median of the paint points seen (None when fewer than 30 points)."""
        pts = np.array([[p[2], p[3]] for p in self.zone_points if p[0] == colour and (phase is None or p[1] == phase)])
        if len(pts) < 30:
            return None
        centre = np.median(pts, axis=0)
        return {'kind': 'zone_' + colour, 'x': float(centre[0]), 'y': float(centre[1]), 'points': int(len(pts)),
                'spread_m': [float(v) for v in (np.percentile(pts, 90, axis=0) - np.percentile(pts, 10, axis=0))]}

    def place_from_description(self, told, door, came_from):
        return place_from_description(told, door, came_from)

    def box_on_floor(self, jpeg, posture, kind, edge_fix=False):
        """Boxes of one colour lying on the floor in the own picture -> [(x, y)] in the body frame (metres). Blobs that
        reach the bottom edge (a box in the gripper) are not counted. edge_fix (DEFAULT False): blobs that lie along the lens border
        (HELD_EDGE_PX, HELD_EDGE_COLUMNS above) are not counted either; they are listed in self.last_edge_excluded."""
        rule = HELD_BOX_RULE.get('red' if kind == 'green' else kind)
        bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if rule is None or bgr is None:
            return []
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        # brightness floor: the black lens border carries saturated colour fringes (V <= 13; about 3700 'red' and 3600
        # 'blue' pixels per frame) that read as a box left on the floor (team-v6/v8 X01 r1: a false 'not held').
        # Box faces are far brighter (V about 200)
        mask = (rule(hsv[..., 0], hsv[..., 1]) & (hsv[..., 2] >= 40)).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
        last_bright = last_bright_rows(hsv[..., 2]) if edge_fix else None
        if edge_fix:
            self.last_edge_excluded = []
        out = []
        for j in range(1, n):
            x, y, w, h, area = stats[j]
            if area < 40 or y + h >= 462:
                continue
            if edge_fix:
                share = lens_edge_share(labels == j, last_bright)
                if share >= HELD_EDGE_COLUMNS:
                    self.last_edge_excluded.append({'x': int(x), 'y': int(y), 'w': int(w), 'h': int(h), 'area': int(area), 'edge_share': round(share, 3)})
                    continue
            pt = self.projection.project_pixels([[x + w / 2., y + h - 1.]], posture)[0]
            if np.isfinite(pt).all():
                out.append((float(pt[0]), float(pt[1])))
        return out

    def forget_looks(self, keep):
        """Drop what the looks not named in `keep` put into the memory. Used when the own pose turns out to have been
        far off: those points were placed with the wrong pose and stand where nothing is. Returns how many went."""
        gone = 0
        for store, at in ((self.obstacles, 5), (self.walls, 3)):
            for key, q in list(store.items()):
                if q[at] not in keep:
                    del store[key]
                    gone += 1
        return gone

    def rebase(self, phase, old, new):
        """The pose a look was taken from has been corrected (old -> new: x, y, yaw): move what that look put into
        the memory along with it. Without this the points of the look stay where the uncorrected pose put them
        (one run found the door wall 0.26 m in front of the door and no place left to stand)."""
        co, so, cn, sn = math.cos(old['yaw']), math.sin(old['yaw']), math.cos(new['yaw']), math.sin(new['yaw'])

        def move(px, py):
            dx, dy = px - old['x'], py - old['y']
            bx, by = dx * co + dy * so, -dx * so + dy * co
            return new['x'] + cn * bx - sn * by, new['y'] + sn * bx + cn * by
        for store, at in ((self.obstacles, 5), (self.walls, 3)):
            moved = {}
            for key, q in list(store.items()):
                if q[at] != phase:
                    continue
                del store[key]
                mx, my = move(q[0], q[1])
                if at == 5:
                    sx, sy = move(q[3], q[4])
                    moved[(round(mx / .05), round(my / .05))] = (mx, my, q[2], sx, sy, phase)
                else:
                    moved[(round(mx / .05), round(my / .05))] = (mx, my, q[2], phase)
            for key, q in moved.items():
                if key not in store or store[key][2] > q[2]:
                    store[key] = q

    def open_distance(self, jpeg, posture, ignore_below_row=None):
        return open_distance(jpeg, posture, self.projection, ignore_below_row)

    def tall_thing_beyond_door(self):
        """From the latest phase with close looks at the door: where something tall stands behind it, as
        {'beyond_m', 'lateral_m'} (medians over the frames that show it), or None when most frames show nothing."""
        close = [o for o in self.observations if 'tall_thing' in o and o['phase'] != 'look_around']
        close = [o for o in close if o['phase'] == close[-1]['phase']] if close else []
        seen = [o['tall_thing'] for o in close if o['tall_thing'] is not None]
        if not close or len(seen) <= len(close) / 2:
            return None
        return {'beyond_m': float(np.median([t['beyond_m'] for t in seen])),
                'lateral_m': float(np.median([t['lateral_m'] for t in seen])), 'frames': len(seen), 'of': len(close)}

    def door(self, phase=None):
        """Median door of one phase (or of everything): centre, jambs, width, count; None when seen < 3 times."""
        obs = [o for o in self.observations if phase is None or o['phase'] == phase]
        # looks from several stops can hold a wrong gap next to the right one: keep the largest group of
        # observations whose centres lie within 0.4 m of each other
        centres = [(.5 * (o['left'][0] + o['right'][0]), .5 * (o['left'][1] + o['right'][1])) for o in obs]
        groups = [[o for o, c2 in zip(obs, centres) if math.hypot(c[0] - c2[0], c[1] - c2[1]) <= .4] for c in centres]
        obs = max(groups, key=len) if groups else []
        if len(obs) < MIN_OBSERVATIONS:
            return None
        left = np.median(np.array([o['left'] for o in obs]), axis=0)
        right = np.median(np.array([o['right'] for o in obs]), axis=0)
        return {'kind': 'door', 'x': float(.5 * (left[0] + right[0])), 'y': float(.5 * (left[1] + right[1])),
                'left': [float(v) for v in left], 'right': [float(v) for v in right],
                'width_m': float(np.linalg.norm(left - right)), 'observations': len(obs)}

    def record(self):
        phases = sorted({o['phase'] for o in self.observations} | set(self.frames))
        return {'frames': dict(self.frames), 'door': self.door(), 'wall_points': len(self.walls), 'obstacle_points': [[round(v, 3) for v in q[:5]] for q in self.obstacles.values()],
                'zone_frames': dict(self.zone_frames),
                'zones': {c: self.zone(c) for c in sorted({p[0] for p in self.zone_points})},
                'door_by_phase': {p: self.door(p) for p in phases},
                'rule': 'gap in the dark-green wall base with floor beyond; jamb base pixels projected to the floor'}
