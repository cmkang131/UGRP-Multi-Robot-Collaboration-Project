"""Default-off footprint/inflation separation and independent audit candidates.

Nav2 inflation is a traversal cost outside the collision footprint, not an
impassable uncertainty wall. Truth is never accepted here. See search25.md.
"""
import math

MODES = {'search25_inflation':'search25_soft_v1',
         'search25_budget':'search25_checks_v1',
         'search25_memory':'search25_memory50_v1',
         'search25_view':'search25_frame_v1'}
# Evaluation-only constant audit: N=5287, empirical p90 rounded to 50mm,
# exceedance 5.4%. This is a comparison, not a 99% safety guarantee.
MEMORY_MARGIN_M = .050
# Actual 640x480 pinhole half-FOV 27.2/21.1deg minus audit's 3deg reserve.
# Separate candidate; requires GCP renderer agreement before queue admission.
VIEW_HALF_X_DEG = 24.
VIEW_HALF_Y_DEG = 18.


def enabled(t,key):
    return t.search15_modes.get(key,'off')!='off'


def configure(nav):
    t=nav.teacher
    if enabled(t,'search25_memory'):
        for d in nav.audit_details:
            if not d['fresh']:d['margin_m']=MEMORY_MARGIN_M
    nav.inflation_soft=enabled(t,'search25_inflation')
    if nav.inflation_soft:
        # Self footprint already uses measured 185x160mm dimensions. Cargo
        # radii are visible bounding envelopes; remove the duplicated .005m
        # disc padding here, and bound interpolation explicitly per edge.
        nav.discs=[(x,y,r-.005 if detail['id'] in nav.world.get('objects',{}) else r)
                   for (x,y,r),detail in zip(nav.discs,nav.details)]


def hard_margins(nav):
    if getattr(nav,'inflation_soft',False):return [0.]*len(nav.audit_details)
    return [d['margin_m'] for d in nav.audit_details]


def segment_envelope(a,b,n):
    from sim.grasp_act_search18 import HALF_X,HALF_Y
    da=math.atan2(math.sin(b[2]-a[2]),math.cos(b[2]-a[2]))
    # Signed distance is 1-Lipschitz. Every point between two samples is
    # <= half the translation plus corner arc from its nearest sample.
    # This replaces an ungrounded constant with the actual sampling bound.
    return (math.dist(a[:2],b[:2])+math.hypot(HALF_X,HALF_Y)*abs(da))/(2*n)


def in_frame(optical):
    return (optical[2]>0 and abs(optical[0])<=optical[2]*math.tan(math.radians(VIEW_HALF_X_DEG))
            and abs(optical[1])<=optical[2]*math.tan(math.radians(VIEW_HALF_Y_DEG)))


def frame_clearance(optical):
    """Signed rectangular optical-plane clearance, not an 18deg cone gap."""
    return min(float(optical[2]),
               optical[2]*math.tan(math.radians(VIEW_HALF_X_DEG))-abs(optical[0]),
               optical[2]*math.tan(math.radians(VIEW_HALF_Y_DEG))-abs(optical[1]))
