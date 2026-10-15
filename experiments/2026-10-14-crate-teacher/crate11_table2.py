"""crate11 table 2: per-seed crate yaw, lug-wall distances, stance-wall clearance, approach angles, outcomes.
Evaluation-only geometry from plan.json/scene.xml (never a controller input). No physics/render/remote."""
import json, math, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path
from harness.static_keepouts import rect_distance

RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')
ROBOT_MARGIN = .17   # planning radius .13 + wall inflation .04 (constraints(): radius .13 folded, extra = .17-radius)
CHOICES = [(math.radians(a), d) for a in (0, -15, 15) for d in (.196, .198, .203, .208)]


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def zjson(p):
    z = Path(str(p) + '.zst')
    return json.loads(subprocess.check_output(['zstd', '-dc', str(z)]) if z.exists() else Path(p).read_bytes())


def walls(scene):
    out = []
    for g in ET.parse(scene).getroot().findall('.//worldbody/geom'):
        n = g.get('name', '')
        if n.startswith('zone_wall_'):
            p = list(map(float, g.get('pos').split())); s = list(map(float, g.get('size').split()))
            out.append((n.replace('zone_wall_', ''), (p[0], p[1], s[0], s[1], 0)))
    return out


def row(name):
    raw = RAW / name / 'raw'
    plan = json.loads((raw / 'plan.json').read_text()); res = zjson(raw / 'result.json')
    W = walls(raw / 'scene.xml')
    x, y, yaw = plan['cargo_pose']
    c, s = math.cos(yaw), math.sin(yaw)
    lug = {'teal': (x - .1 * c, y - .1 * s), 'blue': (x + .1 * c, y + .1 * s)}
    def nearest(pt):
        d = sorted((rect_distance(pt, r), n) for n, r in W)
        return {'wall': d[0][1], 'm': d[0][0]}
    body = nearest((x, y))
    out = {'run': name, 'seed': plan['seed'], 'sha8': res['source_sha'][:8], 'crate_xy': [x, y], 'crate_yaw_deg': math.degrees(wrap(yaw)),
           'near_wall_flag': plan.get('near_wall'), 'peer_case': plan.get('peer_case'), 'center_wall': body,
           'outcomes': res['prefix']['outcomes'], 'success': bool(res.get('prefix_held') and res.get('release_success')), 'robots': {}}
    for rid, end in plan['roles'].items():
        h = yaw + (math.pi if end == 'blue' else 0.)
        sx, sy = plan['spawns'][rid][0], plan['spawns'][rid][1]
        bearing = math.atan2(lug[end][1] - sy, lug[end][0] - sx)
        best = None; nominal = None
        for off, d in CHOICES:
            st = (lug[end][0] - d * math.cos(h + off), lug[end][1] - d * math.sin(h + off))
            clr = min(rect_distance(st, r) for _, r in W) - ROBOT_MARGIN
            if best is None or clr > best[0]:
                best = (clr, math.degrees(off), d)
            if off == 0 and d == .196:
                nominal = clr
        out['robots'][rid] = {'end': end, 'lug_xy': lug[end], 'lug_wall': nearest(lug[end]),
                              'approach_deg': math.degrees(wrap(bearing - h)), 'spawn_to_lug_m': math.dist((sx, sy), lug[end]),
                              'nominal_stance_wall_clear_m': nominal, 'best_candidate_stance_wall_clear_m': best[0],
                              'best_candidate': {'offset_deg': best[1], 'dist_m': best[2]}, 'outcome': res['prefix']['outcomes'][rid]}
    return out


if __name__ == '__main__':
    rows = [row(n) for n in sys.argv[1:]]
    print(json.dumps(rows))


def plan_audit(plan_file, scene_run='crate-diag-77978-bf31840f'):
    """Geometry-only audit of a PLAN file (no run needed): stance wall clearance of every assigned lug."""
    W = walls(RAW / scene_run / 'raw' / 'scene.xml')
    out = []
    for p in json.loads(Path(plan_file).read_text())['episodes']:
        x, y, yaw = p['cargo_pose']; c, s = math.cos(yaw), math.sin(yaw)
        lug = {'teal': (x - .1 * c, y - .1 * s), 'blue': (x + .1 * c, y + .1 * s)}
        rr = {}
        for rid, end in p['roles'].items():
            h = yaw + (math.pi if end == 'blue' else 0.)
            best = max(min(rect_distance((lug[end][0] - d * math.cos(h + off), lug[end][1] - d * math.sin(h + off)), r) for _, r in W) - ROBOT_MARGIN
                       for off, d in CHOICES)
            rr[rid] = best
        out.append({'seed': p['seed'], 'near_wall': p.get('near_wall'), 'best_stance_wall_clear_m': rr,
                    'infeasible': any(v < 0 for v in rr.values())})
    return out
