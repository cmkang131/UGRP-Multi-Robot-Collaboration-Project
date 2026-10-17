"""Pre-registered wide start distribution for the frozen beam-pair teacher.

This module only creates setup plans and static-geometry rejection evidence.
It never runs physics, renders, calls the teacher or reads evaluation truth.
The frozen teacher/adapter remain unmodified.

The distance layers are anchored to the observed handoff-spec TRAIN and
beamdiag A/B assigned-end quantiles.  Each layer has four pre-registered
distances and four runs; r1/r2 role assignment alternates, and an independent
8-bin full-circle heading/bearing schedule covers all quadrants.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import random

from harness.static_keepouts import keepout_rects, rect_distance, pose_clear, polygons_overlap, rect_corners
from harness.zone_final_environment import resolve
from sim.zone_cargo import kind
from sim.zone_arena import BOX_HALF, COLORS
from scripts.audit_beampair1 import dump
from scripts.prepare_beampair1 import EXP as BEAMPAIR_EXP

MODE = 'beampair6_wide_start_v1'
SCENE_PROFILE = 'walls_floor_contrast_v5_indigo110_s80'
GATE_N = 40
MIN_SUCCESS = 38

# Boundaries are the published observed quantiles.  D00 also includes the
# handoff TRAIN minimum; D01 begins at the beamdiag A/B observed minimum.
LAYERS = (
    dict(id='D00', lo=0.1414823425721142, hi=0.2028623700000000,
         values=(0.1540, 0.1600, 0.1800, 0.2020),
         anchors=('TRAIN_min=0.14148234', 'TRAIN_p25=0.15683129')),
    dict(id='D01', lo=0.2028623700000000, hi=0.3070789600000000,
         values=(0.2050, 0.2400, 0.2750, 0.3050),
         anchors=('beampair_A/B_min=0.20286237',)),
    dict(id='D02', lo=0.3070789600000000, hi=0.5295456400000000,
         values=(0.3100, 0.3800, 0.4500, 0.5250),
         anchors=('TRAIN_p50=0.30707896',)),
    dict(id='D03', lo=0.5295456400000000, hi=0.7387497500000000,
         values=(0.5350, 0.6100, 0.6800, 0.7350),
         anchors=('TRAIN_p75=0.52954564',)),
    dict(id='D04', lo=0.7387497500000000, hi=0.7816726300000000,
         values=(0.7420, 0.7550, 0.7700, 0.7810),
         anchors=('TRAIN_p95=0.73874975',)),
    dict(id='D05', lo=0.7816726300000000, hi=0.8244954300000000,
         values=(0.7850, 0.8000, 0.8120, 0.8240),
         anchors=('TRAIN_p99=0.78167263',)),
    dict(id='D06', lo=0.8244954300000000, hi=1.0831999200000000,
         values=(0.8350, 0.9500, 1.0200, 1.0800),
         anchors=('beampair_A/B_p25=0.82449543',)),
    dict(id='D07', lo=1.0831999200000000, hi=1.3439281300000000,
         values=(1.0900, 1.1800, 1.2700, 1.3400),
         anchors=('beampair_A/B_p50=1.08319992',)),
    dict(id='D08', lo=1.3439281300000000, hi=1.5705553400000000,
         values=(1.3500, 1.4300, 1.4900, 1.5700),
         anchors=('beampair_A/B_p75=1.34392813',)),
    dict(id='D09', lo=1.5705553400000000, hi=1.6878017000000000,
         values=(1.5800, 1.6300, 1.6700, 1.6878),
         anchors=('beampair_A/B_p95=1.57055534', 'beampair_A/B_p99=1.67991834',
                  'beampair_A/B_max=1.68780170')),
)
LAYER_BY_ID = {r['id']: r for r in LAYERS}
LOW_ALLOWED_BEARINGS = (0, 1, 2, 3, 5, 6, 7)  # exclude inward-through-beam bin 4
HIGH_ALLOWED_BEARINGS = (0, 1, 2, 3, 4, 5, 6, 7)


def bearing_bin(layer_index, k):
    """Published radial-outward stratum.

    The authored beam envelope (0.3 m half length vs 0.27 m grasp offset)
    already excludes assigned-end radii below 0.1528 m even at the outward
    radial bearing; oblique/inward bearings need larger radii.  We therefore
    hold the position bearing at the outward axis for every registered start
    and vary the robot heading over all eight 45-degree bins.  This keeps the
    distance layers comparable and avoids inventing new clearance constants.
    """
    return 0


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def segment_hits_rect(a, b, rect):
    return polygons_overlap([a, b], rect_corners(rect))


def build_admission(dependency, frozen_root, scenario, static):
    """Replicate the runtime placement-graspable admission exactly.

    This is setup-only geometry. It imports the frozen admission function and
    the pinned certification family; no teacher state or evaluation truth is
    read. Using the runtime function avoids accepting a beam pose that the
    subsequent --placement-graspable-filter-v1 would reject.
    """
    import sys
    sys.path.insert(0, str(Path(frozen_root) / 'scripts'))
    from warp_flow_admission import certify, MODE as ADMISSION_MODE
    from scripts.run_beampair1 import dependency_modules
    rects = [(o['id'], (*o['center_m'], *o['half_extents_m'], o.get('yaw_rad', 0.)))
             for o in static['obstacles']]
    for p in scenario['eval']['setup']['placements']:
        if p['item_id'] == 'beam_1':
            continue
        half = BOX_HALF[:2] if p['kind'] in COLORS else kind(p['kind']).landing_half_extents_m
        rects.append((p['item_id'], (*p['pose_m'][:2], *half, p['pose_m'][2])))
    with dependency_modules(dependency):
        from sim.grasp_act_search24 import reachability_map
        from sim.grasp_act_search18 import body_clearance
        from sim.grasp_act_search21 import FRESH_MARGIN_M
        from sim.zone_cargo import kind as dependency_kind
        beam = dependency_kind('long_beam')
        family = reachability_map(beam.grasps[0].grip_xyz[2])
        offset = abs(beam.grasps[0].grip_xyz[0])
        def check(pose):
            return certify(pose, rects, family, body_clearance, FRESH_MARGIN_M,
                           offset=offset, mode=ADMISSION_MODE)
    return check, dict(mode=ADMISSION_MODE, offset_m=offset, rect_count=len(rects),
                       dependency_sha='26f84d0f0ada1c33473c83cca2d3415ce51bd247',
                       runtime_admission_replicated=True)


def pre_registration(seed, script_sha):
    layers = []
    for r in LAYERS:
        layers.append(dict(id=r['id'], lo_m=r['lo'], hi_m=r['hi'], distances_m=list(r['values']),
                           planned_runs=4, planned_robot_starts=8, anchors=list(r['anchors'])))
    return dict(
        schema='ugrp.beamact5.wide_start_prereg.v1', mode=MODE, seed=seed,
        script_sha256=script_sha, scene_profile=SCENE_PROFILE, gate_N=GATE_N,
        min_success=MIN_SUCCESS, denominator=GATE_N,
        distance_layers=layers, layer_denominator=4,
        robot_starts_per_layer=8,
        roles='r1 alternates teal/blue by global run index; r2 is the opposite end',
        yaw_bins_deg=[0,45,90,135,180,225,270,315],
        bearing_bins_deg=[0], bearing_stratum='radial outward from the assigned end for every run; position-bearing denominator 40',
        feasible_lower_bound_note='D00 boundary is 0.14148234, but the existing authored beam envelope (0.3 m half length, 0.27 m grasp offset, 0.1221 m chassis enclosure) requires at least 0.1528 m at the outward radial bearing; the four registered D00 distances therefore start at 0.154 m. No new tolerance or hidden-object geometry is used.',
        yaw_definition='own heading relative to the assigned-end outward direction; all eight 45-degree bins appear five times per robot across 40 runs',
        bearing_definition='spawn position is radially outward from the assigned end; the authored 0.1528 m envelope lower bound is published instead of pretending a 0.1415 m radial start is feasible',
        allocation='run i: r1 layer i%10 value i//10, r2 layer (i+5)%10 value (i//10+1)%4; radial-outward bearing always; heading offsets cycle eight 45-degree bins',
        sources=dict(
            train_assigned_distance_m=dict(min=0.1414823425721142, p25=0.15683129, p50=0.30707896,
                p75=0.52954564, p95=0.73874975, p99=0.78167263, max=0.84855317),
            beamdiag_AB_initial_distance_m=dict(min=0.20286237, p25=0.82449543, p50=1.08319992,
                p75=1.34392813, p90=1.48639221, p95=1.57055534, p99=1.67991834, max=1.68780170),
            train_approach_yaw_p99_rad=2.9367, train_align_distance_p99_m=0.26759,
            train_align_yaw_p99_rad=0.81203,
        ),
        success_rule='physical_success from the frozen evaluator only; 38/40 required',
        truth_rule='setup geometry only; teacher actions use own camera visible targets; no truth in control',
        gate_recording='training RGB OFF; only existing diagnostic review/tail capture remains',
        setup_validity='frozen warp_flow_admission.certify replicated in setup only: static obstacles + cargo placements + setup_only objects, offset=abs(beam grasp x), criterion free_goal_N>0 per assigned end; mode=placement_graspable_filter_v1',
    )


def generate(seed, output, dependency, frozen_root, *, setup_validity=True, candidate=None):
    """Regenerate the unchanged 40 starts.

    ``candidate`` is forwarded to the runner's case contract.  ``None`` keeps
    the historical unused label; the r2 gate passes the adapter candidate name
    so the same immutable plans select the new default-off mode bundle.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name in ('wide-pre-registration.json', 'wide-gate-plan.json', 'wide-cases.json',
                 'wide-setup-funnel.json', 'wide-distribution.json'):
        if (output / name).exists():
            raise ValueError('new output directory required; previous evidence is immutable')
    script_sha = digest(Path(__file__))
    prereg = pre_registration(seed, script_sha)
    if candidate is not None:
        prereg['candidate'] = candidate
    dump(output / 'wide-pre-registration.json', prereg)

    scenario_path = BEAMPAIR_EXP / 'scenario-v7.json'
    data = scenario_path.read_bytes()
    scenario = json.loads(data)
    static, _, _ = resolve(scenario['map_id'])
    rects = keepout_rects(static, perimeter=True)
    bounds = static['bounds_m']
    cx, cy = static['regions']['pickup']['center_m']
    hx, hy = static['regions']['pickup']['half_extents_m']
    beam = kind('long_beam')
    bhx, bhy = beam.landing_half_extents_m
    radius = math.hypot(.185 / 2, .160 / 2)
    cargo = [p for p in scenario['eval']['setup']['placements'] if p['item_id'] != 'beam_1']
    others = [(p['item_id'], p['pose_m'][:2],
               math.hypot(*(BOX_HALF[:2] if p['kind'] in COLORS else kind(p['kind']).landing_half_extents_m)))
              for p in cargo]
    footprint = [(-bhx, -bhy), (bhx, -bhy), (bhx, bhy), (-bhx, bhy)]

    validity = None
    validity_meta = None
    if setup_validity:
        validity, validity_meta = build_admission(dependency, frozen_root, scenario, static)

    rejected = []
    episodes = []
    stage_passes = Counter()
    attempts = 0

    def reject(stage, obj, gap, **kw):
        rejected.append(dict(proposal=attempts, population='wide_start', reason_category=stage,
                             blocked_object=obj, min_gap_m=gap, **kw))

    def robot_gap(point):
        gaps = [('bounds', min(point[0] - bounds[0], bounds[1] - point[0],
                               point[1] - bounds[2], bounds[3] - point[1]) - radius)]
        gaps += [(f'static_wall_{j}', rect_distance(point, r) - radius) for j, r in enumerate(rects)]
        gaps += [(name, math.dist(point, p) - radius - r) for name, p, r in others]
        return min(gaps, key=lambda v: v[1])

    for i in range(GATE_N):
        layer1 = LAYERS[i % 10]
        layer2 = LAYERS[(i % 10 + 5) % 10]
        k = i // 10
        d1 = layer1['values'][k]
        d2 = layer2['values'][(k + 1) % 4]
        yaw1 = (4 * (i % 10) + k) % 8
        yaw2 = (4 * ((i % 10 + 5) % 10) + k + 3) % 8
        bearing1 = bearing_bin(i % 10, k)
        bearing2 = bearing_bin((i % 10 + 5) % 10, k)
        end1 = 'teal' if i % 2 == 0 else 'blue'
        end2 = 'blue' if end1 == 'teal' else 'teal'
        accepted = False
        for attempt in range(5000):
            attempts += 1
            rng = random.Random(seed + i * 10000 + attempt)
            a = 2 * math.pi * ((i % 12 + rng.random()) / 12)
            pose = [rng.uniform(cx - hx + bhx, cx + hx - bhx),
                    rng.uniform(cy - hy + bhy, cy + hy - bhy), a]
            if not pose_clear(pose, footprint, rects, bounds=bounds, margin=0.):
                gaps = [(f'static_wall_{j}', rect_distance(pose[:2], r) - math.hypot(bhx, bhy))
                        for j, r in enumerate(rects)]
                obj, gap = min(gaps, key=lambda x: x[1])
                reject('beam_static_overlap', obj, gap, gap_scope='circumscribed_envelope_lower_bound')
                continue
            stage_passes['beam_static'] += 1
            obj, gap = min([(name, math.dist(pose[:2], p) - math.hypot(bhx, bhy) - r)
                            for name, p, r in others], key=lambda x: x[1])
            if gap < 0:
                reject('beam_cargo_overlap', obj, gap)
                continue
            stage_passes['beam_cargo'] += 1
            stance_report = None
            if validity is not None:
                stance_report = validity(pose)
                if not stance_report['accepted']:
                    for end, v in stance_report['ends'].items():
                        if v['free_goal_N'] <= 0:
                            reject('placement_graspable_filter', v['blocked_object'], v['min_gap_m'],
                                   end=end, free_goal_N=v['free_goal_N'], certified_N=v['certified_N'])
                    continue
                stage_passes['placement_graspable_filter'] += 1

            def assigned_xy(end, distance, bearing_bin):
                sign = -1.0 if end == 'teal' else 1.0
                ex, ey = pose[0] + sign * abs(beam.grasps[0].grip_xyz[0]) * math.cos(a), \
                         pose[1] + sign * abs(beam.grasps[0].grip_xyz[0]) * math.sin(a)
                outward = a + (math.pi if end == 'teal' else 0.)
                br = outward + bearing_bin * math.pi / 4
                return [ex, ey], [ex + distance * math.cos(br), ey + distance * math.sin(br)], ex, ey, br, outward

            end1_xy, own, ex1, ey1, br1, outward1 = assigned_xy(end1, d1, bearing1)
            end2_xy, peer, ex2, ey2, br2, outward2 = assigned_xy(end2, d2, bearing2)
            points = [own, peer]
            bad = None
            for rid, p in zip(('r1', 'r2'), points):
                obj, gap = robot_gap(p)
                if gap < 0:
                    bad = (obj, gap, rid); break
                gap = math.dist(p, pose[:2]) - math.hypot(bhx, bhy) - radius
                if gap < 0:
                    bad = ('beam_1', gap, rid); break
            if bad:
                reject('robot_environment_overlap', bad[0], bad[1], robot=bad[2])
                continue
            stage_passes['robot_environment'] += 1
            gap = math.dist(own, peer) - 2 * radius
            if gap < 0:
                reject('robot_peer_overlap', 'r2', gap, robot='r1')
                continue
            stage_passes['robot_peer'] += 1
            roles = {'r1': end1, 'r2': end2}
            blocked = False
            for rid, p in zip(roles, points):
                sign = -1.0 if roles[rid] == 'teal' else 1.0
                target = [pose[0] + sign * abs(beam.grasps[0].grip_xyz[0]) * math.cos(a),
                          pose[1] + sign * abs(beam.grasps[0].grip_xyz[0]) * math.sin(a)]
                hit = next((j for j, rect in enumerate(rects) if segment_hits_rect(p, target, rect)), None)
                if hit is not None:
                    reject('initial_static_los', f'static_wall_{hit}', 0., robot=rid,
                           gap_scope='intersecting_center_ray')
                    blocked = True; break
            if blocked:
                continue
            stage_passes['initial_static_los'] += 1
            park = None
            for parking_trial in range(5000):
                p = [rng.uniform(bounds[0] + radius, bounds[1] - radius),
                     rng.uniform(bounds[2] + radius, bounds[3] - radius)]
                obj, gap = robot_gap(p)
                gaps = [(obj, gap), ('r1', math.dist(p, own) - 2 * radius),
                        ('r2', math.dist(p, peer) - 2 * radius),
                        ('beam_1', math.dist(p, pose[:2]) - math.hypot(bhx, bhy) - radius)]
                if min(g for _, g in gaps) >= 0:
                    park = p; break
                obj, gap = min(gaps, key=lambda v: v[1])
                rejected.append(dict(proposal=attempts, population='parking_trials', trial=parking_trial,
                                     reason_category='parking_overlap', blocked_object=obj, min_gap_m=gap))
            if park is None:
                raise ValueError('parking computation budget exhausted')
            stage_passes['parking'] += 1
            ownyaw = outward1 + yaw1 * math.pi / 4
            peeryaw = outward2 + yaw2 * math.pi / 4
            episode = dict(
                episode_id=f'beamact5-wide-{seed + i}', batch='beamact5-wide-gate40',
                seed=seed + i, split='wide_gate40',
                scenario_id=scenario['scenario_id'], scenario_source_sha256=hashlib.sha256(data).hexdigest(),
                map_id=scenario['map_id'], cargo_scene='cargo_v7', scene_profile=SCENE_PROFILE,
                beam_pose=pose,
                spawns={'r1': [*own, .032355118817659255, ownyaw],
                        'r2': [*peer, .032355118817659255, peeryaw],
                        'r3': [*park, .032355118817659255, 0.]},
                roles=roles, target_item='beam_1', object_kind='long_beam',
                assignment_source='demo_rule_color_balanced', end_color_scene='grasp_act_teal_blue_v1',
                peer_case='wide_pair_start_v1',
                initial_pan={r: rng.randint(500, 2500) for r in roles},
                burst_ticks=1 + i % 12, proposal_attempts=attempt + 1,
                start_layers={'r1': dict(layer=layer1['id'], target_distance_m=d1,
                                         yaw_bin=dict(index=yaw1, offset_rad=yaw1 * math.pi / 4),
                                         bearing_bin=dict(index=bearing1, angle_rad=br1)),
                              'r2': dict(layer=layer2['id'], target_distance_m=d2,
                                         yaw_bin=dict(index=yaw2, offset_rad=yaw2 * math.pi / 4),
                                         bearing_bin=dict(index=bearing2, angle_rad=br2))},
                assigned_end_xy={'r1': end1_xy, 'r2': end2_xy})
            if stance_report is not None:
                episode.update(setup_validity=validity_meta['mode'], placement_validity=stance_report)
            episodes.append(episode)
            accepted = True
            break
        if not accepted:
            counts = Counter((r['reason_category'], r['blocked_object']) for r in rejected)
            partial = dict(schema='ugrp.beamact5.wide_setup_funnel.v1', status='proposal_budget_exhausted',
                           funnel=[], rejections=rejected, proposal_count=attempts,
                           exhausted_run=i, exhausted_seed=seed + i,
                           reason_counts={f'{k[0]}|{k[1]}': v for k, v in counts.items()},
                           scope='static initialization only; finite strata and enclosures do not prove physical success')
            dump(output / 'wide-setup-funnel.json', partial)
            raise ValueError(f'finite setup proposal budget exhausted for run {i}: {partial["reason_counts"]}')

    stages = ['beam_static', 'beam_cargo']
    if validity is not None:
        stages.append('placement_graspable_filter')
    stages += ['robot_environment', 'robot_peer', 'initial_static_los', 'parking']
    entered = attempts
    funnel = []
    for stage in stages:
        passed = stage_passes[stage]
        funnel.append(dict(gate=stage, entered=entered, passed=passed, rejected=entered - passed))
        entered = passed
    plan = dict(schema='ugrp.beamact5.wide_gate_setup.v1', episodes=episodes,
                training_rgb=False, setup_only=True, physical_success_verified=False,
                proposal_count=attempts, setup_validity=validity_meta['mode'] if validity is not None else 'off',
                seed=seed, gate_N=GATE_N, min_success=MIN_SUCCESS,
                scenario_source_sha256=hashlib.sha256(data).hexdigest(),
                placement_validity=validity_meta)
    dump(output / 'wide-gate-plan.json', plan)
    # The frozen runner contract is a top-level list [{plan, profile, candidate}].
    cases = [
        dict(plan=e, profile=dict(scene_profile=SCENE_PROFILE, held_object='hidden_v1',
                                  teacher_visibility='visible_only', top_camera_control=False),
             candidate=(candidate if candidate is not None else
                        f"wide_start_{e['start_layers']['r1']['layer']}_{e['seed']}"))
        for e in episodes]
    dump(output / 'wide-cases.json', cases)
    dump(output / 'wide-setup-funnel.json', dict(
        schema='ugrp.beamact5.wide_setup_funnel.v1', funnel=funnel, rejections=rejected,
        proposal_count=attempts, source_scenario_sha256=hashlib.sha256(data).hexdigest(),
        scope='static initialization only; finite strata and enclosures do not prove physical success',
        reproduce=f'python {Path(__file__)} --seed {seed} --output {output} --dependency-root {dependency} --frozen-root {frozen_root}'))

    # Actual distribution, recomputed from the immutable spawns.
    def q(values):
        values = sorted(values)
        if not values:
            return None
        return dict(min=values[0], p25=values[len(values)//4], p50=values[len(values)//2],
                    p75=values[(3*len(values))//4], max=values[-1], N=len(values))
    dist = dict(schema='ugrp.beamact5.wide_distribution.v1', planned_runs=GATE_N,
                completed_setup_runs=len(episodes), min_success=MIN_SUCCESS,
                layers={}, roles=Counter(), ends=Counter(), yaw_bins=Counter(), bearing_bins=Counter())
    for r in LAYERS:
        dist['layers'][r['id']] = dict(planned_runs=4, planned_robot_starts=8, actual_runs=0,
                                       actual_robot_starts=0, distances_m=[])
    for e in episodes:
        for rid in ('r1', 'r2'):
            s = e['start_layers'][rid]
            d = math.dist(e['spawns'][rid][:2], e['assigned_end_xy'][rid])
            layer = dist['layers'][s['layer']]
            layer['actual_robot_starts'] += 1
            layer['distances_m'].append(d)
            if rid == 'r1':
                layer['actual_runs'] += 1
            dist['roles'][rid] += 1
            dist['ends'][e['roles'][rid]] += 1
            dist['yaw_bins'][s['yaw_bin']['index']] += 1
            dist['bearing_bins'][s['bearing_bin']['index']] += 1
    for r in dist['layers'].values():
        r['distance_summary'] = q(r.pop('distances_m'))
    all_d = [math.dist(e['spawns'][rid][:2], e['assigned_end_xy'][rid]) for e in episodes for rid in ('r1', 'r2')]
    dist['all_assigned_end_distance_m'] = q(all_d)
    dist['denominators'] = dict(gate_runs=GATE_N, robot_starts=2 * GATE_N,
                                per_layer_runs=4, per_layer_robot_starts=8)
    dist['role_counts'] = dict(dist['roles'])
    dist['end_counts'] = dict(dist['ends'])
    dist['yaw_bin_counts'] = {str(k): v for k, v in sorted(dist['yaw_bins'].items())}
    dist['bearing_bin_counts'] = {str(k): v for k, v in sorted(dist['bearing_bins'].items())}
    dump(output / 'wide-distribution.json', dist)
    print(json.dumps(dict(planned_N=len(episodes), proposals=attempts, rejections=len(rejected),
                          output=str(output), cases_sha256=digest(output / 'wide-cases.json'))))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed', type=int, default=8420000)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--dependency-root', type=Path, required=True)
    p.add_argument('--frozen-root', type=Path, required=True)
    p.add_argument('--no-setup-validity', action='store_true')
    p.add_argument('--candidate', help='runner case candidate; default keeps the historical unused label')
    a = p.parse_args()
    generate(a.seed, a.output, a.dependency_root, a.frozen_root,
             setup_validity=not a.no_setup_validity, candidate=a.candidate)
