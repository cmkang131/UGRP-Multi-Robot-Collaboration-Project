"""Per-seed P3 collection cases (setup only) for the bins of COLLECT_PREREG_DRAFT.json.

The geometry is the beamact5 wide-start generator (`experiments/2026-10-17-beamact5/
teacher/wide_start.py`, blob c35acca6, the generator of the r13 wide gate cases)
with three changes only:
  * one case per seed; the beam pose rng is
    ``Random(f"pairact_r1_collect_v1:{seed}:beam:{proposal}")`` and its angle is
    uniform on the full circle (wide_start stratified it over 12 runs),
  * both robots' assigned-end distance and heading offset come from
    ``harness.pairact_collect.draw_start(prereg, seed, bin, robot_index)``,
  * r1 takes teal on even seeds and blue on odd seeds.
Position bearing stays radially outward (wide_start bearing bin 0), the clearance,
cargo, line-of-sight, parking and placement-graspable admission checks are the same
code.  Nothing here runs physics, renders or reads evaluation truth.

    python experiments/2026-10-21-pairact-r1/collect_cases.py --prereg P --slots slots.json \
        --out cases.json --dependency-root TEACHER --frozen-root ROOT --adapter-root ADAPTER \
        [--candidate pairact_p2_r13]
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (REPO, REPO / 'experiments/2026-10-17-beamact5/teacher'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from harness.pairact_collect import draw_start  # noqa: E402

CANDIDATE = 'pairact_p2_r13'
PROPOSALS = 5000


@contextmanager
def adapter_packages(adapter_root):
    """Import harness/sim/scripts from the pinned adapter checkout (its run_beampair1 pins the
    teacher dependency used by the runtime --placement-graspable-filter-v1), then restore ours."""
    names = ('harness', 'sim', 'scripts')
    owned = lambda n: n.split('.')[0] in names
    saved = {n: m for n, m in sys.modules.items() if owned(n)}
    path = sys.path[:]
    for n in saved:
        del sys.modules[n]
    sys.path.insert(0, str(Path(adapter_root).resolve()))
    try:
        yield
    finally:
        for n in [n for n in sys.modules if owned(n)]:
            del sys.modules[n]
        sys.modules.update(saved)
        sys.path[:] = path


class Geometry:
    def __init__(self, dependency=None, frozen_root=None, *, setup_validity=True, adapter_root=None):
        import wide_start as ws
        from harness.static_keepouts import keepout_rects
        from harness.zone_final_environment import resolve
        from sim.zone_cargo import kind
        from sim.zone_arena import BOX_HALF, COLORS
        self.ws = ws
        path = ws.BEAMPAIR_EXP / 'scenario-v7.json'
        self.data = path.read_bytes()
        self.scenario = json.loads(self.data)
        self.static, _, _ = resolve(self.scenario['map_id'])
        self.rects = keepout_rects(self.static, perimeter=True)
        self.bounds = self.static['bounds_m']
        self.pickup = self.static['regions']['pickup']
        self.beam = kind('long_beam')
        self.radius = math.hypot(.185 / 2, .160 / 2)
        cargo = [p for p in self.scenario['eval']['setup']['placements'] if p['item_id'] != 'beam_1']
        self.others = [(p['item_id'], p['pose_m'][:2],
                        math.hypot(*(BOX_HALF[:2] if p['kind'] in COLORS else kind(p['kind']).landing_half_extents_m)))
                       for p in cargo]
        self.validity = self.validity_meta = None
        if setup_validity:
            if adapter_root is None:
                raise ValueError('adapter root required: the admission family must match the runtime adapter pin')
            with adapter_packages(adapter_root):
                self.validity, self.validity_meta = ws.build_admission(dependency, frozen_root, self.scenario,
                                                                       self.static)
                self.validity_meta = dict(self.validity_meta, adapter_root=str(adapter_root))

    def robot_gap(self, point):
        from harness.static_keepouts import rect_distance
        b, r = self.bounds, self.radius
        gaps = [('bounds', min(point[0] - b[0], b[1] - point[0], point[1] - b[2], b[3] - point[1]) - r)]
        gaps += [(f'static_wall_{j}', rect_distance(point, q) - r) for j, q in enumerate(self.rects)]
        gaps += [(n, math.dist(point, p) - r - rr) for n, p, rr in self.others]
        return min(gaps, key=lambda v: v[1])


def make_case(geo, prereg, slot, *, candidate=CANDIDATE):
    from harness.static_keepouts import pose_clear
    ws, seed, bin_id = geo.ws, int(slot['seed']), slot['bin']
    (d1, y1), (d2, y2) = draw_start(prereg, seed, bin_id, 0), draw_start(prereg, seed, bin_id, 1)
    end1 = 'teal' if seed % 2 == 0 else 'blue'
    end2 = 'blue' if end1 == 'teal' else 'teal'
    cx, cy = geo.pickup['center_m']
    hx, hy = geo.pickup['half_extents_m']
    bhx, bhy = geo.beam.landing_half_extents_m
    footprint = [(-bhx, -bhy), (bhx, -bhy), (bhx, bhy), (-bhx, bhy)]
    grip = abs(geo.beam.grasps[0].grip_xyz[0])
    rejected = Counter()
    for proposal in range(PROPOSALS):
        rng = random.Random(f'pairact_r1_collect_v1:{seed}:beam:{proposal}')
        a = 2 * math.pi * rng.random()
        pose = [rng.uniform(cx - hx + bhx, cx + hx - bhx), rng.uniform(cy - hy + bhy, cy + hy - bhy), a]
        if not pose_clear(pose, footprint, geo.rects, bounds=geo.bounds, margin=0.):
            rejected['beam_static_overlap'] += 1; continue
        if min(math.dist(pose[:2], p) - math.hypot(bhx, bhy) - r for _, p, r in geo.others) < 0:
            rejected['beam_cargo_overlap'] += 1; continue
        stance = None
        if geo.validity is not None:
            stance = geo.validity(pose)
            if not stance['accepted']:
                rejected['placement_graspable_filter'] += 1; continue

        def assigned(end, distance):
            sign = -1. if end == 'teal' else 1.
            e = [pose[0] + sign * grip * math.cos(a), pose[1] + sign * grip * math.sin(a)]
            outward = a + (math.pi if end == 'teal' else 0.)
            return e, [e[0] + distance * math.cos(outward), e[1] + distance * math.sin(outward)], outward

        e1, own, out1 = assigned(end1, d1)
        e2, peer, out2 = assigned(end2, d2)
        if any(geo.robot_gap(p)[1] < 0 or math.dist(p, pose[:2]) - math.hypot(bhx, bhy) - geo.radius < 0
               for p in (own, peer)):
            rejected['robot_environment_overlap'] += 1; continue
        if math.dist(own, peer) - 2 * geo.radius < 0:
            rejected['robot_peer_overlap'] += 1; continue
        if any(ws.segment_hits_rect(p, e, rect) for p, e in ((own, e1), (peer, e2)) for rect in geo.rects):
            rejected['initial_static_los'] += 1; continue
        park = None
        for _ in range(PROPOSALS):
            p = [rng.uniform(geo.bounds[0] + geo.radius, geo.bounds[1] - geo.radius),
                 rng.uniform(geo.bounds[2] + geo.radius, geo.bounds[3] - geo.radius)]
            if min(geo.robot_gap(p)[1], math.dist(p, own) - 2 * geo.radius, math.dist(p, peer) - 2 * geo.radius,
                   math.dist(p, pose[:2]) - math.hypot(bhx, bhy) - geo.radius) >= 0:
                park = p; break
        if park is None:
            raise ValueError('parking computation budget exhausted')
        z = .032355118817659255
        plan = dict(
            episode_id=f'pairact-r1-collect-{seed}', batch='pairact-r1-p3-collect', seed=seed, split=slot['split'],
            scenario_id=geo.scenario['scenario_id'], scenario_source_sha256=hashlib.sha256(geo.data).hexdigest(),
            map_id=geo.scenario['map_id'], cargo_scene='cargo_v7', scene_profile=ws.SCENE_PROFILE,
            beam_pose=pose,
            spawns={'r1': [*own, z, out1 + y1], 'r2': [*peer, z, out2 + y2], 'r3': [*park, z, 0.]},
            roles={'r1': end1, 'r2': end2}, target_item='beam_1', object_kind='long_beam',
            assignment_source='demo_rule_color_balanced', end_color_scene='grasp_act_teal_blue_v1',
            peer_case='wide_pair_start_v1', initial_pan={r: rng.randint(500, 2500) for r in ('r1', 'r2')},
            burst_ticks=1 + seed % 12, proposal_attempts=proposal + 1, collect_bin=bin_id,
            start_layers={'r1': dict(layer=bin_id, target_distance_m=d1, yaw_bin=dict(index=None, offset_rad=y1),
                                     bearing_bin=dict(index=0, angle_rad=out1)),
                          'r2': dict(layer=bin_id, target_distance_m=d2, yaw_bin=dict(index=None, offset_rad=y2),
                                     bearing_bin=dict(index=0, angle_rad=out2))},
            assigned_end_xy={'r1': e1, 'r2': e2}, setup_rejections=dict(rejected))
        if stance is not None:
            plan.update(setup_validity=geo.validity_meta['mode'], placement_validity=stance)
        return dict(plan=plan, profile=dict(scene_profile=ws.SCENE_PROFILE, held_object='hidden_v1',
                                            teacher_visibility='visible_only', top_camera_control=False),
                    candidate=candidate)
    raise ValueError(f'seed {seed} bin {bin_id}: setup proposal budget exhausted {dict(rejected)}')


def make_cases(geo, prereg, slots, *, candidate=CANDIDATE):
    return [make_case(geo, prereg, s, candidate=candidate) for s in slots]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prereg', type=Path, required=True)
    p.add_argument('--slots', type=Path, required=True, help='[{seed, bin, split}] json')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--dependency-root', type=Path)
    p.add_argument('--frozen-root', type=Path)
    p.add_argument('--adapter-root', type=Path)
    p.add_argument('--no-setup-validity', action='store_true', help='CPU preview only; never for collection')
    p.add_argument('--candidate', default=CANDIDATE)
    a = p.parse_args()
    if a.out.exists():
        raise SystemExit('refusing to overwrite existing cases file')
    prereg = json.loads(a.prereg.read_text())
    geo = Geometry(a.dependency_root, a.frozen_root, setup_validity=not a.no_setup_validity,
                   adapter_root=a.adapter_root)
    cases = make_cases(geo, prereg, json.loads(a.slots.read_text()), candidate=a.candidate)
    a.out.write_text(json.dumps(cases, indent=1) + '\n')
    print(json.dumps({'out': str(a.out), 'sha256': hashlib.sha256(a.out.read_bytes()).hexdigest(), 'n': len(cases)}))


if __name__ == '__main__':
    main()
