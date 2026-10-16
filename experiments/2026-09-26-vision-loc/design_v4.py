#!/usr/bin/env python3
"""Design-only VIS4 fresh-seed/path table, with no renderer or test scores."""
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from design_episodes_v3 import cyan_cell


def design():
    prior_files = [HERE/'episodes.json', HERE/'episodes_v3.json']
    tables = [json.loads(p.read_text()) for p in prior_files]
    prior = [e for t in tables for e in t['episodes']]
    used_seeds = {e['seed'] for e in prior}
    spawn_cell, cell_slot = set(), set()
    for e in prior:
        cell = tuple(e.get('cyan_cell', cyan_cell(e['seed'], e['goal'])))
        spawn_cell.add((e['spawn_y'], cell)); cell_slot.add((cell, e['slot_id']))
    # Fixed order, 8 primary and 4 reserve; no outcome-based route picking.
    assignments = [(.55,'C1'),(-.85,'B2'),(-2.25,'A3'),(.55,'B3'),
                   (-.85,'C2'),(-2.25,'A1'),(.55,'A2'),(-.85,'B1'),
                   (-2.25,'C3'),(.55,'A1'),(-.85,'C1'),(-2.25,'B2')]
    seeds, episodes, rejected = iter(range(1001, 2001)), [], []
    for i, (spawn, slot) in enumerate(assignments):
        goal = {slot[0]: {'cyan': 1}}
        for seed in seeds:
            cell = cyan_cell(seed, goal)
            if seed in used_seeds or (spawn, cell) in spawn_cell or (cell, slot) in cell_slot:
                rejected.append({'seed': seed, 'spawn_y': spawn, 'slot_id': slot, 'cyan_cell': list(cell)})
                continue
            spawn_cell.add((spawn, cell)); cell_slot.add((cell, slot)); used_seeds.add(seed)
            r = random.Random(f'vl4-{seed}')
            offset = [round(r.uniform(-.04,.06),4),round(r.uniform(-.08,.08),4),round(r.uniform(-6,6),3)]
            angle, radius = r.uniform(0, 2*math.pi), r.uniform(.012,.030)
            bias = [round(radius*math.cos(angle),4), round(radius*math.sin(angle),4), round(r.uniform(-1,1),3)]
            episodes.append({'episode_id': f'vl4-test-s{seed}', 'split': 'test',
                'role': 'primary' if i < 8 else 'reserve', 'seed': seed, 'spawn_y': spawn, 'slot_id': slot,
                'goal': goal, 'extra_boxes': {'red':2,'green':1}, 'cyan_cell': list(cell),
                'spawn_offset': offset, 'teacher_pose_bias': bias})
            break
        else:
            raise ValueError(f'seed range exhausted at assignment {i}; revise design BEFORE rendering')
    return {**{k:copy.deepcopy(tables[1][k]) for k in ('schema','base_map','map','controller')},
            'status':'DRAFT_DO_NOT_RENDER', 'episodes':episodes, 'rejected_seeds':rejected,
            'reference_metadata_sha256': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in prior_files},
            'reference_episode_ids':[e['episode_id'] for e in prior],
            'independence':'New seed and both route-pair keys unused in all old train/dev/test metadata. Rendered overlap audit still mandatory.',
            'rng':"random.Random('vl4-<seed>'); dx [-.04,.06], dy [-.08,.08], yaw [-6,6] deg; teacher bias radius [.012,.030], yaw [-1,1] deg"}


if __name__ == '__main__':
    out = HERE/'episodes_v4_DRAFT.json'
    with out.open('x') as f: json.dump(design(),f,indent=1); f.write('\n')
