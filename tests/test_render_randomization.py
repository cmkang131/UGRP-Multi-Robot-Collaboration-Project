"""Model-only checks (no stepping): appearance arrays change, everything else is identical."""
import mujoco, numpy as np
from harness.render_randomization import draw, apply, RANGES

XML = '''<mujoco><asset><texture name="ground" type="2d" builtin="checker" rgb1=".36 .35 .34" rgb2=".62 .61 .59" width="8" height="8"/>
<material name="groundmat" texture="ground" rgba="1 1 1 1"/></asset><worldbody>
<light name="l0" pos="0 0 3" diffuse=".3 .3 .3"/><light name="l1" pos="1 0 3" diffuse=".21 .21 .21"/>
<geom name="floor" type="plane" size="3 3 .1" material="groundmat"/>
<geom name="zone_wall_n" type="box" size="1 .02 .1" pos="0 1 .1" rgba=".23 .28 .33 1"/>
<geom name="beam_end_teal" type="box" size=".03 .02 .02" pos="0 0 .2" rgba=".02 .95 .6 1"/>
<body name="robot" pos="0 0 .5"><freejoint/><geom name="r1__chassis" type="box" size=".1 .1 .05" rgba=".1 .1 .1 1"/></body>
</worldbody></mujoco>'''


def test_off_changes_nothing():
    m = mujoco.MjModel.from_xml_string(XML); ref = mujoco.MjModel.from_xml_string(XML)
    assert apply(m, None)['profile'] == 'off' and apply(m, {'profile': 'off'})['profile'] == 'off'
    assert np.array_equal(m.light_diffuse, ref.light_diffuse) and np.array_equal(m.geom_rgba, ref.geom_rgba)


def test_on_touches_only_lights_floor_and_walls():
    m = mujoco.MjModel.from_xml_string(XML); ref = mujoco.MjModel.from_xml_string(XML)
    p = draw(80001, m.nlight); rec = apply(m, p)
    assert rec['touched'] == {'materials': ['groundmat'], 'geoms': ['zone_wall_n']}
    assert not np.array_equal(m.light_diffuse, ref.light_diffuse)
    names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, g) for g in range(m.ngeom)]
    for g, n in enumerate(names):
        if n != 'zone_wall_n':
            assert np.array_equal(m.geom_rgba[g], ref.geom_rgba[g]), n          # robot, end band, floor geom unchanged
    for arr in ('geom_size', 'geom_pos', 'body_mass', 'geom_friction', 'cam_fovy', 'opt.timestep'):
        a, b = (eval('x.'+arr) for x in (m, ref))
        assert np.array_equal(np.asarray(a), np.asarray(b)), arr
    lo, hi = RANGES['light_diffuse_scale']
    ratio = m.light_diffuse[0, 0]/ref.light_diffuse[0, 0]
    assert lo*.9-1e-9 <= ratio <= hi*1.1+1e-9 and len(rec['params_sha256']) == 64


def test_draw_is_deterministic_per_seed():
    assert draw(5, 4) == draw(5, 4) and draw(5, 4) != draw(6, 4)
