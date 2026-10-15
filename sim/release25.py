"""Own-estimate static-map escape from uncertainty inflation, default OFF.

Nav2 checks swept footprints before recovery motion (Spin::isCollisionFree).
Our uncertainty-only escape additionally uses a fixed separating half-plane:
the nominal whole sweep must be clear, clearance never decreases, and the
endpoint must recover the UNCHANGED release23 halo. This is an adaptation,
not a Nav2 guarantee. See experiments/2026-10-16-release25/README.md.
"""
from __future__ import annotations
from harness.static_keepouts import _axes

MODE = 'release_sweep_wall_aware_v1'
OPTIONS = dict(release_sweep_wall_aware=MODE)


def validate(options):
    mode = options.get('release_sweep_wall_aware', 'off')
    if mode not in ('off', MODE):
        raise ValueError('unknown release_sweep_wall_aware')
    if mode == MODE and (options.get('release_leg_budget') != 'release_leg_budget_v1'
                        or options.get('release_plan_budget') != 'compute_budget_v1'):
        raise ValueError('release25 requires release23 swept geometry and compute budget')


def plane_gaps(shapes, axis, boundary):
    """Signed clearance to one fixed half-plane at each issued-plan vertex."""
    ax, ay = axis
    return [min(x*ax+y*ay for x,y in shape)-boundary for shape in shapes]


def escape_plane(gaps):
    # Zero is geometric contact, not a fitted acceptance tolerance. No halo,
    # footprint radius or success criterion is reduced. Fixed orientation and
    # affine translation make vertex monotonicity a continuous certificate.
    return bool(gaps[0] <= 0. < gaps[-1] and
                all(b >= a for a,b in zip(gaps, gaps[1:])))


def obstacle_escape(shapes, inflated_rect, nominal_swept_gap):
    if nominal_swept_gap <= 0.:
        return None
    for axis in _axes(inflated_rect):
        for sign in (1., -1.):
            a = tuple(sign*v for v in axis)
            boundary = max(x*a[0]+y*a[1] for x,y in inflated_rect)
            gaps = plane_gaps(shapes, a, boundary)
            if escape_plane(gaps):
                return dict(axis=list(a), gaps_m=gaps)
    return None


def bounds_escape(shapes, bounds, halo, nominal_swept_gap):
    if nominal_swept_gap <= 0.:
        return None
    x0,x1,y0,y1 = bounds
    certificates = []
    for axis,boundary in (((1.,0.),x0+halo),((-1.,0.),-x1+halo),
                          ((0.,1.),y0+halo),((0.,-1.),-y1+halo)):
        gaps = plane_gaps(shapes, axis, boundary)
        if min(gaps) > 0.:
            continue
        if not escape_plane(gaps):
            return None
        certificates.append(dict(axis=list(axis), gaps_m=gaps))
    return certificates or None
