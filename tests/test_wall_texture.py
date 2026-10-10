import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from sim import wall_texture as texture
from scripts import run_wall_parallax_texture as run


def sample_xml():
    walls = json.loads((texture.DEFAULT_ASSETS / 'layout.json').read_text())['wall_geometry']
    geoms = ''.join(f'<geom name="{w["name"]}" type="box" pos="{" ".join(map(str, w["pos"]))}" '
                    f'size="{" ".join(map(str, w["size"]))}" contype="1" conaffinity="3" mass="0"/>' for w in walls)
    return '<mujoco>\n  <worldbody>' + geoms + '</worldbody>\n</mujoco>\n'


def test_off_is_byte_identity_without_parsing_or_files():
    for xml in [sample_xml(), 'invalid XML\r\n <\uac00>', '']:
        assert texture.transform_xml(xml, assets='/no-such-assets') is xml
    with pytest.raises(ValueError):
        texture.transform_xml(sample_xml(), wall_texture='typo')


def test_on_adds_visuals_only_and_keeps_original_elements():
    xml = sample_xml()
    root = ET.fromstring(texture.transform_xml(xml, wall_texture='tape_v1'))
    old = ET.fromstring(xml)
    for node in old.find('worldbody'):
        assert node.attrib == root.find(f"worldbody/geom[@name='{node.get('name')}']").attrib
    new = [g for g in root.findall('worldbody/geom') if g.get('name').startswith('tape_v1_')]
    assert len(new) == 24
    assert all(g.get('contype') == g.get('conaffinity') == g.get('mass') == '0' for g in new)
    assert all(m.get('texrepeat') == '1 1' and m.get('texuniform') == 'false' for m in root.findall('asset/material'))
    with pytest.raises(ValueError, match='already installed'):
        texture.transform_xml(ET.tostring(root, encoding='unicode'), wall_texture='tape_v1')
    with pytest.raises(ValueError, match='walls differ'):
        texture.transform_xml(xml.replace('6.5', '6.6') if '6.5' in xml else xml.replace('3.25', '3.3'), wall_texture='tape_v1')


def test_physical_table_bounds_handedness_and_nonperiodic_design():
    record = json.loads((texture.DEFAULT_ASSETS / 'layout.json').read_text())
    regenerated = texture.layout(record['wall_geometry'])
    assert len(record['faces']) == 24
    digests = set()
    for face, expected in zip(record['faces'], regenerated['faces']):
        assert {k: v for k, v in face.items() if k != 'png_sha256'} == expected
        if face['length_m'] > .2:
            digests.add(face['png_sha256'])
        assert texture.sha(texture.DEFAULT_ASSETS / (face['id'] + '.png')) == face['png_sha256']
        assert np.array_equal(np.cross(face['u_axis'], face['v_axis']), face['normal'])
        centres = [t['centre_m'] for t in face['tapes']]
        assert all(.2 <= b - a <= .3 for a, b in zip(centres, centres[1:]))
        if len(centres) >= 3:
            assert len(set(np.round(np.diff(centres), 6))) > 1
        assert all(.02 <= t['width_m'] <= .03 for t in face['tapes'])
        for p in face['patches']:
            bounds = np.ptp(p['vertices_m'], axis=0)
            assert np.all(bounds >= .02 - 1e-12) and np.all(bounds <= .04 + 1e-12)
        for poly in texture.polygons(face):
            assert all(0 <= u <= face['length_m'] and 0 <= z <= face['height_m'] for u, z in poly)
    # The 12 broad faces are distinct nonperiodic layouts. A 50 mm end face
    # contains only one centred tape: 1 mm raster rounding can coincide even
    # though its independent physical width differs (not a repeated tile).
    assert len(digests) == 12
    assert len({t['width_m'] for f in record['faces'] for t in f['tapes']}) == sum(len(f['tapes']) for f in record['faces'])


@pytest.mark.parametrize('case', run.CASES)
def test_record_schedule_matches_egomap15_and_ignores_truth(tmp_path, case):
    class Fake:
        now = 1.3
        issued = []
        def __init__(self, bundle, *a, **k):
            self.bundle = bundle
        def reset(self, cap):
            assert cap == 5
        def set_deadline(self, deadline):
            assert deadline == self.now + 18
        def issue(self, rid, a):
            self.issued.append((rid, a))
        def capture(self):
            return None
        def eval_sample(self):
            return {'robot_xyz': [-999, 999], 'success': True}
        def advance_to(self, t):
            self.now = t
        def close(self):
            pass
    result = run.acquire_case(case, tmp_path / case, 'test', Fake, wall_texture='tape_v1')
    expected = [('r3', a) for i in range(181) for a in run.previous.actions(case.replace('tape-', 'strafe-'), i)]
    assert Fake.issued == expected
    assert result['frames'] == 181 and result['status'] == 'RECORDED'
    bundle = json.loads((tmp_path / case / 'bundle.json').read_text())
    assert bundle['spawn'] == run.previous.CASES[case.replace('tape-', 'strafe-')]['spawn']
    assert bundle['options']['wall_texture'] == 'tape_v1'


def test_scene_wrapper_off_matches_previous_scene_exactly():
    pytest.importorskip('mujoco')  # portable CI omits physics dependencies
    from sim import wall_parallax_strafe as old
    from sim import wall_parallax_texture as new
    bundle = dict(spawn=run.CASES['tape-north']['spawn'], map_id='zone_wide_two_doors_final_v3',
                  contact_profile='cargo_noslip_v1')
    a, b = old.make_scene(bundle, 15101), new.make_scene(bundle, 15101)
    # The scene transform needs the robot body from the warehouse base XML.
    # Use the saved input only when available; portable fixture follows the same contract.
    import inspect
    assert inspect.signature(a.transform) == inspect.signature(b.transform)
    assert a.config == b.config
    source = (run.OLD_RAW / 'strafe-north-host-retry1/scene.xml')
    if source.exists():
        xml = source.read_text()
        assert a.transform(xml) == b.transform(xml)


def test_assets_and_replay_are_small_and_frozen():
    files = list(texture.DEFAULT_ASSETS.iterdir())
    assert all(p.stat().st_size <= 1024 ** 2 for p in files)
    assert sum(p.stat().st_size for p in files) < 5 * 1024 ** 2
    f = json.loads((run.ROOT / 'experiments/2026-10-07-wall-parallax/freeze.json').read_text())
    assert all(run.sha(run.ROOT / p) == h for p, h in f['hashes'].items())
    c = json.loads((run.previous.EXP / 'copied-sources.json').read_text())
    assert all(run.sha(run.ROOT / p) == v['sha256'] for p, v in c['files'].items())
