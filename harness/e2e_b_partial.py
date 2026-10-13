"""b_marker_detect=partial_known_size_v1 (default off): B pose from a lens/border-clipped patch.

Known-geometry planar target on a known floor plane: the B board is a rectangle of
known size (static map) lying on the floor, so its pose is 3 DoF (x, y, yaw) in the
robot frame. Visible *real* edge points (contour points away from the lens circle,
image border and own-body mask) are undistorted (fisheye K/D), intersected with the
floor plane through the commanded camera pose, and a known-size rectangle is fit
to them (coarse grid over x, y, yaw, then robust least squares). Accepted only if:
residual, inlier fraction, identifiability (Gauss-Newton covariance: at least two
non-parallel edges pin x, y and yaw), uniqueness vs the next distinct hypothesis, and
render-and-compare of the rectangle against the patch inside the usable image pass.
No live ground truth; the board size comes from the static map.
"""
import functools, math
import cv2
import numpy as np
from scipy.optimize import least_squares

OPTION = 'partial_known_size_v1'
CFG = dict(min_area_px2=1500, edge_clear_px=6., min_edge_pts=40, max_range_m=4., grid_half_m=1.2, grid_step_m=.06,
           yaw_step_deg=7.5, trunc_m=.06, inlier_m=.04, sigma_m=.02, max_rms_m=.03, min_inlier_fraction=.7,
           max_pos_std_m=.06, max_yaw_std_deg=6., min_second_ratio=1.5, min_iou=.85, max_outside_fraction=.1,
           interior_samples=300)


@functools.lru_cache(maxsize=1)
def board_half_extents():
    """Static-map B board half extents (m). Fixed map data, not an observation."""
    from harness.e2e_b_standoff import load_board
    return tuple(float(v) for v in load_board()['half'])


def rect_sd(points, center, yaw, half):
    """Signed distance (m) from points to a centred rectangle (negative inside)."""
    from harness.e2e_speed5 import ACTIVE
    if ACTIVE.get() != 'off':
        # Broadcasting scalar components avoids an N*2 temporary at each grid pose.
        c, s = math.cos(yaw), math.sin(yaw)
        d = np.asarray(points, float)-center
        ex = np.abs(c*d[...,0]+s*d[...,1])-half[0]
        ey = np.abs(-s*d[...,0]+c*d[...,1])-half[1]
        return np.hypot(np.maximum(ex,0),np.maximum(ey,0))+np.minimum(np.maximum(ex,ey),0)
    c, s = math.cos(yaw), math.sin(yaw)
    d = np.asarray(points, float)-center
    q = np.stack([c*d[..., 0]+s*d[..., 1], -s*d[..., 0]+c*d[..., 1]], axis=-1)
    e = np.abs(q)-np.asarray(half)
    return np.hypot(np.maximum(e[..., 0], 0), np.maximum(e[..., 1], 0))+np.minimum(np.maximum(e[..., 0], e[..., 1]), 0)


def rect_corners(center, yaw, half):
    c, s = math.cos(yaw), math.sin(yaw)
    local = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1]])*np.asarray(half)
    return local@np.array([[c, s], [-s, c]])+center


def _floor_points(px, servo, width, height, max_range):
    from harness.active_camera import goal_camera
    from harness.e2e_b_quad import undistort_norm
    from harness.floor_goal import floor_intersections
    origin, axes = goal_camera(servo, 'camera_v3')
    xy = undistort_norm(px, width, height)
    rays = np.concatenate([xy, np.ones((len(xy), 1))], axis=1)
    pts, ok = floor_intersections(rays, origin, axes, max_range_m=max_range)
    return pts[:, :2], ok, origin, axes


def estimate(contour, servo, usable, board_half=None, *, cfg=CFG):
    """Return (fit dict | None, reason, stats). contour: raw pixels (N,1,2); usable: bool mask (lens & not own body & not border)."""
    height, width = usable.shape
    half = np.asarray(board_half or board_half_extents(), float)
    stats = dict(area_px2=float(cv2.contourArea(contour)))
    if stats['area_px2'] < cfg['min_area_px2']: return None, 'patch_too_small', stats
    from scipy.ndimage import distance_transform_edt
    ok = usable.copy(); ok[:3, :] = ok[-3:, :] = False; ok[:, :3] = ok[:, -3:] = False
    dist = distance_transform_edt(np.pad(ok, 1))[1:-1, 1:-1]
    pts = contour.reshape(-1, 2)
    real = pts[dist[pts[:, 1], pts[:, 0]] >= cfg['edge_clear_px']]
    stats['edge_points_px'] = int(len(real))
    if len(real) < cfg['min_edge_pts']: return None, 'too_few_edge_points', stats
    floor_e, vok, origin, axes = _floor_points(real, servo, width, height, cfg['max_range_m'])
    floor_e = floor_e[vok]
    stats['edge_points_floor'] = int(len(floor_e))
    if len(floor_e) < cfg['min_edge_pts']: return None, 'edge_points_off_floor', stats
    # interior patch samples (inside the usable image) must lie inside the rectangle
    patch = np.zeros((height, width), np.uint8); cv2.drawContours(patch, [contour], -1, 1, -1)
    yy, xx = np.nonzero(patch.astype(bool) & ok)
    rng = np.random.default_rng(0)
    sel = rng.choice(len(yy), min(cfg['interior_samples'], len(yy)), replace=False)
    floor_i, iok, _, _ = _floor_points(np.stack([xx[sel], yy[sel]], 1), servo, width, height, cfg['max_range_m'])
    floor_i = floor_i[iok]
    sub = floor_e[np.linspace(0, len(floor_e)-1, min(80, len(floor_e))).astype(int)]
    # coarse grid x, y, yaw (yaw mod pi: the rectangle is point-symmetric)
    m = floor_e.mean(axis=0); g = np.arange(-cfg['grid_half_m'], cfg['grid_half_m']+1e-9, cfg['grid_step_m'])
    cx, cy = np.meshgrid(m[0]+g, m[1]+g); centers = np.stack([cx.ravel(), cy.ravel()], 1)
    yaws = np.deg2rad(np.arange(0, 180, cfg['yaw_step_deg']))
    t = cfg['trunc_m']; cost = np.empty((len(yaws), len(centers)))
    from harness.e2e_speed5 import ACTIVE, rectangle_grid_cost
    for i, yaw in enumerate(yaws):
        if ACTIVE.get() in ('lean_v2','lean_v3'):
            c=rectangle_grid_cost(sub,centers,yaw,half,t)
            if len(floor_i):c+=rectangle_grid_cost(floor_i,centers,yaw,half,t,interior=True)
            cost[i]=c
            continue
        e = np.minimum(np.abs(rect_sd(sub[None], centers[:, None], yaw, half)), t)**2
        c = e.mean(axis=1)
        if len(floor_i): c = c+(np.minimum(np.maximum(rect_sd(floor_i[None], centers[:, None], yaw, half), 0), t)**2).mean(axis=1)
        cost[i] = c
    k = np.unravel_index(np.argmin(cost), cost.shape); best = cost[k]
    # next distinct hypothesis: centre > .2 m or yaw > 12 deg (mod 180) away
    dyaw = np.abs(((yaws-yaws[k[0]]+np.pi/2) % np.pi)-np.pi/2)
    far = (np.linalg.norm(centers-centers[k[1]], axis=1)[None] > .2) | (dyaw[:, None] > np.deg2rad(12))
    second = float(np.min(np.where(far, cost, np.inf)))
    stats.update(grid_cost=float(best), second_cost=second)
    if second < cfg['min_second_ratio']*max(best, 1e-6): return None, 'ambiguous_pose', stats

    def residual(p):
        r = [rect_sd(floor_e, p[:2], p[2], half)]
        if len(floor_i): r.append(np.maximum(rect_sd(floor_i, p[:2], p[2], half), 0))
        return np.concatenate(r)
    p0 = np.array([*centers[k[1]], yaws[k[0]]])
    sol = least_squares(residual, p0, loss='soft_l1', f_scale=cfg['sigma_m'])
    p = sol.x; sd = rect_sd(floor_e, p[:2], p[2], half)
    inl = np.abs(sd) <= cfg['inlier_m']
    rms = float(np.sqrt(np.mean(sd[inl]**2))) if inl.any() else np.inf
    stats.update(rms_m=rms, inlier_fraction=float(inl.mean()))
    if inl.mean() < cfg['min_inlier_fraction']: return None, 'low_inlier_fraction', stats
    if rms > cfg['max_rms_m']: return None, 'residual_too_large', stats
    # identifiability from the Gauss-Newton Jacobian of the inlier edge residuals
    eps = np.array([1e-3, 1e-3, 1e-3])
    f = lambda q: rect_sd(floor_e[inl], q[:2], q[2], half)
    J = np.stack([(f(p+d)-f(p-d))/2e-3 for d in np.diag(eps)], 1)
    jtj = J.T@J
    if not np.isfinite(jtj).all() or np.linalg.cond(jtj) > 1e7: return None, 'under_constrained', stats
    cov = cfg['sigma_m']**2*np.linalg.inv(jtj)
    if (np.diag(cov) <= 0).any(): return None, 'under_constrained', stats
    pos_std, yaw_std = float(np.sqrt(max(cov[0, 0], cov[1, 1]))), float(math.degrees(math.sqrt(max(cov[2, 2], 0))))
    stats.update(pos_std_m=pos_std, yaw_std_deg=yaw_std)
    if not (np.isfinite(pos_std) and pos_std <= cfg['max_pos_std_m'] and yaw_std <= cfg['max_yaw_std_deg']): return None, 'under_constrained', stats
    # render-and-compare inside the usable image (fisheye-projected rectangle vs patch)
    edge = np.vstack([rect_corners(p[:2], p[2], half)[i]+(rect_corners(p[:2], p[2], half)[(i+1) % 4]-rect_corners(p[:2], p[2], half)[i])*np.linspace(0, 1, 60, endpoint=False)[:, None] for i in range(4)])
    uv, uok = _project_robot(edge, servo, width, height)
    render = np.zeros((height, width), np.uint8)
    if uok.sum() >= 3: cv2.fillPoly(render, [np.rint(uv[uok]).astype(np.int32).reshape(-1, 1, 2)], 1)
    a, b = render.astype(bool) & ok, patch.astype(bool) & ok
    iou = float((a & b).sum()/max((a | b).sum(), 1)); stats['iou'] = iou
    if iou < cfg['min_iou']: return None, 'render_mismatch', stats
    outside = float((rect_sd(floor_i, p[:2], p[2], half) > cfg['inlier_m']).mean()) if len(floor_i) else 0.
    stats['patch_outside_fraction'] = outside
    if outside > cfg['max_outside_fraction']: return None, 'patch_outside_rectangle', stats
    return dict(center_robot_m=p[:2].tolist(), yaw_robot_rad=float(p[2] % math.pi), half_m=half.tolist(),
                corners_robot_m=rect_corners(p[:2], p[2], half).tolist()), 'accepted', stats


def _project_robot(points_robot_xy, servo, width, height):
    """Robot-frame floor points -> raw fisheye pixels (same camera model as the standoff planner)."""
    from harness.active_camera import goal_camera
    from sim.masterpi_camera_profile import CAMERA_FISHEYE_D, scaled_camera_matrix
    origin, axes = goal_camera(servo, 'camera_v3')
    body = np.column_stack([np.asarray(points_robot_xy, float), np.zeros(len(points_robot_xy))])
    optical = (body-origin)@axes.T
    ok = optical[:, 2] > .02
    uv = np.full((len(body), 2), np.nan)
    if ok.any():
        q, _ = cv2.fisheye.projectPoints(optical[ok].reshape(-1, 1, 3), np.zeros(3), np.zeros(3),
                                         np.asarray(scaled_camera_matrix(width, height)), np.asarray(CAMERA_FISHEYE_D))
        uv[ok] = q.reshape(-1, 2)
    ok &= np.isfinite(uv).all(axis=1)
    return uv, ok


def detect_partial(rgb, servo, pose, *, diagnostics=None, board_half=None):
    """b_marker_detect=partial_known_size_v1 on one own RGB frame.

    Same v2 hue mask / self mask as boundary(); every blue patch that the full-quad
    stage cannot accept (lens/border/body clipped) is tried. Returns a list of
    complete=False estimates (own-odometry frame via the issued-command pose). It
    is NOT a full-boundary confirmation: boundary() and ArrivalGate are unchanged
    and never receive these, because remembering a remembered-size hull as the
    full B boundary is what the gate forbids.
    """
    from harness import e2e_b_quad
    from harness.active_camera import goal_camera
    from harness.e2e_rgb_gate import lens_valid
    from harness.floor_goal_self_mask import body_envelopes, project_envelopes
    from harness.self_odom_grid import transform
    height, width = rgb.shape[:2]
    origin, axes = goal_camera(servo, 'camera_v3')
    self_mask = project_envelopes(body_envelopes(servo, 'camera_v3'), origin, axes, width, height)
    blue = e2e_b_quad.floor_blue_mask(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), self_mask)
    usable = lens_valid(width, height) & ~(cv2.dilate(self_mask.astype(np.uint8), np.ones((7, 7), np.uint8)) != 0)
    out = []
    for contour in cv2.findContours(blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        if cv2.contourArea(contour) < CFG['min_area_px2']: continue
        quad, why, _ = e2e_b_quad.fit_quad(contour, lens_valid(width, height))
        if quad is not None:  # a complete quad belongs to the full-boundary stage
            if diagnostics is not None: diagnostics.setdefault('patches', []).append(dict(reason='full_quad_stage'))
            continue
        from harness.e2e_speed5 import ACTIVE
        cfg = dict(CFG,interior_samples=80) if ACTIVE.get() in ('lean_v1','lean_v2','lean_v3') else CFG
        fit, reason, stats = estimate(contour, servo, usable, board_half, cfg=cfg)
        if diagnostics is not None: diagnostics.setdefault('patches', []).append(dict(full_quad_reason=why, reason=reason, **stats))
        if fit is None: continue
        polygon = transform(np.asarray(fit['corners_robot_m']), pose)
        out.append(dict(polygon=polygon.tolist(), center=np.mean(polygon, axis=0).tolist(), complete=False, white_markers=0,
                        estimated_from_partial=True, size_m=[2*v for v in fit['half_m']],
                        center_robot_m=fit['center_robot_m'], yaw_robot_rad=fit['yaw_robot_rad'], stats=stats))
    return out
