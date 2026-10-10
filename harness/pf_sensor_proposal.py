"""Optional finite-support Mixture MCL proposal, shared by PF and RBPF.

The finite quadrature support is an approximation, not the paper's kd-tree.
Importance weights include the actual proposal probability. No new sensor,
truth, seed, likelihood temperature or covariance floor enters the sampler.
"""
import copy
import math
from types import MethodType

import numpy as np
from scipy.special import logsumexp

OPTION = 'sensor_mixture_v1'
PARAMS = dict(sensor_fraction=.1, mismatch_fraction=.2, mismatch_likelihood_ratio=10.,
              motion_mahalanobis2_max=36., mode_min_mass=1e-6, mode_min_samples=2)


class NoSupport(ValueError):
    pass


def mixture(log_motion, log_sensor, valid):
    """Return normalized q and UNNORMALIZED target, on identical support.

    log_motion includes quadrature volumes/prior ancestor mass. Retaining its
    normalizer matters: different RBPF ancestors have different evidence.
    """
    lm, ls = np.asarray(log_motion, float), np.asarray(log_sensor, float)
    valid = np.asarray(valid, bool) & np.isfinite(lm) & np.isfinite(ls)
    if not valid.any():
        raise NoSupport('no reachable observed-free sensor proposal')
    pm, ps = np.zeros(len(lm)), np.zeros(len(lm))
    pm[valid] = np.exp(lm[valid]-logsumexp(lm[valid]))
    ps[valid] = np.exp(ls[valid]-logsumexp(ls[valid]))
    average = logsumexp(np.log(pm[valid])+ls[valid])
    mismatch = float(ls[valid].max()-average) > math.log(PARAMS['mismatch_likelihood_ratio'])
    beta = PARAMS['mismatch_fraction' if mismatch else 'sensor_fraction']
    q = (1-beta)*pm+beta*ps
    target = np.where(valid, lm+ls, -np.inf)
    return q, target, dict(sensor_fraction=beta, mismatch=mismatch,
        support=int(valid.sum()), rejected=int((~valid).sum()))


def draw(log_motion, log_sensor, valid, rng, count=1, labels=None):
    """Sample q; optional stratified mode quotas preserve mass via p/q.

    Quotas change representation, never posterior mode probabilities. A mode
    below the fixed mass cutoff is not protected. Equal raw weights would be
    wrong here, particularly for a weak 180-degree hypothesis.
    """
    q, target, audit = mixture(log_motion, log_sensor, valid)
    if labels is None or count < 4:
        indices = rng.choice(len(q), size=count, p=q)
        logw = target[indices]-np.log(q[indices])
    else:
        labels = np.asarray(labels)
        groups = np.unique(labels[q > 0])
        if len(groups) > 2:
            raise ValueError('only two explicitly represented heading modes')
        mass = np.array([q[labels == k].sum() for k in groups])
        posterior = np.exp(target-logsumexp(target))
        posterior_mass = np.array([posterior[labels == k].sum() for k in groups])
        if len(groups) != 2 or posterior_mass.min() < PARAMS['mode_min_mass']:
            return draw(log_motion, log_sensor, valid, rng, count)
        first = int(np.clip(round(count*mass[0]), 2, count-2))
        counts = [first, count-first]
        indices, logw = [], []
        for k, m, n in zip(groups, mass, counts):
            sub = np.flatnonzero((labels == k) & (q > 0))
            picked = rng.choice(sub, size=n, p=q[sub]/m)
            # Deterministic mixture allocation n/N, conditional q/m.
            effective_q = (n/count)*q[picked]/m
            indices.extend(picked); logw.extend(target[picked]-np.log(effective_q))
        indices, logw = np.array(indices), np.array(logw)
        audit['mode_allocation'] = counts
    audit['unique_nodes'] = len(np.unique(indices))
    return indices, logw, audit


def observed_free(grid, poses):
    """Only this particle's already observed negative-log-odds cells."""
    ij = np.floor(np.asarray(poses)[:, :2]/grid.resolution_m).astype(int)
    return np.array([grid.cells.get(tuple(k), 0.) < 0 for k in ij])


def bounded(offsets, covariance):
    d2 = np.einsum('ni,ij,nj->n', offsets, np.linalg.inv(covariance), offsets)
    return d2 <= PARAMS['motion_mahalanobis2_max']


def own_proposal(original, field, points, camera, prior, covariance, rng, options, grid):
    """Retain archived matching/rejection; sample its quadrature directly.

    The original Gaussian moment fit is replaced by finite importance draws.
    Map history is the same ancestor's; an unknown cell is never called free.
    A support miss takes the original proposal without consuming extra RNG.
    """
    from harness.pf_observation_consistency import _bind
    namespace = original.func.__globals__
    normal, likelihood = namespace['log_normal'], namespace['likelihood']
    sigma = namespace['sensor_sigma'](points, camera, options)
    selected = {}

    def moments(offsets, log_product):
        step = np.minimum([.05, .05, math.radians(1.)], np.sqrt(np.diag(covariance)))
        lm = normal(offsets, covariance)+math.log(float(np.prod(step)))
        ls = log_product-normal(offsets, covariance)
        poses = prior+offsets
        valid = observed_free(grid, poses) & bounded(offsets, covariance)
        idx, logw, row = draw(lm, ls, valid, rng)
        selected.update(pose=poses[idx[0]], logw=float(logw[0]), audit=row)
        # The frozen caller's return ABI is retained, but no Gaussian draw is
        # made and no covariance estimate from this dummy value is published.
        return np.zeros(3), covariance, np.exp(log_product-logsumexp(log_product))

    class SelectedRNG:
        def multivariate_normal(self, mean, cov):
            return selected['pose'].copy() if selected else rng.multivariate_normal(mean, cov)

    def increment(*args):
        return selected['logw']

    function = _bind(original.func, moments=moments, importance_increment=increment)
    try:
        pose, weight, event = function(field, points, camera, prior, covariance,
            SelectedRNG(), options, **original.keywords)
    except NoSupport:
        pose, weight, event = original(field, points, camera, prior, covariance, rng, options)
        event['sensor_proposal'] = dict(option=OPTION, fallback='no_observed_free_reachable_support')
        return pose, weight, event
    if selected:
        event.pop('proposal_mean', None); event.pop('proposal_covariance', None)
        event.update(proposal='finite_sensor_motion_mixture', sensor_proposal=selected['audit'])
    return pose, weight, event


def _own_proposals(self, points, camera, attempt):
    """Archived selective two-phase ABI, with an explicit ancestor map.

    Insertion and rejection policy remain owned by rbpf_composition. No global
    function patch or pose-based guess of which ancestor owns a map is used.
    """
    from harness.self_map_rbpf import GridField
    from harness.self_map_prob import wrap
    priors = self.poses.copy()
    covs = self.pending_cov+(np.eye(3)*1e-10 if attempt else 0.)
    poses, events, increments = {}, {}, np.zeros(len(priors))

    def propose(i):
        past = self.maps[i].occupied_points()
        past = past[np.linalg.norm(past-priors[i, :2], axis=1) <= 6.]
        if attempt and len(past) >= self.options.min_points:
            pose, increment, pe = own_proposal(self._selective_proposal, GridField(past),
                points, camera, priors[i], covs[i], self.rng, self.options, self.maps[i])
            increments[i] = increment if pe['reason'] == 'improved_proposal' else 0.
            pe['applied_log_weight_increment'] = float(increments[i])
        else:
            pose = self.rng.multivariate_normal(priors[i], covs[i])
            pe = dict(reason='bootstrap' if attempt else 'keyframe_interval' if len(points) >= self.options.min_points
                      else 'insufficient_match_points', proposal='motion_bootstrap' if attempt else 'motion_deferred_no_sensor_weight')
        pose[2] = wrap(pose[2]); pe['particle'] = i
        poses[i], events[i] = pose, pe

    reference = self.best
    propose(reference)
    reject = attempt and events[reference]['reason'] not in ('improved_proposal', 'bootstrap')
    if not reject:
        for i in range(len(priors)):
            if i != reference: propose(i)
        candidate = int(np.argmax(self.log_weights+increments))
        reject = attempt and events[candidate]['reason'] not in ('improved_proposal', 'bootstrap')
        if reject: reference = candidate
    if reject:
        reason = events[reference]['reason']
        for i in range(len(priors)):
            pe = events.get(i, dict(particle=i, reason='frame_rejected', proposal='not_evaluated'))
            if pe.get('proposal') != 'motion_fallback':
                poses[i] = self.rng.multivariate_normal(priors[i], covs[i]); poses[i][2] = wrap(poses[i][2])
            pe.update(frame_rejection_reason=reason, applied_log_weight_increment=0., inserted=False)
            events[i] = pe
        self._selective_state['rejected_frames'] += 1
        update = False
    else:
        update = attempt and any(e['reason'] == 'improved_proposal' for e in events.values())
        if update:
            self.log_weights += increments
            self.log_weights -= logsumexp(self.log_weights)
            self.weights = np.exp(self.log_weights); self.best = int(np.argmax(self.weights))
            self._selective_state['sensor_updates'] += 1
    # Existing insert_selective_v1 intentionally inserts motion fallback too.
    for pe in events.values():
        pe.update(inserted=True, insertion_reason='motion_fallback' if reject else pe['reason'])
    self.poses = np.array([poses[i] for i in range(len(priors))])
    self.pending_cov[:] = np.eye(3)*1e-10
    row = dict(t=float(self.odom.t), n=len(priors), attempt=bool(attempt), rejected=bool(reject),
        sensor_proposals=sum(e.get('proposal') == 'finite_sensor_motion_mixture' for e in events.values()),
        support_fallbacks=sum(e.get('sensor_proposal', {}).get('fallback') is not None for e in events.values()))
    self.sensor_proposal_audit['rows'].append(row)
    return [events[i] for i in range(len(priors))], update, events[reference]['reason'] if reject else None


def attach_ownmap(grid, *, sensor_proposal='off'):
    if sensor_proposal == 'off': return grid
    if sensor_proposal != OPTION or getattr(grid, '_composition_search', None) != 'correlative_20deg_v1':
        raise ValueError('sensor proposal requires explicit composed own-map RBPF')
    if hasattr(grid, 'sensor_proposal_audit'): raise ValueError('sensor proposal already installed')
    grid.sensor_proposal_audit = dict(option=OPTION, parameters=copy.deepcopy(PARAMS),
        scope='per-ancestor observed map and command covariance', gt_inputs=False, rows=[])
    grid._selective_proposals = _own_proposals
    return grid


def predictive_nodes(poses, weights):
    """Scott bandwidth KDE, integrated with three-point Gaussian quadrature.

    Unlike a reset this only interpolates each *predicted* mode. No opposite
    pose is fabricated. Kernel smoothing is an explicit density approximation,
    as kd-tree smoothing is in dual MCL; it is not new measurement evidence.
    There is no positive covariance floor: a collapsed mode stays collapsed.
    """
    p, w = np.asarray(poses), np.asarray(weights)
    anchor = p[int(np.argmax(w)), 2]
    labels = (np.cos(p[:, 2]-anchor) < 0).astype(int)
    nodes, logp, ancestors, groups = [], [], [], []
    z = np.array([-math.sqrt(3), 0., math.sqrt(3)])
    zw = np.array([1/6, 2/3, 1/6])
    grid = np.stack(np.meshgrid(z, z, z, indexing='ij'), -1).reshape(-1, 3)
    mass = np.prod(np.stack(np.meshgrid(zw, zw, zw, indexing='ij'), -1), -1).ravel()
    for group in np.unique(labels):
        indices = np.flatnonzero(labels == group)
        v = w[indices]/w[indices].sum()
        x = p[indices].copy()
        yaw = math.atan2(v@np.sin(x[:, 2]), v@np.cos(x[:, 2]))
        x[:, 2] = np.arctan2(np.sin(x[:, 2]-yaw), np.cos(x[:, 2]-yaw))
        centered = x-v@x
        covariance = (centered.T*v)@centered
        neff = 1/(v@v)
        values, vectors = np.linalg.eigh(covariance*neff**(-2/7))
        root = vectors@np.diag(np.sqrt(np.maximum(values, 0.)))
        offsets = grid@root.T
        for i in indices:
            current = p[i]+offsets
            current[:, 2] = np.arctan2(np.sin(current[:, 2]), np.cos(current[:, 2]))
            nodes.append(current); logp.extend(np.log(max(w[i], 1e-300))+np.log(mass))
            ancestors.extend([i]*len(grid)); groups.extend([group]*len(grid))
    return np.concatenate(nodes), np.array(logp), np.array(ancestors), np.array(groups)


def static_free(pf, static, poses):
    good = pf._map_logprior(poses) == 0.
    # The existing PF map prior excludes bounds/clearance-expanded walls.
    # Also exclude authored non-traversable terrain; no live objects enter.
    for row in static.get('terrain', ()):
        xy = poses[:, :2]-np.asarray(row['center_m'])[:2]
        angle = row.get('yaw_rad', 0.); c, s = math.cos(angle), math.sin(angle)
        local = xy@np.array([[c, -s], [s, c]])
        good &= ~np.all(abs(local) <= np.asarray(row['half_extents_m'])[:2], axis=1)
    return good


def attach_s3(runtime, *, sensor_proposal='off', tracking_particles=None, static=None):
    """Leave global initialization exact; switch budget at issued first move.

    tracking_particles is an explicit saved-replay ablation, not a new default.
    The current field/feature packet is captured at the real likelihood call;
    proposed poses are installed at that update's resampling boundary.
    """
    if sensor_proposal == 'off' and tracking_particles is None: return runtime
    if sensor_proposal not in ('off', OPTION) or tracking_particles not in (100, 500):
        raise ValueError('registered tracking comparison requires N100/500')
    if sensor_proposal != 'off' and (tracking_particles != 100 or static is None):
        raise ValueError('candidate requires N100 and its static map')
    from harness.pf_observation_consistency import _closure, _bind
    from harness.zone_solo_cyan_bias_tempering import replace_cell
    from harness.zone_solo_cyan_kld_start import assign
    pf = runtime.pose.provider.loc._pf
    if hasattr(runtime, 'sensor_proposal_audit'): raise ValueError('already attached')
    audit = dict(option=sensor_proposal, tracking_particles=tracking_particles,
        initial_particles=pf.n, global_unchanged=True, gt_inputs=False, handoff=None,
        parameters=copy.deepcopy(PARAMS), rows=[])
    command, record = runtime.on_command, runtime.record

    def on_command(rid, now, action):
        direct_handoff = (sensor_proposal != 'off' and audit['handoff'] is None
            and runtime.global_policy.active and action['kind'] in ('mecanum', 'drive')
            and any(action.get(k, 0) for k in ('forward', 'left', 'turn')))
        sampling = runtime.particle_sampling
        try:
            # Do not first lose a weak mode in the legacy 2000-particle draw.
            # All ordinary command/global-phase transitions still execute.
            if direct_handoff: runtime.particle_sampling = 'off'
            out = command(rid, now, action)
        finally:
            runtime.particle_sampling = sampling
        if audit['handoff'] is None and not runtime.global_policy.active:
            before = pf.n
            detail = {}
            if sensor_proposal == 'off':
                indices = pf.rng.choice(pf.n, size=tracking_particles, p=pf._weights())
                assign(pf, indices)
            else:
                weights = pf._weights()
                heading = pf.px[int(np.argmax(weights)), 2]
                labels = (np.cos(pf.px[:, 2]-heading) < 0).astype(int)
                # The same posterior, including weak opposite modes, survives
                # the budget handoff. This is not an extra sensor update.
                indices, logw, detail = draw(np.log(np.maximum(weights, 1e-300)), np.zeros(pf.n),
                    static_free(pf, static, pf.px), pf.rng, tracking_particles, labels)
                assign(pf, indices); pf.logw = logw-logsumexp(logw)
            pf.stats['resamples'] += 1
            audit['handoff'] = dict(t=now, before=before, after=pf.n, **detail)
            if direct_handoff:
                runtime.kld_audit['handoff'] = dict(t=now, before=before, after=pf.n,
                    adapter=OPTION, intermediate_2000_draw=False)
        return out

    runtime.on_command = on_command
    runtime.sensor_proposal_audit = audit
    runtime.record = lambda: {**record(), 'sensor_proposal': copy.deepcopy(audit)}
    from harness.zone_solo_cyan_v106 import hp
    inner = runtime.pose.provider
    inner.runtime_contract['s3_sensor_proposal'] = {k: copy.deepcopy(v) for k, v in audit.items()
        if k not in ('rows', 'handoff')}
    inner.identity_sha256 = hp.base.digest(inner.runtime_contract)
    inner.source = 'owncam_pf_s3_sensor_proposal:'+inner.identity_sha256[:8]
    runtime.pose.source = inner.source
    wrapper = pf.update_obs
    selected = _closure(wrapper, 'selected').cell_contents
    original_score = selected.__globals__['likelihood']
    # Actual-cloud ESS is an action trigger, not part of the sensor model.
    # Hypothetical nodes must neither trigger looks nor count as new frames.
    node_score = original_score
    if node_score.__module__ == 'harness.zone_solo_cyan_active_observation':
        node_score = _closure(node_score, 'score').cell_contents
    if node_score.__module__ == 'harness.zone_solo_cyan_sensor_consistency':
        node_score = replace_cell(node_score, 'audit', dict(likelihood_rows=[]))
    original_resample = selected.__globals__['resample']
    pending = {}

    def likelihood(field, px, packet):
        if audit['handoff'] is not None:
            pending.update(field=field, packet=packet, poses=px.copy(), weights=pf._weights().copy())
        return original_score(field, px, packet)

    def resample(p):
        if sensor_proposal == 'off' or audit['handoff'] is None:
            value = original_resample(p)
            if audit['handoff'] is not None:
                audit['rows'].append(dict(t=float(p.t), n=p.n, unique=len(np.unique(p.px, axis=0)),
                    ess=float(1/(p._weights()**2).sum())))
            return value
        if not pending: raise ValueError('actual RGB likelihood packet required')
        ess = float(1/(p._weights()**2).sum())
        if ess > p.n/2:
            # Keep the configured selective-resampling rule. Merely having a
            # new RGB frame is not a reason to resample a healthy posterior.
            pending.clear()
            original_resample(p)
            audit['rows'].append(dict(t=float(p.t), n=p.n, unique=len(np.unique(p.px, axis=0)),
                ess=ess, skipped='existing_ESS_above_half'))
            return
        nodes, lm, parents, labels = predictive_nodes(pending['poses'], pending['weights'])
        ls = np.log(node_score(pending['field'], nodes, pending['packet']))
        valid = static_free(p, static, nodes)
        try:
            indices, logw, detail = draw(lm, ls, valid, p.rng, p.n, labels)
        except NoSupport:
            detail = dict(fallback='no_free_predictive_support')
            original_resample(p)
        else:
            assign(p, parents[indices], nodes[indices])
            p.logw = logw-logsumexp(logw)
            p.stats['resamples'] += 1
        pending.clear()
        audit['rows'].append(dict(t=float(p.t), n=p.n, unique=len(np.unique(p.px, axis=0)),
            ess=float(1/(p._weights()**2).sum()), **detail))

    bindings = dict(resample=resample)
    if sensor_proposal != 'off': bindings['likelihood'] = likelihood
    pf.update_obs = replace_cell(wrapper, 'selected', _bind(selected, **bindings))
    return runtime
