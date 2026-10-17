"""Own RGB -> observed zone-boundary corners / doors, without map palette.

Reuse frozen PR406 OpenCV floor/door detector and fixed command-camera FK.
Hue candidates cover the entire circular hue space at the existing detector's
tolerance spacing. Neither color-to-zone layout nor a static catalogue enters.
Partial line midpoints are NOT stationary point landmarks.
"""
from functools import lru_cache
from types import SimpleNamespace
import math
import cv2
import numpy as np
from harness.own_map_amcl_vendor import landmarks as lm


def colour_component_pixels(rgb, target_hue):
    """Appearance visibility, not zone identity. Same frozen HSV/300px gate.

    Unlike a boundary detector miss, a large colored interior still counts as
    visible. Evaluator/human review separately rejects a same-color impostor.
    """
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);h,s,v=np.moveaxis(hsv.astype(float),-1,0)
    dh=abs(h-target_hue);dh=np.minimum(dh,180-dh)
    mask=((dh<=lm.PARAMS['hue_tolerance'])&(s>=lm.PARAMS['saturation_min'])&
          (s<=lm.PARAMS['saturation_max'])&(v>=lm.PARAMS['value_min'])).astype(np.uint8)
    n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    return int(sum(stats[j,cv2.CC_STAT_AREA] for j in range(1,n) if stats[j,cv2.CC_STAT_AREA]>=lm.PARAMS['min_component_px']))


def point_covariance(xy):
    # Existing PR406 range/bearing observation sigmas (.2m,3deg), propagated
    # through Cartesian Jacobian. These are inherited assumptions, not a
    # measured uncertainty calibration of this scene/derived corner detector.
    xy = np.asarray(xy); r = np.linalg.norm(xy); a = math.atan2(xy[1], xy[0])
    c, s = math.cos(a), math.sin(a)
    j = np.array([[c, -r*s], [s, r*c]])
    return j @ np.diag([lm.PARAMS['sigma_range_m']**2, lm.PARAMS['sigma_bearing_rad']**2]) @ j.T


def corners(features):
    out = []; reasons = []
    lines = [f for f in features if f['kind'] == 'floor_line']
    for i, a in enumerate(lines):
        for b in lines[i+1:]:
            dh = abs(a['hue']-b['hue']); dh = min(dh, 180-dh)
            if dh > lm.PARAMS['hue_tolerance']:
                reasons.append('different_floor_hue'); continue
            pa, qa = np.asarray(a['endpoints']); pb, qb = np.asarray(b['endpoints'])
            va, vb = qa-pa, qb-pb
            matrix = np.c_[va, -vb]
            # Inherited line-angle resolution, not a new fitted cutoff.
            if abs(np.linalg.det(matrix)) <= np.linalg.norm(va)*np.linalg.norm(vb)*math.sin(lm.PARAMS['sigma_line_angle_rad']):
                reasons.append('parallel_floor_lines'); continue
            u, v = np.linalg.solve(matrix, pb-pa)
            # No extending partial lines to an unobserved corner. Endpoint
            # uncertainty is represented in covariance, not an extrapolation.
            if not (0 <= u <= 1 and 0 <= v <= 1):
                reasons.append('corner_outside_observed_segments'); continue
            xy = pa+u*va
            if np.linalg.norm(xy) == 0:
                reasons.append('point_at_robot_origin'); continue
            hue = math.atan2(math.sin(a['hue']*math.pi/90)+math.sin(b['hue']*math.pi/90),
                             math.cos(a['hue']*math.pi/90)+math.cos(b['hue']*math.pi/90))*90/math.pi % 180
            # Bucket is appearance only, never a zone identity. Width is twice
            # the inherited tolerance so adjacent indistinguishable hues merge.
            bucket = int(round(hue/(2*lm.PARAMS['hue_tolerance']))) % math.ceil(180/(2*lm.PARAMS['hue_tolerance']))
            out.append(dict(id=f'corner-{i}-{len(out)}', kind='zone_corner', signature=f'floor_hue_{bucket}',
                            relative_xy_m=xy.tolist(), covariance_m2=point_covariance(xy).tolist(), hue=hue,
                            pixels=[a['pixels'], b['pixels']]))
    for f in features:
        if f['kind'] != 'door': continue
        xy = np.asarray(f['center'])
        if np.linalg.norm(xy) == 0: continue
        out.append(dict(id=f'door-{len(out)}', kind='door', signature='observed_door',
                        relative_xy_m=xy.tolist(), covariance_m2=point_covariance(xy).tolist(), pixels=f['pixels']))
    return out, reasons


class EgocentricDetector:
    def __init__(self):
        self.palette = SimpleNamespace(hues=list(range(0, 180, lm.PARAMS['hue_tolerance'])))

    @lru_cache(maxsize=16)
    def geometry(self, items):
        from harness.active_wall_vision import modules
        from harness.servo_camera_fk import transform_from_commands, CARRY_OPTION
        from harness.floor_goal_self_mask import body_envelopes, project_envelopes
        from harness.e2e_rgb_vo import K, D
        servo = dict(items); mp = modules()[0]
        value, reason = transform_from_commands(servo, camera_pose=CARRY_OPTION)
        if value is None: raise ValueError(reason)
        origin, rotation = value
        cm = mp.ColumnModel(items, 0., mp.column_positions(96, 2), camera_transform=(origin, rotation))
        yy, xx = np.indices((480, 640))
        _, valid, _ = lm.ground(cm, np.c_[xx.ravel(), yy.ravel()], np.linalg.inv(K))
        mask = project_envelopes(body_envelopes(servo, 'camera_v3'), origin, rotation.T, 640, 480).astype(np.uint8)
        mx, my = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), K, (640, 480), cv2.CV_32FC1)
        mask = cv2.remap(mask, mx, my, cv2.INTER_NEAREST)>0
        return cm, valid.reshape(480, 640) & ~mask

    def observe(self, rgb, servo, scan=None):
        from harness.e2e_rgb_vo import K
        from harness.active_wall_vision import modules
        from harness.opencv_wall_observation_robot_mask import robot_occluded_columns
        cm, clear = self.geometry(tuple(sorted((int(k), int(v)) for k, v in servo.items())))
        mp = modules()[0]
        image = mp.undistort(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        clear = clear & ~robot_occluded_columns(image)[None, :]
        # A downward ray alone does not certify a floor pixel: it may hit a
        # colored wall first. Only columns with an observed wall/floor foot
        # permit floor classification BELOW that foot. Missing stays unknown.
        if scan is None:
            clear = np.zeros_like(clear)
        else:
            columns = np.asarray([r['column'] for r in scan['columns']])
            nearest = np.argmin(abs(np.arange(640)[:,None]-columns), axis=1)
            foot = np.asarray([r['row'] if r['status']=='hit' else np.inf for r in scan['columns']])
            clear = clear & (np.arange(480)[:,None] > foot[nearest][None,:])
        features = lm.floor_features(image, cm, np.linalg.inv(K), self.palette, clear)
        if scan is not None:
            obs = SimpleNamespace(b_lo=np.full(96, np.nan), b_kind=np.zeros(96, int), columns=cm.columns)
            for j, row in enumerate(scan['columns']):
                if row['status'] == 'hit': obs.b_lo[j] = row['row']; obs.b_kind[j] = 1
            features += lm.door_features(image, cm, obs, K, clear)
        points, reasons = corners(features)
        # A partial floor boundary is an ORIENTED LINE, never a fixed midpoint.
        # Keep its unobserved extent explicit. Do not double-count an edge used
        # by a corner in the same frame; line mode is used only without corners.
        if not points:
            for i, f in enumerate(features):
                if f['kind'] != 'floor_line': continue
                normal = np.asarray(f['normal']); phi = math.atan2(normal[1],normal[0])
                rho = float(np.mean(f['endpoints'],axis=0) @ normal)
                bucket = int(round(f['hue']/(2*lm.PARAMS['hue_tolerance']))) % math.ceil(180/(2*lm.PARAMS['hue_tolerance']))
                points.append(dict(id=f'line-{i}',kind='zone_boundary',signature=f'floor_hue_{bucket}',
                    representation='oriented_line',measurement_state=[rho,phi],
                    covariance_m2=np.diag([lm.PARAMS['sigma_line_m']**2,lm.PARAMS['sigma_line_angle_rad']**2]).tolist(),
                    hue=f['hue'],pixels=f['pixels'],observed_endpoints_m=f['endpoints']))
        return points, dict(features=features, rejected_corner_reasons=reasons, points=len(points),
                            category='rgb_landmark_detector', reason='observed_points' if points else 'no_supported_point_landmark',
                            blocked_object='not_observed', minimum_gap_m=None, gap_status='not_measured')
