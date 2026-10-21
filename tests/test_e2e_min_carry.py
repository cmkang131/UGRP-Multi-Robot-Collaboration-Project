"""Carry-pose candidates/verdict and E2E world helpers (CPU only, no simulator)."""
import json

import numpy as np
import pytest

from harness import e2e_min_carry_pose as C
from harness import e2e_min_world as W

LIFT = {'1': 1499, '3': 738, '4': 1828, '5': 2216, '6': 1493}


# -- carry pose ---------------------------------------------------------------
def test_medoid_is_a_real_row():
    rows = [dict(LIFT), dict(LIFT, **{'3': 700}), dict(LIFT, **{'3': 760, '5': 2100})]
    best, median = C.medoid(rows)
    assert best in [{k: int(v) for k, v in r.items()} for r in rows]
    assert median['3'] == 738


def test_teacher_hold_selects_highest_tool_pitch_closed_gripper():
    rows = [dict(skill='grasp', teacher_phase='hold', issued_pwm=LIFT),
            dict(skill='grasp', teacher_phase='hold',
                 issued_pwm={'1': 1500, '3': 837, '4': 1930, '5': 2173, '6': 1510}),
            dict(skill='grasp', teacher_phase='approach',           # open gripper / not hold
                 issued_pwm={'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}),
            dict(skill='grasp', teacher_phase='lift',                # transient phase excluded
                 issued_pwm={'1': 1500, '3': 900, '4': 2000, '5': 1600, '6': 1500})]
    pwm, meta = C.teacher_hold_max_pitch(rows)
    assert pwm == {'1': 1500, '3': 837, '4': 1930, '5': 2173, '6': 1510}
    assert meta['distinct_hold_vectors'] == 2
    with pytest.raises(ValueError):
        C.teacher_hold_max_pitch(rows[2:3])


def test_carry_look_moves_only_shoulder_and_wrist_and_nears_search_camera():
    look = C.carry_look_v1(LIFT, step=50)
    assert {k: look[k] for k in ('1', '4', '6')} == {k: LIFT[k] for k in ('1', '4', '6')}
    cam, search = C.camera_pose(look), C.camera_pose(C.search_pwm())
    lift_cam = C.camera_pose(LIFT)
    assert abs(cam['pitch_down_deg'] - search['pitch_down_deg']) < \
        abs(lift_cam['pitch_down_deg'] - search['pitch_down_deg'])
    assert C.LOOK_TOOL_PITCH_DEG[0] <= cam['tool_pitch_deg'] <= C.LOOK_TOOL_PITCH_DEG[1]


def test_committed_candidates_file_is_consistent():
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'experiments/2026-10-21-e2e-min/carry_pose_candidates.json'
    data = json.loads(path.read_text())
    assert data['candidates'] == list(C.CANDIDATES) and data['reference'] == C.REFERENCE
    poses = data['poses']
    assert all(int(p['1']) <= C.GRIPPER_CLOSED_MAX for p in poses.values())   # gripper closed
    ref = dict(C.search_pwm(), **{'1': poses['act_lift_end']['1']})
    assert poses[C.REFERENCE] == ref
    assert data['provenance']['act_lift_end']['worlds'] == 11


def test_occlusion_and_mask_loss():
    off = np.zeros((10, 10, 3), np.uint8)
    on = off.copy()
    on[:3, :] = 200
    assert C.occlusion_fraction(on, off) == pytest.approx(0.3)
    assert C.occlusion_fraction(off + 5, off) == 0.0       # below the JPEG-noise threshold
    m_off = np.zeros((10, 10), bool); m_off[5:, :] = True
    m_on = m_off.copy(); m_on[5:6, :] = False
    assert C.mask_loss(m_off, m_on) == pytest.approx(0.2)
    assert C.mask_loss(np.zeros((2, 2), bool), m_on[:2, :2]) is None


def _rows(px, occ):
    return [dict(pose=p, robot=r, x=C.VERDICT_X, largest_component_px=px[p], occlusion_fraction=occ[p])
            for p in C.CANDIDATES for r in ('r1', 'r2')]


def test_verdict_adopts_first_passing_candidate_in_order():
    rows = _rows({'act_lift_end': 100, 'teacher_hold_max_pitch': 900, 'carry_look_v1': 5000},
                 {'act_lift_end': 0.1, 'teacher_hold_max_pitch': 0.1, 'carry_look_v1': 0.05})
    v = C.verdict(rows)
    assert v['adopted'] == 'teacher_hold_max_pitch' and v['fallback'] is False
    assert v['candidates']['act_lift_end']['passed'] is False


def test_verdict_fallback_and_both_robots_required():
    rows = _rows({p: 5000 for p in C.CANDIDATES}, {p: 0.35 for p in C.CANDIDATES})
    v = C.verdict(rows)
    assert v['adopted'] == 'gripper_hold_arm_search_v1' and v['fallback'] is True
    rows = [r for r in _rows({p: 5000 for p in C.CANDIDATES}, {p: 0.1 for p in C.CANDIDATES})
            if not (r['pose'] == 'act_lift_end' and r['robot'] == 'r2')]
    v = C.verdict(rows)
    assert v['candidates']['act_lift_end']['passed'] is False       # missing robot fails
    assert v['adopted'] == 'teacher_hold_max_pitch'


def test_measure_frame_on_synthetic_zone_patch():
    import colorsys
    img = np.full((480, 640, 3), 128, np.uint8)
    r, g, b = colorsys.hsv_to_rgb(224 / 360, 0.7, 0.6)
    img[300:340, 200:300] = [int(r * 255), int(g * 255), int(b * 255)]
    m = C.measure_frame(img)
    assert m['largest_component_px'] == 4000 and m['bbox_bottom_row'] == 339


# -- world helpers --------------------------------------------------------------
OBJECTS = {'cyan_1': dict(kind='cyan', body_name='cargo_cyan_1', joint_name='cargo_cyan_1_free',
                          position_m=[0.125, 0.45, 0.016], half_extents_m=[0.017, 0.02, 0.016]),
           'red_1': dict(kind='red', body_name='cargo_red_1', joint_name='cargo_red_1_free',
                         position_m=[0.125, -0.85, 0.016], half_extents_m=[0.017, 0.02, 0.016])}
CUBES = {'r1': dict(item_id='cyan_1', xy=[-0.05, -2.375]), 'r2': dict(item_id='red_1', xy=[-0.05, -2.875])}


def test_select_cube_objects_moves_and_validates():
    keep = W.select_cube_objects(OBJECTS, CUBES)
    assert keep['cyan_1']['position_m'] == [-0.05, -2.375, 0.016]
    assert keep['red_1']['carried_by'] == 'r2' and OBJECTS['red_1']['position_m'][0] == 0.125
    for bad in ({'r1': CUBES['r1']},
                {'r1': CUBES['r1'], 'r2': dict(CUBES['r2'], item_id='cyan_1')},
                {'r1': CUBES['r1'], 'r2': dict(item_id='beam_1', xy=[0, 0])},
                {'r1': CUBES['r1'], 'r2': dict(item_id='red_1', xy=[float('nan'), 0])}):
        with pytest.raises(W.E2EWorldError):
            W.select_cube_objects(OBJECTS, bad)


XML = """<mujoco><worldbody>
<body name='r1__robot'><geom name='r1__left_finger'/><geom name='r1__right_finger'/></body>
<body name='cargo_cyan_1'><joint name='cargo_cyan_1_free' type='free'/><geom name='cargo_cyan_1_geom'/></body>
<body name='cargo_red_1'><geom name='cargo_red_1_geom'/></body>
</worldbody><contact>
<pair geom1='r1__left_finger' geom2='cargo_cyan_1_geom' condim='4' friction='1 1 0.01 0.0001 0.0001'/>
<pair geom1='r1__left_finger' geom2='r1__right_finger'/>
</contact></mujoco>"""


def test_cube_body_audit_and_pair_audit():
    assert W.audit_cube_bodies(XML, CUBES) == ['cargo_cyan_1', 'cargo_red_1']
    with pytest.raises(W.E2EWorldError, match='E2E_CUBE_BODIES_MISMATCH'):
        W.audit_cube_bodies(XML.replace("cargo_red_1'", "cargo_beam_1'"), CUBES)
    audit = W.cargo_pair_audit(XML)
    assert audit['pair_n'] == 1 and audit['finger_pair_n'] == 1
    assert audit['pairs'][0]['condim'] == '4' and audit['asserted_equal_to_act_owner'] is False


def test_arm_pwm_default_is_search_and_validates():
    search = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
    assert W.arm_pwm(None, 'r1', search) == search
    assert W.arm_pwm({'r1': LIFT}, 'r1', search) == {int(k): v for k, v in LIFT.items()}
    with pytest.raises(W.E2EWorldError):
        W.arm_pwm({'r1': {'1': 1500}}, 'r1', search)


# -- render-batch scene identity ----------------------------------------------
def _scene(cube_x=1.7, robot_x=0.0, *, wall=False, cube_size='.016 .016 .016', cube_quat=None,
           extra_body=False, free_style='freejoint'):
    joint = ('<freejoint name="cargo_cyan_1_free"/>' if free_style == 'freejoint'
             else '<joint name="cargo_cyan_1_free" type="free"/>')
    quat = '' if cube_quat is None else f' quat="{cube_quat}"'
    return ('<mujoco><worldbody>'
            '<geom name="floor" type="plane" size="8 8 .1"/>'
            + ('<geom name="wall_x" type="box" pos="2 0 .1" size=".1 1 .1"/>' if wall else '')
            + f'<body name="r1__robot" pos="{robot_x} -2.375 .03"><freejoint name="r1__base_free"/>'
            '<geom name="r1__chassis" type="box" size=".1 .1 .03"/>'
            '<body name="r1__arm" pos=".05 0 .05"><joint name="r1__shoulder" type="hinge"/>'
            '<geom name="r1__link" type="capsule" size=".01 .05"/></body></body>'
            f'<body name="cargo_cyan_1" pos="{cube_x} -2.375 .016"{quat}>{joint}'
            f'<geom name="cargo_cyan_1_geom" type="box" size="{cube_size}"/></body>'
            + ('<body name="cargo_extra" pos="1 1 .016"><freejoint/><geom type="box" size=".01 .01 .01"/></body>'
               if extra_body else '')
            + '</worldbody></mujoco>')


def test_scene_identity_spawn_pos_only_passes_and_records_shas():
    xmls = [_scene(cube_x=x + 0.2, robot_x=x) for x in C.RENDER_X]
    rec = C.require_scene_identity(xmls, 'act_lift_end')
    assert rec['identical'] and not rec['raw_identical']
    assert len(rec['raw_sha256']) == 4 and len(rec['normalized_sha256']) == 1
    assert rec['differing_fields'] == ["body[@name='cargo_cyan_1']/@pos", "body[@name='r1__robot']/@pos"]
    assert set(rec['differing_fields']) <= set(rec['normalized_fields'])
    # byte-identical batch (the fixed render path): raw and normalised agree
    same = C.scene_identity([_scene(), _scene()])
    assert same['raw_identical'] and same['identical'] and same['differing_fields'] == []
    # <joint type="free"> is treated like <freejoint>
    assert C.scene_identity([_scene(1.7, free_style='joint'), _scene(2.2, free_style='joint')])['identical']


def test_scene_identity_nested_non_free_body_pos_is_not_normalised():
    a = _scene()
    b = a.replace('<body name="r1__arm" pos=".05 0 .05">', '<body name="r1__arm" pos=".06 0 .05">')
    assert a != b
    with pytest.raises(ValueError, match='POSE_SCENE_XML_NOT_IDENTICAL'):
        C.require_scene_identity([a, b])


@pytest.mark.parametrize('other', [
    dict(wall=True),                          # wall added
    dict(extra_body=True),                    # object added
    dict(cube_size='.02 .016 .016'),          # size changed
    dict(cube_quat='0.92 0 0 0.38'),          # orientation is not normalised (fail closed)
])
def test_scene_identity_different_scene_fails(other):
    with pytest.raises(ValueError, match='POSE_SCENE_XML_NOT_IDENTICAL'):
        C.require_scene_identity([_scene(), _scene(cube_x=2.2, **other)], 'p')
    assert not C.scene_identity([_scene(), _scene(**other)])['identical']


def test_scene_identity_empty_fails():
    with pytest.raises(ValueError, match='POSE_SCENE_XML_NOT_IDENTICAL'):
        C.scene_identity([])
