"""Copy v5 to v6 with can/tile replaced by the existing small colour boxes.

Process orders in file order, choosing the least-used colour by item count;
zero counts win first. Ties use cyan, red, green, yellow. Update counts after
each replacement. Item identifiers and their references follow the new colour.
Never edit v5 or overwrite a different existing v6 config.
"""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
V5 = ROOT / 'configs/zone_study_scenarios_v5'
V6 = ROOT / 'configs/zone_study_scenarios_v6'
BOX_KINDS = ('cyan', 'red', 'green', 'yellow')
RETIRED = ('can', 'tile')


def convert(source):
    out = copy.deepcopy(source)
    assert out['scenario_id'].endswith('_v5')
    out['scenario_id'] = out['scenario_id'][:-3] + '_v6'
    placements = out['eval']['setup']['placements']
    counts = Counter(p['kind'] for p in placements if p['kind'] in BOX_KINDS)
    used_ids = {p['item_id'] for p in placements}
    replacements, id_map, kind_map = [], {}, {}
    for order in out['orders']:
        old_kind = order['kind']
        if old_kind not in RETIRED:
            continue
        colour = min(BOX_KINDS, key=lambda k: counts[k])
        counts[colour] += order['count']
        order['kind'] = colour
        kind_map[old_kind] = colour
        item_map = {}
        for p in placements:
            if p['order_id'] != order['order_id']:
                continue
            assert p['kind'] == old_kind
            old_id = p['item_id']
            suffix = 1
            while f'{colour}_{suffix}' in used_ids:
                suffix += 1
            new_id = f'{colour}_{suffix}'
            used_ids.add(new_id)
            p['kind'], p['item_id'] = colour, new_id
            id_map[old_id] = item_map[old_id] = new_id
        if 'item_ids' in order:
            order['item_ids'] = [id_map.get(i, i) for i in order['item_ids']]
        replacements.append({'scenario_id': out['scenario_id'], 'order_id': order['order_id'],
                             'old_kind': old_kind, 'new_kind': colour, 'item_ids': item_map,
                             'destination_zone': order['destination_zone'],
                             'initial_location': copy.deepcopy(order['initial_location'])})

    # Preserve event actions/times/poses; only renamed identifiers follow their
    # physical item. Also keep private narrative references consistent (s6).
    def references(value):
        if isinstance(value, dict):
            return {k: references(v) for k, v in value.items()}
        if isinstance(value, list):
            return [references(v) for v in value]
        if isinstance(value, str):
            for old, new in id_map.items():
                value = value.replace(old, new)
            for old, new in kind_map.items():
                value = re.sub(r'(?<![A-Za-z0-9_])' + old + r'(?![A-Za-z0-9_])', new, value)
        return value

    out = references(out)
    orders = {o['order_id']: o for o in out['orders']}
    groups = {}
    for p in out['eval']['setup']['placements']:
        if p['kind'] in BOX_KINDS:
            zone = orders[p['order_id']]['destination_zone']
            groups.setdefault((p['kind'], zone), []).append(p['item_id'])
    collisions = [{'kind': kind, 'destination_zone': zone, 'item_ids': items}
                  for (kind, zone), items in sorted(groups.items()) if len(items) > 1]
    for row in replacements:
        row['same_colour_same_zone'] = next((g for g in collisions
            if (g['kind'], g['destination_zone']) == (row['new_kind'], row['destination_zone'])), None)
    return out, replacements, collisions


def main():
    V6.mkdir(exist_ok=True)
    replacements, collisions = [], []
    for path in sorted(V5.glob('*.json')):
        out, rows, groups = convert(json.loads(path.read_text()))
        target = V6 / f"{out['scenario_id']}.json"
        content = json.dumps(out, ensure_ascii=False, indent=2) + '\n'
        if target.exists() and target.read_text() != content:
            raise ValueError(f'refusing to change existing {target.name}')
        target.write_text(content)
        replacements.extend(rows)
        collisions.extend({'scenario_id': out['scenario_id'], **g} for g in groups)
        print(target.name)
    report = {'colour_tie_order': list(BOX_KINDS), 'collision_scope': 'same colour + destination zone',
              'replacements': replacements, 'collisions': collisions}
    (Path(__file__).parent / 'replacements.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
