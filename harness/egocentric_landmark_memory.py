"""Opt-in, bounded robocentric point memory; no world pose or map input.

Castellanos et al. RAS 2007, sec.4 eqs.11--16: augment independent
increment, update in the old frame, THEN compose with its inverse. Keep
the full covariance, including shared motion error between landmarks.
The preserved legacy candidate uses that update order. Opt-in rovio_local_v1
instead predicts relative features before the image update and directly calls
ROVIO FeatureStatistics for retention; see the experiment survey/deviations.
"""
from dataclasses import dataclass
import math
import numpy as np

OPTION = 'egocentric_landmark_memory_v1'
# chi-square(2), .99: same .99 probability as existing RGB VO gate, 2D point.
CHI2_99 = 9.210340371976184
CHI2_95 = 5.991464547107979


def rotation(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


def relative(point, delta):
    return rotation(-delta[2]) @ (np.asarray(point)-delta[:2])


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def observation_model(x, index, representation='point'):
    """Cartesian observation of old-frame point from uncertain current frame."""
    if representation == 'oriented_line':
        rho, phi = x[2*index:2*index+2]; dx, dy, theta = x[-3:]
        c, s = math.cos(phi), math.sin(phi)
        z = np.array([rho-c*dx-s*dy, wrap(phi-theta)])
        h = np.zeros((2, len(x)))
        h[:, 2*index:2*index+2] = [[1., s*dx-c*dy], [0., 1.]]
        h[:, -3:] = [[-c, -s, 0.], [0., 0., -1.]]
        return z, h
    z = relative(x[2*index:2*index+2], x[-3:])
    r = rotation(-x[-1]); h = np.zeros((2, len(x)))
    h[:, 2*index:2*index+2] = r
    h[:, -3:-1] = -r
    h[:, -1] = [z[1], -z[0]]
    return z, h


def covariance(value, n, *, positive=False):
    p = np.asarray(value, float)
    if p.shape != (n, n) or not np.isfinite(p).all() or not np.allclose(p, p.T):
        raise ValueError('INVALID_COVARIANCE')
    e = np.linalg.eigvalsh(p)
    if e.min() < -np.finfo(float).eps*n*max(1., float(np.linalg.norm(p))) or (positive and e.min() <= 0):
        raise ValueError('INVALID_COVARIANCE')
    return p


@dataclass(frozen=True)
class MemoryOptions:
    # Resource budget, not a physical acceptance threshold. Candidate explicitly
    # selects 32 slots: at most 64 point variables + 3 increment variables.
    implementation: str = 'legacy_v1'
    statistics_library: str | None = None
    max_landmarks: int = 32
    # Existing RGB landmark detector's measurable range, not GT-fitted tolerance.
    sensor_range_m: float = 6.
    # Optional empirically measured revisit-gap P95; no invented time cutoff.
    fade_tau_s: float | None = None


class LandmarkMemory:
    def __init__(self, *, option='off', options=None):
        if option not in ('off', OPTION):
            raise ValueError('UNKNOWN_EGOCENTRIC_MEMORY')
        self.enabled = option == OPTION
        self.options = options or MemoryOptions()
        if self.options.max_landmarks < 1 or self.options.sensor_range_m <= 0:
            raise ValueError('INVALID_MEMORY_BUDGET')
        if self.options.fade_tau_s is not None and self.options.fade_tau_s <= 0:
            raise ValueError('INVALID_FADE_TIME')
        from harness.rovio_feature_statistics import RovioLibrary, PROFILE
        if self.options.implementation not in ('legacy_v1', PROFILE):
            raise ValueError('UNKNOWN_MEMORY_IMPLEMENTATION')
        self.rovio = self.options.implementation == PROFILE
        self.statistics = {}
        self.library = None
        if self.enabled and self.rovio:
            if self.options.fade_tau_s is not None:
                raise ValueError('ROVIO_POLICY_REPLACES_CUSTOM_FADE')
            if not self.options.statistics_library:
                raise ValueError('EXPLICIT_ROVIO_LIBRARY_REQUIRED')
            self.library = RovioLibrary(self.options.statistics_library)
        self.x = np.empty(0); self.p = np.empty((0, 0))
        self.items = []; self.sequence = 0; self.t = None

    def snapshot(self, t):
        result = []
        for i, meta in enumerate(self.items):
            state = self.x[2*i:2*i+2]; p = self.p[2*i:2*i+2, 2*i:2*i+2]
            if meta['representation'] == 'oriented_line':
                rho, phi = state; c, s = math.cos(phi), math.sin(phi)
                xy = rho*np.array([c,s]); j = np.array([[c,-rho*s],[s,rho*c]])
                cartesian_p = j @ p @ j.T
            else:
                xy = state; cartesian_p = p
            sigma = math.sqrt(max(0., float(np.linalg.eigvalsh(cartesian_p).max())))
            age = t-meta['last_seen_s']; tau = self.options.fade_tau_s
            result.append({**meta, 'relative_xy_m': xy.tolist(), 'range_m': float(np.linalg.norm(xy)),
                           'bearing_rad': math.atan2(xy[1], xy[0]), 'covariance_m2': cartesian_p.tolist(),
                           'measurement_covariance': p.tolist(),
                           'radius95_m': math.sqrt(CHI2_95)*sigma, 'age_s': age,
                           'measurement_state': state.tolist(),
                           'extent_unknown': meta['representation'] == 'oriented_line',
                           'retention_policy': self.options.implementation,
                           'tracking_statistics': self.statistics[meta['id']].values() if self.rovio else None,
                           'freshness': (self.statistics[meta['id']].values()['local_quality']*self.statistics[meta['id']].values()['local_visibility']
                                         if self.rovio else math.exp(-age/tau) if tau is not None else None)})
        return result

    def step(self, t, delta, motion_covariance, observations=(), *, observation_tick=True):
        if not self.enabled:
            return dict(status='off', memories=[], events=[], self_pose=[0., 0., 0.])
        if not math.isfinite(t) or (self.t is not None and t <= self.t):
            raise ValueError('NONCAUSAL_MEMORY_TIME')
        delta = np.asarray(delta, float)
        if delta.shape != (3,) or not np.isfinite(delta).all():
            raise ValueError('INVALID_OWN_INCREMENT')
        q = covariance(motion_covariance, 3)
        # eq.12: no global/world reference in this state.
        n = len(self.x); x = np.r_[self.x, delta]
        p = np.zeros((n+3, n+3)); p[:n, :n] = self.p; p[n:, n:] = q
        if self.rovio:
            # ROVIO ImuPrediction -> ImgUpdate order. Finite SE(2) inverse
            # transport is the planar Cartesian restriction of its robocentric
            # bearing/depth motion; retain common-motion cross covariance.
            y = []; jac = np.zeros((n, n+3))
            for i, item in enumerate(self.items):
                z, h = observation_model(x, i, item['representation'])
                y.extend(z); jac[2*i:2*i+2] = h
            x = np.asarray(y); p = jac @ p @ jac.T
        if self.rovio and observations and not observation_tick:
            raise ValueError('OBSERVATIONS_REQUIRE_OBSERVATION_TICK')
        events = []; pending = []; used = set()
        for obs in observations:
            allowed = {'id','kind','signature','relative_xy_m','measurement_state','covariance_m2',
                       'representation','hue','pixels','observed_endpoints_m'}
            if set(obs)-allowed:
                raise ValueError('UNEXPECTED_OBSERVATION_FIELDS')
            representation = obs.get('representation', 'point')
            z = np.asarray(obs.get('measurement_state', obs.get('relative_xy_m')), float)
            if z.shape != (2,) or not np.isfinite(z).all():
                raise ValueError('INVALID_RELATIVE_OBSERVATION')
            r = covariance(obs['covariance_m2'], 2, positive=True)
            # The same frame cannot vote for one landmark twice. Multiple
            # in-gate same-kind candidates are ambiguous; never pick by truth.
            matches = []; checked = 0; nearest_d2 = None
            for i, item in enumerate(self.items):
                if item['kind'] != obs['kind'] or item['signature'] != obs['signature'] or item['representation'] != representation:
                    continue
                if self.rovio:
                    predicted = x[2*i:2*i+2].copy()
                    h = np.zeros((2, n)); h[:,2*i:2*i+2] = np.eye(2)
                else:
                    predicted, h = observation_model(x, i, representation)
                s = h @ p @ h.T+r; innovation = z-predicted
                if representation == 'oriented_line': innovation[1] = wrap(innovation[1])
                d2 = float(innovation @ np.linalg.solve(s, innovation))
                checked += 1; nearest_d2 = d2 if nearest_d2 is None else min(nearest_d2,d2)
                if d2 <= CHI2_99:
                    matches.append((i, d2, predicted, h, s, innovation))
            if len(matches) > 1:
                events.append(self.event('association_ambiguous', observation=obs['id'], candidates=len(matches)))
                continue
            if not matches:
                if checked:
                    events.append(self.event('association_gate_rejected',observation=obs['id'],
                                             candidates_checked=checked,nearest_mahalanobis2=nearest_d2))
                pending.append(obs)
                continue
            i, d2, predicted, h, s, innovation = matches[0]
            if i in used:
                events.append(self.event('duplicate_frame_observation', observation=obs['id']))
                continue
            used.add(i)
            before = predicted.tolist()
            k = np.linalg.solve(s, h @ p).T
            x = x+k @ innovation
            a = np.eye(len(x))-k @ h
            p = a @ p @ a.T+k @ r @ k.T  # Joseph form, standard EKF eq.6.
            item = self.items[i]
            updated = x[2*i:2*i+2].tolist() if self.rovio else observation_model(x, i, representation)[0].tolist()
            events.append(self.event('reobserved', observation=obs['id'], memory_id=item['id'],
                                     gap_s=t-item['last_seen_s'], mahalanobis2=d2,
                                     representation=representation,
                                     predicted_state=before, updated_state=updated))
            item['last_seen_s'] = t; item['observations'] += 1
            if 'hue' in obs:item['appearance_hue']=obs['hue']
        if self.rovio:
            self.x = x; self.p = (p+p.T)/2
            for i, item in enumerate(self.items):
                if item['representation'] == 'oriented_line':
                    self.x[2*i+1] = wrap(self.x[2*i+1])
            if observation_tick:
                for i, item in enumerate(self.items):
                    self.statistics[item['id']].observe(t, i in used)
                # ImgUpdate.hpp: remove bad features, then enforce the same
                # tracked+free reserve using factors 1.1, 1.1^2, ... .
                keep = []
                for i, item in enumerate(self.items):
                    if self.statistics[item['id']].good():
                        keep.append(i)
                    else:
                        events.append(self.event('rovio_quality_removed', memory_id=item['id'],
                                                 statistics=self.statistics[item['id']].values()))
                self._retain(keep)
                params = self.library.parameters
                tracked = {e['memory_id'] for e in events if e['reason']=='reobserved'}
                required_free = int(self.options.max_landmarks*params['minTrackedAndFreeFeatures']-len(tracked))
                factor = params['removalFactor']
                while self.options.max_landmarks-len(self.items) < required_free:
                    keep = []
                    for i, item in enumerate(self.items):
                        if item['id'] not in tracked and not self.statistics[item['id']].good(factor):
                            events.append(self.event('rovio_reserve_removed', memory_id=item['id'], factor=factor))
                        else:
                            keep.append(i)
                        # Match upstream early termination after enough free slots.
                        if self.options.max_landmarks-(len(self.items)-(i+1-len(keep))) >= required_free:
                            keep.extend(range(i+1,len(self.items))); break
                    self._retain(keep)
                    factor *= params['removalFactor']
        else:
            # Preserved Castellanos old-frame update -> inverse composition.
            y = []; jac = np.zeros((n, n+3))
            for i in range(len(self.items)):
                z, h = observation_model(x, i, self.items[i]['representation']); y.extend(z); jac[2*i:2*i+2] = h
            self.x = np.asarray(y); self.p = jac @ p @ jac.T
            self.p = (self.p+self.p.T)/2
            prior = self.snapshot(t)
            keep = [i for i, item in enumerate(prior) if item['radius95_m'] <= self.options.sensor_range_m]
            for i, item in enumerate(prior):
                if i not in keep:
                    events.append(self.event('uncertainty_exceeds_sensor_range', memory_id=item['id']))
            self._retain(keep)
        for obs in pending:
            if len(self.items) >= self.options.max_landmarks:
                if self.rovio:
                    events.append(self.event('rovio_no_free_slot', observation=obs['id']))
                    continue
                # Bounded list eviction is a resource policy, never a failure
                # inference about the observed object.
                i = min(range(len(self.items)), key=lambda i: self.items[i]['last_seen_s'])
                events.append(self.event('memory_slot_evicted', memory_id=self.items[i]['id']))
                self._retain([j for j in range(len(self.items)) if j != i])
            size = len(self.x); expanded = np.zeros((size+2, size+2))
            expanded[:size, :size] = self.p
            expanded[size:, size:] = obs['covariance_m2']
            self.p = expanded; self.x = np.r_[self.x, obs.get('measurement_state', obs.get('relative_xy_m'))]
            self.sequence += 1
            self.items.append(dict(id=f'm{self.sequence}', kind=obs['kind'], signature=obs['signature'],
                                   representation=obs.get('representation', 'point'),
                                   appearance_hue=obs.get('hue'),
                                   first_seen_s=t, last_seen_s=t, observations=1))
            if self.rovio:
                self.statistics[f'm{self.sequence}'] = self.library.create(t)
            events.append(self.event('created', observation=obs['id'], memory_id=f'm{self.sequence}'))
        self.t = t
        return dict(status='updated', self_pose=[0., 0., 0.], memories=self.snapshot(t), events=events,
                    implementation=self.options.implementation, observation_tick=observation_tick,
                    work=dict(landmarks=len(self.items), max_landmarks=self.options.max_landmarks,
                              wall_cap=None, cap_end=False))

    def _retain(self, keep):
        if self.rovio:
            for i, item in enumerate(self.items):
                if i not in keep:
                    self.statistics.pop(item['id']).close()
        indices = [j for i in keep for j in (2*i, 2*i+1)]
        self.items = [self.items[i] for i in keep]
        self.x = self.x[indices]; self.p = self.p[np.ix_(indices, indices)]

    @staticmethod
    def event(reason, **extra):
        return dict(category='egocentric_memory', reason=reason, blocked_object='not_observed',
                    minimum_gap_m=None, gap_status='not_measured', **extra)


def language_context(memories, *, goal_signature=None, scan=None, footprint_radius_m=None):
    """Stable instructions first; all time-varying memory/choices at the end."""
    fixed = ('자기 자신은 항상 (0,0)·정면이다. 아래는 자기 RGB와 자기 발행 명령으로 갱신한 '
             '불확실한 상대 기억이다. 목적지는 자기 카메라로 확인한다. 기억만으로 도착을 선언하지 않는다.')
    lines = []
    for m in memories:
        a = math.degrees(m['bearing_rad'])
        direction = ('왼쪽' if a > 0 else '오른쪽')+(' 앞' if abs(a) <= 90 else ' 뒤')
        lines.append(f"{m['signature']}({m['kind']}): {direction} 약 {m['range_m']:.1f} m, "
                     f"{m['age_s']:.0f}초 전에 봄, 불확실 95% 반경 {m['radius95_m']:.1f} m"+
                     (' (부분 경계, 끝/중심 위치 미관측)' if m['extent_unknown'] else '')+
                     (f", 기억 선명도 {100*m['freshness']:.0f}%" if m['freshness'] is not None else ''))
    goals = [m for m in memories if m['signature'] == goal_signature]
    candidates = ([dict(action='look_toward_memory', memory_id=m['id'], bearing_rad=m['bearing_rad'],
                        range_m=m['range_m'], arrival_verified=False) for m in goals]
                  if goals else [dict(action='look_left'), dict(action='look_right'), dict(action='turn_and_observe')])
    if not goals and scan is not None and footprint_radius_m is not None:
        # Relative, currently observed directions only. Missing returns are
        # unknown, never free. Three choices is an LLM context work budget.
        observed=[r for r in scan['columns'] if r['status']=='hit' and r['range_m'] is not None]
        candidates=[dict(action='inspect_observed_direction',bearing_rad=r['bearing_rad'],
                         minimum_gap_m=r['range_m']-footprint_radius_m,blocked_object='observed_wall_boundary',
                         reason='current_own_rgb_measured_range',arrival_verified=False)
                    for r in sorted(observed,key=lambda r:-r['range_m'])[:3]] or candidates
    return dict(fixed_prefix=fixed, dynamic_suffix='\n'.join(lines) or '관측한 지형지물 기억 없음', candidates=candidates)
