import json
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from sim.active_wall_texture import transform_xml,generate,EXP
from sim.wall_texture import DEFAULT_ASSETS


def xml():
    walls=json.loads((DEFAULT_ASSETS/'layout.json').read_text())['wall_geometry']
    geoms=''.join(f'<geom name="{w["name"]}" type="box" pos="{" ".join(map(str,w["pos"]))}" size="{" ".join(map(str,w["size"]))}"/>' for w in walls)
    return '<mujoco>\n<worldbody>'+geoms+'</worldbody></mujoco>\n'


def test_off_identical_even_without_assets():
    for s in ('\r\ninvalid',xml(),''):
        assert transform_xml(s,assets='/unavailable') is s


def test_cc0_photo_hash_and_printable_faces(tmp_path):
    import hashlib
    src=json.loads((EXP/'assets/photo-source.json').read_text())
    assert src['license']=='CC0-1.0' and src['technique']=='Surface Photogrammetry'
    assert hashlib.sha256((EXP/'assets'/src['file']).read_bytes()).hexdigest()==src['sha256']
    for profile in ('photo_v1','speckle_v1'):
        record=generate(profile,tmp_path/profile)
        assert len(record['faces'])==24
        candidate=ET.fromstring(transform_xml(xml(),wall_texture=profile,assets=tmp_path/profile))
        old=ET.fromstring(xml())
        for geom in old.findall('worldbody/geom'):
            assert candidate.find(f"worldbody/geom[@name='{geom.get('name')}']").attrib==geom.attrib
        dressed=[g for g in candidate.findall('worldbody/geom') if g.get('name').startswith('tape_v1_')]
        assert len(dressed)==24
        assert all(g.get('contype')==g.get('conaffinity')==g.get('mass')=='0' for g in dressed)
        assert len({f['png_sha256'] for f in record['faces']})>=20
