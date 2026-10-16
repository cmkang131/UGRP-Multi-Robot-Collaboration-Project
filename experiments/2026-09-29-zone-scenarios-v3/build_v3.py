"""Build configs/zone_study_scenarios_v3 from the six v2 scenarios plus two cargo-tier scenarios.

v3 = v2's six scenarios (byte-identical except ``scenario_id``) + s7 (trio) and s8 (all tiers).
Existing files are never overwritten with different content.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / 'configs' / 'zone_study_scenarios_v2'
V3 = ROOT / 'configs' / 'zone_study_scenarios_v3'
TWO_DOORS_SHA = 'e93bce155c01aef3cc7c8418c4d921aee1e50b9539167fb7b9f94cdd2a29d888'
SUFFIX = '_v3'
BUDGET = {'sim_seconds': 1800, 'http_attempts_per_trial': 90, 'http_attempts_per_actor': 30,
          'output_tokens_per_call': 768}


def _order(index, kind, count, dest, slot, item_ids=None, robots=1):
    order = {'order_id': f'order-{index}', 'kind': kind, 'count': count,
             'identity': 'specific_item' if item_ids else 'kind_fungible',
             'required_robots': robots, 'destination_zone': dest,
             'initial_location': {'pickup_bay': slot.split('-')[0], 'slot': slot}}
    if item_ids:
        order['item_ids'] = item_ids
    return order


def _place(item_id, kind, order, slot, pose, note=None):
    out = {'item_id': item_id, 'kind': kind, 'order_id': f'order-{order}', 'slot': slot, 'pose_m': pose}
    if note:
        out['notes_ko'] = note
    return out


def _scenario(sid, seeds, orders, placements, design, tests, notes):
    return {'schema': 'ugrp.zone_scenario.v1', 'scenario_id': sid, 'map_id': 'zone_wide_two_doors_final_v1',
            'landmark_detail': 'none', 'seeds': seeds, 'orders': orders,
            'eval': {'schema': 'ugrp.zone_study_scenario_private.v1', 'design_notes_ko': design,
                     'tests_ko': tests, 'notes_ko': notes,
                     'setup': {'arena_variant': 'zone_wide_two_doors', 'map_file_sha256': TWO_DOORS_SHA,
                               'contact_profile': 'cargo_noslip_v1', 'weld': 'off',
                               'robot_spawns': 'arena_default', 'placements': placements},
                     'hidden_events': [], 'budget': dict(BUDGET)}}


def new_scenarios() -> dict:
    s7 = _scenario(
        's7_trio_rendezvous_v3', [661, 662, 663],
        [_order(1, 'tri_frame', 1, 'B', 'P2-1', ['frame_1'], robots=3),
         _order(2, 'cyan', 1, 'A', 'P1-3'), _order(3, 'tile', 1, 'C', 'P1-2')],
        [_place('frame_1', 'tri_frame', 1, 'P2-1', [1.275, -2.15, 0.0],
                '세 vertex lug가 각각 한 대의 집게 자리다. 문 앞을 막지 않도록 문에 가장 가까운 슬롯 안쪽에 둔다.'),
         _place('cyan_1', 'cyan', 2, 'P1-3', [0.125, 0.45, 0.0]),
         _place('tile_1', 'tile', 3, 'P1-2', [0.125, -0.85, 0.0])],
        '3대 동시 운반. tri_frame(1.5 kg, 세 대 필요)은 폭 0.889 m 편대로만 운반되므로 폭 1.0 m의 door_wide만 지날 수 있다. '
        '세 로봇이 모두 편대에 묶이는 동안 다른 주문은 진행되지 않는다.',
        '삼자 결속: 누가 어느 vertex를 잡고 언제 함께 드는지 합의해야 하고, 한 대라도 늦으면 나머지 둘이 기다린다. '
        '단독 주문 두 건을 편대 전후 어느 쪽에 처리할지도 순서 협상이다. 무통신은 관례(정거장 채우기)로만 결속한다.',
        '숨은 사건은 없다(구조적 조건). 문 통과 여유·편대 경로는 harness.zone_scenario_feasibility로 오프라인 확인했고 '
        '실제 3대 자기 카메라 운반 실행기는 아직 없다. 이 시나리오는 그 실행기가 준비되기 전에는 실행할 수 없다.')
    s8 = _scenario(
        's8_mixed_tiers_v3', [671, 672, 673],
        [_order(1, 'yellow', 2, 'A', 'P1-3'), _order(2, 'can', 1, 'C', 'P2-3'),
         _order(3, 'heavy_crate', 1, 'B', 'P1-1', ['crate_1'], robots=2),
         _order(4, 'tri_frame', 1, 'C', 'P2-1', ['frame_1'], robots=3)],
        [_place('yellow_1', 'yellow', 1, 'P1-3', [-0.2, 0.75, 0.0]),
         _place('yellow_2', 'yellow', 1, 'P1-3', [0.4, 0.75, 0.0]),
         _place('can_1', 'can', 2, 'P2-3', [1.275, 0.45, 0.0]),
         _place('crate_1', 'heavy_crate', 3, 'P1-1', [0.125, -2.15, 0.0],
                'west/east 두 lug를 동서로 두어 2대가 마주 보고 든다.'),
         _place('frame_1', 'tri_frame', 4, 'P2-1', [1.275, -2.15, 0.0])],
        '세 종류(1대·2대·3대)가 한 시행에 섞인다. 로봇은 3대뿐이라 삼자 운반 중에는 다른 일을 못 하고, 이인 운반 중에는 '
        '한 대만 남는다. 어떤 순서로 누구를 어느 작업에 붙일지가 시행의 핵심이다.',
        '팀 크기 배정: 세 대 편대·두 대 편대·단독 작업의 순서와 인원 배분을 합의하는 비용. 통신이 없으면 각자 같은 관례를 '
        '가정해야 하고, 어긋나면 편대가 덜 모인 채 대기한다.',
        '숨은 사건은 없다(구조적 조건). 두 큰 물건은 door_wide만 쓰는 것으로 가정하지 않고 오프라인 경로 검사로 확인했다. '
        '3대 자기 카메라 운반 실행기가 준비되기 전에는 실행할 수 없다.')
    return {s['scenario_id']: s for s in (s7, s8)}


def carried_forward() -> dict:
    out = {}
    for path in sorted(V2.glob('*.json')):
        value = copy.deepcopy(json.loads(path.read_text()))
        assert value['scenario_id'].endswith('_v2'), path
        value['scenario_id'] = value['scenario_id'][:-3] + SUFFIX
        out[value['scenario_id']] = value
    return out


def main() -> int:
    V3.mkdir(exist_ok=True)
    everything = {**carried_forward(), **new_scenarios()}
    for sid, value in everything.items():
        target = V3 / f'{sid}.json'
        text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if target.exists() and json.loads(target.read_text()) != value:
            print(f'refusing to change existing {target.name}', file=sys.stderr)
            return 1
        target.write_text(text)
        print('wrote', target.name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
