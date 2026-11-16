"""Two robots act in ONE world at the same time (development run).

Each robot runs the unchanged Solo sequence on its own box (look around, approach, square up, ACT grasp, carry through
the door to a floor-colour zone, code release). They share one door. The order at the door is FIXED here, not planned:
the second robot stands still with its box held until the first robot says that its carry has ended. That message is
the only thing passed between them; nothing measured is passed.

Task definition (evaluation side, not a robot input): which second box, where the second robot starts.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path

from harness.grasp_act_data import write_json
import scripts.run_grasp_act_student as solo

ROOM = (-1.05, 2.2, -3.15, 1.45)   # pickup room x0, x1, y0, y1 (task definition)
BOX_KINDS = ('cyan', 'red')   # kinds whose look-around name equals the task name (a 'green' object is drawn red)


def second_task(plan, objects, item=None):
    """Pick the second robot's box and a start pose facing it, clear of everything else. Returns (item_id, spawn)."""
    first = objects[plan['item_id']]['position_m'][:2]
    start = plan['spawns'][plan['robot_id']][:2]
    boxes = {k: v for k, v in objects.items() if v.get('kind') in BOX_KINDS and k != plan['item_id']
             and ROOM[0] + .35 < v['position_m'][0] < ROOM[1] - .35 and ROOM[2] + .35 < v['position_m'][1] < ROOM[3] - .35}
    if item is not None:
        boxes = {item: boxes[item]}
    best = None
    for key, box in sorted(boxes.items()):
        b = box['position_m'][:2]
        if math.dist(b, first) < 1.0:
            continue
        for step in range(24):
            angle = step * math.pi / 12
            pose = (b[0] + .75 * math.cos(angle), b[1] + .75 * math.sin(angle))
            if not (ROOM[0] + .40 < pose[0] < ROOM[1] - .40 and ROOM[2] + .40 < pose[1] < ROOM[3] - .40):
                continue
            others = [v['position_m'][:2] for k, v in objects.items() if k != key and 'position_m' in v]
            gap = min([math.dist(pose, o) for o in others] + [9.])
            if gap < .55 or math.dist(pose, start) < 1.2 or math.dist(pose, first) < 1.0:
                continue
            # prefer a start far from the first robot and from its box
            score = min(math.dist(pose, start), math.dist(pose, first)) + .3 * gap
            if best is None or score > best[0]:
                best = (score, key, [pose[0], pose[1], plan['spawns'][plan['robot_id']][2], angle + math.pi - .1])
    if best is None:
        raise ValueError('no second box with a free start pose in the pickup room')
    return best[1], best[2]


def run_duo(plan, protocol, model, output, *, first_to, second_to, second_item=None, scene_without=(), **kw):
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    objects = ScenarioFinalV3Scene.from_scenario(plan['scenario_id'], plan['seed']).config['setup_only']['objects']
    first_id = plan['robot_id']
    second_id = 'r2' if first_id != 'r2' else 'r3'
    item, spawn = second_task(plan, objects, second_item)
    box = objects[item]
    plan_a = dict(plan, spawns=dict(plan['spawns'], **{second_id: spawn}))
    plan_b = dict(plan_a, robot_id=second_id, item_id=item, object_kind=box['kind'],
                  target_setup_xy=list(box['position_m'][:2]),
                  cargo_pose_m=list(box['position_m'][:2]) + [0.],
                  start_to_cargo_m=math.dist(spawn[:2], box['position_m'][:2]))
    shared = {'robots': (first_id, second_id)}
    events = {first_id: {}, second_id: {}}
    record = {'schema': 'ugrp.solo.duo.v1', 'seed': plan['seed'], 'robots': [first_id, second_id],
              'first': {'item': plan['item_id'], 'to': first_to}, 'second': {'item': item, 'to': second_to, 'spawn': spawn},
              'door_order': 'fixed: the second robot starts to carry only after the first says its carry has ended',
              'scene_without': list(scene_without), 'status': 'running'}
    write_json(output / 'duo.json', record)
    steps = {
        first_id: solo.run_steps(plan_a, protocol, model, output / ('out-' + first_id), carry_to=first_to, shared=shared,
                                 events=events[first_id], scene_without=scene_without, **kw),
        second_id: solo.run_steps(plan_b, protocol, model, output / ('out-' + second_id), carry_to=second_to, shared=shared,
                                  events=events[second_id], scene_without=scene_without,
                                  carry_gate=lambda: 'carry_finished' in events[first_id], **kw)}
    requests, reports = {}, {}
    try:
        for rid in (first_id, second_id):      # the first call builds the world, the second borrows it
            requests[rid] = next(steps[rid])
        world = shared['world']
        while requests:
            until = min(r['until'] for r in requests.values())
            solo.advance_physics(world, list(requests.values()), until)
            for rid in [r for r in (first_id, second_id) if r in requests and requests[r]['until'] <= until + 1e-8]:
                try:
                    requests[rid] = next(steps[rid])
                except StopIteration as stop:
                    reports[rid] = stop.value
                    del requests[rid]
        record['status'] = 'complete'
    finally:
        for gen in steps.values():
            gen.close()
        if 'world' in shared:
            shared['world'].close()
        record.update(events=events, finished=sorted(reports))
        write_json(output / 'duo.json', record)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--actor-python', required=True)
    p.add_argument('--cap-s', type=float, default=420.)
    p.add_argument('--actor-threads', type=int, default=2)
    p.add_argument('--first-to', default='zone_blue')
    p.add_argument('--second-to', default='zone_orange')
    p.add_argument('--second-item')
    p.add_argument('--scene-without', default='beam,can,tile,frame,crate,robots')
    p.add_argument('--scene-source', type=Path, required=True)
    a = p.parse_args()
    from scripts.run_grasp_act_recovery import dependency_modules
    with dependency_modules(a.scene_source):
        run_duo(json.loads(a.plan.read_text()), json.loads(a.protocol.read_text()), a.model, a.output,
                first_to=a.first_to, second_to=a.second_to, second_item=a.second_item,
                scene_without=tuple(k for k in a.scene_without.split(',') if k),
                actor_python=a.actor_python, cap_s=a.cap_s, n_action_steps=8, actor_threads=a.actor_threads,
                teacher_start_v1=True, grasp_transition_rule=True, approach_survey_v1=True)


if __name__ == '__main__':
    main()
