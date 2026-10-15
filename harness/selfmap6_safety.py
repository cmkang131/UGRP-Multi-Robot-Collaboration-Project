"""Opt-in pre-mutation SE(2) admission and bounded revision rollback policy.

Only own visual correspondences, issued motion and authored map geometry enter.
NIS <= 9 is an ellipsoidal 3-sigma-radius gate (not 99.73% in 3 DOF).
"""
import math
import numpy as np

from harness.natural_floor_slam import compose, wrap
from harness.selfmap4_geometry import inverse
from harness.selfmap5_revision import revision_test
from harness.natural_floor_slam import NaturalFloorSLAM
from harness.self_map_bootstrap import PriorBootstrapSLAM

OPTION = 'selfmap6_correction_safety_v1'
QUARANTINE_DEADLINE_S = 10.
CONFIRMATION_WINDOW_S = 5.


class PreMutationGate:
    """Interpose at the fit seam; preserve the pinned natural-floor core bytes."""
    def guarded_step(self, observation, *, command_delta, command_covariance,
                     correction_gate, pose_override=None):
        self._admit, self._override, self._admission = correction_gate, pose_override, None
        try:
            if getattr(self, 'reloc15_pose_handoff', False) and pose_override is not None and not self.landmarks:
                # NaturalFloorSLAM's empty-bank branch never calls _fit. Map
                # observations must still reach execution when ORB has no bank.
                from harness.natural_floor_slam import _motion_covariance
                prior=compose(self.pose,command_delta)
                decision=correction_gate(prior,pose_override[0],self._gate_prediction,
                    dict(covariance=pose_override[1],matched=[]))
                self._admission=decision
                event=self.step(observation,command_delta=command_delta,command_covariance=command_covariance)
                if decision['accepted']:
                    self.pose=np.asarray(pose_override[0]).copy();self.covariance=np.asarray(pose_override[1]).copy()
                    event.update(status='visual_relocalized',reason='visual_relocalized',
                        pose=self.pose.tolist(),covariance=self.covariance.tolist())
                    self.trajectory[-1].update(pose=event['pose'],covariance=event['covariance'],source=event['status'])
            else:
                event = self.step(observation, command_delta=command_delta, command_covariance=command_covariance)
            if self._admission is not None:
                event['correction_gate'] = self._admission
            return event
        finally:
            self._admit = None; self._override = None

    def _fit(self, points, descriptors, prior, frame_id):
        if getattr(self, '_override', None) is None and getattr(self, 'reloc14_pf_tracking', False):
            # The prior-seeded ORB bank shares its old pose bias. Known-mode PF
            # tracking supplies map corrections; LOST invokes global R7 recovery.
            return None, [], dict(matches=0,inliers=0,fit_rms_m=None,spread_m=None,reason='pf_tracking_or_relocalization')
        if getattr(self, '_override', None) is None:
            pose, pairs, detail = super()._fit(points, descriptors, prior, frame_id)
        else:
            pose, covariance = self._override
            pairs, detail = [], dict(covariance=covariance, matched=[], matches=0, inliers=0,
                fit_rms_m=None, spread_m=None, reason='visual_relocalized')
        if pose is not None and getattr(self, '_admit', None) is not None:
            # Prior and covariance must refer to the same prediction. The latter
            # was computed before entering the frozen step implementation.
            self._admission = self._admit(prior, pose, self._gate_prediction, detail)
            if not self._admission['accepted']:
                return None, pairs, dict(detail, reason='pose_correction_rejected')
        return pose, pairs, detail

    def _add_landmarks(self, *args, **kwargs):
        if getattr(self, '_override', None) is not None:
            return 0
        return super()._add_landmarks(*args, **kwargs)


class GatedFloorSLAM(PreMutationGate, NaturalFloorSLAM):
    pass


class GatedPriorSLAM(PreMutationGate, PriorBootstrapSLAM):
    pass


class CorrectionGate:
    """Keep competing left-SE(2) corrections outside the live landmark bank.

    Three consecutive confirmations require fresh frames, >=0.5 s spacing,
    >=10 deg optical bearing or 0.1 m baseline, and disjoint matched map IDs.
    These are conservative evidence proxies, not a claim of statistical IID.
    """
    def __init__(self):
        self.hypotheses = []
        self.last = None

    def consider(self, prior, candidate, predicted, measured, *, t, frame_id,
                 source, view, evidence_ids=()):
        detail = revision_test(prior, candidate, predicted, measurement_covariance=measured)
        detail.update(source=source, accepted=False, confirmations=0,
                      nis=None if detail['mahalanobis'] is None else detail['mahalanobis']**2,
                      chi2_threshold=9., confirmed_outlier=False,
                      evidence_ids=sorted(str(k) for k in evidence_ids), view=np.asarray(view).tolist(),
                      measurement_covariance=np.asarray(measured).tolist())
        if not detail['required']:
            self.hypotheses.clear()
            detail.update(accepted=True, reason='within_innovation_gate')
        else:
            self.hypotheses = [h for h in self.hypotheses if t-h['started'] <= CONFIRMATION_WINDOW_S]
            correction = compose(candidate, inverse(prior))
            ids, view = set(evidence_ids), np.asarray(view)
            same = [h for h in self.hypotheses
                    if np.linalg.norm(h['correction'][:2]-correction[:2]) <= .05
                    and abs(wrap(h['correction'][2]-correction[2])) <= math.radians(5)]
            if not same:
                # Bounded memory; overflow remains ambiguous, never prunes to a winner.
                if len(self.hypotheses) >= 8:
                    detail['reason'] = 'hypothesis_capacity_rejected'
                    self.last = detail
                    return detail
                for h in self.hypotheses:
                    h['count'] = 0  # a competing observation breaks consecutiveness
                h = dict(correction=correction, ids=set(), views=[], frame=-1,
                         last_t=float(t), started=float(t), confirmed_t=-math.inf, count=0)
                self.hypotheses.append(h)
            else:
                h = same[0]
            independent = (ids and not ids.intersection(h['ids']) and frame_id > h['frame']
                and t-h['confirmed_t'] >= .5 and all(
                    np.linalg.norm(view[:2]-v[:2]) >= .1 or abs(wrap(view[2]-v[2])) >= math.radians(10)
                    for v in h['views']))
            if independent:
                h['count'] += 1; h['ids'].update(ids); h['views'].append(view.copy())
                h['frame'] = frame_id; h['confirmed_t'] = float(t)
            h['last_t'] = float(t)
            unique = len(self.hypotheses) == 1
            accept = unique and h['count'] >= 3
            detail.update(accepted=accept, confirmations=h['count'],
                          hypothesis_count=len(self.hypotheses), confirmed_outlier=accept,
                          reason='independent_confirmations' if accept else
                                 'competing_hypotheses' if not unique else 'outlier_pending')
            if accept:
                self.hypotheses.clear()
        self.last = detail
        return detail


def release_due(started, t, failed_attempts):
    return failed_attempts >= 2 or t-started >= QUARANTINE_DEADLINE_S


def registration_hypotheses(evidence, edges, own_pose, covariance):
    """Enumerate global directed-line pair alignments, even if PF lost a mode.

    Both pair constraints determine yaw/translation. Every buffered line must
    agree in hue, directed normal and finite endpoint extent. Stop at two
    separated solutions: enough to reject repeated/symmetric rooms. No PF
    mass, GT, or previously collapsed covariance can remove an alternative.
    """
    lines = []
    for frame in evidence.frames:
        relative = compose(inverse(own_pose), frame['pose'])
        c, s = math.cos(relative[2]), math.sin(relative[2])
        R = np.array([[c, -s], [s, c]])
        for line in frame['lines']:
            lines.append(dict(hue=line['hue'], endpoints=np.asarray(line['endpoints'])@R.T+relative[:2],
                              normal=np.asarray(line['normal'])@R.T))
    if len(lines) < 2:
        return dict(candidate_count=0, unique=False, candidates=[], search_complete=True)
    first = lines[0]
    second = max(lines, key=lambda l: abs(np.linalg.det([first['normal'], l['normal']])))
    if abs(np.linalg.det([first['normal'], second['normal']])) < .5:
        return dict(candidate_count=0, unique=False, candidates=[], search_complete=True)
    def hue_ok(a, b):
        d = abs(a-b)
        return min(d, 180-d) <= 12
    def bearing(n):
        return math.atan2(n[1], n[0])
    angle_tol = 3*math.sqrt(covariance[2, 2]+(math.radians(5)/3)**2)
    candidates = []
    for e1 in edges:
        if not hue_ok(e1['hue'], first['hue']):
            continue
        yaw = wrap(bearing(e1['normal'])-bearing(first['normal']))
        c, s = math.cos(yaw), math.sin(yaw); R = np.array([[c, -s], [s, c]])
        for e2 in edges:
            if not hue_ok(e2['hue'], second['hue']) or abs(wrap(
                    bearing(e2['normal'])-bearing(second['normal'])-yaw)) > angle_tol:
                continue
            A = np.asarray([e1['normal'], e2['normal']])
            if abs(np.linalg.det(A)) < .5:
                continue
            b = [np.asarray(e['normal'])@(np.asarray(e['a'])-R@np.mean(l['endpoints'], axis=0))
                 for e, l in [(e1, first), (e2, second)]]
            pose = np.r_[np.linalg.solve(A, b), yaw]
            if any(np.linalg.norm(pose[:2]-p[:2]) < .15 and abs(wrap(pose[2]-p[2])) < math.radians(10)
                   for p in candidates):
                continue
            valid = True
            for line in lines:
                ends = line['endpoints']@R.T+pose[:2]
                fits = False
                for edge in edges:
                    if not hue_ok(edge['hue'], line['hue']) or abs(wrap(
                            bearing(edge['normal'])-bearing(line['normal'])-yaw)) > angle_tol:
                        continue
                    a, b = np.asarray(edge['a']), np.asarray(edge['b']); v = b-a
                    residual = ends-a-np.clip((ends-a)@v/(v@v), 0, 1)[:, None]*v
                    nis = []
                    for p, error in zip(ends, residual):
                        dx, dy = p-pose[:2]
                        J = np.array([[1., 0., -dy], [0., 1., dx]])
                        S = J@covariance@J.T+np.eye(2)*(.05/3)**2
                        nis.append(float(error@np.linalg.solve(S, error)))
                    if max(nis) <= 9.:
                        fits = True; break
                if not fits:
                    valid = False; break
            if valid:
                candidates.append(pose)
                if len(candidates) == 2:
                    return dict(candidate_count=2, unique=False, candidates=[p.tolist() for p in candidates],
                                search_complete=False, reason='multiple_geometric_modes')
    return dict(candidate_count=len(candidates), unique=len(candidates) == 1,
                candidates=[p.tolist() for p in candidates], search_complete=True)
