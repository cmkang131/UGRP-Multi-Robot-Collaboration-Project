"""Speech bubbles are an opt-in, observer-only picture of delivered peer messages."""
import ast
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from harness import speech_bubble_overlay as bubbles
from harness.communication_overlay import KOREAN_FONTS
from harness.speech_bubble_overlay import (
    BubbleMessage, ObserverCamera, SpeechBubbleOverlay, active_bubbles, head_point,
    normalize_observer_overlay, peer_messages_from_events, place_boxes, presentation_timeline)

ROOT = Path(__file__).resolve().parents[1]
HAS_KOREAN_FONT = any(Path(path).is_file() for path in KOREAN_FONTS)


def message(seq, sender, text, start, recipients=('r2', 'r3')):
    return BubbleMessage(seq, sender, tuple(recipients), text, float(start), float(start))


def free_camera(width=640, height=360):
    return ObserverCamera.free(lookat=(0., 0., .1), distance=4., azimuth=90, elevation=-60,
                               fovy_deg=45., width=width, height=height)


# ---- option and observer-only boundary ------------------------------------

def test_overlay_option_is_off_by_default_and_rejects_unknown_values():
    for off in (None, False, '', 'none', 'OFF', 'off'):
        assert normalize_observer_overlay(off) is None
    assert normalize_observer_overlay('speech_bubbles_v1') == 'speech_bubbles_v1'
    with pytest.raises(ValueError, match='unsupported observer_overlay'):
        normalize_observer_overlay('speech_bubbles_v2')


@pytest.mark.parametrize('name', ['r1__robot_cam', 'r3__robot_cam', 'robot_cam',
                                  'cctv_top', 'cctv_top_east', 'cctv_top_north_east'])
def test_actor_cameras_are_refused(name):
    with pytest.raises(ValueError, match='observer-only'):
        ObserverCamera(name, (0, 0, 1), (0, 0, -1), (0, 1, 0), 45., 64, 48)


def test_observer_cameras_are_allowed_and_overlay_needs_an_observer_camera():
    ObserverCamera('cctv_warehouse', (0, 0, 1), (0, 0, -1), (0, 1, 0), 45., 64, 48)
    overlay = SpeechBubbleOverlay([message(1, 'r1', 'hello', 0.)])
    with pytest.raises(TypeError, match='ObserverCamera'):
        overlay.render(np.zeros((48, 64, 3), np.uint8), 1., 'cctv_top', {'r1': (0, 0, 0)})


def _imported_modules(path, *, with_names=True):
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            found.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
            if with_names:
                found.update(f'{node.module}.{item.name}' for item in node.names)
    return found


def test_only_the_observer_renderer_imports_the_overlay():
    """No controller, planner, referee or actor-camera code can reach the bubbles."""
    importers = set()
    for folder in ('harness', 'sim', 'scripts'):
        for path in (ROOT/folder).rglob('*.py'):
            if 'harness.speech_bubble_overlay' in _imported_modules(path):
                importers.add(str(path.relative_to(ROOT)))
    assert importers == {'scripts/render_speech_bubble_video.py'}


def test_overlay_module_depends_on_no_controller_or_simulator_code():
    modules = _imported_modules(ROOT/'harness/speech_bubble_overlay.py', with_names=False)
    local = {name for name in modules if name.startswith(('harness', 'sim', 'scripts'))}
    assert local == {'harness.communication_overlay'}
    source = (ROOT/'harness/speech_bubble_overlay.py').read_text(encoding='utf-8')
    assert 'ground-truth' in source and 'presentation' in source.lower()


def test_renderer_script_never_names_an_actor_camera():
    source = (ROOT/'scripts/render_speech_bubble_video.py').read_text(encoding='utf-8')
    assert 'robot_cam' not in source and 'cctv_top' not in source


# ---- projection ----------------------------------------------------------

def _gl_renderer(model, height, width):
    mujoco = pytest.importorskip('mujoco')
    try:
        return mujoco.Renderer(model, height, width)
    except Exception as error:  # no GL context on this host
        pytest.skip(f'MuJoCo offscreen rendering unavailable: {error}')


def _red_centroid(pixels):
    # Red-ness, not brightness: shading darkens the sphere but keeps G, B well below R.
    red, green, blue = (pixels[..., i].astype(float) for i in range(3))
    mask = (red > 40) & (green < .35*red) & (blue < .35*red)
    assert mask.sum() >= 4, 'marker not visible'
    rows, cols = np.nonzero(mask)
    return float(cols.mean()), float(rows.mean())


MARKER_XML = '''<mujoco><visual><global offwidth="640" offheight="480"/></visual>
<worldbody><light pos="0 0 3" dir="0 0 -1"/>
<geom type="plane" size="3 3 .1" rgba=".5 .5 .5 1"/>
<geom name="marker" type="sphere" size=".06" pos=".4 -.3 .5" rgba="1 0 0 1"/>
<camera name="cctv_warehouse" pos="1.5 -3 2" xyaxes="1 .3 0 -.15 .4 1" fovy="46"/>
</worldbody></mujoco>'''


def test_free_camera_projection_matches_the_real_render():
    mujoco = pytest.importorskip('mujoco')
    model = mujoco.MjModel.from_xml_string(MARKER_XML)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    width, height = 320, 240
    renderer = _gl_renderer(model, height, width)
    try:
        for azimuth, elevation, distance in ((90, -60, 3.), (30, -35, 2.5), (200, -80, 4.)):
            camera = mujoco.MjvCamera()
            camera.type = mujoco.mjtCamera.mjCAMERA_FREE
            camera.lookat[:] = (.2, -.1, .1)
            camera.distance, camera.azimuth, camera.elevation = distance, azimuth, elevation
            renderer.update_scene(data, camera=camera)
            rendered = renderer.render()
            observer = ObserverCamera.free(
                lookat=(.2, -.1, .1), distance=distance, azimuth=azimuth, elevation=elevation,
                fovy_deg=model.vis.global_.fovy, width=width, height=height)
            xy, depth = observer.project(data.geom_xpos[model.geom('marker').id])
            assert depth[0] > 0
            found = _red_centroid(rendered)
            assert abs(found[0] - xy[0, 0]) < 1.5 and abs(found[1] - xy[0, 1]) < 1.5, (azimuth, found, xy)
    finally:
        renderer.close()


def test_fixed_model_camera_projection_matches_the_real_render():
    mujoco = pytest.importorskip('mujoco')
    model = mujoco.MjModel.from_xml_string(MARKER_XML)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    renderer = _gl_renderer(model, 240, 320)
    try:
        renderer.update_scene(data, camera='cctv_warehouse')
        rendered = renderer.render()
    finally:
        renderer.close()
    observer = ObserverCamera.from_mujoco(model, data, 'cctv_warehouse', 320, 240)
    xy, depth = observer.project(data.geom_xpos[model.geom('marker').id])
    found = _red_centroid(rendered)
    assert depth[0] > 0 and abs(found[0] - xy[0, 0]) < 1.5 and abs(found[1] - xy[0, 1]) < 1.5


def test_points_behind_the_camera_are_not_projected():
    camera = free_camera()
    xy, depth = camera.project([camera.position[0] - 10*camera.forward[0],
                                camera.position[1] - 10*camera.forward[1],
                                camera.position[2] - 10*camera.forward[2]])
    assert depth[0] < 0 and np.isnan(xy).all()


def test_head_point_lifts_the_recorded_base_position():
    assert head_point([1., 2., .03]).tolist() == [1., 2., .03 + bubbles.HEAD_OFFSET_M]


# ---- messages and timing --------------------------------------------------

def test_only_delivered_real_model_messages_become_bubbles():
    rows = [
        {'kind': 'decision_explanation', 'seq': 1, 'sender': 'r1', 'text': 'private', 'sim_time_s': 1.},
        {'kind': 'fixture_peer_message', 'seq': 2, 'sender': 'r1', 'text': 'scripted', 'sim_time_s': 1.,
         'source': 'fixture'},
        {'kind': 'peer_message', 'seq': 4, 'sender': 'r2', 'recipients': ['r1', 'r3'],
         'text': '둘째', 'sim_time_s': 3., 'source': 'llm'},
        {'kind': 'peer_message', 'seq': 3, 'sender': 'r1', 'recipients': ['r2', 'r3'],
         'text': '첫째', 'sim_time_s': 3., 'source': 'llm'},
        {'kind': 'peer_message', 'seq': 5, 'sender': 'r3', 'text': 'no time', 'sim_time_s': None},
        {'kind': 'peer_message', 'seq': 6, 'sender': 'r3', 'text': '', 'sim_time_s': 4.},
    ]
    found = peer_messages_from_events(rows)
    assert [(m.seq, m.sender, m.text) for m in found] == [(3, 'r1', '첫째'), (4, 'r2', '둘째')]
    assert found[0].recipients == ('r2', 'r3') and found[0].sim_time_s == 3.


def test_bubble_lives_show_seconds_and_is_replaced_by_the_senders_next_message():
    first, second = message(1, 'r1', 'one', 10.), message(2, 'r1', 'two', 13.)
    other = message(3, 'r2', 'other', 11.)
    messages = [first, second, other]
    assert active_bubbles(messages, 9.9, show_s=6.)[0] == []
    seen = active_bubbles(messages, 12., show_s=6.)[0]
    assert {b.message.seq for b in seen} == {1, 3}
    seen = active_bubbles(messages, 13.5, show_s=6.)[0]
    assert {b.message.seq for b in seen} == {2, 3}          # r1's newer message replaced seq 1
    assert {b.message.seq for b in active_bubbles(messages, 17.5, show_s=6.)[0]} == {2}
    assert active_bubbles(messages, 19.1, show_s=6.)[0] == []
    fade = {b.message.seq: b.alpha for b in active_bubbles(messages, 10.1, show_s=6.)[0]}
    assert 0 < fade[1] < 1
    assert active_bubbles(messages, 12., show_s=6.)[0][0].alpha == 1.


def test_receiver_chip_is_optional_short_and_skipped_for_speakers():
    sent = [message(1, 'r1', 'hi', 5., ('r2', 'r3')), message(2, 'r3', 'ok', 5.5, ('r1',))]
    assert active_bubbles(sent, 5.6, show_s=6.)[1] == []                       # off by default
    _, chips = active_bubbles(sent, 5.6, show_s=6., receipt_s=1.5, receipts=True)
    assert {(c.receiver, c.sender) for c in chips} == {('r2', 'r1')}          # r1 and r3 are speaking
    assert active_bubbles(sent, 8., show_s=6., receipt_s=1.5, receipts=True)[1] == []


def test_timeline_freezes_the_scene_while_same_instant_messages_appear_in_order():
    talk = [message(1, 'r1', 'a', 5.), message(2, 'r2', 'b', 5.), message(3, 'r3', 'c', 5.),
            message(4, 'r1', 'd', 8.)]
    frames, retimed = presentation_timeline(talk, start_s=0., end_s=10., speed=4., fps=10.,
                                            beat_s=2., linger_s=1.)
    sims = [sim for sim, _ in frames]
    assert sims == sorted(sims) and sims[0] == 0.
    held = [clock for sim, clock in frames if sim == 5.]
    assert len(held) == 50                                    # (3-1)*2 s beats + 1 s linger at 10 fps
    onsets = {m.seq: m.start_s for m in retimed}
    assert onsets[2] - onsets[1] == pytest.approx(2.) and onsets[3] - onsets[2] == pytest.approx(2.)
    assert onsets[1] == pytest.approx(held[0])
    assert all(m.sim_time_s in (5., 8.) for m in retimed)      # the logged time is untouched
    assert onsets[4] > onsets[3]
    clocks = [clock for _, clock in frames]
    assert clocks == sorted(clocks) and clocks[1] - clocks[0] == pytest.approx(.1)
    # without the pause the scene never stops and every message starts when SIM reaches it
    frames2, retimed2 = presentation_timeline(talk, start_s=0., end_s=10., speed=4., fps=10.,
                                              pause_for_dialogue=False)
    assert len({sim for sim, _ in frames2}) == len(frames2)
    assert all(abs(m.start_s - ((m.sim_time_s)/4.)) < .31 for m in retimed2)


def test_timeline_skips_messages_outside_the_window_and_checks_arguments():
    outside = [message(1, 'r1', 'early', 1.), message(2, 'r1', 'late', 50.)]
    _, retimed = presentation_timeline(outside, start_s=5., end_s=20., speed=4., fps=10.)
    assert retimed == []
    with pytest.raises(ValueError):
        presentation_timeline(outside, start_s=5., end_s=5., speed=4., fps=10.)


# ---- layout ----------------------------------------------------------------

def _inside(rect, size, margin=0):
    return (rect[0] >= margin and rect[1] >= margin
            and rect[0] + rect[2] <= size[0] - margin and rect[1] + rect[3] <= size[1] - margin)


def _overlaps(a, b):
    return min(a[0] + a[2], b[0] + b[2]) > max(a[0], b[0]) and min(a[1] + a[3], b[1] + b[3]) > max(a[1], b[1])


def test_close_robots_get_separate_bubbles_inside_the_frame_with_tails_on_their_heads():
    size = (1280, 720)
    heads = {'r1': (300., 430.), 'r2': (305., 365.), 'r3': (310., 300.)}
    items = [(rid, head, (280, 100)) for rid, head in heads.items()]
    placed = place_boxes(items, size)
    rects = [p.rect for p in placed]
    assert all(_inside(rect, size, 8) for rect in rects)
    assert not any(_overlaps(a, b) for i, a in enumerate(rects) for b in rects[i + 1:])
    assert {p.key: p.tip for p in placed} == heads
    for place in placed:       # a bubble never sits on its own head
        assert not _overlaps(place.rect, (place.tip[0] - 1, place.tip[1] - 1, 2, 2))


def test_bubbles_are_clamped_and_flip_below_when_the_head_is_near_the_frame_top():
    size = (400, 300)
    near_top = place_boxes([('a', (200., 30.), (120, 60))], size)[0]
    assert near_top.side == 'below' and near_top.rect[1] > 30 and _inside(near_top.rect, size, 8)
    corner = place_boxes([('b', (4., 280.), (120, 60))], size)[0]
    assert _inside(corner.rect, size, 8) and corner.side == 'above'
    edge = place_boxes([('c', (396., 200.), (120, 60))], size)[0]
    assert _inside(edge.rect, size, 8) and edge.tip == (396., 200.)


def test_placement_keeps_its_previous_spot_while_it_is_still_free():
    size = (800, 600)
    items = [('r1', (300., 400.), (200, 80)), ('r2', (320., 340.), (200, 80))]
    first = place_boxes(items, size)
    again = place_boxes(items, size, prefer={p.key: p.choice for p in first})
    assert [p.rect for p in again] == [p.rect for p in first]
    # a stale preference that now collides is dropped, never forced
    crowded = place_boxes(items, size, prefer={'r2': 0})
    assert not _overlaps(crowded[0].rect, crowded[1].rect)


def test_tail_leaves_the_edge_that_faces_the_head():
    rect = (200., 100., 160., 60.)
    assert bubbles.tail_edge(rect, (260., 200.), 20.) == {'edge': 'bottom', 'point': (260., 160.), 'normal': (0., 1.)}
    assert bubbles.tail_edge(rect, (260., 40.), 20.)['edge'] == 'top'
    assert bubbles.tail_edge(rect, (20., 130.), 20.) == {'edge': 'left', 'point': (200., 130.), 'normal': (-1., 0.)}
    assert bubbles.tail_edge(rect, (500., 135.), 20.)['edge'] == 'right'
    # a head slightly off to one side still uses the bottom edge; the point stays off the corners
    near = bubbles.tail_edge(rect, (180., 190.), 20.)
    assert near['edge'] == 'bottom' and near['point'] == (220., 160.)
    assert bubbles.tail_edge(rect, (230., 110.), 20.)['edge'] == 'bottom'       # head inside: fallback


# ---- drawing ---------------------------------------------------------------

def _scene(width=640, height=360):
    camera = free_camera(width, height)
    heads = {'r1': head_point([-.4, -.2, .03]), 'r2': head_point([.1, -.1, .03]),
             'r3': head_point([.5, .1, .03])}
    return camera, heads


def test_render_draws_near_the_head_without_touching_the_input_or_other_pixels():
    camera, heads = _scene()
    frame = np.full((camera.height, camera.width, 3), 90, np.uint8)
    before = frame.copy()
    overlay = SpeechBubbleOverlay([message(1, 'r1', 'I take the red box to zone A.', 2.)], show_s=6.)
    drawn = overlay.render(frame, 3., camera, heads)
    assert np.array_equal(frame, before) and drawn is not frame
    changed = np.argwhere((drawn != frame).any(axis=2))
    assert len(changed) > 500
    head_xy, _ = camera.project(heads['r1'])
    top, left = changed.min(axis=0)
    bottom, right = changed.max(axis=0)
    assert top < head_xy[0, 1] and left < head_xy[0, 0] + 20 and right > head_xy[0, 0] - 20
    assert bottom >= head_xy[0, 1] - 2          # the tail reaches down to the head
    assert (right - left) < camera.width*.6 and (bottom - top) < camera.height*.6
    # nothing visible -> the very same array comes back (off-path bytes stay identical)
    assert overlay.render(frame, 0., camera, heads) is frame
    assert overlay.render(frame, 99., camera, heads) is frame


def test_each_sender_gets_a_distinct_colour_and_robots_off_screen_get_no_bubble():
    camera, heads = _scene()
    frame = np.full((camera.height, camera.width, 3), 60, np.uint8)
    one = SpeechBubbleOverlay([message(1, 'r1', 'hello', 1.)]).render(frame, 2., camera, heads)
    two = SpeechBubbleOverlay([message(1, 'r2', 'hello', 1.)]).render(frame, 2., camera, heads)
    three = SpeechBubbleOverlay([message(1, 'r3', 'hello', 1.)]).render(frame, 2., camera, heads)
    assert not np.array_equal(one, two) and not np.array_equal(two, three)
    away = dict(heads, r1=head_point([50., 50., .03]))
    gone = SpeechBubbleOverlay([message(1, 'r1', 'hello', 1.)])
    assert gone.render(frame, 2., camera, away) is frame


def test_long_messages_wrap_to_three_lines_and_end_with_an_ellipsis():
    from PIL import Image, ImageDraw
    from harness.communication_overlay import _wrapped_lines
    font, _ = bubbles.load_font(KOREAN_FONTS, 40)
    draw = ImageDraw.Draw(Image.new('L', (8, 8)))
    lines = _wrapped_lines('claim green-1 for zone C then wait ' * 12, draw, font, 500, limit=3)
    assert len(lines) == 3 and lines[-1].endswith('…')


@pytest.mark.skipif(not HAS_KOREAN_FONT, reason='no Korean font on this host')
def test_korean_message_and_receipt_chip_render_with_a_korean_font():
    camera, heads = _scene()
    frame = np.full((camera.height, camera.width, 3), 60, np.uint8)
    sent = [message(1, 'r1', '두 로봇이 함께 빨간 상자를 구역 A로 옮깁니다.', 1.)]
    overlay = SpeechBubbleOverlay(sent, receipts=True)
    assert overlay.korean_font
    plain = SpeechBubbleOverlay(sent).render(frame, 1.5, camera, heads)
    with_chips = overlay.render(frame, 1.5, camera, heads)
    assert not np.array_equal(plain, frame) and not np.array_equal(plain, with_chips)


def test_without_a_korean_font_text_falls_back_without_failing():
    camera, heads = _scene()
    frame = np.full((camera.height, camera.width, 3), 60, np.uint8)
    overlay = SpeechBubbleOverlay([message(1, 'r1', '한글 메시지', 1.)], font_paths=())
    assert not overlay.korean_font
    assert not np.array_equal(overlay.render(frame, 1.5, camera, heads), frame)


def test_frame_must_match_the_observer_camera():
    camera, heads = _scene()
    overlay = SpeechBubbleOverlay([message(1, 'r1', 'hi', 0.)])
    with pytest.raises(ValueError, match='matching the observer camera'):
        overlay.render(np.zeros((10, 10, 3), np.uint8), 1., camera, heads)


# ---- renderer script -------------------------------------------------------

REPLAY_XML = '''<mujoco><visual><global offwidth="640" offheight="480"/></visual>
<worldbody><light pos="0 0 3" dir="0 0 -1"/>
<geom type="plane" size="3 3 .1" rgba=".6 .6 .6 1"/>
<body name="r1__robot" pos="-.3 0 .03"><freejoint name="r1__base_free"/>
  <geom type="box" size=".08 .06 .03" rgba=".9 .6 0 1"/></body>
<body name="r2__robot" pos=".3 .2 .03"><freejoint name="r2__base_free"/>
  <geom type="box" size=".08 .06 .03" rgba="0 .5 .9 1"/></body>
</worldbody></mujoco>'''


def _make_run(tmp_path, *, with_conversation=True):
    mujoco = pytest.importorskip('mujoco')
    run = tmp_path/'run'
    (run/'replay').mkdir(parents=True)
    model = mujoco.MjModel.from_xml_string(REPLAY_XML)
    mujoco.mj_saveModel(model, str(run/'replay/model.mjb'), None)
    count = 41
    qpos = np.tile(model.qpos0, (count, 1))
    qpos[:, 0] += np.linspace(0, .2, count)                 # r1 drives a little
    np.savez_compressed(run/'replay/states.npz', time=np.linspace(0., 4., count), qpos=qpos,
                        mocap_pos=np.zeros((count, 0, 3)), mocap_quat=np.zeros((count, 0, 4)))
    (run/'replay/labels.json').write_text('[]\n')
    (run/'replay/view.json').write_text(json.dumps({'lookat': [0, .1, .1], 'distance': 2.2,
                                                    'azimuth': 90, 'elevation': -60}))
    sha = lambda name: hashlib.sha256((run/'replay'/name).read_bytes()).hexdigest()
    (run/'replay/replay.json').write_text(json.dumps({
        'schema': 'ugrp.dispatch_replay.v1', 'fps_sim': 10, 'frames': count,
        'files_sha256': {name: sha(name) for name in ('model.mjb', 'states.npz', 'labels.json')}}))
    if with_conversation:
        (run/'team').mkdir()
        rows = [{'kind': 'peer_message', 'seq': 1, 'sender': 'r1', 'recipients': ['r2'], 'source': 'llm',
                 'text': 'I take the box.', 'sim_time_s': 1.0},
                {'kind': 'peer_message', 'seq': 2, 'sender': 'r2', 'recipients': ['r1'], 'source': 'llm',
                 'text': 'Then I wait.', 'sim_time_s': 1.0}]
        (run/'team/conversation.jsonl').write_text(
            '\n'.join(json.dumps(row) for row in rows) + '\n', encoding='utf-8')
    return run


def _frames(path):
    cv2 = pytest.importorskip('cv2')
    capture = cv2.VideoCapture(str(path))
    found = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        found.append(frame)
    capture.release()
    return found


needs_ffmpeg = pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='ffmpeg missing')


@needs_ffmpeg
def test_render_script_default_is_off_and_never_touches_the_overlay(tmp_path, monkeypatch):
    from scripts import render_speech_bubble_video as script
    run = _make_run(tmp_path, with_conversation=False)     # no conversation needed when off
    monkeypatch.setattr(SpeechBubbleOverlay, 'render',
                        lambda *args, **kwargs: pytest.fail('overlay used while off'))
    out = tmp_path/'off.mp4'
    try:
        assert script.main([str(run), str(out), '--size', '320x240', '--fps', '5', '--speed', '4']) == 0
    except Exception as error:
        if 'Renderer' in repr(error) or 'GL' in str(error):
            pytest.skip(f'offscreen rendering unavailable: {error}')
        raise
    record = json.loads(out.with_suffix('.render.json').read_text())
    assert record['observer_overlay'] is None and record['schedule'] == []
    assert len(_frames(out)) == record['frames'] > 0


@needs_ffmpeg
def test_render_script_with_the_option_draws_bubbles_and_audits_the_schedule(tmp_path):
    from scripts import render_speech_bubble_video as script
    run = _make_run(tmp_path)
    plain, bubbled = tmp_path/'plain.mp4', tmp_path/'bubbled.mp4'
    common = ['--size', '320x240', '--fps', '5', '--speed', '2', '--zoom', '1.2', '--beat-seconds', '1',
              '--linger-seconds', '1', '--bubble-seconds', '3']
    try:
        assert script.main([str(run), str(plain), *common]) == 0
    except Exception as error:
        if 'Renderer' in repr(error) or 'GL' in str(error):
            pytest.skip(f'offscreen rendering unavailable: {error}')
        raise
    assert script.main([str(run), str(bubbled), '--observer-overlay', 'speech_bubbles_v1', '--receipts',
                        *common]) == 0
    record = json.loads(bubbled.with_suffix('.render.json').read_text())
    assert record['observer_overlay'] == 'speech_bubbles_v1' and record['zoom'] == 1.2
    assert 'ground-truth' in record['head_positions']
    assert [row['sender'] for row in record['schedule']] == ['r1', 'r2']
    assert [row['logged_sim_time_s'] for row in record['schedule']] == [1.0, 1.0]
    assert record['schedule'][1]['video_onset_s'] - record['schedule'][0]['video_onset_s'] == pytest.approx(1.)
    assert record['frames'] > json.loads(plain.with_suffix('.render.json').read_text())['frames'] - 1
    before, after = _frames(plain), _frames(bubbled)
    # the first frames (before anyone talks) are unchanged; later frames carry the bubbles
    assert np.abs(before[0].astype(int) - after[0].astype(int)).mean() < 1.
    held = [i for i, frame in enumerate(after) if np.abs(frame.astype(int) - before[min(i, len(before)-1)].astype(int)).mean() > 2.]
    assert held


@needs_ffmpeg
def test_render_script_refuses_long_videos_and_existing_outputs(tmp_path):
    from scripts import render_speech_bubble_video as script
    run = _make_run(tmp_path)
    with pytest.raises(SystemExit) as error:
        script.main([str(run), str(tmp_path/'long.mp4'), '--observer-overlay', 'speech_bubbles_v1',
                     '--speed', '0.5', '--fps', '10', '--max-video-seconds', '5', '--size', '320x240'])
    assert error.value.code == 2 and not (tmp_path/'long.mp4').exists()
    existing = tmp_path/'there.mp4'
    existing.write_bytes(b'x')
    with pytest.raises(SystemExit):
        script.main([str(run), str(existing), '--size', '320x240'])
    assert existing.read_bytes() == b'x'
    with pytest.raises(SystemExit):
        script.main([str(run), str(tmp_path/'bad.mp4'), '--observer-overlay', 'bubbles_v9'])
