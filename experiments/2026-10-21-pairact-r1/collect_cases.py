"""Per-seed P3 collection cases (setup only) for the bins of COLLECT_PREREG_DRAFT.json.

The geometry is the beamact5 wide-start generator (`experiments/2026-10-17-beamact5/
teacher/wide_start.py`, blob c35acca6, the generator of the r13 wide gate cases)
with three changes only:
  * one case per seed; the beam pose rng is
    ``Random(f"pairact_r1_collect_v1:{seed}:beam:{proposal}")`` and its angle is
    uniform on the full circle (wide_start stratified it over 12 runs),
  * both robots' assigned-end distance and heading offset come from
    ``harness.pairact_collect.draw_start(prereg, seed, bin, robot_index)``,
  * r1's end is ``role_of(seed)`` (str-seeded coin), not seed parity: parity would tie the
    role to the round-robin bin (6 bins, consecutive seeds); burst_ticks likewise uses a
    str-seeded draw instead of wide_start's ``1 + i % 12``.
Position bearing stays radially outward (wide_start bearing bin 0), the clearance,
cargo, line-of-sight, parking and placement-graspable admission checks are the same
code.  Nothing here runs physics, renders or reads evaluation truth.

Audit (COLLECT_PREREG v2 audit_outputs): every case plan and every generator budget
exhaustion carries the gate funnel (per gate cumulative passed / rejected), the blocking
objects, the minimum gap per gate, the generator SHA / file sha256 and a reproduce command.
An exhausted seed is returned as ``{'setup_rejected': audit}`` (written to the ledger by the
runner, seed consumed, never re-queued) instead of raising before the ledger.

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
GATES = ('beam_static_overlap', 'beam_cargo_overlap', 'placement_graspable_filter', 'robot_environment_overlap',
         'robot_peer_overlap', 'initial_static_los', 'parking')


class SetupRejected(ValueError):
    def __init__(self, audit):
        super().__init__(f"seed {audit['seed']} bin {audit['bin']}: setup proposal budget exhausted {audit['rejected']}")
        self.audit = audit


def generator_source():
    """Generator identity for the audit: repo HEAD (None outside git) and file sha256s."""
    import subprocess
    try:
        sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True,
                                      stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sha = None
    files = {str(f.relative_to(REPO)): hashlib.sha256(f.read_bytes()).hexdigest()
             for f in (HERE / 'collect_cases.py', REPO / 'harness/pairact_collect.py')}
    return dict(source_sha=sha, file_sha256=files)


class Funnel:
    """Per gate cumulative passed / rejected, blockers and the smallest observed gap (m)."""
    def __init__(self):
        self.passed, self.rejected, self.blockers, self.min_gap = Counter(), Counter(), Counter(), {}

    def ok(self, gate):
        self.passed[gate] += 1
        return True

    def reject(self, gate, blocker=None, gap=None):
        self.rejected[gate] += 1
        if blocker is not None:
            self.blockers[f'{gate}:{blocker}'] += 1
        if gap is not None:
            self.min_gap[gate] = min(gap, self.min_gap.get(gate, math.inf))
        return False

    def audit(self, proposals):
        return dict(proposals=proposals, gates=[dict(gate=g, passed_cumulative=self.passed[g], rejected=self.rejected[g])
                                                for g in GATES],
                    blocked_objects=dict(self.blockers), min_gap_m={g: round(v, 6) for g, v in self.min_gap.items()})


def reproduce_command(slot, candidate):
    return ['python', 'experiments/2026-10-21-pairact-r1/collect_cases.py', '--prereg', '<COLLECT_PREREG_DRAFT.json>',
            '--slots', '<json: [%s]>' % json.dumps(dict(seed=int(slot['seed']), bin=slot['bin'], split=slot['split'])),
            '--out', '<new file>', '--dependency-root', '<teacher>', '--frozen-root', '<root>', '--adapter-root',
            '<adapter>', '--candidate', candidate]


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
        self.generator = generator_source()
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


def role_of(seed):
    return 'teal' if random.Random(f'pairact_r1_collect_v1:{seed}:role').random() < .5 else 'blue'


def make_case(geo, prereg, slot, *, candidate=CANDIDATE):
    from harness.static_keepouts import pose_clear
    ws, seed, bin_id = geo.ws, int(slot['seed']), slot['bin']
    (d1, y1), (d2, y2) = draw_start(prereg, seed, bin_id, 0), draw_start(prereg, seed, bin_id, 1)
    end1 = role_of(seed)
    end2 = 'blue' if end1 == 'teal' else 'teal'
    cx, cy = geo.pickup['center_m']
    hx, hy = geo.pickup['half_extents_m']
    bhx, bhy = geo.beam.landing_half_extents_m
    footprint = [(-bhx, -bhy), (bhx, -bhy), (bhx, bhy), (-bhx, bhy)]
    grip = abs(geo.beam.grasps[0].grip_xyz[0])
    funnel, gen = Funnel(), getattr(geo, 'generator', None) or generator_source()
    for proposal in range(PROPOSALS):
        rng = random.Random(f'pairact_r1_collect_v1:{seed}:beam:{proposal}')
        a = 2 * math.pi * rng.random()
        pose = [rng.uniform(cx - hx + bhx, cx + hx - bhx), rng.uniform(cy - hy + bhy, cy + hy - bhy), a]
        if not pose_clear(pose, footprint, geo.rects, bounds=geo.bounds, margin=0.):
            funnel.reject('beam_static_overlap', 'static_map'); continue
        funnel.ok('beam_static_overlap')
        name, gap = min(((n, math.dist(pose[:2], p) - math.hypot(bhx, bhy) - r) for n, p, r in geo.others),
                        key=lambda v: v[1])
        if gap < 0:
            funnel.reject('beam_cargo_overlap', name, gap); continue
        funnel.ok('beam_cargo_overlap')
        stance = None
        if geo.validity is not None:
            stance = geo.validity(pose)
            if not stance['accepted']:
                funnel.reject('placement_graspable_filter', 'certified_stance_set'); continue
        funnel.ok('placement_graspable_filter')

        def assigned(end, distance):
            sign = -1. if end == 'teal' else 1.
            e = [pose[0] + sign * grip * math.cos(a), pose[1] + sign * grip * math.sin(a)]
            outward = a + (math.pi if end == 'teal' else 0.)
            return e, [e[0] + distance * math.cos(outward), e[1] + distance * math.sin(outward)], outward

        e1, own, out1 = assigned(end1, d1)
        e2, peer, out2 = assigned(end2, d2)
        gaps = [geo.robot_gap(p) for p in (own, peer)]
        gaps += [('beam_1', math.dist(p, pose[:2]) - math.hypot(bhx, bhy) - geo.radius) for p in (own, peer)]
        name, gap = min(gaps, key=lambda v: v[1])
        if gap < 0:
            funnel.reject('robot_environment_overlap', name, gap); continue
        funnel.ok('robot_environment_overlap')
        gap = math.dist(own, peer) - 2 * geo.radius
        if gap < 0:
            funnel.reject('robot_peer_overlap', 'peer_robot', gap); continue
        funnel.ok('robot_peer_overlap')
        hit = next((j for p, e in ((own, e1), (peer, e2)) for j, rect in enumerate(geo.rects)
                    if ws.segment_hits_rect(p, e, rect)), None)
        if hit is not None:
            funnel.reject('initial_static_los', f'static_wall_{hit}'); continue
        funnel.ok('initial_static_los')
        park = None
        for _ in range(PROPOSALS):
            p = [rng.uniform(geo.bounds[0] + geo.radius, geo.bounds[1] - geo.radius),
                 rng.uniform(geo.bounds[2] + geo.radius, geo.bounds[3] - geo.radius)]
            if min(geo.robot_gap(p)[1], math.dist(p, own) - 2 * geo.radius, math.dist(p, peer) - 2 * geo.radius,
                   math.dist(p, pose[:2]) - math.hypot(bhx, bhy) - geo.radius) >= 0:
                park = p; break
        if park is None:
            funnel.reject('parking', 'parking_budget_exhausted'); continue
        funnel.ok('parking')
        audit = dict(funnel.audit(proposal + 1), generator=gen, reproduce=reproduce_command(slot, candidate))
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
            burst_ticks=1 + random.Random(f'pairact_r1_collect_v1:{seed}:burst').randrange(12), proposal_attempts=proposal + 1, collect_bin=bin_id,
            start_layers={'r1': dict(layer=bin_id, target_distance_m=d1, yaw_bin=dict(index=None, offset_rad=y1),
                                     bearing_bin=dict(index=0, angle_rad=out1)),
                          'r2': dict(layer=bin_id, target_distance_m=d2, yaw_bin=dict(index=None, offset_rad=y2),
                                     bearing_bin=dict(index=0, angle_rad=out2))},
            assigned_end_xy={'r1': e1, 'r2': e2}, setup_rejections=dict(funnel.rejected), setup_audit=audit)
        if stance is not None:
            plan.update(setup_validity=geo.validity_meta['mode'], placement_validity=stance)
        return dict(plan=plan, profile=dict(scene_profile=ws.SCENE_PROFILE, held_object='hidden_v1',
                                            teacher_visibility='visible_only', top_camera_control=False),
                    candidate=candidate)
    raise SetupRejected(dict(seed=seed, bin=bin_id, split=slot['split'], rejected=dict(funnel.rejected),
                             **funnel.audit(PROPOSALS), generator=gen, reproduce=reproduce_command(slot, candidate)))


def make_cases(geo, prereg, slots, *, candidate=CANDIDATE):
    """One entry per slot: a case, or {'setup_rejected': audit} when the proposal budget is exhausted."""
    out = []
    for s in slots:
        try:
            out.append(make_case(geo, prereg, s, candidate=candidate))
        except SetupRejected as rejected:
            out.append(dict(setup_rejected=rejected.audit))
    return out


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
