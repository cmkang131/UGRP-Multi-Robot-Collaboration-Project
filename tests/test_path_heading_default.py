"""Changed shared factory, bundle/result boundary and saved s1068 counterexample."""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from harness import path_heading_policy as policy
from harness import zone_path_heading_contract as contract
from harness import zone_solo_cyan_contract_v106 as legacy
from scripts.run_s2_unknown_start import runtime_factory
from scripts.run_final_environment_checks import write

FIX = Path(__file__).parent/'fixtures/path_heading'


def config(mode=None):
    b = contract.bundle('a'*40, 1066)
    b = copy.deepcopy(b)
    b['options'].pop('active_localization')
    b['options'].pop('active_rotation_guard')
    if mode is None:
        b['options'].pop('heading_mode')
    else:
        b['options']['heading_mode'] = mode
    return b


def build(b):
    return runtime_factory(b)(legacy.hp.resolve(legacy.MAP_ID)[0],
        legacy.ROOT/legacy.CALIBRATION, legacy.CALIBRATION_SHA, **b['task'])


def test_new_bundle_and_cli_default_and_explicit_off():
    from scripts.run_path_heading import parser
    args = ['--expected-source-sha', 'a'*40, '--seed', '1066', '--output', '/tmp/not-executed']
    assert parser().parse_args(args).heading_mode == policy.DEFAULT
    for mode in (policy.DEFAULT, 'off'):
        b = contract.bundle('a'*40, 1066, heading_mode=mode)
        contract.require_execution(b)
        assert b['heading_mode'] == b['options']['heading_mode'] == mode
    assert parser().parse_args(args+['--heading-mode', 'off']).heading_mode == 'off'
    with pytest.raises(ValueError):
        contract.bundle('a'*40, 1066, heading_mode='off', heading_visual_lock=policy.VISUAL_LOCK)


@pytest.mark.parametrize('entry', ['zone-path-heading-v145', 'zone-s3-host-heading-v144',
                                  's4-via-s3', 'own-map-movement'])
def test_new_callers_use_one_default_command_generator(entry):
    from harness.zone_solo_cyan_path_heading import _HeadingPulse
    b = config(); b['execution_bundle_id'] = entry
    rt = build(b)
    try:
        assert isinstance(rt, _HeadingPulse)
        assert rt.heading_mode == policy.DEFAULT
        assert rt.record()['heading_mode']['option'] == policy.DEFAULT
        # Exercise the actual cooperative drive chain on an own-estimate stub.
        # Disable only startup bookkeeping; the tested generator is unchanged.
        rt.start_prior = 'off'
        rt.last_report = NS(initialized=True, x_m=.3, y_m=-2.15, yaw_rad=0.,
                            std_xy_m=.01, std_yaw_rad=.01, last_fix_t=0.)
        action, arrived = rt.drive((.3, -.85), 1.)
        assert not arrived
        assert action[0]['forward'] == action[0]['left'] == 0.
        assert action[0]['turn'] > 0
    finally:
        rt.close()


def test_explicit_off_record_matches_pre_change_frozen_bytes():
    from scripts.run_s2_graduation59 import runtime_factory as old
    from harness import zone_s2_graduation59_contract as before
    a = before.bundle('a'*40, 1066, **before.NEW_OPTIONS)
    b = contract.bundle('a'*40, 1066, heading_mode='off')
    args = (legacy.hp.resolve(legacy.MAP_ID)[0], legacy.ROOT/legacy.CALIBRATION, legacy.CALIBRATION_SHA)
    x, y = old(a, {}, [])(*args, **a['task']), old(b, {}, [])(*args, **b['task'])
    try:
        left, right = json.dumps(x.record()).encode(), json.dumps(y.record()).encode()
        assert left == right
        from tests.pinned_source_bundle import json_at
        # The fixture's provider identity includes source hashes. Reproduce
        # its original source rather than importing today's shared backend.
        code = '''import json,hashlib
from scripts.run_s2_graduation59 import runtime_factory
from harness import zone_s2_graduation59_contract as before
from harness import zone_solo_cyan_contract_v106 as legacy
a=before.bundle('a'*40,1066,**before.NEW_OPTIONS)
args=(legacy.hp.resolve(legacy.MAP_ID)[0],legacy.ROOT/legacy.CALIBRATION,legacy.CALIBRATION_SHA)
x=runtime_factory(a,{},[])(*args,**a['task'])
try:
 portable=json.dumps(x.record()).replace(str(legacy.ROOT),'$ROOT').encode()
 import cv2
 import platform
 print(json.dumps(dict(record=json.loads(portable),opencv_version=cv2.__version__,
                      platform=[platform.system(),platform.machine()])))
finally:x.close()
'''
        companions = {str((legacy.ROOT/p).with_name('input_manifest_dev.json').relative_to(legacy.ROOT))
                      for p in a['source_sha256']
                      if (legacy.ROOT/p).with_name('input_manifest_dev.json').is_file()}
        from harness.vision_loc_protocol import VIS3_DIR, FROZEN_FILES
        companions.update(str((VIS3_DIR/p).resolve().relative_to(legacy.ROOT))
                          for p in (*FROZEN_FILES, 'prereg_v3.json', 'selected_config_v3.json'))
        original = json_at('d89912703432117e47b5306bbe50ec9c31a0663c', code,
                         tuple(a['source_sha256']) + tuple(sorted(companions))
                         + tuple(str(p.relative_to(legacy.ROOT)) for p in (before.PLAN, before.old.PLAN)))
        frozen_bytes = (FIX/'off-initial-record.json').read_bytes()
        assert hashlib.sha256(frozen_bytes).hexdigest() == (FIX/'off-initial-record.sha256').read_text().strip()
        frozen = json.loads(frozen_bytes)
        current = json.loads(json.dumps(x.record()).replace(str(legacy.ROOT),'$ROOT'))
        # Execute the actual pre-change producer on this host. Camera matrix
        # derivation hashes can differ across numeric libraries/CPU builds;
        # every field and float still has to match on the same environment.
        assert json.dumps(current,sort_keys=True).encode() == json.dumps(original['record'],sort_keys=True).encode()
        def portable_environment(value, reference):
            if isinstance(value, dict):
                result = {k: portable_environment(v, reference[k]) for k,v in value.items()}
                if 'opencv_version' in value:
                    assert value['opencv_version'] == original['opencv_version']
                    result['opencv_version'] = reference['opencv_version']
                return result
            if isinstance(value, list):
                return [portable_environment(v, r) for v,r in zip(value,reference,strict=True)]
            return value
        if original['platform'] == ['Darwin','arm64']:
            normalized = portable_environment(original['record'], frozen)
            # The additional fixed reference was captured on this platform.
            # Only paths and verified OpenCV metadata are portable here.
            assert json.dumps(normalized,sort_keys=True).encode() == json.dumps(frozen,sort_keys=True).encode()
        assert not hasattr(y, 'heading_mode')
        assert x.pose.provider.loc._pf.rng.bit_generator.state == y.pose.provider.loc._pf.rng.bit_generator.state
    finally:
        x.close(); y.close()


def test_result_writer_records_s2_s3_options_and_preserves_historical_bytes(tmp_path):
    for container in ('options', 'controller_config'):
        for mode in (policy.DEFAULT, 'off'):
            options = dict(heading_mode=mode)
            b = {container: options if container == 'options' else dict(options=options)}
            write(tmp_path/'bundle.json', b)
            original = dict(status='HOST_ERROR', model_calls=0)
            write(tmp_path/'result.json', original)
            assert json.loads((tmp_path/'result.json').read_text())['heading_mode'] == mode
            assert original == dict(status='HOST_ERROR', model_calls=0)
    write(tmp_path/'bundle.json', dict(options={}))
    value = dict(status='DEV_NOT_DELIVERED')
    write(tmp_path/'result.json', value)
    assert (tmp_path/'result.json').read_bytes() == (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def test_own_map_plan_schema_uses_shared_selector_and_off_is_identical():
    from harness.own_map_heading import command
    from harness.zone_solo_cyan_path_heading import select_waypoint
    from harness.zone_solo_cyan_pulse_cal import action_of
    from test_s2_path_heading import profiles
    plan = dict(coordinate_frame='r3/own_odom', status='goal_approach',
                path_m=[[0., 0.], [0., .04], [0., 1.]])
    action = command(plan, [0., 0., 0.], profiles(), robot_id='r3')
    assert action == action_of(select_waypoint(profiles(), False, [0., 0., 0.], [0., .04], [0., 1.])[0])
    assert action['turn'] > 0 and action['left'] == action['forward'] == 0
    old = dict(kind='mecanum', left=.35)
    assert command(None, None, None, robot_id='r3', heading_mode='off', legacy_action=old) is old
    with pytest.raises(ValueError):
        command(plan, [0., 0., 0.], profiles(), robot_id='r1')
    plan['status'] = 'shared_carry_action_required'
    assert command(plan, [0., 0., 0.], profiles(), robot_id='r3') == dict(kind='hold')


def test_saved_visible_cyan_rejected_by_slot_gate_optional_local_tracking():
    row = json.loads((FIX/'s1068-visible-rejected.json').read_text())
    image = (FIX/'s1068-visible-rejected.jpg').read_bytes()
    assert hashlib.sha256(image).hexdigest() == row['frame_sha256']
    b = config(); rt = build(b)
    try:
        rt.state = 'align'; rt.target = [.47387588499942523, .030434633705182332]
        rt.slot = row['slot']
        rt.last_obs = dict(image=image)
        from harness.owncam_pair_beam_v2 import pose_of
        rt.servo = {**pose_of('search'), 1: 2000}
        p = row['own_pose']
        rt.last_report = NS(x_m=p['x'], y_m=p['y'], yaw_rad=p['yaw'])
        raw = rt.vision.detect(rt.last_obs, rt.servo)
        assert len(raw) == 1 and rt.vision.mask_bottom_row(rt.last_obs) < 440
        assert rt.detections() == []
        rt.heading_visual_lock = policy.VISUAL_LOCK
        assert rt.detections() == raw
        # Search must still establish the target with the unchanged slot gate.
        rt.state = 'search'
        assert rt.detections() == []
        # Do not choose an identity when two candidates are visible.
        rt.state = 'align'; rt.vision.detect = lambda *args: raw+raw
        assert len(rt.detections()) == 2
    finally:
        rt.close()
