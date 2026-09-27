"""Versioned own-camera memory v3; v2 geometry/KF are reused without mutation.

Existence is an exponential-survival Bernoulli filter (independent derivation;
no Persistence-Filter source copied). Repeated or ambiguous frames are not new
evidence. Unknown visibility is never a negative detection.
"""
from __future__ import annotations

import copy
import math

import numpy as np

from harness import owncam_memory as v2
from harness.owncam_memory_kf import associate, kf_update, observation_to_map
from harness.owncam_pose_guard_v3 import CONFIG as POSE_CONFIG
from harness.owncam_pose_guard_v3 import FIX_MAX_AGE_S, FIX_MAX_TRAVEL_M, PoseGuardV3
from harness.owncam_visibility_v3 import absence_visible

SCHEMA = 'ugrp.owncam_memory.v3'
SURVIVAL_HAZARD_S = .005
P_INITIAL = .5
P_MISS_NEAR, P_FALSE_NEAR = .25, .10
P_MISS_FAR, P_FALSE_FAR = .60, .25
P_ABSENT, P_KEEPOUT, P_CONFIRMED = .10, .20, .95
MIN_HIT_INTERVAL_S = .4
TARGET_MAX_AGE_S = 8.
TARGET_MAX_SIGMA_M = .05
VISIBILITY_MAX_SIGMA_M = .08
KEEPOUT_SIGMAS = 2.
PEER_TTL_S = 12.
CONFIG = {k: v for k, v in dict(globals()).items() if k.isupper() and isinstance(v, (int, float, str))}


def existence_update(p, *, detected, p_miss, p_false):
    if not all(math.isfinite(v) for v in (p, p_miss, p_false)) or not 0 <= p <= 1 \
            or not 0 < p_miss < 1 or not 0 < p_false < 1:
        raise ValueError('invalid existence probability')
    a, b = (1 - p_miss, p_false) if detected else (p_miss, 1 - p_false)
    return p*a / (p*a + (1 - p)*b)


class BoxTrackV3(v2.BoxTrack):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.existence_p = P_INITIAL
        self.last_evidence_t = -math.inf
        self.last_near_t = None
        self.last_pose_sigma_m = None
        self.last_detection_sigma_m = None
        self.independent_near_hits = 0
        self.pose_verified = False

    def _maybe_confirm(self, now):
        return False  # v2 constructor hook: confirmation is exclusively probabilistic below

    def predict(self, now):
        dt = max(0., float(now) - self.t)
        super().predict(now)
        if self.state not in ('held', 'placed'):
            self.existence_p *= math.exp(-SURVIVAL_HAZARD_S*dt)
            self._classify(now)

    def _classify(self, now):
        if self.state in ('held', 'placed'):
            return
        if self.existence_p <= P_ABSENT:
            self.state = 'absent'
        elif (self.existence_p >= P_CONFIRMED and self.independent_near_hits >= 2
              and self.pose_verified and self.sigma_m() <= TARGET_MAX_SIGMA_M):
            if self.state != 'claimed':
                self.state = 'confirmed'
            if self.confirmed_t is None:
                self.confirmed_t = float(now)
        elif self.state != 'claimed':
            self.state = 'tentative'

    def evidence(self, now, *, detected, range_class='near', pose_sigma=None, pose_verified=False):
        if now - self.last_evidence_t < MIN_HIT_INTERVAL_S - 1e-9:
            return False
        pm, pf = (P_MISS_NEAR, P_FALSE_NEAR) if range_class == 'near' else (P_MISS_FAR, P_FALSE_FAR)
        self.existence_p = existence_update(self.existence_p, detected=detected, p_miss=pm, p_false=pf)
        self.last_evidence_t = float(now)
        if detected:
            self.misses = 0
            self.pose_verified = bool(pose_verified)
            self.last_pose_sigma_m = float(pose_sigma)
            if range_class == 'near':
                self.last_near_t = float(now)
                self.independent_near_hits += 1
        else:
            self.misses += 1  # audit only; never a state threshold
            self.last_absent_t = float(now)
        self._classify(now)
        return True

    def record(self, now):
        return {**super().record(now), 'existence_p': self.existence_p,
                'last_near_t': self.last_near_t, 'independent_near_hits': self.independent_near_hits,
                'last_pose_sigma_m': self.last_pose_sigma_m, 'pose_verified': self.pose_verified,
                'last_detection_sigma_m': self.last_detection_sigma_m}


class OwnCamMemoryV3(v2.OwnCamMemory):
    def __init__(self, *args, guard=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.guard = guard if guard is not None else PoseGuardV3()
        self.last_frame_id = -1
        self.last_frame_t = None
        self.free_observed_at = np.full(len(self.view.cells), -math.inf)
        self.peer_claims = []
        self.rejected_targets = set()
        self._frame_loaded = False
        self._frame_pose_good = False

    def observe_frame(self, now, *, frame_id, report, **kwargs):
        if not math.isfinite(now) or (self.last_frame_t is not None and now < self.last_frame_t):
            raise ValueError('non-monotonic memory time')
        if frame_id <= self.last_frame_id:
            raise ValueError('duplicate or out-of-order own frame')
        self.last_frame_id, self.last_frame_t = int(frame_id), float(now)
        self.guard.advance(now)
        if report.initialized and (not np.isfinite([report.t_est, report.x_m, report.y_m, report.yaw_rad,
                                                    report.std_xy_m, report.std_yaw_rad]).all()
                                   or not np.isfinite(report.cov).all()
                                   or not -1e-8 <= now - report.t_est <= .25 + 1e-8):
            self.event(now, 'invalid_pose_frame', frame_id=frame_id)
            return {'posture': v2.posture_name(servo=kwargs['servo']), 'settled': False, 'observed': []}
        self.guard.observe_pose(report)
        report = self.guard.effective_report(report, now)
        # Callers supply the effective report; raw PoseReport remains supported.
        # Never confirm boxes without the independent consistency evidence.
        self._frame_pose_good = self.guard.consistent(now)
        self._frame_loaded = bool(kwargs['loaded'])
        previous = self.last_look_fix
        out = super().observe_frame(now, frame_id=frame_id, report=report, **kwargs)
        if self.last_look_fix is not previous:
            if self.guard.consistent(now) and self.last_look_fix is not None:
                self.last_look_fix.update(self.guard.stamp())
            else:
                self.last_look_fix = previous
        # A loaded look may verify only the visible, unoccluded upper image band.
        if report.initialized and kwargs['loaded'] and out['settled'] and out['posture'] in ('look', 'carry'):
            out['boxes'] = self._observe_boxes(now, frame_id, kwargs['image'],
                                              (report.x_m, report.y_m, report.yaw_rad),
                                              np.asarray(report.cov), kwargs['servo'])
        return out

    def look_fix_fresh(self, now, xy):
        self.guard.advance(now)
        f = self.last_look_fix
        return bool(f is not None and 'command_travel_m' in f
                    and -1e-8 <= now - f['t'] <= FIX_MAX_AGE_S + 1e-8
                    and self.guard.travel_since(f) <= FIX_MAX_TRAVEL_M + 1e-9
                    and math.dist(xy, f['xy']) <= FIX_MAX_TRAVEL_M + 1e-9
                    and self.guard.consistent(now))

    def look_fix_since(self, t):
        f = self.last_look_fix
        now = self.t if self.t is not None else float(t)
        return bool(f is not None and f['t'] >= t - 1e-8 and self.guard.consistent(now, since=t))

    def _visible_for_absence(self, tr, pose, cov, servo, rows):
        # All translations/headings in the 2-sigma support must be visible;
        # unknown arm visibility and swept wall/box occlusion defer the miss.
        if not self._frame_pose_good or self._frame_loaded or tr.sigma_m() > VISIBILITY_MAX_SIGMA_M:
            return False
        return absence_visible(self.view, tr, pose, cov, servo, rows,
                               box_half=v2.KEEPOUT_BASE_HALF_M, box_z=v2.BOX_CENTRE_Z_M,
                               max_range=v2.ABSENT_RANGE_M)

    def _observe_boxes(self, now, frame_id, image, pose, cov, servo):
        dets = self._detections(image, servo)
        self.counts['box_frames'] += 1
        self.counts['box_detections'] += len(dets)
        meas, rows = [], []
        for d in dets:
            rx, ry = d['estimated_box_center_base_m'][:2]
            if not np.isfinite([rx, ry]).all() or d['range_class'] not in ('near', 'far_coarse'):
                continue
            bx, by = v2.correct_box_detection((rx, ry), servo, self.params, loaded=self._frame_loaded)
            rng = math.hypot(bx, by)
            a, b = v2.NEAR_SIGMA_M if d['range_class'] == 'near' else v2.FAR_SIGMA_M
            sig = a + b*rng
            z, R = observation_to_map(pose, cov, (bx, by), sig)
            if self._frame_loaded and not self.view.point_in_view(pose, servo, True, (*z, v2.BOX_CENTRE_Z_M)):
                continue  # held cargo and pixels hidden by it are not floor observations
            pose_var = max(float(np.linalg.eigvalsh(R - sig**2*np.eye(2)).max()), 0.)
            meas.append((z, R, pose_var, sig))
            rows.append({'kind': d['kind'], 'range_class': d['range_class'], 'map_xy': z.tolist(),
                         'base_xy': [bx, by], 'raw_base_xy': [rx, ry], 'range_m': rng,
                         'sigma_m': math.sqrt(max(float(np.linalg.eigvalsh(R).max()), 0.))})
        updated, ambiguous_kinds = set(), set()
        for kind in sorted({r['kind'] for r in rows}):
            idx = [i for i, r in enumerate(rows) if r['kind'] == kind]
            cands = [t for t in self.tracks if t.kind == kind and t.state not in ('held', 'placed')]
            decisions = associate([(t.x, t.P) for t in cands], [meas[i][:2] for i in idx])
            for dec in decisions:
                i = idx[dec['measurement']]
                z, R, pose_var, sig = meas[i]
                rows[i]['decision'] = dec['decision']
                if dec['decision'] == 'new':
                    tr = BoxTrackV3(f'{self.robot_id}-v3-box-{self._next_track:03d}', kind, z, R, now,
                                    frame_id, rows[i]['range_class'], pose_var)
                    self._next_track += 1
                    self.tracks.append(tr)
                elif dec['decision'] == 'update':
                    tr = cands[dec['track']]
                    # Correlated far frames must not shrink a coarse obstacle into
                    # a precise point. A real near observation can reduce this floor.
                    if now - tr.last_evidence_t >= MIN_HIT_INTERVAL_S - 1e-9:
                        tr.x, tr.P, _ = kf_update(tr.x, tr.P, z, R)
                    tr.last_seen_t = float(now)
                    tr.frames.append(int(frame_id))
                    tr.near_hits += int(rows[i]['range_class'] == 'near')
                    tr.far_hits += int(rows[i]['range_class'] != 'near')
                else:
                    self.counts['ambiguous_detections'] += 1
                    ambiguous_kinds.add(kind)
                    continue
                old_state = tr.state
                # Current pose uncertainty is a floor, even after an older good fix.
                tr.floor_var = max(v2.TRACK_FLOOR_M**2, pose_var,
                                   sig**2 if rows[i]['range_class'] != 'near' else 0.)
                w, v = np.linalg.eigh(tr.P)
                tr.P = (v*np.maximum(w, tr.floor_var)) @ v.T
                tr.last_detection_sigma_m = sig
                tr.evidence(now, detected=True, range_class=rows[i]['range_class'],
                            pose_sigma=math.sqrt(pose_var), pose_verified=self._frame_pose_good)
                rows[i]['track'] = tr.track_id
                updated.add(tr.track_id)
                if tr.state == 'confirmed' and old_state != 'confirmed':
                    self.event(now, 'track_confirmed', track=tr.record(now))
                if dec['decision'] == 'new':
                    self.event(now, 'track_new', track=tr.record(now), detection=rows[i])
        for tr in self.tracks:
            if tr.track_id in updated or tr.kind in ambiguous_kinds or tr.state in ('held', 'placed'):
                continue
            if self._visible_for_absence(tr, pose, cov, servo, rows):
                old = tr.state
                tr.evidence(now, detected=False)
                if old != 'absent' and tr.state == 'absent':
                    self.event(now, 'track_absent', track=tr.record(now))
        self._observe_floor(now, pose, servo, rows)
        return rows

    def _observe_floor(self, now, pose, servo, rows):
        if not self._frame_pose_good:
            return  # uncertain pose cannot certify free cells
        near, _ = self.view.floor_footprint(pose, servo, self._frame_loaded, max_range=v2.FREE_RANGE_M)
        # Clear only rays not possibly blocked by a remembered or detected box.
        cam = self.view.camera_world(pose, servo)[:2]
        clear = np.ones(len(near), bool)
        rays = self.view.cells[near] - cam
        lengths2 = np.maximum(np.sum(rays*rays, axis=1), 1e-12)
        obstacles = [(t.x, .03 + 2*t.sigma_m()) for t in self.tracks
                     if t.state not in ('held', 'placed', 'absent') and t.existence_p >= P_KEEPOUT]
        obstacles += [(np.asarray(r['map_xy']), .03 + 2*r['sigma_m']) for r in rows]
        for xy, radius in obstacles:
            rel = xy - cam
            f = (rays @ rel)/lengths2
            perp = np.linalg.norm(rel - np.clip(f, 0., 1.)[:, None]*rays, axis=1)
            clear &= ~((f > 0) & (perp <= radius))
        free = near[clear]
        self.log_odds[free] -= .4
        self.free_observed_at[free] = now
        for xy, radius in obstacles:
            occ = np.linalg.norm(self.view.cells - xy, axis=1) <= radius
            self.log_odds[occ] += .4
            self.free_observed_at[occ] = -math.inf
            self.counts['occupied_updates'] += int(occ.sum())
        np.clip(self.log_odds, v2.L_MIN, v2.L_MAX, out=self.log_odds)
        self.counts['free_updates'] += len(free)

    def fresh(self, tr, now):
        tr.predict(now)
        return (tr.last_near_t is not None and 0 <= now - tr.last_near_t <= TARGET_MAX_AGE_S
                and tr.sigma_m() <= TARGET_MAX_SIGMA_M and tr.existence_p >= P_CONFIRMED
                and tr.pose_verified)

    def reverify(self, track_id, now, *, since=None):
        tr = self.track(track_id)
        if tr is None:
            return {'status': 'missing'}
        good = self.fresh(tr, now) and tr.state in ('confirmed', 'claimed')
        if since is not None:
            good = good and tr.last_near_t is not None and tr.last_near_t >= since
        status = 'absent' if tr.existence_p <= P_ABSENT else 'fresh' if good else 'stale'
        row = {'status': status, 'track': tr.record(now)}
        self.event(now, 'reverify', **row)
        return row

    def best_far(self, kind, now, exclude=()):
        self._decay_to(now)
        cands = [t for t in self.tracks if t.kind == kind and t.state == 'tentative'
                 and t.track_id not in exclude and t.track_id not in self.rejected_targets
                 and t.existence_p >= P_KEEPOUT
                 and now - t.last_seen_t <= FIX_MAX_AGE_S and self._in_region(t.x, .5)]
        return min(cands, key=lambda t: t.sigma_m()) if cands else None

    def best_target(self, kind, now, near_xy=None):
        candidates = [t for t in self.tracks if t.kind == kind and t.state in ('confirmed', 'claimed')
                      and t.track_id not in self.rejected_targets and self.fresh(t, now)
                      and self._in_region(t.x, .10)]
        return min(candidates, key=lambda t: (0. if near_xy is None else math.dist(t.x, near_xy),
                                              t.sigma_m())) if candidates else None

    def keepouts(self, exclude=()):
        # No upper radius cap: coarse detections are NOT precise obstacles.
        return [{'id': t.track_id, 'center_m': t.x.tolist(),
                 'half_extents_m': [v2.KEEPOUT_BASE_HALF_M + KEEPOUT_SIGMAS*t.sigma_m()]*2,
                 'source': 'own RGB memory_v3', 'existence_p': t.existence_p}
                for t in self.tracks if t.track_id not in exclude and t.state not in ('held', 'placed')
                and t.existence_p >= P_KEEPOUT]

    def slot_state(self, now, centre_xy, half_xy, exclude=(), *, since=None):
        self._decay_to(now)
        c, h = np.asarray(centre_xy), np.asarray(half_xy)
        occupants = [k for k in self.keepouts(exclude) if np.all(np.abs(np.asarray(k['center_m']) - c)
                                                                       <= h + k['half_extents_m'])]
        cells = np.all(np.abs(self.view.cells - c) <= h, axis=1)
        recent = max(now - TARGET_MAX_AGE_S, since if since is not None else -math.inf)
        free = cells & (self.log_odds <= -v2.L_KNOWN) & (self.free_observed_at >= recent)
        state = 'occupied' if occupants else 'free' if cells.any() and free.sum() == cells.sum() else 'unknown'
        row = {'state': state, 'occupants': occupants, 'cells': int(cells.sum()), 'known_free_cells': int(free.sum())}
        self.event(now, 'slot_check', **row)
        return row

    def remember_peer_claim(self, *, sender, observed_at, received_at, content):
        """Same fields for Korean text / structured content. No automatic translation.

        Opaque received content is for private recall only, never a measurement.
        The reference is exactly (sender, observed_at), not a new observation ID.
        """
        if not isinstance(sender, str) or not sender or sender == self.robot_id:
            raise ValueError('claim needs another sender')
        if not all(math.isfinite(t) and t >= 0 for t in (observed_at, received_at)) or observed_at > received_at:
            raise ValueError('invalid peer observation time')
        if not isinstance(content, (str, dict, list)):
            raise ValueError('claim content must be text or structured message')
        ref = (sender, float(observed_at))
        existing = next((r for r in self.peer_claims if (r['sender'], r['observed_at']) == ref), None)
        if existing is not None:
            return copy.deepcopy(existing)  # replay cannot refresh age or add evidence
        row = {'sender': sender, 'observed_at': float(observed_at), 'received_at': float(received_at),
               'expires_at': float(observed_at) + PEER_TTL_S, 'content': copy.deepcopy(content),
               'status': 'unverified'}
        self.peer_claims.append(row)
        return copy.deepcopy(row)

    def active_peer_claims(self, now):
        return copy.deepcopy([r for r in self.peer_claims if r['observed_at'] <= now < r['expires_at']])

    def snapshot(self, now):
        self._decay_to(now)
        return {**super().snapshot(now), 'schema': SCHEMA, 'config_v3': dict(CONFIG),
                'pose_config_v3': dict(POSE_CONFIG),
                'pose_evidence': copy.deepcopy(self.guard.evidence), 'travel': self.guard.stamp(),
                'rejected_targets': sorted(self.rejected_targets),
                'peer_claims': copy.deepcopy(self.peer_claims)}
