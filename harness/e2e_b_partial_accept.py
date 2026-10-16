"""Opt-in temporal admission of known-size fits; no complete-edge claim.

Only own RGB fits and issued-command/visual odometry enter this consensus.
Different timestamps alone are insufficient: require a changed viewpoint too.
"""
import copy
import math
import numpy as np

OPTION = 'on_v1'
PARAMS = dict(min_views=2, min_translation_m=.03, min_rotation_deg=3.,
              max_gap_s=5., center_tolerance_m=.08, corner_tolerance_m=.12)


def valid_fit(row):
    from harness.e2e_b_partial import CFG, board_half_extents
    try:
        if row.get('complete') is not False or row.get('estimated_from_partial') is not True:
            return False
        p = np.asarray(row['polygon'], float)
        size = np.asarray(row['size_m'], float)
        center = np.asarray(row['center'], float)
        if p.shape != (4, 2) or size.shape != (2,) or center.shape != (2,): return False
        if not np.isfinite(np.r_[p.ravel(), size, center]).all(): return False
        expected = 2*np.asarray(board_half_extents())
        if not np.allclose(size, expected, atol=.001, rtol=0): return False
        sides = np.linalg.norm(np.roll(p, -1, axis=0)-p, axis=1)
        if not np.allclose(sorted(sides), sorted([*expected, *expected]), atol=.01, rtol=0): return False
        if np.linalg.norm(center-p.mean(axis=0)) > .001: return False
        s = row['stats']
        keys = ('rms_m','inlier_fraction','pos_std_m','yaw_std_deg','iou',
                'patch_outside_fraction','grid_cost','second_cost')
        if not all(math.isfinite(s[k]) and s[k] >= 0 for k in keys): return False
        return (s['rms_m'] <= CFG['max_rms_m'] and
                CFG['min_inlier_fraction'] <= s['inlier_fraction'] <= 1 and
                s['pos_std_m'] <= CFG['max_pos_std_m'] and
                s['yaw_std_deg'] <= CFG['max_yaw_std_deg'] and
                CFG['min_iou'] <= s['iou'] <= 1 and
                s['patch_outside_fraction'] <= CFG['max_outside_fraction'] and
                s['second_cost'] >= CFG['min_second_ratio']*max(s['grid_cost'], 1e-6))
    except (KeyError, ValueError, TypeError):
        return False


def usable(row, option='off'):
    return bool(row and (row.get('complete') is True or
                (option == OPTION and row.get('partial_consensus') == OPTION and valid_fit(row))))


class Consensus:
    def __init__(self):
        self.rows = []
        self.last = dict(accepted=False, reason='two_viewpoints_required')

    def observe(self, candidates, ref, pose):
        if len(candidates) != 1 or not valid_fit(candidates[0]):
            self.rows.clear()
            self.last = dict(accepted=False, reason='ambiguous_or_invalid_fit')
            return None
        row = candidates[0]
        if self.rows:
            prev = self.rows[-1]
            if ref['frame_id'] <= prev['ref']['frame_id'] or ref['t_sim'] <= prev['ref']['t_sim']:
                self.last = dict(accepted=False, reason='fresh_frame_required')
                return None
            def consistent(old):
                a, b = np.asarray(old['fit']['polygon']), np.asarray(row['polygon'])
                distances = np.linalg.norm(a[:, None]-b[None, :], axis=2)
                return (math.dist(old['fit']['center'], row['center']) <= PARAMS['center_tolerance_m'] and
                        max(distances.min(axis=0).max(), distances.min(axis=1).max()) <= PARAMS['corner_tolerance_m'])
            if ref['t_sim']-prev['ref']['t_sim'] > PARAMS['max_gap_s'] or not all(consistent(r) for r in self.rows):
                self.rows.clear()
        current = dict(ref=copy.deepcopy(ref), pose=list(pose), fit=copy.deepcopy(row))
        diverse = []
        for old in self.rows:
            yaw = abs(math.atan2(math.sin(pose[2]-old['pose'][2]), math.cos(pose[2]-old['pose'][2])))
            if (math.dist(pose[:2], old['pose'][:2]) >= PARAMS['min_translation_m'] or
                    yaw >= math.radians(PARAMS['min_rotation_deg'])):
                diverse.append(old)
        self.rows.append(current)
        self.rows = [r for r in self.rows if ref['t_sim']-r['ref']['t_sim'] <= PARAMS['max_gap_s']][-32:]
        self.last = dict(accepted=bool(diverse), reason='verified' if diverse else 'two_viewpoints_required',
                         consistent_frames=len(self.rows), distinct_views=2 if diverse else 1)
        if not diverse: return None
        return dict(copy.deepcopy(row), partial_consensus=OPTION,
                    evidence_refs=[copy.deepcopy(diverse[-1]['ref']), copy.deepcopy(ref)],
                    acceptance=copy.deepcopy(self.last))
