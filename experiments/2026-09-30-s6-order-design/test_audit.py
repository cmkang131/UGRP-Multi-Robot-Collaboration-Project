"""Static counterexamples and input boundaries only; never creates a simulator."""
import copy
import math

import pytest

import audit
from harness import zone_study_contract as contract
from harness import zone_study_inputs as inputs
from harness.zone_scenario_feasibility import ScenarioItem, check_free_robot_access


def test_catalogue_any_is_not_a_west_only_rule():
    assert audit.CATALOGUE['can'].grasps[0].role == 'any'
    scenario, static_map = audit.inputs()
    report = audit.approach_report(scenario, static_map)
    assert report['legacy_station_check']['gap_m']['any'] == pytest.approx(.00167)
    for name in ('disc_017', 'legacy_chassis_arm', 'v3_drawing_rectangle_only'):
        row = report['profiles'][name]
        assert row['all_heading_proxy_clear_by_radius_bound']
        assert len(row['clear_heading_samples_deg']) == 360
    assert report['profiles']['disc_021']['cardinal']['0']['station_clear'] is False
    assert report['profiles']['disc_021']['cardinal']['180']['station_clear'] is True
    assert report['final_v3_complete_footprint'].startswith('unsupported')


def test_nearby_blocker_is_a_counterexample_to_station_clearance():
    _, static_map = audit.inputs()
    items = (ScenarioItem('can_1', 'can', (1.45, -.85, 0.), 'C', 1),
             ScenarioItem('beam_1', 'long_beam', (1.28, -.85, math.pi / 2), 'A', 2))
    stations, findings = check_free_robot_access(static_map, items)
    assert stations['can_1']['blocked_roles'] == ['any']
    assert 'station_not_standable' in [f.code for f in findings]


def test_end_pos_contact_is_not_the_robot_base_or_beam_centre():
    start, pivot = (1.1, -.85, math.pi / 2), (.27, 0.)
    for delta in (-math.pi / 2, 0., math.pi / 2):
        end = audit.pivot_pose(start, pivot, delta)
        assert audit.tf.transform([pivot], end)[0] == pytest.approx((1.1, -.58))
    assert audit.pivot_pose(start, pivot, -math.pi / 2) == pytest.approx((.83, -.58, 0.))
    assert audit.pivot_pose(start, pivot, math.pi / 2) == pytest.approx((1.37, -.58, math.pi))
    assert audit.pivot_pose(start, (0., 0.), math.pi / 2)[:2] == pytest.approx(start[:2])
    assert audit.can_station(0., .155 + audit.YAW_AXIS_X_M)[0] == pytest.approx(1.2468)


@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf])
def test_nonfinite_geometry_is_rejected(value):
    with pytest.raises(ValueError):
        audit.can_station(value)
    with pytest.raises(ValueError):
        audit.pivot_pose((1.1, -.85, math.pi / 2), (.27, 0.), value)


def test_station_is_not_an_entry_route():
    part = audit.ko.disc_footprint(.17)
    wall = ((0., 0., .025, 1., 0.),)
    assert audit.ko.pose_clear((.4, 0., 0.), part, wall)
    assert not audit.ko.swept_clear((-.4, 0., 0.), (.4, 0., 0.), part, wall)
    # Boundary contact counts as blocked, so a zero-width separation is no PASS.
    assert audit.ko.polygons_overlap(audit.tf.rect(0., 1., 0., 1.), audit.tf.rect(1., 2., 0., 1.))


def test_structured_allows_a_report_but_not_a_conditional_plan_field():
    vocabulary = contract.Vocabulary(items=frozenset({'can_1', 'beam_1'}),
                                     roles=frozenset({'end_pos', 'end_neg'}))
    message = {'act': 'inform', 'item': 'can_1', 'state': 'blocked', 'confidence': 'high'}
    assert not contract.structured_violations(message, vocabulary=vocabulary)
    for extension in ({'after': 'rotate_beam'}, {'if': 'partner_retreated'}, {'sequence': []},
                      {'act': 'pivot'}, {'role': 'retreat_then_can'}):
        assert contract.structured_violations({**message, **extension}, vocabulary=vocabulary)


@pytest.mark.parametrize('condition', contract.MAIN_CONDITIONS)
def test_private_changes_do_not_change_actual_public_payload(condition):
    scenario, _ = audit.inputs()
    changed = copy.deepcopy(scenario)
    changed['eval']['setup']['placements'][0]['pose_m'] = [1.8, -.6, 0.]
    changed['eval']['setup']['placements'][0]['order_id'] = 'private_binding_changed'
    changed['eval']['hidden_events'] = [{'at_sim_s': 17., 'kind': 'item_moved', 'target': 'can_1'}]
    changed['eval']['referee'] = {'orders_complete': True, 'contacts': ['beam_1']}
    bundle = audit.ms.map_bundle(scenario['map_id'], maps_dir=audit.ROOT / 'maps/zones_final',
                                 landmark_detail='none', schematic=False)

    def payload(value):
        return inputs.build_call_input(
            robot_id='r2', condition_name=condition, request_id='t11-static', sim_time_s=0.,
            static_map=audit.ms.static_map_section(bundle), source=inputs.OrderSheetSource(value, bundle),
            own_rgb_refs=[inputs.own_rgb_ref('r2', 0, 0., '1' * 64)],
            own_command_history=[], inbox=None if condition == 'no_comm' else [], seed=651)

    assert payload(scenario) == payload(changed)


def test_cardinal_mirrors_do_not_claim_continuous_or_v3_physics():
    scenario, static_map = audit.inputs()
    rows = audit.pivot_report(scenario, static_map)
    assert len(rows) == 8
    centre = [r for r in rows if r['pivot'] == 'centre']
    assert all(r['obstacle_sweep']['can_1']['hit_samples'] > 0 for r in centre)
    assert all(r['continuous_physical_clearance'] == 'unmeasured' for r in rows)
