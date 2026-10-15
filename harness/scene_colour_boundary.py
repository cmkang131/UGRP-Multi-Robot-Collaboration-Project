"""Default-off scene-v5 RGB colour transition, preserving the selfmap scan ABI.

OpenCV cvtColor/inRange-style interval classification; scalar Lab chroma projection
and bottom-up per-column first transition. Adjacent range/bearing support uses the
UNCHANGED height_free_wall linker. No world state, segmentation or map input.
Colour endpoints/intervals come only from a frozen rendered-pixel percentile file.
"""
from __future__ import annotations
import copy
import cv2
import numpy as np

OPTION = 'scene_colour_transition_v1'


class ColourBoundaryState:
    def __init__(self, profile, calibration):
        from sim.scene_contrast_v5 import resolve, profile_record
        self.profile = resolve(profile)
        if (calibration.get('scene_profile') != profile or
                calibration.get('scene_sha256') != profile_record(profile)['sha256'] or
                calibration.get('schema') != 'ugrp.scene_colour_calibration.v2'):
            raise ValueError('SCENE_COLOUR_CALIBRATION_MISMATCH')
        self.calibration = copy.deepcopy(calibration)
        self.last_result = None


def surface_masks(bgr, calibration):
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(float)
    axis = np.asarray(calibration['axis_ab'])
    score = lab[..., 1:] @ axis
    split = float(calibration['split'])
    masks = {}
    for surface in ('floor', 'wall'):
        lo, hi = np.asarray(calibration['lab'][surface]['p00']), np.asarray(calibration['lab'][surface]['p100'])
        masks[surface] = ((lab >= lo) & (lab <= hi)).all(-1)
    if 'wall_hsv' in calibration:
        hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
        bounds=calibration['wall_hsv']
        masks['wall'] &= ((hsv>=bounds['p01']) & (hsv<=bounds['p99'])).all(-1)
    masks['wall'] &= score > split
    masks['floor'] &= score < split
    return masks, score


def detect(hfw, und_bgr, cm, *, params, loaded, state):
    if not isinstance(state, ColourBoundaryState):
        raise ValueError('EXPLICIT_SCENE_COLOUR_STATE_REQUIRED')
    p = {**hfw.PARAMS, **params}
    masks, score = surface_masks(und_bgr, state.calibration)
    cols = np.asarray(cm.columns, int)
    n, k = len(cols), int(p['candidates'])
    scan = {key: np.full((n, k), np.nan) for key in ('vb', 'vt', 'h', 'h_lb', 'c', 's', 'r', 'b')}
    half, window = int(p['strip_half_px']), int(p['window_px'])
    # Reuse the existing RGB orange-column exclusion; all its constants and
    # failure limits are documented at 2026-10-06-owncam-robot-mask, unchanged.
    from harness.opencv_wall_observation_robot_mask import robot_occluded_columns
    robot = robot_occluded_columns(und_bgr)
    top = hfw.self_top_mask(und_bgr, cm, p, loaded)
    strips = hfw.ColumnStrips(und_bgr, cols, half)
    grey=cv2.cvtColor(und_bgr,cv2.COLOR_BGR2GRAY).astype(float)
    reasons = []
    for j, u in enumerate(cols):
        sl = slice(max(0, u-half), min(und_bgr.shape[1], u+half+1))
        # Median over the existing five-pixel strip = majority vote, no new
        # fitted fraction. Use the inherited three-row support window across
        # antialias/JPEG mixtures; unknown objects never become a wall class.
        f = np.median(masks['floor'][:, sl], axis=1).astype(bool)
        w = np.median(masks['wall'][:, sl], axis=1).astype(bool)
        s = np.median(score[:, sl], axis=1) - state.calibration['split']
        y = np.flatnonzero((s[:-1] > 0) & (s[1:] <= 0))
        found = False
        for v in y[::-1]:
            above, below = v-window, v+1+window
            if above < 0 or below >= len(s) or not np.median(w[max(0,v-int(p['band_px'])):above+1]) or not f[below]: continue
            # Linear interpolation of the scalar colour crossing. This is a
            # measured subpixel edge, not a snapped GT boundary or line fill.
            # Brightness is deliberately separated in scene-v5: choose the
            # strongest local luminance step, within the inherited support
            # window. Preserve the legacy integer-row convention (GT scores
            # against half-pixel label edges); no fitted px correction.
            lum=np.median(grey[:,sl],axis=1)
            edges=np.arange(max(0,v-window),min(len(lum)-1,v+window+1))
            row=float(edges[np.argmax(abs(lum[edges+1]-lum[edges]))])
            if row >= top[j]-p['self_margin_px']-1: continue
            ts = cm.t_of_row(np.full(n, row)); t = float(ts[j])
            if not np.isfinite(t): continue
            r, b = hfw.column_range_bearing(cm, j, t)
            if not p['min_range_m'] <= r <= p['max_range_m']: continue
            vt = above
            while vt > 0 and w[vt-1]: vt -= 1
            scan['vb'][j, 0], scan['vt'][j, 0] = row, vt
            scan['r'][j, 0], scan['b'][j, 0] = r, b
            # Keep downstream contrast/std units and geometry unchanged.
            hi = strips.window(np.full((1,n), max(0,v-int(p['band_px'])),int), np.full((1,n),max(1,v-1),int))
            lo = strips.window(np.full((1,n),v+1,int),np.full((1,n),below+1,int))
            scan['c'][j,0] = np.hypot(hi[0][0,j]-lo[0][0,j], hi[1][0,j]-lo[1][0,j])
            scan['s'][j,0] = np.sqrt(hi[2][0,j])
            h = hfw.solve_height(cm, j, t, float(vt))
            if h is not None: scan['h_lb' if vt <= p['top_edge_px'] else 'h'][j,0] = h
            found = True; break
        reasons.append('COLOUR_TRANSITION' if found else 'NO_VISIBLE_WALL_FLOOR_TRANSITION')
    # Deterministic RANSAC, seeded ONLY by columns without orange. Observed
    # transitions through a robot's open gaps may join a background wall line;
    # a robot silhouette cannot seed its own wall. No missing column is filled.
    # Tolerance = v1/native original boundary-error p95 (all encodings:1.5px),
    # frozen raw manifest/source in the calibration, not a new admission slack.
    tol=float(state.calibration['line_residual_px_p95'])
    primary=np.isfinite(scan['vb'][:,0])
    seed=primary & np.array([not robot[max(0,u-half):min(len(robot),u+half+1)].any() for u in cols])
    remaining=primary.copy();supported_line=np.zeros(n,bool);checks=0
    while np.count_nonzero(seed & remaining)>=2:
        ids=np.flatnonzero(seed & remaining);best=None
        for ia,i in enumerate(ids[:-1]):
            for j in ids[ia+1:]:
                slope=(scan['vb'][j,0]-scan['vb'][i,0])/(cols[j]-cols[i])
                residual=abs(scan['vb'][:,0]-(scan['vb'][i,0]+slope*(cols-cols[i])))
                keep=remaining & (residual<=tol);checks+=1
                if best is None or keep.sum()>best.sum():best=keep
        if best is None or best.sum()<p['min_run_columns']:break
        supported_line|=best;remaining[best]=False
    for j in np.flatnonzero(primary & ~supported_line):reasons[j]='NO_UNOCCLUDED_LINE_CONSENSUS'
    for arr in scan.values():arr[~supported_line]=np.nan
    # Local support only; never fill occluded columns or extrapolate a line.
    segments = hfw.link_segments(scan, p)
    supported = np.zeros(n, bool)
    for seg in segments: supported[seg['col_first']:seg['col_last']+1] = True
    for j in np.flatnonzero(np.isfinite(scan['vb'][:,0]) & ~supported): reasons[j] = 'NO_NEIGHBOUR_CONTINUITY'
    for arr in scan.values(): arr[~supported] = np.nan
    state.last_result = {'option':OPTION,'scene_profile':state.profile,'column_reasons':reasons,
                         'work_budget':{'columns':n,'rows_per_column':und_bgr.shape[0],'line_pair_checks':checks},
                         'truth_inputs':0,'interpolated_missing_columns':0}
    return scan
