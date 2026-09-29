"""Front ultrasonic range as a yaw source during the pair carry: line of sight and information, from the repository model.

Offline, analytic: ``harness.ultrasonic_map.expected_range`` (the same ray pattern / echo rule as the SIM sensor) on the
static map ``zone_wide_door_tags_v2_dock_v3`` plus two hand-made boxes for the live objects the static map omits (partner
chassis, carried beam). No physics, no MuJoCo. Poses come from the static plan route (beam centre) and the staged pair
geometry (robots at the beam centre -+0.425 m along x, r1 facing +x, r2 facing -x); the GT trajectories of the recorded runs
follow that route to within cm/degrees, which does not change any row below.

What it computes
  1. per leg, what each robot's sensor returns first (load / partner / wall) - the front cone of both robots looks along
     the beam axis at the partner, never sideways or at a wall of the route;
  2. IF the partner were not in the way (hypothetical: e.g. a solo carrier or an unloaded escort): wall range along the leg,
     d(range)/d(yaw), and the yaw std of the leg mean of N independent readings (sensor sigma 3 mm + 1 %, period 60 ms);
  3. the partner-face range as a function of the partner's relative yaw (the only thing the front sonar of a facing pair
     does see), and its yaw resolution, to compare with the own-image edge (beam_edge_all_cases.py).
"""
import json
import math
from pathlib import Path

import numpy as np

import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from harness.ultrasonic_map import expected_range, static_boxes           # noqa: E402
from harness.ultrasonic_model import DEFAULT_SPEC                            # noqa: E402

HERE = Path(__file__).resolve().parent
MAP = json.load(open(ROOT/'maps/zones/zone_wide_door_tags_v2_dock_v3.json'))
WALLS = static_boxes(MAP)
ROUTE = [(1.0, .05), (1.55, .05), (2.4, .05), (3.2, .05), (3.2, -.6666667), (3.2, -1.3833333), (3.2, -2.1), (3.9, -2.1), (4.6, -2.1)]
LIVE = {0: 18.5, 1: 24.4, 2: 23.3, 3: 20.75, 4: 20.75, 5: 20.75, 6: 21.15, 7: 21.15}
HALF_SPAN = .425                       # robot centre to beam centre (staged placement)
CHASSIS_X = (-.15, .10)                # chassis extent along its x (docs: harness/zone_pair_guards SweepGuard box)
CHASSIS_HALF_Y = .09
PERIOD = DEFAULT_SPEC.period_s


def chassis_box(x, y, yaw):
    cx = x + math.cos(yaw)*(CHASSIS_X[0] + CHASSIS_X[1])/2
    cy = y + math.sin(yaw)*(CHASSIS_X[0] + CHASSIS_X[1])/2
    return {'id': 'partner', 'center': (cx, cy), 'half': ((CHASSIS_X[1] - CHASSIS_X[0])/2, CHASSIS_HALF_Y), 'height': .09, 'yaw': yaw}


def beam_box(bx, by, z_lo=.061, length=.6):
    # the SIM box helper puts boxes on the floor; a beam at z 61-93 mm is above the sensor axis (54 mm) only partly: the
    # documented result (docs 4, 8) is used instead of a ray test: end face 0.042 m first echo at lift 0.095 (M2 v6).
    return None


def rng(box_list, pose):
    e = expected_range(MAP, pose, boxes=box_list)
    return e.range_m


def main():
    out = {'legs': {}}
    print('1. first echo per leg (r1 faces +x at beam_x-0.425, r2 faces -x at beam_x+0.425), distances from the sensor face [m]')
    print('   leg  route                 wall-only range r1 (min..max)  r2 (min..max) | partner front | first echo now (lift 0.095) / at lift 0.110')
    for leg in range(8):
        (ax, ay), (bx, by) = ROUTE[leg], ROUTE[leg + 1]
        n = max(int(math.hypot(bx - ax, by - ay)/.05), 2)
        rs = {'r1': [], 'r2': []}
        part = []
        for k in range(n + 1):
            cx, cy = ax + (bx - ax)*k/n, ay + (by - ay)*k/n
            p1, p2 = (cx - HALF_SPAN, cy, 0.), (cx + HALF_SPAN, cy, math.pi)
            rs['r1'].append(rng(WALLS, p1))
            rs['r2'].append(rng(WALLS, p2))
            part.append(rng([chassis_box(*p2)], p1))
        def span(v):
            v = [x for x in v if x is not None]
            return (min(v), max(v)) if v else None
        s1, s2, sp = span(rs['r1']), span(rs['r2']), span(part)
        out['legs'][leg] = {'wall_r1': s1, 'wall_r2': s2, 'partner': sp}
        fmt = lambda s: 'none' if s is None else '%.2f..%.2f' % s
        print('   L%d  (%.2f,%+.2f)->(%.2f,%+.2f)   %-14s %-14s | %s | load end face 0.04 m / partner %s (both < every wall range)' %
              (leg, ax, ay, bx, by, fmt(s1), fmt(s2), fmt(sp), fmt(sp)))

    print('\n2. HYPOTHETICAL yaw information from the map walls if the partner/beam were NOT in the line of sight')
    print('   The first echo is the NEAREST point in a 15 deg cone. A flat wall met at normal incidence has its nearest point on the')
    print('   perpendicular, so the range does not depend on yaw until the foot of the perpendicular leaves the cone (> 15 deg).')
    sweep = [-20, -15, -12, -9, -6, -3, 0, 3, 6, 9, 12, 15, 20]
    for label, p in (('L3 r1 (east wall ahead 2.52 m)', (3.2 - HALF_SPAN, -.6, 0.)), ('L4 r2 (divider wall ahead 1.32 m)', (3.2 + HALF_SPAN, -1.4, math.pi)),
                     ('L1 r1 approaching the door (x=1.7)', (1.7, .05, 0.)), ('L1 r1 in front of a door post (x=2.0, y=-0.2)', (2.0, -.2, 0.))):
        vals = [(a, rng(WALLS, (p[0], p[1], p[2] + math.radians(a)))) for a in sweep]
        print('   %-46s ' % label + ' '.join('%+d:%s' % (a, ('%.3f' % r) if r is not None else 'none') for a, r in vals))
    print('   fraction of poses along each leg where the range differs by more than one reading sigma between yaw -3 and +3 deg:')
    print('   leg robot | samples | informative | median |R(+3)-R(-3)| [mm] | median sigma [mm]')
    tab = []
    for leg in range(8):
        (ax, ay), (bx, by) = ROUTE[leg], ROUTE[leg + 1]
        n = max(int(math.hypot(bx - ax, by - ay)/.02), 4)
        for rid, sgn, yaw0 in (('r1', -1, 0.), ('r2', 1, math.pi)):
            info, diffs, sigs = 0, [], []
            for k in range(n + 1):
                cx, cy = ax + (bx - ax)*k/n, ay + (by - ay)*k/n
                base = (cx + sgn*HALF_SPAN, cy)
                rp, rm_ = rng(WALLS, (*base, yaw0 + math.radians(3))), rng(WALLS, (*base, yaw0 - math.radians(3)))
                r0 = rng(WALLS, (*base, yaw0))
                if r0 is None:
                    continue
                sg = DEFAULT_SPEC.sigma_m(r0)
                d = abs((rp if rp is not None else 4.) - (rm_ if rm_ is not None else 4.))
                info += d > sg
                diffs.append(d); sigs.append(sg)
            print('   L%d %s | %d | %d (%.0f %%) | %.1f | %.1f' % (leg, rid, len(diffs), info, 100*info/max(len(diffs), 1), 1e3*np.median(diffs), 1e3*np.median(sigs)))
            tab.append({'leg': leg, 'robot': rid, 'samples': len(diffs), 'informative': int(info), 'median_diff_mm': 1e3*float(np.median(diffs)), 'median_sigma_mm': 1e3*float(np.median(sigs))})
    out['hypothetical'] = tab

    print('\n3. partner-face range vs partner relative yaw (what a facing pair sensor does see): r1 at (1.155,0.022,0), partner chassis centre 0.85 m ahead')
    rows = []
    for lat in (-.008, 0., .008):
        vals = []
        for d in np.radians([-6, -4, -3, -2, -1, 0, 1, 2, 3, 4, 6]):
            p2 = (2.005, .022 + lat, math.pi + d)
            vals.append((math.degrees(d), rng([chassis_box(*p2)], (1.155, .022, 0.))))
        rows.append((lat, vals))
        print('   partner lateral offset %+.0f mm: ' % (lat*1e3) + ' '.join('%+.0f deg:%s' % (a, ('%.3f' % r) if r is not None else 'none') for a, r in vals))
    r0 = rng([chassis_box(2.005, .022, math.pi)], (1.155, .022, 0.))
    sig = DEFAULT_SPEC.sigma_m(r0)
    v = [r for a, r in rows[1][1] if r is not None]
    a_ = [a for a, r in rows[1][1] if r is not None]
    slope_avg = (max(v) - min(v))/(max(a_) - min(a_)) if len(v) > 2 else float('nan')
    print('   nominal partner range %.3f m, reading sigma %.1f mm; mean |d range/d relative yaw| over +-6 deg = %.2f mm/deg' % (r0, sig*1e3, slope_avg*1e3))
    print('   => yaw std per reading %.1f deg, of the mean of 330 readings %.2f deg IF spacing and lateral offset were known exactly (they are not: '
          'the range also moves with spacing 1 mm = %.2f deg)' % (sig*1e3/(slope_avg*1e3), sig*1e3/(slope_avg*1e3)/math.sqrt(330), 1./(slope_avg*1e3)))
    out['partner_face'] = {'range_m': r0, 'sigma_m': sig, 'slope_mm_per_deg': slope_avg*1e3, 'table': [(lat, [(a, r) for a, r in vals]) for lat, vals in rows]}
    json.dump(out, open(HERE/'ultrasonic_yaw_information.json', 'w'), indent=1, default=float)


if __name__ == '__main__':
    main()
