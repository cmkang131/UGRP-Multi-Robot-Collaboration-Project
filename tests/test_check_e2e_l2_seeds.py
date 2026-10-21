"""L2 seeds: 0 overlap with every registered range, pinned to pairact-r1 v2 seeds.json."""
import json

from scripts import check_e2e_l2_seeds as chk

PAIRACT_REF = 'bcfefaadc5ecbc24a65f898e44eabcdf886f7ef5'   # dsh/pairact-carry-r1-v2 (pilot 8343000-8343039)


def spec():
    return json.loads(chk.DEFAULT.read_text())


def test_l2_range_is_8344000_up_and_disjoint():
    s = spec()
    assert s['l2']['first'] == 8344000 and s['l2']['last'] == 8344099
    assert chk.check(s) == []


def test_required_ranges_are_registered():
    names = {r['name']: (r['first'], r['last']) for r in spec()['registered_ranges']}
    assert names['pairact_r1_train'][0] == 8340000 and names['pairact_r1_train_extension'][1] == 8340599
    assert names['pairact_r1_validation'] == (8341000, 8341019)
    assert names['pairact_r1_heldout'] == (8342000, 8342019)
    assert names['pairact_r1_pilot'] == (8343000, 8343039)


def test_pairact_v2_seeds_fully_covered():
    # fails (not skips) if the pinned commit is missing (repo audit ④)
    assert chk.drift(spec(), PAIRACT_REF) == []


def test_overlap_is_detected():
    s = spec()
    s['l2'] = {'first': 8343030, 'last': 8343050}
    assert any('pairact_r1_pilot' in p for p in chk.check(s))


def test_drift_is_detected():
    s = spec()
    s['registered_ranges'] = [r for r in s['registered_ranges'] if r['name'] != 'pairact_r1_pilot']
    assert any('pilot' in p for p in chk.drift(s, PAIRACT_REF))
