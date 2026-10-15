"""Task-relative planar inverse reachability for the visible-only teacher.

The finite command-space map is built BEFORE environmental collision checks.
T_world_base = T_world_task * inverse(T_base_task). Exact visible target height
is part of the cache key; no rounding, world object lookup or evaluator input.
See search24.md for references, resolution and the limited coverage claim.
"""
import math
from functools import lru_cache

MODES = {'search24_irm': 'search24_irm_v1',
         'search24_budget': 'search24_checks_v1'}
DISTANCE_STEP_M = .002
ANGLE_STEP_DEG = 5


def enabled(t):
    return t.search15_modes.get('search24_irm', 'off') != 'off'


def compute_budget(t):
    return t.search15_modes.get('search24_budget', 'off') != 'off'


@lru_cache(maxsize=128)
def reachability_map(z):
    """Immutable certificates for the entire unchanged hover/descent/lift IK.

    Sample the calibrated radial envelope, then invert only reachable poses.
    Angles cover the outward half-circle; the geometric jaw predicate prunes
    them while building the map, never while exploring a scene's obstacles.
    """
    from harness.visual_arm import CALIBRATED_GRASP_RADIUS_CM
    from harness.visual_arm_v3 import MOUNT_X_M
    from sim.grasp_act_teacher import grasp_poses, STATION_M
    from sim.grasp_act_pregrasp import jaw_geometry
    lo, hi = (MOUNT_X_M+r/100 for r in CALIBRATED_GRASP_RADIUS_CM)
    distances = sorted({lo+i*DISTANCE_STEP_M for i in range(math.floor((hi-lo)/DISTANCE_STEP_M)+1)} |
                       {d for d in (.190,.194,.198,STATION_M,.208,.212) if lo<=d<=hi})
    result=[]
    for d in distances:
        try: hover, descent=grasp_poses((d,0.,z))
        except ValueError: continue
        for deg in range(-90,91,ANGLE_STEP_DEG):
            a=math.radians(deg);jaw=jaw_geometry(a,descent[-1])
            if jaw['allowed']:
                result.append((a,d,(-d*math.cos(a),-d*math.sin(a),a),
                    tuple(tuple(sorted(p.items())) for p in (hover,*descent))))
    # Stable, no RNG or wall-clock dependent ordering. Preserve the nominal
    # distance first among equal offsets; environment chooses the route after.
    return tuple(sorted(result,key=lambda p:(abs(p[0]),abs(p[1]-STATION_M),p[0],p[1])))


def choices_for_world(t,world):
    from sim.grasp_act_search23 import BodyNavigation
    nav=BodyNavigation(t,world,admission=True)
    if not nav.fresh_target or world['beam'] is None:
        return []
    z=world['beam']['ends'][t.end][2]
    cells=reachability_map(z)
    t.search23_log.append({'t':world['t'],'event':'inverse_reachability',
        'target':'band_'+t.end,'target_z_m':z,'reachable_cells':len(cells),
        'radial_step_m':DISTANCE_STEP_M,'angle_step_deg':ANGLE_STEP_DEG,
        'frame':'assigned visible end; yaw points inward',
        'kinematics':'unchanged full grasp_poses and jaw_geometry',
        'reason':'reachable_map' if cells else 'empty_reachability_map',
        'blocked_object':'none_kinematic_map','min_gap_m':None,
        'gap_scope':'environment not inspected'})
    return [(a,d) for a,d,_,_ in cells]
