"""Build configs/zone_study_scenarios_v5 from the eight v4 scenarios (tri_frame removed).

User 2026-10-14: "3명이서 하는 짐은 뺴주라". v5 = v4 with no three-robot cargo.
* s1-s6: only ``scenario_id`` (_v4 -> _v5) changes.
* s7: ``s7_trio_rendezvous_v4`` becomes ``s7_pair_with_solo_v5``. The tri_frame order-1 is replaced by one
  heavy_crate (2 robots) at the same slot/pose; the two single-robot orders stay. The third robot takes the solo cargo.
* s8: the tri_frame order-4 and its placement are removed.
v4 files are never edited; an existing v5 file is never overwritten with different content.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V4 = ROOT / 'configs' / 'zone_study_scenarios_v4'
V5 = ROOT / 'configs' / 'zone_study_scenarios_v5'
S7_V4, S7_V5 = 's7_trio_rendezvous_v4', 's7_pair_with_solo_v5'


def _s7(out: dict) -> dict:
    out['scenario_id'] = S7_V5
    order = out['orders'][0]
    assert order['kind'] == 'tri_frame' and order['required_robots'] == 3
    order['kind'] = 'heavy_crate'
    order['required_robots'] = 2
    order['item_ids'] = ['crate_1']
    place = out['eval']['setup']['placements'][0]
    assert place['kind'] == 'tri_frame'
    place['item_id'] = 'crate_1'
    place['kind'] = 'heavy_crate'
    place['notes_ko'] = 'west/east 두 lug를 동서로 두어 2대가 마주 보고 든다. 문 앞을 막지 않도록 문에 가장 가까운 슬롯 안쪽에 둔다.'
    ev = out['eval']
    ev['design_notes_ko'] = ('2대 운반과 단독 운반이 동시에 있다. heavy_crate(2대 필요) 하나와 단독 주문 두 건이고, '
                             '로봇 3대 중 2대가 화물을 함께 드는 동안 남은 1대가 단독 주문을 맡는다. '
                             '3대 공동 운반 화물은 2026-10-14 사용자 결정으로 연구에서 뺐다(v4 s7의 tri_frame을 heavy_crate로 바꿨다).')
    ev['tests_ko'] = ('짝 짓기와 역할 분담: 누가 누구와 크레이트를 들고, 남은 한 대는 어느 단독 주문을 먼저 할지 합의해야 한다. '
                      '한 대라도 늦으면 짝이 기다린다. 무통신은 관례(정거장 채우기)로만 결속한다.')
    ev['notes_ko'] = ('숨은 사건은 없다(구조적 조건). 크레이트 경로는 harness.zone_scenario_feasibility로 오프라인 확인한다. '
                      '실제 2대 크레이트 자기 카메라 운반 실행기는 별도로 검증해야 한다. v4 결과와 합치지 않는다.')
    return out


def _s8(out: dict) -> dict:
    out['scenario_id'] = 's8_mixed_tiers_v5'
    out['orders'] = [o for o in out['orders'] if o['kind'] != 'tri_frame']
    pl = out['eval']['setup']['placements']
    out['eval']['setup']['placements'] = [p for p in pl if p['kind'] != 'tri_frame']
    ev = out['eval']
    ev['design_notes_ko'] = ('두 종류(1대·2대)가 한 시행에 섞인다. 이인 운반 중에는 한 대만 남는다. '
                             '누구를 어느 작업에 붙이고 어떤 순서로 할지가 시행의 핵심이다. '
                             '3대 공동 운반 화물(tri_frame)은 2026-10-14 사용자 결정으로 뺐다.')
    ev['tests_ko'] = ('팀 크기 배정: 두 대 편대와 단독 작업의 순서와 인원 배분을 합의하는 비용. '
                      '통신이 없으면 각자 같은 관례를 가정해야 하고, 어긋나면 짝이 덜 모인 채 대기한다.')
    ev['notes_ko'] = ('숨은 사건은 없다(구조적 조건). 큰 물건 경로는 오프라인 경로 검사로 확인한다. '
                      '2대 크레이트 자기 카메라 운반 실행기는 별도로 검증해야 한다. v4 결과와 합치지 않는다.')
    return out


def convert(v4: dict) -> dict:
    out = copy.deepcopy(v4)
    sid = out['scenario_id']
    assert sid.endswith('_v4'), sid
    if sid == S7_V4:
        return _s7(out)
    if sid == 's8_mixed_tiers_v4':
        return _s8(out)
    out['scenario_id'] = sid[:-3] + '_v5'
    return out


def main() -> int:
    V5.mkdir(exist_ok=True)
    for path in sorted(V4.glob('*.json')):
        value = convert(json.loads(path.read_text()))
        target = V5 / f"{value['scenario_id']}.json"
        if target.exists() and json.loads(target.read_text()) != value:
            print(f'refusing to change existing {target.name}', file=sys.stderr)
            return 1
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        print('wrote', target.name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
