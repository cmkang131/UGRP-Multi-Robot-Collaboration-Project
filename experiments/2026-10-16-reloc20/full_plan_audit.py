"""gcp2-only retrospective audit of all five complete placement plans.

Uses the first held travel frame's own estimate/command FK/RGB memory and
authored map. No evaluator pose/contact enters these planning queries.
Separate from control: does not authorize or execute another physics round.
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

R = Path('/home/ugrp/ugrp-sim/runs')


def read(p):
    return p.read_bytes() if p.exists() else subprocess.check_output(['zstd', '-dc', str(p)+'.zst'])


def main(n):
    assert platform.node().startswith('ugrp-sim-gcp2')
    batch = R/f'reloc20-round{n}'
    assert (batch/'DONE').exists()
    queue = json.loads(read(batch/'queue.json'))
    source = R.parent/'src'/queue['source_sha']
    sys.path.insert(0, str(source))
    from harness.reloc20_motion import LoadedRoute
    from harness.visual_arm_v3 import forward_grip
    from sim.solo_carry_obstacles import RGBObstacleMemory
    output = []
    for task in queue['runs']:
        if task['kind'] != 'carry' or task['condition'] == 'baseline':
            continue
        raw = Path(task['raw'])
        if json.loads(read(raw/'result.json')).get('status') == 'HOST_ERROR':
            continue
        commands = [json.loads(x) for x in read(raw/'teacher-commands.jsonl').splitlines()]
        first = next((x for x in commands if x.get('phase_before', x['phase']) == 'carry_to_zone'), None)
        if first is None:
            output.append(dict(run=task['name'], status='travel_not_reached'))
            continue
        plan = json.loads(read(raw/'plan.json'))
        static = json.loads(read(raw/'carry-static-map.json'))
        low = {int(k): v for k, v in next(x['command']['pwm'] for x in commands if x['phase'] == 'close').items()}
        grip = forward_grip(low)
        route = LoadedRoute(static)
        route.update_load(True, plan['kind'], low, {int(k): v for k, v in first['command']['pwm'].items()})
        memory = RGBObstacleMemory()
        memory.tracks = first['carry_obstacles']['tracks']
        discs = memory.discs(first['t'])  # preserve existing stale-peer inflation
        route.disc_names = [f"own_rgb_{o['kind']}_track_{o.get('id', i)}" for i, o in enumerate(memory.tracks)]
        start = first['map_pose']['pose_estimate'][:2]
        cx, cy = static['regions']['zone_'+plan['destination_zone']]['center_m']
        hx, hy = static['regions']['zone_'+plan['destination_zone']]['half_extents_m']
        records = []
        # Exact existing CarryToZone five slots, advance and retreat distances.
        for sx, sy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            slot = (cx+sx*max(0., hx-.20), cy+sy*max(0., hy-.20))
            goal = (slot[0]-grip[0]-.15, slot[1]-grip[1])
            final = (goal[0]+.15, goal[1])
            retreat = (final[0]-.15, final[1])
            checks = [route.segment(a, b, discs) for a, b in ((goal, goal), (goal, final), (final, retreat))]
            path = route.plan(start, goal, static['bounds_m'], discs)
            edges = [route.segment(a, b, discs) for a, b in zip(path, path[1:])] if path else []
            accepted = path is not None and all(ok for ok, _ in checks+edges)
            if accepted:
                context = min((c for _, c in checks+edges), key=lambda x: x['minimum_gap_m'])
            elif path is None:
                context = dict(route.last)
            else:
                context = min((c for ok, c in checks if not ok), key=lambda x: x['minimum_gap_m'])
            records.append(dict(slot=slot, goal=goal, final=final, retreat=retreat, accepted=accepted,
                                checked_route_edges=len(edges), path=path, context=context))
        output.append(dict(run=task['name'], source_sha=task['source_sha'], raw=str(raw), frame_t=first['t'],
                           source_commands_decoded_sha256=hashlib.sha256(read(raw/'teacher-commands.jsonl')).hexdigest(),
                           radius_m=route.radius, load_corners=route.footprint, start=start,
                           cumulative=dict(slot_candidates=5, complete_plan_clear=sum(x['accepted'] for x in records)),
                           records=records))
    result = dict(scope='offline full-plan geometry only, own estimated frame; no physical arrival/success guarantee',
                  controller_source_sha=queue['source_sha'], analysis_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  reproduce=f'{sys.executable} {__file__} --round {n}', runs=output)
    (batch/'full-plan-audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps([dict(run=x['run'], cumulative=x.get('cumulative'), status=x.get('status')) for x in output]))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--round', type=int, required=True)
    main(p.parse_args().round)
