"""Opt-in v7: copy v6, replacing every heavy crate with one two-carrier beam.

Keep all slots/centres, orders/counts/destinations, events, budgets and seeds.
The beam yaw follows the existing long_beam placements (north/south, 1.5708).
No simulator imports. Never change v6 or overwrite a different v7 config.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V6 = ROOT / 'configs/zone_study_scenarios_v6'
V7 = ROOT / 'configs/zone_study_scenarios_v7'


def convert(source):
    out = copy.deepcopy(source)
    assert out['scenario_id'].endswith('_v6')
    out['scenario_id'] = out['scenario_id'][:-3] + '_v7'
    placements = out['eval']['setup']['placements']
    used_ids = {p['item_id'] for p in placements}
    for order in out['orders']:
        if order['kind'] != 'heavy_crate':
            continue
        assert order['required_robots'] == 2
        order['kind'] = 'long_beam'
        renamed = {}
        for p in placements:
            if p['order_id'] != order['order_id']:
                continue
            assert p['kind'] == 'heavy_crate'
            suffix = 1
            while f'beam_{suffix}' in used_ids:
                suffix += 1
            new_id = f'beam_{suffix}'
            used_ids.add(new_id)
            renamed[p['item_id']] = new_id
            p.update(item_id=new_id, kind='long_beam')
            p['pose_m'][2] = 1.5708
            p['notes_ko'] = '기존 long_beam과 같은 남북 축 배치. end_neg/end_pos를 두 로봇이 나눠 든다.'
        if 'item_ids' in order:
            order['item_ids'] = [renamed[item_id] for item_id in order['item_ids']]
    private = out['eval']
    if source['scenario_id'] == 's7_pair_with_solo_v6':
        private['design_notes_ko'] = ('2대 운반과 단독 운반이 동시에 있다. long_beam(2대 필요) 하나와 '
            '단독 주문 두 건이며, 로봇 3대 중 2대가 빔을 함께 드는 동안 남은 1대가 단독 주문을 맡는다. '
            'v7은 무거운 상자 제외 결정에 따른 별도 시나리오이며 v6 결과와 합산하지 않는다.')
    if source['scenario_id'] == 's8_mixed_tiers_v6':
        private['notes_ko'] = ('숨은 사건은 없다(구조적 조건). v7은 두 로봇 화물을 long_beam으로 통일한다. '
            '정적 배치·목적 구역 적합성과 실제 자기 카메라 운반 성공은 별도 검증한다. '
            'v6 이전 결과와 합산하지 않는다.')
    return out


def main():
    V7.mkdir(exist_ok=True)
    for source in sorted(V6.glob('*.json')):
        scenario = convert(json.loads(source.read_text()))
        target = V7 / (scenario['scenario_id'] + '.json')
        content = json.dumps(scenario, ensure_ascii=False, indent=2) + '\n'
        if target.exists() and target.read_text() != content:
            raise ValueError(f'refusing to change existing {target}')
        target.write_text(content)
        print(target.name)


if __name__ == '__main__':
    main()
