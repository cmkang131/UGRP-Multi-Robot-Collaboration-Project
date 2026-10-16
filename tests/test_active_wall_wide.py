import json
import numpy as np
import pytest
from harness.active_wall_mapping import ActiveMapper,OPTIONS
from harness.active_camera import SEARCH
from scripts.run_active_wall_wide import frozen_bundle,install_profile
from tests.test_self_map_prob import CORNER
from tests.test_wall_confidence import FEATURE


def test_profile_off_keeps_existing_bytes_and_frozen_physical_settings():
    a=ActiveMapper('r3',0.,SEARCH,active_mapping='frontier_rbpf_v1')
    b=ActiveMapper('r3',0.,SEARCH,active_mapping='frontier_rbpf_v1')
    assert install_profile(a.memory.self_map) is a.memory.self_map
    assert json.dumps(a.memory.self_map.export())==json.dumps(b.memory.self_map.export())
    bundle=frozen_bundle('new-seed','a'*40)
    assert bundle['task']['seed']==28001 and bundle['case_cap_s']==180.
    assert bundle['initial_servo']==SEARCH and bundle['capture_s']==.2
    assert bundle['options']['wall_texture']=='tape_v1'
    assert bundle['options']['camera_pose']=='SEARCH'
    assert bundle['estimator_options']==OPTIONS
    assert bundle['options']['rbpf_search']=='correlative_20deg_v1'
    with pytest.raises(ValueError):install_profile(a.memory.self_map,profile='retuned')


def test_live_installer_identical_to_frozen_replay_and_forecast_private():
    from harness.rbpf_motion_gate import install as motion,OPTION as M
    from harness.rbpf_rejection import install as selective,OPTION as S
    from harness.rbpf_composition import install as compose,OPTION as C,SEARCH as W
    from harness.rbpf_manhattan import install as manhattan,OPTION as Y
    from harness.active_information_gain import forecast
    a=ActiveMapper('r3',0.,SEARCH,active_mapping='frontier_rbpf_v1')
    b=ActiveMapper('r3',0.,SEARCH,active_mapping='frontier_rbpf_v1')
    g=install_profile(a.memory.self_map,profile='egomap27_wide')
    h=manhattan(compose(selective(motion(b.memory.self_map,rbpf_update=M),rbpf_rejection=S),
                        rbpf_composition=C,rbpf_search=W),yaw_prior=Y)
    for grid in (g,h):
        grid.settle_s=None
        grid.observe_contacts_confident(t=0.,frame_id=0,robot_id='r3',segments=CORNER,
            features=[FEATURE]*len(CORNER),camera_xy=[0,0])
    frozen=lambda z:json.dumps([z.export(),z.decisions,z.ledger,z.rng.bit_generator.state])
    assert frozen(g)==frozen(h)
    before=frozen(g)
    assert np.isfinite(forecast(g,[[0,0],[.5,0]],seed=28001)['utility'])
    assert frozen(g)==before
