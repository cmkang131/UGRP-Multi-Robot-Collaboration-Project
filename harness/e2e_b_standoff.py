"""boundary_views=standoff_fullquad_v1 (default off): static-map stand-off view for B.

The fixed camera (height/pitch from servo FK, measured fisheye K/D, lens circle,
body self mask) and the static map's B board size are the only inputs. A view
pose is admitted only when the board's whole outline (all four corners, edges
sampled densely and bent by the fisheye model) lies inside the usable image with
a pixel margin, clear of the own-body mask, with slot marks large enough to see,
and the pose is footprint-clear and reachable in the static map.
No live ground truth: map-frame poses are moved to the own frame by the caller.
"""
import json, math
from pathlib import Path
import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt
from harness.active_camera import SEARCH, goal_camera
from harness.public_navigation.costmap import Costmap, HALF
from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix

OPTION = 'standoff_fullquad_v1'
MAP = Path(__file__).resolve().parents[1]/'maps/zones_e2e/zone_wide_door_e2e_b80_v1.json'
W, H = 640, 480
CFG = dict(margin_px=14., min_mark_px=9., res_m=.1, yaw_step_deg=10., max_range_m=4., self_dilate_px=7,
           jitter_xy_m=.05, jitter_yaw_deg=4.)


def load_board(path=MAP, zone='B'):
    d = json.load(open(path))
    r = d['regions'][f'zone_{zone}']
    c, h = np.array(r['center_m'], float), np.array(r['half_extents_m'], float)
    corners = c+np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])*h
    return dict(center=c, half=h, corners=corners, slots=[np.array(s['center_m'], float) for s in d['zone_slots'][zone]],
                slot_half=float(d['zone_slots'][zone][0]['half_extents_m'][0]), map=d)


def project_floor(points_xy, pose, servo=SEARCH):
    """World floor points -> raw fisheye pixels. Returns (uv, ok)."""
    x, y, yaw = pose; c, s = math.cos(yaw), math.sin(yaw)
    d = np.asarray(points_xy, float)-[x, y]
    body = np.column_stack([c*d[:, 0]+s*d[:, 1], -s*d[:, 0]+c*d[:, 1], np.zeros(len(d))])
    origin, axes = goal_camera(servo, 'camera_v3')
    optical = (body-origin)@axes.T
    angle = np.degrees(np.arctan2(np.linalg.norm(optical[:, :2], axis=1), np.maximum(optical[:, 2], 1e-9)))
    ok = (optical[:, 2] > .02) & (angle < 80) & (np.linalg.norm(body-origin, axis=1) <= CFG['max_range_m'])
    uv = np.full((len(d), 2), np.nan)
    if ok.any():
        p, _ = cv2.fisheye.projectPoints(optical[ok].reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                                         np.asarray(scaled_camera_matrix(W, H)), np.asarray(CAMERA_FISHEYE_D))
        uv[ok] = p.reshape(-1, 2)
    return uv, ok


def _usable(servo):
    """Image pixels usable by the detector: inside lens circle and not own body. Fixed per servo."""
    from harness.e2e_rgb_gate import lens_valid
    from harness.floor_goal_self_mask import body_envelopes, project_envelopes
    from harness.active_camera import mask_camera
    origin, axes = mask_camera(servo, 'camera_v3')  # body envelopes stay on the nominal FK frame
    body = project_envelopes(body_envelopes(servo, 'camera_v3'), origin, axes, W, H)
    body = cv2.dilate(body.astype(np.uint8), np.ones((CFG['self_dilate_px'],)*2, np.uint8)) != 0
    valid = lens_valid(W, H)
    return valid, body, distance_transform_edt(np.pad(valid, 1)&~np.pad(body, 1))[1:-1, 1:-1]


_cache = {}
def usable(servo=SEARCH):
    key = tuple(sorted(servo.items()))
    if key not in _cache: _cache[key] = _usable(servo)
    return _cache[key]


def outline(board, n=40):
    c = board['corners']
    return np.vstack([c[i]+(c[(i+1) % 4]-c[i])*np.linspace(0, 1, n, endpoint=False)[:, None] for i in range(4)])


def occluded(camera_xy, points, board_map):
    """Static walls (0.40 m, above the 0.23 m camera) hide the floor behind them: segment vs AABB, slab method."""
    a = np.asarray(camera_xy, float); hit = np.zeros(len(points), bool)
    for o in board_map['obstacles']:
        lo, hi = np.array(o['center_m'])-o['half_extents_m'], np.array(o['center_m'])+o['half_extents_m']
        d = np.asarray(points, float)-a
        with np.errstate(divide='ignore', invalid='ignore'):
            t1, t2 = (lo-a)/d, (hi-a)/d
        parallel_in = (a >= lo) & (a <= hi)  # d == 0 on this axis: whole segment inside the slab, or never inside
        t1 = np.where(d == 0, np.where(parallel_in, -np.inf, np.inf), t1)
        t2 = np.where(d == 0, np.inf, t2)
        tn, tf = np.minimum(t1, t2).max(axis=1), np.maximum(t1, t2).min(axis=1)
        hit |= (tn <= tf) & (tn < 1) & (tf > 0)
    return hit


def sight_clear(pose, board, servo=SEARCH):
    """Corners, edge samples and slot centres (nudged 1 cm inward, as walls may touch the edge) are unoccluded."""
    origin, _ = goal_camera(servo, 'camera_v3'); c, s = math.cos(pose[2]), math.sin(pose[2])
    cam = [pose[0]+c*origin[0]-s*origin[1], pose[1]+s*origin[0]+c*origin[1]]
    pts = np.vstack([board['corners'], outline(board, 8), np.array(board['slots'])])
    pts = board['center']+.99*(pts-board['center'])
    return not occluded(cam, pts, board['map']).any()


def view_check(pose, board, servo=SEARCH, cfg=CFG):
    """Offline projection check from a planned pose. Returns dict(ok, ...)."""
    valid, body, dist = usable(servo)
    if not sight_clear(pose, board, servo): return dict(ok=False, reason='wall_occludes_board', margin_px=-1.)
    uv, ok = project_floor(np.vstack([board['corners'], outline(board)]), pose, servo)
    out = dict(corners_projected=int(ok[:4].sum()), all_outline_projected=bool(ok.all()))
    if not ok.all(): return dict(out, ok=False, reason='outline_not_projectable', margin_px=-1.)
    ij = np.rint(uv).astype(int)
    inside = (ij[:, 0] >= 0) & (ij[:, 0] < W) & (ij[:, 1] >= 0) & (ij[:, 1] < H)
    if not inside.all(): return dict(out, ok=False, reason='outline_off_image', margin_px=-1.)
    margin = float(dist[ij[:, 1], ij[:, 0]].min())
    corner_margin = float(dist[ij[:4, 1], ij[:4, 0]].min())
    region = np.zeros((H, W), np.uint8); cv2.fillPoly(region, [ij[4:].reshape(-1, 1, 2)], 1)
    overlap = int(np.count_nonzero(body & (cv2.dilate(region, np.ones((5, 5), np.uint8)) != 0)))
    # Slot mark size: projected +-slot_half square, smaller side in pixels.
    sh = board['slot_half']; mark = []
    for s in board['slots']:
        q = s+np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])*sh
        quv, qok = project_floor(q, pose, servo)
        mark.append(float(min(np.linalg.norm(quv[0]-quv[1]), np.linalg.norm(quv[1]-quv[2]))) if qok.all() else 0.)
    out.update(margin_px=margin, corner_margin_px=corner_margin, self_mask_overlap_px=overlap, min_mark_px=min(mark),
               board_area_px2=float(region.sum()), corners_px=np.rint(uv[:4]).tolist())
    reason = ('outline_clipped' if margin < cfg['margin_px'] else 'self_mask_clipped' if overlap else
              'marks_too_small' if min(mark) < cfg['min_mark_px'] else 'ok')
    return dict(out, ok=reason == 'ok', reason=reason)


CONE_MAP = Path(__file__).resolve().parents[1]/'maps/zones_e2e/zone_wide_door_e2e_b80_cones_v1.json'
CONE_CFG = dict(margin_px=14., min_range_m=1.5, max_range_m=3.8, min_cones=3, tip_height_m=.30, min_blob_px=8.)


def load_cone_board(path=CONE_MAP, zone='B'):
    """Board dict as load_board plus the corner cones' floor positions (static map `landmarks`, fixed map data)."""
    board = load_board(path, zone)
    cones = [l for l in board['map'].get('landmarks', []) if l.get('kind') == 'cone']
    if len(cones) < 3: raise ValueError('map has no corner cones')
    return dict(board, cones=np.array([l['position_m'] for l in cones], float))


def cone_view_check(pose, board, servo=SEARCH, cfg=CFG, ccfg=CONE_CFG):
    """cones_v1 viewpoint: at least `min_cones` (3: the rigid fit needs >=3) cone BASES inside the usable image with a
    margin, closer than the detector's range, not hidden by static walls, and tall enough in pixels. Uses goal_camera
    (camera_calib applies when on)."""
    valid, body, dist = usable(servo)
    cones = board['cones']; n = len(cones)
    seen = ~occluded(_camera_xy(pose, servo), cones, board['map'])
    uv, ok = project_floor(cones, pose, servo)
    rng = np.linalg.norm(cones-np.asarray(pose[:2]), axis=1)
    seen &= ok & (rng <= ccfg['max_range_m']) & (rng >= ccfg['min_range_m'])  # a cone nearer than ~1.5 m overfills the frame (not blobbed)
    top = _project_points_robot(np.column_stack([cones, np.full(n, ccfg['tip_height_m'])]), pose, servo)
    if top is None: top = np.full((n, 2), np.nan)
    # the detector uses base points; a tip above the lens edge is fine (README: tips are often cut), so only the BASE needs a margin
    finite = np.isfinite(uv).all(axis=1)
    ij = np.where(finite[:, None], np.rint(np.nan_to_num(uv)), -1).astype(int)
    inside = (ij[:, 0] >= 0) & (ij[:, 0] < W) & (ij[:, 1] >= 0) & (ij[:, 1] < H)
    margin = np.full(n, -1.)
    margin[inside] = dist[ij[inside, 1], ij[inside, 0]]
    height_px = np.linalg.norm(np.nan_to_num(uv, nan=1e9)-np.nan_to_num(top, nan=-1e9), axis=1)
    good = seen & (margin >= ccfg['margin_px']) & (height_px >= ccfg['min_blob_px'])
    out = dict(cones_ok=int(good.sum()), cones_seen=int(seen.sum()), margin_px=float(np.sort(margin[good])[:ccfg['min_cones']].min()) if good.sum() >= ccfg['min_cones'] else -1.,
               min_cone_height_px=float(height_px[good].min()) if good.any() else 0., good=good.tolist())
    return dict(out, ok=int(good.sum()) >= ccfg['min_cones'], reason='ok' if good.sum() >= ccfg['min_cones'] else f'only_{int(good.sum())}_cones_visible')


def _camera_xy(pose, servo):
    origin, _ = goal_camera(servo, 'camera_v3'); c, s = math.cos(pose[2]), math.sin(pose[2])
    return [pose[0]+c*origin[0]-s*origin[1], pose[1]+s*origin[0]+c*origin[1]]


def _project_points_robot(points_world_xyz, pose, servo):
    x, y, yaw = pose; c, s = math.cos(yaw), math.sin(yaw)
    d = np.asarray(points_world_xyz, float)-[x, y, 0.]
    body = np.column_stack([c*d[:, 0]+s*d[:, 1], -s*d[:, 0]+c*d[:, 1], d[:, 2]])
    origin, axes = goal_camera(servo, 'camera_v3')
    optical = (body-origin)@axes.T
    if (optical[:, 2] <= .02).any(): return None
    q, _ = cv2.fisheye.projectPoints(optical.reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                                     np.asarray(scaled_camera_matrix(W, H)), np.asarray(CAMERA_FISHEYE_D))
    return q.reshape(-1, 2)


def robust(pose, board, servo=SEARCH, cfg=CFG, view=None):
    """Still admitted under own-pose error (+-jitter xy, +-jitter yaw): corners must stay inside the usable image."""
    j, a = cfg['jitter_xy_m'], math.radians(cfg['jitter_yaw_deg'])
    for dx, dy, dyaw in [(sx*j, sy*j, sa*a) for sx in (-1, 1) for sy in (-1, 1) for sa in (-1, 1)]:
        if not (view or view_check)([pose[0]+dx, pose[1]+dy, pose[2]+dyaw], board, servo, cfg)['ok']: return False
    return True


def static_costmap(board_map, res=.1):
    """Raw static occupancy (walls/obstacles only, 254) in the repo Costmap convention."""
    b = board_map['bounds_m']; x0, x1, y0, y1 = b
    origin = np.array([x0-.2, y0-.2]); shape = (int(math.ceil((y1-y0+.4)/res)), int(math.ceil((x1-x0+.4)/res)))
    raw = np.zeros(shape, np.uint8)
    for o in board_map['obstacles']:
        cx, cy = o['center_m']; hx, hy = o['half_extents_m']
        a = np.floor((np.array([cx-hx, cy-hy])-origin)/res).astype(int); z = np.ceil((np.array([cx+hx, cy+hy])-origin)/res).astype(int)
        raw[max(a[1], 0):z[1], max(a[0], 0):z[0]] = 254
    raw[0, :] = raw[-1, :] = raw[:, 0] = raw[:, -1] = 254
    return Costmap(raw, origin, res)


def reach_lengths(costmap, start_xy):
    """Chamfer-free BFS path length (m, 8-connected) over cells the footprint's inscribed radius clears."""
    s = costmap.world_to_map(start_xy)
    free = costmap.costs < 253
    dist = np.full(free.shape, np.inf)
    if s is None or not free[s[1], s[0]]: return dist
    dist[s[1], s[0]] = 0.; q = [s]
    for x, y in q:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = x+dx, y+dy
                if (dx or dy) and 0 <= nx < free.shape[1] and 0 <= ny < free.shape[0] and free[ny, nx]:
                    nd = dist[y, x]+math.hypot(dx, dy)*costmap.resolution
                    if nd < dist[ny, nx]: dist[ny, nx] = nd; q.append((nx, ny))
    return dist


def plan_standoffs(board=None, start_xy=(.7, -.85), servo=SEARCH, cfg=CFG, top=12, board_map=None, cones=False):
    """Admitted stand-off poses (map frame), best first: all four corners inside the usable image."""
    board = board or (load_cone_board() if cones else load_board())
    check = cone_view_check if cones else view_check
    cm = static_costmap(board['map']); reach = reach_lengths(cm, start_xy)
    res, rng = cfg['res_m'], cfg['max_range_m']
    xs = np.arange(board['center'][0]-rng, board['center'][0]+rng+1e-9, res)
    ys = np.arange(board['center'][1]-rng, board['center'][1]+rng+1e-9, res)
    yaws = np.deg2rad(np.arange(0, 360, cfg['yaw_step_deg']))
    n = dict(positions=0, free=0, reachable=0, footprint_clear=0, poses_tested=0, admitted=0)
    found = []
    for x in xs:
        for y in ys:
            n['positions'] += 1
            cell = cm.world_to_map((x, y))
            if cell is None or cm.costs[cell[1], cell[0]] >= 253: continue
            n['free'] += 1
            if not np.isfinite(reach[cell[1], cell[0]]): continue
            n['reachable'] += 1
            if np.linalg.norm([x, y]-board['center']) > rng: continue
            # only headings that face the board enough to matter (+-60 deg of board bearing)
            bearing = math.atan2(board['center'][1]-y, board['center'][0]-x)
            for yaw in yaws:
                if abs(math.atan2(math.sin(yaw-bearing), math.cos(yaw-bearing))) > math.radians(60): continue
                if not cm.pose_clear([x, y, yaw]): continue
                n['footprint_clear'] += 1; n['poses_tested'] += 1
                v = check([x, y, yaw], board, servo, cfg)
                if v['ok']:
                    n['admitted'] += 1
                    found.append(dict(pose=[float(x), float(y), float(yaw)], margin_px=v['margin_px'], path_m=float(reach[cell[1], cell[0]]),
                                      stand_off_m=float(np.linalg.norm([x, y]-board['center'])), board_area_px2=v.get('board_area_px2', 0.),
                                      min_mark_px=v.get('min_mark_px', 0.), min_cone_height_px=v.get('min_cone_height_px'), bearing_error_deg=float(np.degrees(abs(math.atan2(math.sin(yaw-bearing), math.cos(yaw-bearing)))))))
    # prefer robust framing first (margin capped at 40 px), then short travel
    found.sort(key=lambda v: (-(min(v['margin_px'], 30.)//10), v['path_m']))
    kept = []
    for v in found:
        if len(kept) >= top: break
        n['robust_tested'] = n.get('robust_tested', 0)+1
        if robust(v['pose'], board, servo, cfg, view=check): kept.append(v)
    n['robust_admitted'] = len(kept)
    return kept, n, len(found)
