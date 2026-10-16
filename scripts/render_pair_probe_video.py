#!/usr/bin/env python3
"""Render a pair stage-probe case (or two cases side by side) as an mp4 for reports and submissions.

The video is built ONLY from files the probe already wrote to a case directory:

* ``eval_only/trace.jsonl``: evaluation ground truth, sampled at 20 Hz (beam pose, robot poses) and, for runs made with
  ``--pf-track``, the robots' own particle-filter estimate (``pf.<robot>.std_yaw_rad``) about every 0.25 s.
* ``robots.json`` (optional ``--wrist``): each robot's saved camera frame index, its sim time ``t`` and the robot's own
  report (``report.std_yaw_rad``).  The frame index in ``frames/<robot>/NNNNN.jpg`` matches ``frames[].frame``.

What the picture shows, and what it does not
--------------------------------------------
* The top-down panel is a DRAWING of the evaluation ground-truth positions (beam and robots r1/r2).  It is NOT a
  camera image: the shared top camera is not saved by the probe.  It is for the evaluator and is never a robot input.
* The lower panel is the robot's own yaw uncertainty sigma (what its filter believes), with the loaded uncertainty
  gate imported from ``harness.zone_own_guards.GATE_LOADED`` (never hard-coded here).
* ``--wrist`` adds each robot's saved own-camera frame.  Frames are 5 Hz and are matched to the sim time through
  ``robots.json``; when that record is missing the match is an approximation (index * 0.2 s from the first trace time) and
  the video says so.

Usage (from the repository root; needs matplotlib and ffmpeg)::

    .venv-sim-worker-mac/bin/python scripts/render_pair_probe_video.py \\
        --case outputs/<runA>/cases/<case> --label "이전 (실패)" \\
        --case outputs/<runB>/cases/<case> --label "yaw 수정 (통과)" \\
        --output outputs/videos/topdown.mp4 --fps 8 --dt 0.25 [--wrist]

No physics or simulation runs here; the script only reads saved case directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.ultrasonic_carry import BEAM_LENGTH_M  # noqa: E402
from harness.zone_own_guards import GATE_LOADED, GATE_UNLOADED  # noqa: E402

GATES = {'loaded': GATE_LOADED, 'unloaded': GATE_UNLOADED, 'none': None}
ROBOTS = ('r1', 'r2')
FRAME_PERIOD_S = 0.2                      # own-camera rate (5 Hz); used only when robots.json is missing
FONT_CANDIDATES = (
    '/System/Library/Fonts/Supplemental/AppleGothic.ttf',
    '/System/Library/Fonts/AppleSDGothicNeo.ttc',
    '/Library/Fonts/NanumGothic.ttf',
    '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
)
FONT_FAMILIES = ('AppleGothic', 'Apple SD Gothic Neo', 'NanumGothic', 'Noto Sans CJK KR', 'Noto Sans KR')

TEXT = {
    'ko': {
        'title': '위에서 본 정답 위치(평가용, 로봇 입력 아님)',
        'beam': '빔', 'ended': '실행 종료 %.1f s', 'beam_yaw': '빔 yaw(정답) %.1f mrad',
        'sigma_ylabel': 'yaw 불확실도 σ (mrad)', 'xlabel': 'sim 시간 (s)',
        'gate': '게이트 %.0f° (%.1f mrad): σ가 %.1f s 넘으면 SELF_POSE_UNCERTAIN(yaw)',
        'no_gate': '게이트 선 없음(이 단계의 종료 원인은 σ 게이트가 아님)',
        'src_trace': 'σ 출처: 로봇 PF(trace.jsonl pf)', 'src_report': 'σ 출처: 로봇 보고(robots.json report)',
        'src_none': 'σ 기록 없음', 'wrist_title': '%s %s 손목 카메라', 'wrist_none': '프레임 없음',
        'wrist_approx': '손목 프레임 시각은 근사(robots.json 없음)',
        'footer': 'sim t=%.1f s (재생 x%.1f) | 정답 그림이며 카메라 영상 아님 | stage probe, E2E 성공 아님',
    },
    'en': {
        'title': 'Top-down ground-truth positions (evaluation only, not robot input)',
        'beam': 'beam', 'ended': 'run ended %.1f s', 'beam_yaw': 'beam yaw (truth) %.1f mrad',
        'sigma_ylabel': 'own yaw uncertainty sigma (mrad)', 'xlabel': 'sim time (s)',
        'gate': 'gate %.0f deg (%.1f mrad): sigma above it for %.1f s -> SELF_POSE_UNCERTAIN(yaw)',
        'no_gate': 'no gate line (this stage does not end on the sigma gate)',
        'src_trace': 'sigma source: robot PF (trace.jsonl pf)', 'src_report': 'sigma source: robot report (robots.json)',
        'src_none': 'no sigma recorded', 'wrist_title': '%s %s wrist camera', 'wrist_none': 'no frame',
        'wrist_approx': 'wrist frame time is approximate (no robots.json)',
        'footer': 'sim t=%.1f s (playback x%.1f) | drawing of ground truth, not a camera image | stage probe, not E2E success',
    },
}


class RenderError(RuntimeError):
    """A clear, user-facing failure (missing tool, unreadable case)."""


@dataclass
class CaseData:
    directory: Path
    label: str
    rows: list                                   # trace rows in time order
    sigma: dict = field(default_factory=dict)    # robot -> (times, sigma_mrad) arrays as lists
    sigma_source: str = 'none'                   # 'trace' | 'report' | 'none'
    frame_times: dict = field(default_factory=dict)   # robot -> {frame index: t}
    frame_time_exact: bool = False
    result: dict = field(default_factory=dict)

    @property
    def verdict(self) -> Optional[tuple]:
        """(text, passed) from the probe's own result.json row, or None when the record is missing."""
        row = self.result.get('row') or {}
        if not row.get('category'):
            return None
        text = str(row['category'])
        ff = row.get('first_failure') or {}
        if ff.get('sim_s') is not None:
            text += ' (%s @ %.1f s)' % (ff.get('robot_id', '?'), ff['sim_s'])
        elif row.get('exit_sim_s'):
            text += ' (exit @ %.1f s)' % max(row['exit_sim_s'].values())
        return text, bool(row.get('passed'))

    @property
    def t_first(self) -> float:
        return self.rows[0]['t']

    @property
    def t_last(self) -> float:
        return self.rows[-1]['t']


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def load_trace(case_dir: Path) -> list:
    path = case_dir / 'eval_only' / 'trace.jsonl'
    if not path.is_file():
        raise RenderError(f'{path} not found (is this a stage-probe case directory?)')
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue                              # a truncated last line of a killed run
        if isinstance(row.get('t'), (int, float)) and isinstance(row.get('robots'), dict) \
                and all(r in row['robots'] for r in ROBOTS):
            rows.append(row)
    if not rows:
        raise RenderError(f'{path} has no usable rows (need t and robots.r1/r2)')
    rows.sort(key=lambda r: r['t'])
    return rows


def sigma_from_trace(rows: Sequence[dict]) -> dict:
    """Rows without ``pf`` (or without the robot's std_yaw_rad) are skipped, never interpolated."""
    out = {}
    for rid in ROBOTS:
        ts, ss = [], []
        for row in rows:
            std = ((row.get('pf') or {}).get(rid) or {}).get('std_yaw_rad')
            if isinstance(std, (int, float)) and math.isfinite(std):
                ts.append(row['t'])
                ss.append(std * 1000.0)
        out[rid] = (ts, ss)
    return out


def sigma_from_report(robots_json: Optional[dict]) -> dict:
    out = {}
    for rid in ROBOTS:
        ts, ss = [], []
        for fr in ((robots_json or {}).get(rid) or {}).get('frames') or []:
            std = (fr.get('report') or {}).get('std_yaw_rad')
            if isinstance(std, (int, float)) and isinstance(fr.get('t'), (int, float)) and math.isfinite(std):
                ts.append(fr['t'])
                ss.append(std * 1000.0)
        out[rid] = (ts, ss)
    return out


def frame_time_map(robots_json: Optional[dict]) -> dict:
    out = {}
    for rid in ROBOTS:
        out[rid] = {fr['frame']: fr['t'] for fr in ((robots_json or {}).get(rid) or {}).get('frames') or []
                    if isinstance(fr.get('frame'), int) and isinstance(fr.get('t'), (int, float))}
    return out


def load_case(case_dir: Path, label: str) -> CaseData:
    case_dir = Path(case_dir)
    rows = load_trace(case_dir)
    robots_json = _read_json(case_dir / 'robots.json')
    sig = sigma_from_trace(rows)
    source = 'trace'
    if not any(sig[r][0] for r in ROBOTS):
        sig = sigma_from_report(robots_json)
        source = 'report' if any(sig[r][0] for r in ROBOTS) else 'none'
    times = frame_time_map(robots_json)
    return CaseData(case_dir, label, rows, sig, source, times,
                    frame_time_exact=any(times[r] for r in ROBOTS), result=_read_json(case_dir / 'result.json') or {})


def frame_schedule(cases: Sequence[CaseData], dt: float) -> list:
    """Sim times of the video frames: every ``dt`` s from the earliest first trace row to the latest last row."""
    if dt <= 0:
        raise ValueError('dt must be > 0')
    t0 = min(c.t_first for c in cases)
    t1 = max(c.t_last for c in cases)
    n = int(math.floor((t1 - t0) / dt + 1e-9)) + 1
    times = [t0 + i * dt for i in range(n)]
    if times[-1] < t1 - 1e-9:
        times.append(t1)
    return times


def gate_mrad(profile) -> float:
    """The yaw sigma the gate trips at, in mrad, straight from the harness profile (None profile = no gate line)."""
    return profile.high_yaw_rad * 1000.0 if profile else 0.0


def row_at(rows: Sequence[dict], t: float) -> dict:
    """The last row at or before t (the first row when t precedes the run)."""
    lo, hi = 0, len(rows) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if rows[mid]['t'] <= t + 1e-9:
            lo = mid
        else:
            hi = mid - 1
    return rows[lo]


def wrist_frame_index(case: CaseData, rid: str, t: float) -> Optional[int]:
    """Latest saved frame at or before t. Exact through robots.json; else an approximation from the 5 Hz period."""
    times = case.frame_times.get(rid) or {}
    if times:
        done = [(idx, ft) for idx, ft in times.items() if ft <= t + 1e-9]
        return max(done, key=lambda p: p[1])[0] if done else None
    if t < case.t_first - 1e-9:
        return None
    return int((t - case.t_first) / FRAME_PERIOD_S + 1e-9)


def pick_font() -> Optional[str]:
    """Register a Korean-capable font if one exists. Returns its family name or None (never raises)."""
    from matplotlib import font_manager
    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            try:
                font_manager.fontManager.addfont(path)
                return font_manager.FontProperties(fname=path).get_name()
            except Exception:                     # a broken font file must not stop the render
                continue
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for family in FONT_FAMILIES:
        if family in installed:
            return family
    return None


def _require_matplotlib():
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.image as mpimg
        from matplotlib import transforms
    except ImportError as exc:
        raise RenderError('matplotlib is required (install requirements-sim.txt or `pip install matplotlib`)') from exc
    return plt, mpimg, transforms


def render_frames(cases: Sequence[CaseData], *, dt: float = 0.25, fps: float = 8.0, wrist: bool = False,
                  gate: str = 'loaded', lang: str = 'auto', size_px: tuple = (1280, 720),
                  max_frames: Optional[int] = None) -> Iterator:
    """Yield one RGBA uint8 array (H, W, 4) per video frame."""
    import numpy as np
    plt, mpimg, transforms = _require_matplotlib()
    profile = GATES[gate]
    font = pick_font()
    if lang == 'auto':
        lang = 'ko' if font else 'en'
    if font:
        plt.rcParams['font.family'] = font
    plt.rcParams['axes.unicode_minus'] = False
    tx = TEXT[lang]
    gate_line = gate_mrad(profile)
    times = frame_schedule(cases, dt)
    if max_frames is not None:
        times = times[:max_frames]
    n = len(cases)
    w_in, h_in, dpi = size_px[0] / 100.0, size_px[1] / 100.0, 100
    fig = plt.figure(figsize=(w_in, h_in), dpi=dpi)
    rows_ratio = [1.0, 0.7, 0.8] if wrist else [1.0, 0.8]
    gs = fig.add_gridspec(len(rows_ratio), 2 * n, height_ratios=rows_ratio, hspace=0.42, wspace=0.12,
                          left=0.07, right=0.985, top=0.94, bottom=0.13)
    top_axes = [fig.add_subplot(gs[0, 2 * i:2 * i + 2]) for i in range(n)]
    wrist_axes = [[fig.add_subplot(gs[1, 2 * i + j]) for j in range(2)] for i in range(n)] if wrist else []
    ax_sig = fig.add_subplot(gs[-1, :])
    all_x = [r['robots'][rid][0] for c in cases for r in c.rows for rid in ROBOTS] \
        + [r['beam_xyz'][0] for c in cases for r in c.rows if r.get('beam_xyz')]
    all_y = [r['robots'][rid][1] for c in cases for r in c.rows for rid in ROBOTS] \
        + [r['beam_xyz'][1] for c in cases for r in c.rows if r.get('beam_xyz')]
    xlim = (min(all_x) - 0.4, max(all_x) + 0.4)
    ylim = (min(all_y) - 0.4, max(all_y) + 0.4)
    sig_max = max([s for c in cases for rid in ROBOTS for s in c.sigma[rid][1]] + [gate_line]) * 1.25
    t_axis = (min(c.t_first for c in cases), max(c.t_last for c in cases))
    speed = dt * fps
    styles = ['--', '-', ':', '-.']
    img_cache: dict = {}
    footer = fig.text(0.5, 0.012, '', fontsize=8, ha='center', va='bottom')

    def load_img(path: Path):
        if path not in img_cache:
            if len(img_cache) > 64:
                img_cache.clear()
            try:
                img_cache[path] = mpimg.imread(str(path))
            except (OSError, ValueError):
                img_cache[path] = None
        return img_cache[path]

    for t in times:
        for i, case in enumerate(cases):
            ax = top_axes[i]
            ax.clear()
            ax.set_xlim(*xlim), ax.set_ylim(*ylim), ax.set_aspect('equal', adjustable='box'), ax.grid(alpha=.3)
            ax.set_title(f'{case.label} - {tx["title"]}', fontsize=10)
            ended = t > case.t_last + 1e-9
            row = case.rows[-1] if ended else row_at(case.rows, t)
            if ended:
                ax.text(xlim[0] + .03, ylim[1] - .07, tx['ended'] % case.t_last, color='red', fontsize=10)
            if case.verdict and t >= case.t_last - 1e-9:      # the verdict appears when the run ends
                ax.text(xlim[1] - .03, ylim[1] - .07, case.verdict[0], ha='right', fontsize=9,
                        color='green' if case.verdict[1] else 'red')
            beam = row.get('beam_xyz')
            if beam:
                byaw = row.get('beam_yaw') or 0.0
                dx, dy = .5 * BEAM_LENGTH_M * math.cos(byaw), .5 * BEAM_LENGTH_M * math.sin(byaw)
                ax.plot([beam[0] - dx, beam[0] + dx], [beam[1] - dy, beam[1] + dy], lw=8, color='#c8a24a',
                        solid_capstyle='butt', label=tx['beam'])
                ax.text(xlim[0] + .03, ylim[0] + .05, tx['beam_yaw'] % (byaw * 1000), fontsize=8)
            for rid, color in (('r1', 'tab:blue'), ('r2', 'tab:red')):
                x, y, h = row['robots'][rid]
                ax.add_patch(plt.Rectangle((x - .12, y - .09), .24, .18, color=color, alpha=.6,
                                           transform=transforms.Affine2D().rotate_around(x, y, h) + ax.transData))
                ax.arrow(x, y, .16 * math.cos(h), .16 * math.sin(h), head_width=.035, color='k')
                ax.text(x, y + .14, rid, ha='center', fontsize=9)
            if wrist:
                for j, rid in enumerate(ROBOTS):
                    wax = wrist_axes[i][j]
                    wax.clear(), wax.set_xticks([]), wax.set_yticks([])
                    title = tx['wrist_title'] % (case.label.split(' ')[0], rid)
                    idx = wrist_frame_index(case, rid, t)
                    img = load_img(case.directory / 'frames' / rid / f'{idx:05d}.jpg') if idx is not None else None
                    if img is not None:
                        wax.imshow(img)
                    else:
                        wax.text(.5, .5, tx['wrist_none'], ha='center', va='center', transform=wax.transAxes)
                    wax.set_title(title + ('' if case.frame_time_exact else ' *'), fontsize=8)
        ax_sig.clear()
        for i, case in enumerate(cases):
            for rid, color in (('r1', 'tab:blue'), ('r2', 'tab:red')):
                ts, ss = case.sigma[rid]
                k = sum(1 for tt in ts if tt <= t + 1e-9)
                if k:
                    ax_sig.plot(ts[:k], ss[:k], styles[i % len(styles)], color=color,
                                label=f'{case.label} {rid}')
        if profile:
            ax_sig.axhline(gate_line, color='k', lw=1)
            ax_sig.text(t_axis[1], gate_line + sig_max * .03, ha='right', fontsize=8,
                        s=tx['gate'] % (math.degrees(profile.high_yaw_rad), gate_line, profile.enter_dwell_s))
        else:
            ax_sig.text(t_axis[1], sig_max * .93, tx['no_gate'], ha='right', fontsize=8)
        ax_sig.set_xlim(t_axis[0] - .3, t_axis[1] + .3), ax_sig.set_ylim(0, sig_max), ax_sig.grid(alpha=.3)
        ax_sig.set_xlabel(tx['xlabel']), ax_sig.set_ylabel(tx['sigma_ylabel'], fontsize=9)
        if ax_sig.get_legend_handles_labels()[0]:
            ax_sig.legend(loc='upper left', ncol=2, fontsize=7)
        srcs = {c.sigma_source for c in cases}
        src = ' / '.join(tx['src_' + s] for s in sorted(srcs))
        ax_sig.set_title(src, fontsize=8, loc='right')
        note = tx['footer'] % (t, speed)
        if wrist and not all(c.frame_time_exact for c in cases):
            note += ' | ' + tx['wrist_approx']
        footer.set_text(note)
        fig.canvas.draw()
        yield np.asarray(fig.canvas.buffer_rgba()).copy()
    plt.close(fig)


def encode_mp4(frames: Iterator, output: Path, fps: float, size_px: tuple, crf: int = 30) -> int:
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RenderError('ffmpeg is required to write mp4 (brew install ffmpeg / apt install ffmpeg)')
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg, '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', f'{size_px[0]}x{size_px[1]}',
           '-r', str(fps), '-i', '-', '-c:v', 'libx264', '-preset', 'slow', '-crf', str(crf), '-pix_fmt', 'yuv420p',
           '-movflags', '+faststart', str(output)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    count = 0
    try:
        for frame in frames:
            proc.stdin.write(frame.tobytes())
            count += 1
        proc.stdin.close()
    except BrokenPipeError:
        pass
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    err = proc.stderr.read().decode(errors='replace')
    if proc.wait() != 0:
        raise RenderError(f'ffmpeg failed: {err.strip()[:500]}')
    return count


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--case', action='append', required=True, type=Path,
                    help='case directory (contains eval_only/trace.jsonl); give it once or twice (before vs after)')
    ap.add_argument('--label', action='append', help='label per --case, in the same order')
    ap.add_argument('--output', required=True, type=Path, help='output .mp4')
    ap.add_argument('--fps', type=float, default=8.0, help='video frame rate (default 8)')
    ap.add_argument('--dt', type=float, default=0.25, help='sim seconds between video frames (default 0.25)')
    ap.add_argument('--wrist', action='store_true', help='add each robot\'s saved own-camera frame (frames/r1, r2)')
    ap.add_argument('--gate', choices=sorted(GATES), default='loaded',
                    help='uncertainty gate line to draw (loaded: carrying the beam; unloaded: before the grasp; none: omit)')
    ap.add_argument('--lang', choices=('auto', 'ko', 'en'), default='auto', help='label language (auto: ko if a Korean font exists)')
    ap.add_argument('--width', type=int, default=1280)
    ap.add_argument('--height', type=int, default=720)
    ap.add_argument('--crf', type=int, default=30, help='x264 quality (higher = smaller file)')
    ap.add_argument('--max-frames', type=int, help='stop after N frames (debug)')
    args = ap.parse_args(argv)
    if not 1 <= len(args.case) <= 2:
        ap.error('give one or two --case')
    if args.label and len(args.label) != len(args.case):
        ap.error('--label must be given once per --case')
    if args.fps <= 0 or args.dt <= 0:
        ap.error('--fps and --dt must be > 0')
    if args.width % 2 or args.height % 2:
        ap.error('--width and --height must be even (yuv420p)')
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        _require_matplotlib()
        labels = args.label or [p.name[:40] for p in args.case]
        cases = [load_case(p, lab) for p, lab in zip(args.case, labels)]
        size = (args.width, args.height)
        frames = render_frames(cases, dt=args.dt, fps=args.fps, wrist=args.wrist, gate=args.gate, lang=args.lang,
                               size_px=size, max_frames=args.max_frames)
        count = encode_mp4(frames, args.output, args.fps, size, args.crf)
    except RenderError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    print(json.dumps({'output': str(args.output), 'frames': count, 'bytes': args.output.stat().st_size,
                      'sha256': sha256_of(args.output),
                      'sigma_source': {c.label: c.sigma_source for c in cases},
                      'wrist_frame_time_exact': {c.label: c.frame_time_exact for c in cases}}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
