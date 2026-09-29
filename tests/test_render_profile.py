"""Render profiles: opt-in, hashed, XML-only. The default path must not move a byte."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sim import render_profile as rp

ROOT = Path(__file__).resolve().parents[1]

SYNTH = ('<mujoco><default><material reflectance=".2"/></default>'
         '<asset><material name="groundmat" reflectance=".035"/><material name="plain"/></asset>'
         '<worldbody><light pos="0 0 2"/><light pos="1 0 2" castshadow="true"/>'
         '<body><light name="nested" pos="0 1 2" diffuse=".5 .5 .5"/></body></worldbody></mujoco>')


def test_profile_hashes_are_pinned_and_default_equals_shadows_v1():
    assert rp.profile_sha256('shadows_v1') == 'f10e51dab22f30913f68eb3981f8373ce747676a66292f4b1cd0c974c598f8c5'
    assert rp.profile_sha256('noshadow_v1') == 'c30f1ef68e8c28de662ee541020181cc41cf68a13d58f3a44ed2624c3abc5809'
    assert rp.profile_sha256(None) == rp.profile_sha256('shadows_v1')
    assert rp.profile_sha256('noshadow_v1') != rp.profile_sha256('shadows_v1')
    record = rp.profile_record('noshadow_v1')
    assert record['name'] == 'noshadow_v1' and record['sha256'] == rp.profile_sha256('noshadow_v1')
    assert record['changes_images'] and not record['changes_physics']
    assert not rp.profile_record(None)['changes_images']
    assert 'softshadow_v1' not in rp.PROFILES           # no measured room lighting to base it on


def test_unknown_profile_name_fails_closed():
    with pytest.raises(ValueError, match='unknown render profile'):
        rp.resolve('noshadows')
    with pytest.raises(ValueError):
        rp.apply_xml(SYNTH, 'bogus')


def test_default_and_shadows_v1_return_the_same_string_object():
    assert rp.apply_xml(SYNTH, None) is SYNTH
    assert rp.apply_xml(SYNTH, 'shadows_v1') is SYNTH


def test_noshadow_v1_xml_edit_touches_only_castshadow_and_reflectance():
    import xml.etree.ElementTree as ET
    out = rp.apply_xml(SYNTH, 'noshadow_v1')
    assert SYNTH.count('castshadow') == 1                # input string is not mutated
    root, ref = ET.fromstring(out), ET.fromstring(SYNTH)
    lights = list(root.iter('light'))
    assert len(lights) == 3 and all(light.get('castshadow') == 'false' for light in lights)
    assert [m.get('reflectance') for m in root.iter('material')] == ['0', '0', None]   # default class, groundmat, plain
    assert root.find('.//light[@name="nested"]').get('diffuse') == '.5 .5 .5'
    for element in list(ref.iter()) + list(root.iter()):   # nothing else differs
        element.attrib.pop('castshadow', None)
        element.attrib.pop('reflectance', None)
    assert ET.tostring(root) == ET.tostring(ref)
    assert rp.apply_xml(out, 'noshadow_v1') == out       # idempotent


class _FakeScene:
    """Like the zone scenes: ``transform`` rebuilds ``self.manifest`` on every call."""
    def __init__(self):
        self.manifest = {}

    def transform(self, xml):
        self.manifest = {'scene_xml_sha256': 'inner'}
        return xml


def test_install_is_noop_without_a_name_and_records_after_the_inner_manifest_rebuild():
    plain = _FakeScene()
    assert rp.install(plain, None) is plain and 'transform' not in vars(plain) and not hasattr(plain, '_render_profile_name')
    scene = rp.install(_FakeScene(), 'noshadow_v1')
    out = scene.transform(SYNTH)
    record = scene.manifest['render_profile']
    assert scene.manifest['scene_xml_sha256'] == 'inner'                     # the scene's own hash is kept
    assert record['sha256'] == rp.profile_sha256('noshadow_v1') and record['name'] == 'noshadow_v1'
    assert record['scene_xml_sha256_before_profile'] == hashlib.sha256(SYNTH.encode()).hexdigest()
    assert record['scene_xml_sha256_after_profile'] == hashlib.sha256(out.encode()).hexdigest() != record['scene_xml_sha256_before_profile']
    assert rp.install(scene, 'noshadow_v1') is scene                        # same profile twice: no double wrapping
    with pytest.raises(ValueError, match='already carries'):
        rp.install(scene, 'shadows_v1')
    kept = rp.install(_FakeScene(), 'shadows_v1')
    assert kept.transform(SYNTH) is SYNTH and kept.manifest['render_profile']['changes_images'] is False


# ---- real zone scene: compiled-model checks -------------------------------------------------------------

def _zone_xml():
    from sim.multi_masterpi_production import build_multi_robot_xml
    from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene
    beam = {'item_id': 'beam', 'kind': 'long_beam', 'pose': [.5, .5, 0.]}
    scene = TaggedCargoZoneScene.from_tagged_cargo('zone_wide_door_tags_v2', 11, cargo=[beam],
                                                   goal={'A': {'cyan': 1}}, contact_profile='local_contact_fine')
    return scene, build_multi_robot_xml(None)


@pytest.fixture(scope='module')
def zone_models():
    mujoco = pytest.importorskip('mujoco')
    base_scene, raw = _zone_xml()
    xml = base_scene.transform(raw)
    profiled = _zone_xml()[0]
    rp.install(profiled, 'noshadow_v1')
    xml_noshadow = profiled.transform(raw)
    kept = rp.install(_zone_xml()[0], 'shadows_v1')
    xml_kept = kept.transform(raw)
    return {'xml': xml, 'noshadow_xml': xml_noshadow, 'kept_xml': xml_kept,
            'scene': profiled, 'default': mujoco.MjModel.from_xml_string(xml),
            'kept': mujoco.MjModel.from_xml_string(xml_kept),
            'noshadow': mujoco.MjModel.from_xml_string(xml_noshadow)}


def _arrays(model):
    import numpy as np
    return {name: getattr(model, name) for name in dir(model)
            if not name.startswith('_') and isinstance(getattr(model, name, None), np.ndarray)}


def test_default_scene_has_four_shadow_lights_and_a_reflective_floor(zone_models):
    audit = rp.audit_model(zone_models['default'])
    assert audit['nlight'] == 4 and audit['light_castshadow'] == [1, 1, 1, 1]
    assert audit['materials_with_reflectance'] == {'groundmat': pytest.approx(.035)}


def test_shadows_v1_leaves_the_compiled_model_and_xml_bytes_unchanged(zone_models):
    import numpy as np
    assert zone_models['kept_xml'] == zone_models['xml']
    default, kept = _arrays(zone_models['default']), _arrays(zone_models['kept'])
    assert default.keys() == kept.keys() and len(default) > 100
    assert all(np.array_equal(default[k], kept[k], equal_nan=True) for k in default)


def test_noshadow_v1_changes_exactly_light_castshadow_and_mat_reflectance(zone_models):
    import numpy as np
    default, profiled = _arrays(zone_models['default']), _arrays(zone_models['noshadow'])
    assert default.keys() == profiled.keys()
    changed = sorted(k for k in default if not np.array_equal(default[k], profiled[k], equal_nan=True))
    assert changed == ['light_castshadow', 'mat_reflectance']
    audit = rp.verify_model(zone_models['noshadow'], 'noshadow_v1')
    assert audit['light_castshadow'] == [0, 0, 0, 0] and audit['materials_with_reflectance'] == {}
    model = zone_models['noshadow']            # light values, camera, timestep, contact settings kept
    ref = zone_models['default']
    assert (model.light_diffuse == ref.light_diffuse).all() and (model.light_ambient == ref.light_ambient).all()
    assert (model.cam_pos == ref.cam_pos).all() and (model.cam_fovy == ref.cam_fovy).all()
    assert model.opt.timestep == ref.opt.timestep and model.opt.noslip_iterations == ref.opt.noslip_iterations


def test_verify_model_fails_closed_when_the_profile_is_missing(zone_models):
    with pytest.raises(RuntimeError, match='still has shadows'):
        rp.verify_model(zone_models['default'], 'noshadow_v1')
    assert rp.verify_model(zone_models['default'], 'shadows_v1')['nlight'] == 4   # nothing to enforce


def test_scene_manifest_carries_name_hash_and_both_xml_hashes(zone_models):
    record = zone_models['scene'].record()['render_profile']
    assert record['sha256'] == rp.profile_sha256('noshadow_v1')
    assert record['scene_xml_sha256_before_profile'] == hashlib.sha256(zone_models['xml'].encode()).hexdigest()
    assert record['scene_xml_sha256_after_profile'] == hashlib.sha256(zone_models['noshadow_xml'].encode()).hexdigest()


def test_default_output_pixels_are_identical_and_noshadow_changes_them(zone_models):
    """One small robot_cam frame per model. Skipped where no offscreen GL exists."""
    import numpy as np
    mujoco = pytest.importorskip('mujoco')

    def frame(model):
        try:
            renderer = mujoco.Renderer(model, height=120, width=160)
        except Exception as exc:                          # no GL context on this host
            pytest.skip(f'no offscreen renderer: {exc}')
        try:
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            renderer.update_scene(data, camera='r1__robot_cam')
            return renderer.render().copy()
        finally:
            renderer.close()
    default, kept, profiled = frame(zone_models['default']), frame(zone_models['kept']), frame(zone_models['noshadow'])
    assert default.tobytes() == kept.tobytes()
    assert np.any(default != profiled)


# ---- probe flag ------------------------------------------------------------------------------------------

def test_probe_flag_is_off_by_default_and_marks_cases_only_when_given():
    from harness import pair_stage_probe as sp
    from scripts import run_pair_stage_probes as r
    cases = sp.teacher_cases('align', subset={'nominal'}, nominal_seeds=(911,))
    assert r.with_render_profile(cases, None) is cases and all('render_profile' not in c for c in cases)
    marked = r.with_render_profile(cases, 'noshadow_v1')
    assert [c['case_id'] for c in marked] == [c['case_id'] for c in cases]      # ids unchanged, output dir decides the arm
    assert all(c['render_profile'] == 'noshadow_v1' for c in marked) and all('render_profile' not in c for c in cases)
    assert sp.digest(marked) != sp.digest(cases)
    with pytest.raises(ValueError):
        r.with_render_profile(cases, 'bogus')


def test_probe_plan_mode_with_the_flag_stays_simulator_free():
    program = ('import sys; import scripts.run_pair_stage_probes as r; '
               'r.main(["--stage","align","--output","/nonexistent/never","--sources","teacher","--render-profile","noshadow_v1"]); '
               'assert "mujoco" not in sys.modules, sorted(m for m in sys.modules if "mujoco" in m)')
    out = subprocess.run([sys.executable, '-c', program], cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)['cases'] == 19
    bad = subprocess.run([sys.executable, '-m', 'scripts.run_pair_stage_probes', '--stage', 'align', '--output', '/nonexistent/never',
                          '--sources', 'teacher', '--render-profile', 'softshadow_v1'], cwd=ROOT, capture_output=True, text=True)
    assert bad.returncode == 2 and 'invalid choice' in bad.stderr
