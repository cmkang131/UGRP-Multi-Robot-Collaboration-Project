"""Preparation invariants; no policy, MuJoCo rollout or held-out tuning."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from harness import zone_heldout_maps as hm
from scripts import prepare_zone_heldout as prep
from sim.zone_heldout_scene import install


def base():
    return json.loads((hm.MAP_DIR/(hm.BASE_ID+'.json')).read_text())


@pytest.mark.parametrize('map_id', hm.IDS)
def test_frozen_geometry_goals_cameras_and_cues(map_id):
    b, v = base(), hm.load(map_id)
    for k in ('bounds_m', 'top_cameras', 'regions', 'zone_slots', 'wall_profile',
              'robot_model', 'base_map', 'parent_scene', 'approach_convention'):
        assert v[k] == b[k]
    assert v['obstacles'][:4] == b['obstacles'][:4]
    assert not v['heldout']['development_use']
    for o in v['obstacles']:
        assert o['height_m'] == .4
        # No new wall hides any painted region or its border.
        x,y = o['center_m']; hx,hy = o['half_extents_m']
        for r in v['regions'].values():
            rx,ry = r['center_m']; rhx,rhy = r['half_extents_m']
            assert abs(x-rx) > hx+rhx or abs(y-ry) > hy+rhy
    old, new = prep.cues(b), prep.cues(v)
    for key in ('color_regions','color_boundary_m','wall_tapes','wall_patches','tapes_per_arena_m2'):
        assert new[key] >= old[key]


@pytest.mark.parametrize('map_id', hm.IDS)
def test_every_start_reaches_every_goal_with_continuous_clearance(map_id):
    result = prep.static_check(hm.load(map_id))
    assert result['reachable_pairs'] == 48
    assert all(p['continuous_swept_aabb_clear'] for goals in result['paths'].values() for p in goals.values())
    if map_id == hm.IDS[0]:
        assert len(result['alternative_routes']) == 2


def test_blocked_arena_and_blocked_endpoint_rejected():
    v = hm.load(hm.IDS[1])
    for door in v['passages']:
        v['obstacles'].append(dict(id='seal_'+door['id'], center_m=door['center_m'],
            half_extents_m=door['half_extents_m'], height_m=.4, kind='wall'))
    with pytest.raises(ValueError, match='NO_STATIC_PATH'):
        prep.plan_all(v, [0.,-.85], {'B': [4.6,-2.1]}, 0.)
    with pytest.raises(ValueError, match='blocked authored endpoint'):
        prep.plan_all(v, [2.2,-2.], {'B': [4.6,-2.1]}, 0.)


def test_rigid_reuse_and_exact_56cm_door():
    value = hm.load(hm.IDS[1])
    for row in value['heldout']['geometry_sources']:
        source = json.loads((hm.ROOT/row['file']).read_text())
        assert hm.sha(hm.ROOT/row['file']) == row['sha256']
        for obs in source['obstacles']:
            actual = next(o for o in value['obstacles'] if o['id']=='wall_h2_'+obs['id'])
            assert actual['half_extents_m'] == obs['half_extents_m']
            assert actual['center_m'] == [row['x_scale']*obs['center_m'][0]+row['translation_m'][0],
                                         obs['center_m'][1]+row['translation_m'][1]]
    lower = next(o for o in value['obstacles'] if o['id']=='wall_h2_door_lower')
    upper = next(o for o in value['obstacles'] if o['id']=='wall_h2_door_upper')
    assert (upper['center_m'][1]-upper['half_extents_m'][1] -
            lower['center_m'][1]-lower['half_extents_m'][1]) == pytest.approx(.56)


def test_adapter_off_identity_and_explicit_standard_scene():
    sentinel = object()
    assert install(sentinel) is sentinel
    with pytest.raises(ValueError, match='REQUIRES_BASE'):
        install(sentinel, heldout_map=hm.IDS[0])
    from sim.zone_final_v3_scene import FinalV3Scene
    scene = FinalV3Scene.from_spec(dict(map=hm.BASE_ID, seed=11, goal={'B':{'cyan':1}}), 'local_contact_fine')
    prior = copy.deepcopy(scene.config)
    assert install(scene) is scene and scene.config == prior
    install(scene, heldout_map=hm.IDS[0])
    assert scene.config['setup_only'] == prior['setup_only']
    assert scene.config['static_map'] == hm.load(hm.IDS[0])


def test_wall_texture_copy_and_off_are_exact():
    receipt = json.loads((prep.EXP/'texture-source.json').read_text())
    assert hm.sha(hm.ROOT/receipt['vendored_path']) == receipt['sha256']
    xml = '<mujoco>\n  </mujoco>'
    assert prep.texture.transform_xml(xml) == xml
    baseline = prep.texture.layout(sorted(prep.walls(base()), key=lambda w:w['name']))
    h1 = prep.texture.layout(sorted(prep.walls(hm.load(hm.IDS[0])), key=lambda w:w['name']))
    original = {f['id']: f for f in baseline['faces']}
    assert all(f == original[f['id']] for f in h1['faces'] if f['id'] in original)
