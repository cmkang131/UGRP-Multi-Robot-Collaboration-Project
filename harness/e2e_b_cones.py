"""b_marker_detect=cones_v1 (default off): B pose from four lime corner cones (own RGB + fixed map layout).

Cones (b_marker_style=corner_cones_v1) are fixed landmarks in the static map. Per frame:
HSV lime blob -> vertical-shape checks (undistorted aspect, fill, and a 3-D height check from the tip ray
over the base point) -> base pixel undistorted (fisheye K/D) and intersected with the floor plane through the
commanded camera pose (range + bearing; the visible near edge is moved back by the base radius) ->
association by rigid fit (Kabsch) of the detected base points to the map's cone layout in B-local
coordinates -> residual gate. Two cones leave the layout symmetric (4 equivalent poses), so a pose is
accepted only with >=3 consistent cones and a single pose cluster. No live ground truth or simulator state.
"""
import itertools, math
import cv2
import numpy as np

OPTION = 'cones_v1'
ACCEPT_OPTION = 'on_v1'
CFG = dict(hsv_lo=(34, 110, 110), hsv_hi=(52, 255, 255), min_area_px2=20, min_height_px=8,
           min_aspect=.9, fill_range=(.30, .90), height_m=(.20, .42), max_range_m=5.0, base_radius_m=.09,
           edge_clear_px=4, pair_tol_m=.20, max_rms_m=.08, max_point_m=.12, cluster_m=.10, cluster_yaw_deg=8.)


def layout_from_static(static):
    """B-local cone layout (n,2), ids and B half extents from the static map's landmarks (fixed map data)."""
    zone = static['regions']['zone_B']
    c = np.array(zone['center_m'], float)
    cones = [l for l in static.get('landmarks', []) if l.get('kind') == 'cone']
    if len(cones) < 3: raise ValueError('map has no corner cones')
    return dict(ids=[l['id'] for l in cones], local=np.array([l['position_m'] for l in cones], float)-c,
                half=np.array(zone['half_extents_m'], float))


def project_points(xyz_robot, servo, width=640, height=480):
    """Robot-frame 3-D points -> raw fisheye pixels, (uv, ok). Same model as the detector's inverse."""
    from harness.active_camera import goal_camera
    from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix
    origin, axes = goal_camera(servo, 'camera_v3')
    optical = (np.asarray(xyz_robot, float)-origin)@np.asarray(axes).T
    ok = optical[:, 2] > .02
    uv = np.full((len(optical), 2), np.nan)
    if ok.any():
        q, _ = cv2.fisheye.projectPoints(optical[ok].reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                                         np.asarray(scaled_camera_matrix(width, height)), np.asarray(CAMERA_FISHEYE_D))
        uv[ok] = q.reshape(-1, 2)
    return uv, ok & np.isfinite(uv).all(axis=1)


def _rays(px, width, height):
    from harness.e2e_b_quad import undistort_norm
    xy = undistort_norm(px, width, height)
    return np.concatenate([xy, np.ones((len(xy), 1))], axis=1)


def find_cones(rgb, servo, *, cfg=CFG, diagnostics=None):
    """Cone base points (robot frame, m) from one own RGB frame. Returns list of dicts."""
    from harness.active_camera import goal_camera
    from harness.e2e_rgb_gate import lens_valid
    from harness.floor_goal import floor_intersections
    from harness.floor_goal_self_mask import body_envelopes, project_envelopes
    height, width = rgb.shape[:2]
    origin, axes = goal_camera(servo, 'camera_v3')
    self_mask = project_envelopes(body_envelopes(servo, 'camera_v3'), origin, axes, width, height)
    usable = lens_valid(width, height) & ~(cv2.dilate(self_mask.astype(np.uint8), np.ones((7, 7), np.uint8)) != 0)
    k = cfg['edge_clear_px']*2+1
    clear = cv2.erode(usable.astype(np.uint8), np.ones((k, k), np.uint8)) != 0
    clear[:cfg['edge_clear_px']] = clear[-cfg['edge_clear_px']:] = False
    clear[:, :cfg['edge_clear_px']] = clear[:, -cfg['edge_clear_px']:] = False
    mask = cv2.inRange(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), cfg['hsv_lo'], cfg['hsv_hi'])
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    out, rej = [], []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        why = None
        if area < cfg['min_area_px2'] or h < cfg['min_height_px']: why = 'too_small'
        else:
            ys, xs = np.nonzero(labels == i)
            bottom = ys >= ys.max()-2
            if not clear[ys[bottom], xs[bottom]].all() or (self_mask[ys, xs]).any(): why = 'base_clipped_or_body'
            tip_clipped = not clear[ys[ys <= ys.min()+2], xs[ys <= ys.min()+2]].all()
        if why: rej.append(dict(reason=why, area=int(area))); continue
        base_px = np.array([xs[ys >= ys.max()-2].mean(), ys.max()])
        tip_px = np.array([xs[ys <= ys.min()+2].mean(), ys.min()])
        pts, ok = floor_intersections(_rays(base_px[None], width, height), origin, axes, max_range_m=cfg['max_range_m'])
        if not ok[0]: rej.append(dict(reason='base_off_floor_or_far', area=int(area))); continue
        # shape in the undistorted plane: tall, triangle-like fill
        u = _rays(np.stack([xs, ys], 1), width, height)[:, :2]
        extent = u.max(0)-u.min(0)
        aspect = float(extent[1]/max(extent[0], 1e-9))
        fill = float(area/max(w*h, 1))
        if aspect < cfg['min_aspect'] or not (cfg['fill_range'][0] <= fill <= cfg['fill_range'][1]):  # cut tip lowers aspect only a little
            rej.append(dict(reason='not_vertical_cone_shape', aspect=aspect, fill=fill)); continue
        # 3-D height: closest point of the tip ray to the vertical line over the base point
        near = pts[0, :2]
        away = (near-origin[:2])/max(np.linalg.norm(near-origin[:2]), 1e-9)
        base = near+away*cfg['base_radius_m']
        d = np.asarray(axes).T@_rays(tip_px[None], width, height)[0]
        # line: o + t d ; vertical: (bx, by, z). Minimise horizontal miss -> t from horizontal projection.
        dh = d[:2]
        t = float(np.dot(base-origin[:2], dh)/max(np.dot(dh, dh), 1e-12))
        z = float(origin[2]+t*d[2])
        miss = float(np.linalg.norm(origin[:2]+t*dh-base))
        if tip_clipped:  # tip beyond the usable image (top of the lens): height unknown, base still valid
            z = None
        elif not (cfg['height_m'][0] <= z <= cfg['height_m'][1]) or t <= 0:
            rej.append(dict(reason='height_implausible', height_m=z, miss_m=miss)); continue
        out.append(dict(base_robot_m=base.tolist(), range_m=float(np.linalg.norm(base-origin[:2])),
                        bearing_rad=float(math.atan2(base[1]-origin[1], base[0]-origin[0])), height_m=z,
                        aspect=aspect, fill=fill, tip_clipped=bool(tip_clipped), area_px2=int(area), base_px=base_px.tolist()))
    if diagnostics is not None: diagnostics.update(cone_blobs=len(out), cone_rejects=rej)
    return out


def _kabsch(src, dst):
    cs, cd = src.mean(0), dst.mean(0)
    h = (src-cs).T@(dst-cd)
    u, _, vt = np.linalg.svd(h)
    r = vt.T@np.diag([1., np.sign(np.linalg.det(vt.T@u.T))])@u.T
    return r, cd-r@cs


def fit_layout(points, layout, *, cfg=CFG):
    """Associate detected base points to layout cones. Returns (fit | None, reason, info)."""
    points = np.asarray(points, float).reshape(-1, 2)
    local, half = layout['local'], layout['half']
    nl, hyps = len(local), []
    for m in range(min(len(points), nl), 1, -1):
        for subset in itertools.combinations(range(len(points)), m):
            for assign in itertools.permutations(range(nl), m):
                p, l = points[list(subset)], local[list(assign)]
                if any(abs(np.linalg.norm(p[a]-p[b])-np.linalg.norm(l[a]-l[b])) > cfg['pair_tol_m']
                       for a, b in itertools.combinations(range(m), 2)): continue
                r, t = _kabsch(l, p)
                res = np.linalg.norm(l@r.T+t-p, axis=1)
                if math.sqrt(float(np.mean(res**2))) <= cfg['max_rms_m'] and res.max() <= cfg['max_point_m']:
                    yaw = math.atan2(r[1, 0], r[0, 0])
                    hyps.append(dict(m=m, rms=math.sqrt(float(np.mean(res**2))), center=t, yaw=yaw, used=subset, assign=assign))
        if hyps: break  # largest consistent set wins
    if not hyps: return None, 'no_consistent_layout', dict(n_points=len(points))
    clusters = []
    for hyp in sorted(hyps, key=lambda q: q['rms']):
        for c in clusters:  # B is point-symmetric: yaw modulo pi
            dyaw = abs((hyp['yaw']-c['yaw']+math.pi/2) % math.pi-math.pi/2)
            if np.linalg.norm(hyp['center']-c['center']) < cfg['cluster_m'] and dyaw < math.radians(cfg['cluster_yaw_deg']):
                break
        else: clusters.append(hyp)
    info = dict(n_points=len(points), n_used=hyps[0]['m'], clusters=len(clusters))
    if hyps[0]['m'] < 3: return None, 'two_cones_ambiguous', info
    if len(clusters) != 1: return None, 'ambiguous_pose', info
    best = clusters[0]
    c, s = math.cos(best['yaw']), math.sin(best['yaw'])
    corners = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])*half
    return dict(center_robot_m=best['center'].tolist(), yaw_robot_rad=float(best['yaw']), rms_m=best['rms'],
                n_cones=best['m'], half_m=half.tolist(),
                corners_robot_m=(corners@np.array([[c, s], [-s, c]])+best['center']).tolist()), 'accepted', info


def detect_cones(rgb, servo, pose, layout, *, diagnostics=None):
    """Full-B candidate (own-odometry frame via the issued-command pose) or None."""
    from harness.self_odom_grid import transform
    cones = find_cones(rgb, servo, diagnostics=diagnostics)
    fit, reason, info = fit_layout([c['base_robot_m'] for c in cones], layout) if len(cones) >= 2 else (None, 'fewer_than_two_cones', dict(n_points=len(cones)))
    if diagnostics is not None: diagnostics.update(cone_fit_reason=reason, cone_fit=info, cones=cones)
    if fit is None: return None
    polygon = transform(np.asarray(fit['corners_robot_m']), pose)
    return dict(polygon=polygon.tolist(), center=np.mean(polygon, axis=0).tolist(), pixel_polygon=[], complete=True,
                white_markers=0, source=OPTION, n_cones=fit['n_cones'], rms_m=fit['rms_m'],
                center_robot_m=fit['center_robot_m'], yaw_robot_rad=fit['yaw_robot_rad'])
