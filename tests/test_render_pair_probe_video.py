"""scripts/render_pair_probe_video.py: reads saved stage-probe case directories only (no physics, no simulation)."""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from harness.zone_own_guards import GATE_LOADED, GATE_UNLOADED
from scripts import render_pair_probe_video as rv

ROOT = Path(__file__).resolve().parents[1]
HAVE_FFMPEG = shutil.which('ffmpeg') is not None


def make_case(tmp_path, name, *, t_end=2.0, with_pf=True, pf_every=5, with_robots_json=True, with_frames=False,
              verdict=None):
    """A synthetic case: trace at 20 Hz from t=1.0, pf every ``pf_every`` rows, frames at 5 Hz named by index."""
    case = tmp_path / name
    (case / 'eval_only').mkdir(parents=True)
    rows = []
    n = int(round((t_end - 1.0) / 0.05)) + 1
    for i in range(n):
        t = 1.0 + 0.05 * i
        row = {'t': t, 'states': {'r1': None, 'r2': None}, 'beam_xyz': [1.5, 0.0, 0.0], 'beam_yaw': 0.01 * i,
               'robots': {'r1': [1.0 + 0.01 * i, 0.0, 0.0], 'r2': [2.0, 0.0, math.pi]}}
        if with_pf and i % pf_every == 0:
            row['pf'] = {'r1': {'std_yaw_rad': 0.010 + 0.001 * i}, 'r2': {'std_yaw_rad': 0.012 + 0.001 * i}}
        rows.append(row)
    (case / 'eval_only' / 'trace.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\ntruncated {')
    frames = {}
    for rid in ('r1', 'r2'):
        frames[rid] = {'frames': [{'frame': k, 't': 1.0 + 0.2 * k, 'report': {'std_yaw_rad': 0.02 + 0.001 * k}}
                                  for k in range(int((t_end - 1.0) / 0.2) + 1)]}
    if with_robots_json:
        (case / 'robots.json').write_text(json.dumps(frames))
    if with_frames:
        import matplotlib.image as mpimg
        import numpy as np
        for rid in ('r1', 'r2'):
            (case / 'frames' / rid).mkdir(parents=True)
            for k in range(len(frames[rid]['frames'])):
                mpimg.imsave(str(case / 'frames' / rid / f'{k:05d}.jpg'), np.full((8, 8, 3), 100 + k, np.uint8))
    if verdict:
        (case / 'result.json').write_text(json.dumps({'row': verdict}))
    return case


def test_gate_comes_from_the_harness_constants_not_a_local_number():
    assert rv.GATES['loaded'] is GATE_LOADED and rv.GATES['unloaded'] is GATE_UNLOADED and rv.GATES['none'] is None
    assert rv.gate_mrad(GATE_LOADED) == pytest.approx(GATE_LOADED.high_yaw_rad * 1000)
    assert rv.gate_mrad(None) == 0.0
    source = (ROOT / 'scripts' / 'render_pair_probe_video.py').read_text()
    code = '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('#'))
    assert not re.search(r'radians\(\s*3\b|52\.3|52\.4|0\.0523', code)     # no copy of the 3 degree gate


def test_rows_without_pf_are_skipped_and_a_truncated_last_line_is_ignored(tmp_path):
    case = rv.load_case(make_case(tmp_path, 'a', pf_every=5), 'A')
    assert len(case.rows) == 21                                   # 1.0 .. 2.0 s at 20 Hz; the broken line is dropped
    times, sigma = case.sigma['r1']
    assert len(times) == 5 and times == pytest.approx([1.0, 1.25, 1.5, 1.75, 2.0])
    assert sigma[0] == pytest.approx(10.0)                        # mrad
    assert case.sigma_source == 'trace'


def test_sigma_falls_back_to_the_robot_reports_when_the_trace_has_no_pf(tmp_path):
    case = rv.load_case(make_case(tmp_path, 'nopf', with_pf=False), 'N')
    assert case.sigma_source == 'report' and len(case.sigma['r1'][0]) == 6
    none = rv.load_case(make_case(tmp_path, 'nothing', with_pf=False, with_robots_json=False), 'X')
    assert none.sigma_source == 'none' and none.sigma['r1'] == ([], [])


def test_frame_schedule_covers_the_longest_case_at_the_requested_step(tmp_path):
    a = rv.load_case(make_case(tmp_path, 'a', t_end=2.0), 'A')
    b = rv.load_case(make_case(tmp_path, 'b', t_end=3.0), 'B')
    times = rv.frame_schedule([a, b], 0.25)
    assert times[0] == pytest.approx(1.0) and times[-1] == pytest.approx(3.0) and len(times) == 9
    assert len(rv.frame_schedule([a], 0.3)) == 5                  # 1.0, 1.3, 1.6, 1.9 and the last row 2.0
    with pytest.raises(ValueError):
        rv.frame_schedule([a], 0)


def test_wrist_frame_index_uses_robots_json_and_flags_the_approximation(tmp_path):
    exact = rv.load_case(make_case(tmp_path, 'e'), 'E')
    assert exact.frame_time_exact
    assert rv.wrist_frame_index(exact, 'r1', 0.5) is None
    assert rv.wrist_frame_index(exact, 'r1', 1.0) == 0
    assert rv.wrist_frame_index(exact, 'r1', 1.39) == 1 and rv.wrist_frame_index(exact, 'r2', 1.41) == 2
    approx = rv.load_case(make_case(tmp_path, 'p', with_robots_json=False), 'P')
    assert not approx.frame_time_exact
    assert rv.wrist_frame_index(approx, 'r1', 1.41) == 2


def test_verdict_text_comes_from_result_json(tmp_path):
    fail = rv.load_case(make_case(tmp_path, 'f', verdict={'category': 'POSE_UNCERTAIN', 'passed': False,
                                                          'first_failure': {'robot_id': 'r1', 'sim_s': 1.9}}), 'F')
    assert fail.verdict == ('POSE_UNCERTAIN (r1 @ 1.9 s)', False)
    ok = rv.load_case(make_case(tmp_path, 'o', verdict={'category': 'PASS', 'passed': True,
                                                        'exit_sim_s': {'r1': 2.0, 'r2': 2.05}}), 'O')
    assert ok.verdict == ('PASS (exit @ 2.0 s)', True)
    assert rv.load_case(make_case(tmp_path, 'n'), 'N').verdict is None


def test_missing_trace_is_a_clear_error(tmp_path):
    with pytest.raises(rv.RenderError, match='trace.jsonl'):
        rv.load_case(tmp_path, 'x')
    assert rv.main(['--case', str(tmp_path), '--output', str(tmp_path / 'o.mp4')]) == 2


def test_render_yields_one_frame_per_scheduled_time_and_survives_no_korean_font(tmp_path, monkeypatch):
    pytest.importorskip('matplotlib')
    monkeypatch.setattr(rv, 'FONT_CANDIDATES', ())
    monkeypatch.setattr(rv, 'FONT_FAMILIES', ())
    assert rv.pick_font() is None
    a = rv.load_case(make_case(tmp_path, 'a', t_end=2.0, with_frames=True), 'before')
    b = rv.load_case(make_case(tmp_path, 'b', t_end=2.6, with_frames=True), 'after')
    frames = list(rv.render_frames([a, b], dt=0.25, wrist=True, size_px=(640, 360)))
    assert len(frames) == len(rv.frame_schedule([a, b], 0.25)) == 8
    assert frames[0].shape == (360, 640, 4)


def test_gate_line_follows_the_selected_profile(tmp_path, monkeypatch):
    pytest.importorskip('matplotlib')
    seen = []
    real = rv.gate_mrad
    monkeypatch.setattr(rv, 'gate_mrad', lambda p: seen.append(p) or real(p))
    case = rv.load_case(make_case(tmp_path, 'g', t_end=1.2), 'G')
    list(rv.render_frames([case], gate='unloaded', size_px=(320, 180), max_frames=1))
    list(rv.render_frames([case], gate='none', size_px=(320, 180), max_frames=1))
    assert seen == [GATE_UNLOADED, None]


@pytest.mark.skipif(not HAVE_FFMPEG, reason='ffmpeg not installed')
def test_main_writes_an_mp4_with_the_expected_frame_count(tmp_path, capsys):
    pytest.importorskip('matplotlib')
    a = make_case(tmp_path, 'a', t_end=2.0)
    b = make_case(tmp_path, 'b', t_end=2.5)
    out = tmp_path / 'sub' / 'v.mp4'
    code = rv.main(['--case', str(a), '--label', 'A', '--case', str(b), '--label', 'B', '--output', str(out),
                    '--fps', '4', '--dt', '0.25', '--width', '640', '--height', '360'])
    assert code == 0 and out.is_file() and out.stat().st_size > 0
    info = json.loads(capsys.readouterr().out)
    assert info['frames'] == 7 and info['sha256'] == rv.sha256_of(out)
    if shutil.which('ffprobe'):
        probe = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v:0', '-show_entries',
                                'stream=nb_read_frames', '-of', 'csv=p=0', str(out)], capture_output=True, text=True)
        assert probe.stdout.strip() == '7'


def test_missing_ffmpeg_is_a_clear_error(tmp_path, monkeypatch, capsys):
    pytest.importorskip('matplotlib')
    monkeypatch.setattr(rv.shutil, 'which', lambda name: None)
    case = make_case(tmp_path, 'a')
    assert rv.main(['--case', str(case), '--output', str(tmp_path / 'o.mp4')]) == 2
    assert 'ffmpeg is required' in capsys.readouterr().err
