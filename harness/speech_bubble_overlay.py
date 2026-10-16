"""Observer-only speech bubbles above robot heads (``observer_overlay=speech_bubbles_v1``).

Scope and boundaries
--------------------
* Presentation only. Bubbles are drawn into *copies* of observer frames: the
  free viewer camera or the fixed ``cctv_warehouse`` observer camera. They are
  never drawn into a robot's own camera (``*__robot_cam``) or into the shared
  top RGB views that controllers read (``cctv_top*``), and nothing computed here
  is returned to a controller, planner, referee or request builder.
  :class:`ObserverCamera` refuses those cameras by name, and no module outside
  the observer renderers imports this file (checked by a test).
* Head positions come from the recorded ground-truth robot state (free-joint
  qpos). Using ground truth is acceptable only because the result is a picture
  for humans; the controllers' observation boundary is unchanged.
* Default off. ``normalize_observer_overlay`` maps ``None``/``none``/``off`` to
  ``None``; callers then skip every function here and their output bytes stay
  exactly as before. The existing dialogue text box
  (``harness.communication_overlay``) is untouched and can be shown together.
* Text wrapping and the Korean font list are reused from
  ``harness.communication_overlay`` without changing that (execution-bundle
  pinned) file.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence

import numpy as np

from harness.communication_overlay import KOREAN_FONTS, _wrapped_lines

SPEECH_BUBBLES_V1 = 'speech_bubbles_v1'
OBSERVER_OVERLAYS = (SPEECH_BUBBLES_V1,)

# Height of the drawn "head" above a robot's base origin. The stowed arm and
# camera bracket top out near 0.26 m, so the tail tip sits just above that.
HEAD_OFFSET_M = 0.27

# Same hues as scripts/render_warehouse_dialogue.py (r1 yellow, r2 blue, r3
# red); `edge` is a darker tone so the bubble outline reads on a light floor.
ROBOT_COLORS = {
    'r1': {'fill': (255, 220, 40), 'edge': (184, 143, 0)},
    'r2': {'fill': (60, 165, 255), 'edge': (27, 111, 196)},
    'r3': {'fill': (255, 100, 120), 'edge': (204, 47, 71)},
}
_FALLBACK_COLORS = (
    {'fill': (120, 220, 150), 'edge': (36, 140, 78)},
    {'fill': (190, 150, 255), 'edge': (112, 72, 190)},
    {'fill': (255, 170, 80), 'edge': (190, 100, 20)},
)
INK = (28, 36, 48)
MUTED_INK = (92, 104, 120)
PAPER = (252, 252, 254)
SUPERSAMPLE = 2


def normalize_observer_overlay(value):
    """Return ``None`` (off, the default) or a supported overlay id."""
    if value is None or value is False or str(value).strip().lower() in ('', 'none', 'off'):
        return None
    if value == SPEECH_BUBBLES_V1:
        return SPEECH_BUBBLES_V1
    raise ValueError(f'unsupported observer_overlay {value!r}; use one of {OBSERVER_OVERLAYS} or off')


def robot_colors(robot_id: str) -> dict:
    if robot_id in ROBOT_COLORS:
        return ROBOT_COLORS[robot_id]
    return _FALLBACK_COLORS[sum(map(ord, str(robot_id))) % len(_FALLBACK_COLORS)]


# --------------------------------------------------------------------------
# Observer camera and projection (pure math; no GL context needed)
# --------------------------------------------------------------------------

def is_actor_camera(name) -> bool:
    """True for cameras whose pixels reach a robot or controller."""
    text = str(name or '')
    return 'robot_cam' in text or text.startswith('cctv_top')


@dataclass(frozen=True)
class ObserverCamera:
    """Pinhole camera for an observer image; ``name`` is ``None`` for the free viewer."""
    name: str | None
    position: tuple
    forward: tuple
    up: tuple
    fovy_deg: float
    width: int
    height: int

    def __post_init__(self):
        if is_actor_camera(self.name):
            raise ValueError(f'speech bubbles are observer-only; refusing actor camera {self.name!r}')
        if self.width <= 0 or self.height <= 0 or not 1. <= self.fovy_deg < 179.:
            raise ValueError('invalid observer camera size or field of view')

    @classmethod
    def free(cls, *, lookat, distance, azimuth, elevation, fovy_deg, width, height):
        """MuJoCo free-camera convention (azimuth/elevation in degrees)."""
        az, el = math.radians(azimuth), math.radians(elevation)
        forward = np.array([math.cos(el)*math.cos(az), math.cos(el)*math.sin(az), math.sin(el)])
        position = np.asarray(lookat, float) - float(distance)*forward
        right = np.cross(forward, [0., 0., 1.])
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        return cls(None, tuple(position), tuple(forward), tuple(up), float(fovy_deg), int(width), int(height))

    @classmethod
    def from_mujoco(cls, model, data, name, width, height):
        """A fixed model camera such as ``cctv_warehouse`` (data must be forwarded)."""
        cid = model.camera(name).id
        frame = np.asarray(data.cam_xmat[cid], float).reshape(3, 3)
        return cls(str(name), tuple(np.asarray(data.cam_xpos[cid], float)), tuple(-frame[:, 2]),
                   tuple(frame[:, 1]), float(model.cam_fovy[cid]), int(width), int(height))

    def project(self, points):
        """World points (N, 3) -> pixel (N, 2) and depth (N,) along the view axis."""
        points = np.atleast_2d(np.asarray(points, float))
        forward, up = np.asarray(self.forward), np.asarray(self.up)
        right = np.cross(forward, up)
        rel = points - np.asarray(self.position)
        depth = rel @ forward
        focal = (self.height/2.)/math.tan(math.radians(self.fovy_deg)/2.)
        safe = np.where(depth > 1e-9, depth, np.nan)
        u = self.width/2. + focal*(rel @ right)/safe
        v = self.height/2. - focal*(rel @ up)/safe
        return np.stack([u, v], axis=1), depth


def head_point(base_xyz) -> np.ndarray:
    """Recorded ground-truth base position -> drawn head point (presentation only)."""
    point = np.asarray(base_xyz, float).copy()
    point[2] += HEAD_OFFSET_M
    return point


# --------------------------------------------------------------------------
# Messages and what is visible at a given time
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BubbleMessage:
    seq: int
    sender: str
    recipients: tuple
    text: str
    start_s: float          # onset on the bubble clock (SIM time in a live view)
    sim_time_s: float | None = None   # time recorded in the log, unchanged


def peer_messages_from_events(events: Iterable[Mapping]) -> list[BubbleMessage]:
    """Delivered real-model messages from ``team/conversation.jsonl`` rows.

    Only ``kind == 'peer_message'`` rows count; scripted fixtures are logged as
    ``fixture_peer_message`` and never get a bubble.
    """
    found = []
    for row in events:
        text, when = row.get('text'), row.get('sim_time_s')
        if row.get('kind') != 'peer_message' or row.get('source', 'llm') != 'llm':
            continue
        if not text or when is None or not row.get('sender'):
            continue
        found.append(BubbleMessage(int(row.get('seq', len(found))), str(row['sender']),
                                   tuple(row.get('recipients') or ()), str(text),
                                   float(when), float(when)))
    return sorted(found, key=lambda message: (message.start_s, message.seq))


def load_conversation(path) -> list[BubbleMessage]:
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    return peer_messages_from_events(json.loads(line) for line in lines if line.strip())


@dataclass(frozen=True)
class ActiveBubble:
    message: BubbleMessage
    alpha: float
    age_s: float


@dataclass(frozen=True)
class ActiveReceipt:
    receiver: str
    sender: str
    alpha: float


def _fade(age, show_s, fade_in_s, fade_out_s):
    rise = 1. if fade_in_s <= 0 else min(1., age/fade_in_s)
    fall = 1. if fade_out_s <= 0 else min(1., (show_s-age)/fade_out_s)
    return max(0., min(rise, fall))


def active_bubbles(messages: Sequence[BubbleMessage], t: float, *, show_s: float = 6.,
                   fade_in_s: float = .25, fade_out_s: float = .6,
                   receipt_s: float = 0., receipts: bool = False):
    """Bubbles (one per sender: the newest) and optional receiver indicators at time ``t``.

    A message is shown for ``show_s`` seconds after ``start_s``. A newer message
    from the same sender replaces the older one at once.
    """
    live = [m for m in messages if m.start_s <= t + 1e-9 < m.start_s + show_s]
    newest = {}
    for message in sorted(live, key=lambda m: (m.start_s, m.seq)):
        newest[message.sender] = message
    bubbles = [ActiveBubble(m, _fade(t - m.start_s, show_s, fade_in_s, fade_out_s), t - m.start_s)
               for m in newest.values()]
    bubbles = [b for b in bubbles if b.alpha > .02]
    chips = []
    if receipts and receipt_s > 0:
        speaking = {b.message.sender for b in bubbles}
        latest = {}
        for message in sorted(live, key=lambda m: (m.start_s, m.seq)):
            if t - message.start_s <= receipt_s:
                for receiver in message.recipients:
                    if receiver != message.sender and receiver not in speaking:
                        latest[receiver] = message
        for receiver, message in latest.items():
            alpha = _fade(t - message.start_s, receipt_s, fade_in_s, min(fade_out_s, receipt_s/2))
            if alpha > .02:
                chips.append(ActiveReceipt(receiver, message.sender, alpha))
    return bubbles, chips


# --------------------------------------------------------------------------
# Presentation timeline for videos (SIM is paused while the team talks)
# --------------------------------------------------------------------------

def presentation_timeline(messages: Sequence[BubbleMessage], *, start_s: float, end_s: float,
                          speed: float, fps: float, beat_s: float = 2., linger_s: float = 2.5,
                          pause_for_dialogue: bool = True):
    """Frame list ``[(sim_t, clock_t)]`` and the messages re-timed onto the video clock.

    The recorded SIM clock stands still while the models answer (several
    messages share one ``sim_time_s``). With ``pause_for_dialogue`` the video
    freezes the scene at that SIM time and lets the bubbles appear one after
    another, ``beat_s`` apart in recorded order, then holds ``linger_s`` after
    the last one. Re-timed messages keep their logged ``sim_time_s``; the
    delay exists only on the video clock.
    """
    if not (speed > 0 and fps > 0 and end_s > start_s and beat_s >= 0 and linger_s >= 0):
        raise ValueError('timeline needs positive speed/fps, end after start, non-negative holds')
    ordered = sorted((m for m in messages if start_s - 1e-9 <= m.start_s <= end_s + 1e-9),
                     key=lambda m: (m.start_s, m.seq))
    step, dt = speed/fps, 1./fps
    frames, retimed, index, motion, held = [], [], 0, 0, 0
    sim = start_s
    while sim < end_s + 1e-9 or index < len(ordered):
        clock = (motion + held)*dt
        if index < len(ordered) and ordered[index].start_s <= sim + 1e-9:
            due = ordered[index].start_s
            cluster = []
            while index < len(ordered) and ordered[index].start_s <= due + 1e-9:
                cluster.append(ordered[index])
                index += 1
            if pause_for_dialogue:
                for order, message in enumerate(cluster):
                    retimed.append(replace(message, start_s=clock + order*beat_s,
                                           sim_time_s=message.start_s))
                hold = int(math.ceil(((len(cluster)-1)*beat_s + linger_s)*fps - 1e-9))
                for _ in range(max(1, hold)):
                    frames.append((due, (motion + held)*dt))
                    held += 1
            else:
                retimed.extend(replace(m, start_s=clock, sim_time_s=m.start_s) for m in cluster)
            continue
        if sim >= end_s + 1e-9:
            break
        frames.append((sim, clock))
        motion += 1
        sim = start_s + motion*step
    return frames, retimed


# --------------------------------------------------------------------------
# Layout (pure geometry)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Placement:
    key: str
    rect: tuple          # x, y, w, h in pixels
    tip: tuple           # point the tail (or dot) touches: the robot head
    side: str            # 'above' or 'below' the head
    choice: int = 0      # candidate index; pass back as ``prefer`` for a steadier layout


def _overlap(a, b):
    width = min(a[0]+a[2], b[0]+b[2]) - max(a[0], b[0])
    height = min(a[1]+a[3], b[1]+b[3]) - max(a[1], b[1])
    return width*height if width > 0 and height > 0 else 0.


def _bubble_candidates(hx, hy, w, h, gap, tail, levels):
    shift = w*.62 + 6.
    ranked = []
    for level in range(levels):
        for steps in (0, 1, -1, 2, -2):
            # Prefer small moves: one step sideways costs a little less than one level up.
            ranked.append((level + .9*abs(steps), steps < 0, level, steps))
    found = []
    for _, _, level, steps in sorted(ranked):
        found.append((hx - w/2. + steps*shift, hy - gap - tail - h - level*(h + gap), 'above'))
    for steps in (0, 1, -1, 2, -2):
        found.append((hx - w/2. + steps*shift, hy + gap + tail, 'below'))
    return found


def _chip_candidates(hx, hy, w, h, gap):
    # A small tag stays next to its robot: above, right, left, then below.
    return [(hx - w/2., hy - gap - h, 'above'), (hx + 10., hy - h/2. - 2., 'right'),
            (hx - 10. - w, hy - h/2. - 2., 'left'), (hx - w/2., hy + gap + 8., 'below')]


def place_boxes(items, frame_size, *, margin: float = 8., gap: float = 4., tail: float = 16.,
                obstacles: Sequence[tuple] = (), stack_levels: int = 4, kind: str = 'bubble',
                prefer: Mapping[str, int] | None = None):
    """Choose a non-overlapping, in-frame rectangle for each box near its head.

    ``items`` is ``[(key, (head_x, head_y), (w, h))]`` in priority order: the
    first item gets its preferred spot and later ones move around it. A bubble's
    candidates run from directly above the head to small sideways shifts and
    higher stacking levels, then farther shifts, and last below the head. A chip (``kind='chip'``) tries above,
    right, left, below and never stacks. A box that cannot avoid overlap takes
    the least-overlapping candidate. Horizontal position is always clamped into
    the frame. ``prefer`` maps a key to the candidate index it used last time;
    that spot is kept while it is still free, so bubbles do not hop around
    between video frames.
    """
    frame_w, frame_h = frame_size
    taken = list(obstacles)
    placements = []
    for key, (hx, hy), (w, h) in items:
        candidates = (_bubble_candidates(hx, hy, w, h, gap, tail, stack_levels) if kind == 'bubble'
                      else _chip_candidates(hx, hy, w, h, gap))
        def cost_of(left, top):
            left = min(max(left, margin), max(margin, frame_w - margin - w))
            if top < margin or top + h > frame_h - margin:
                return (left, 1e9 + abs(top))  # off-frame: only as a last resort
            return left, sum(_overlap((left, top, w, h), other) for other in taken)

        order = list(range(len(candidates)))
        wanted = (prefer or {}).get(key)
        if wanted is not None and 0 <= wanted < len(order):
            order.remove(wanted)
            order.insert(0, wanted)
        best, best_cost, chosen = None, None, 0
        for number in order:
            left, top, side = candidates[number]
            left, cost = cost_of(left, top)
            if best is None or cost < best_cost - 1e-9:
                best, best_cost, chosen = ((left, top, w, h), side), cost, number
            if cost == 0.:
                break
        rect, side = best
        taken.append(rect)
        placements.append(Placement(key, tuple(float(v) for v in rect), (float(hx), float(hy)), side, chosen))
    return placements


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

@lru_cache(maxsize=64)
def load_font(paths, size):
    from PIL import ImageFont
    for path in paths:
        try:
            return ImageFont.truetype(path, size), True
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size), False
    except TypeError:  # Pillow without sized default fonts
        return ImageFont.load_default(), False


def _natural(name):
    return [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', str(name))]


def _plain(text):
    return ' '.join(str(text).split())


class SpeechBubbleOverlay:
    """Draw bubbles for the messages active at a time onto an observer frame copy."""

    def __init__(self, messages: Sequence[BubbleMessage], *, show_s: float = 6.,
                 receipts: bool = False, receipt_s: float = 1.5, max_lines: int = 3,
                 font_paths: Sequence[str] = KOREAN_FONTS):
        self.messages = list(messages)
        self.show_s = float(show_s)
        self.receipts = bool(receipts)
        self.receipt_s = float(receipt_s)
        self.max_lines = int(max_lines)
        self.font_paths = tuple(font_paths)
        self._choices = {}   # layout memory between frames (video only)

    def add(self, message: BubbleMessage) -> None:
        self.messages.append(message)

    @property
    def korean_font(self) -> bool:
        return load_font(self.font_paths, 20)[1]

    def render(self, frame_rgb, t: float, camera: ObserverCamera, heads: Mapping[str, Sequence[float]]):
        """Return ``frame_rgb`` with bubbles for time ``t``; the input array is never modified.

        ``heads`` maps robot id -> world head point (see :func:`head_point`). When
        nothing is visible the same array object is returned.
        """
        if not isinstance(camera, ObserverCamera):
            raise TypeError('speech bubbles need an ObserverCamera (observer-only)')
        frame = np.asarray(frame_rgb)
        if frame.shape != (camera.height, camera.width, 3) or frame.dtype != np.uint8:
            raise ValueError('frame must be uint8 (height, width, 3) matching the observer camera')
        bubbles, chips = active_bubbles(self.messages, t, show_s=self.show_s,
                                        receipt_s=self.receipt_s, receipts=self.receipts)
        pixels = {}
        for robot, point in heads.items():
            xy, depth = camera.project(point)
            if depth[0] > 0 and np.isfinite(xy[0]).all() and 0 <= xy[0, 0] < camera.width and 0 <= xy[0, 1] < camera.height:
                pixels[robot] = (float(xy[0, 0]), float(xy[0, 1]))
        bubbles = [b for b in bubbles if b.message.sender in pixels]
        chips = [c for c in chips if c.receiver in pixels]
        if not bubbles and not chips:
            return frame_rgb
        from PIL import Image, ImageDraw
        scale = camera.width/1280.
        body_px = max(11, int(round(20*scale)))
        head_px = max(9, int(round(body_px*.78)))
        body, korean = load_font(self.font_paths, body_px*SUPERSAMPLE)
        small, _ = load_font(self.font_paths, head_px*SUPERSAMPLE)
        scratch = ImageDraw.Draw(Image.new('L', (8, 8)))
        pad = max(6, int(round(body_px*.6)))
        text_width = int(camera.width*.2)
        boxes, specs = [], {}
        # Fixed robot order, not onset order: a bubble must not jump when a
        # different robot starts talking.
        for bubble in sorted(bubbles, key=lambda b: _natural(b.message.sender)):
            message = bubble.message
            text = _plain(message.text)
            if not korean and not text.isascii():
                text = '[see log]'
            lines = _wrapped_lines(text, scratch, body, text_width*SUPERSAMPLE, limit=self.max_lines)
            widths = [scratch.textlength(line, font=body)/SUPERSAMPLE for line in lines]
            names = ' '.join(r.upper() for r in message.recipients if r != message.sender)
            tag = message.sender.upper()
            header = f'→ {names}' if names else ''
            tag_w = scratch.textlength(tag, font=small)/SUPERSAMPLE + head_px
            header_w = scratch.textlength(header, font=small)/SUPERSAMPLE + head_px*.5 if header else 0
            line_h = int(round(body_px*1.3))
            head_h = int(round(head_px*1.7))
            width = max(max(widths, default=0), tag_w + header_w) + 2*pad
            height = pad*.8 + head_h + 3 + line_h*len(lines) + pad*.8
            key = f'bubble:{message.sender}'
            boxes.append((key, pixels[message.sender], (int(math.ceil(width)), int(math.ceil(height)))))
            specs[key] = ('bubble', bubble, lines, tag_w, tag, header, line_h, head_h)
        obstacles = [(x - 14, y - 14, 28, 28) for x, y in pixels.values()]
        placed = place_boxes(boxes, (camera.width, camera.height), obstacles=obstacles,
                             tail=body_px*.8, margin=max(6, body_px*.4), prefer=self._choices)
        chip_boxes = []
        chip_label = '받음' if korean else 'RX'
        chip_w = int(scratch.textlength(chip_label, font=small)/SUPERSAMPLE + head_px*1.6)
        chip_h = int(head_px*1.9)
        for chip in chips:
            key = f'chip:{chip.receiver}'
            chip_boxes.append((key, pixels[chip.receiver], (chip_w, chip_h)))
            specs[key] = ('chip', chip, chip_label)
        self._choices = {p.key: p.choice for p in placed}
        taken = [p.rect for p in placed]
        placed += place_boxes(chip_boxes, (camera.width, camera.height), obstacles=obstacles + taken,
                              gap=3., margin=max(6, body_px*.4), kind='chip')
        canvas = Image.fromarray(frame).convert('RGBA')
        bubble_places = [p for p in placed if specs[p.key][0] == 'bubble']
        for part in ('tail', 'body', 'dot'):
            for place in bubble_places:
                _draw_bubble(canvas, place, specs[place.key], body, small, body_px, head_px, pad, part)
        for place in placed:
            if specs[place.key][0] == 'chip':
                _draw_chip(canvas, place, specs[place.key], small, head_px)
        return np.asarray(canvas.convert('RGB'))


def _layer_for(canvas, box):
    """(layer, origin) covering ``box`` (x0, y0, x1, y1) clipped to the canvas, at SUPERSAMPLE."""
    from PIL import Image
    x0, y0 = max(0, int(math.floor(box[0]))), max(0, int(math.floor(box[1])))
    x1, y1 = min(canvas.width, int(math.ceil(box[2]))), min(canvas.height, int(math.ceil(box[3])))
    return Image.new('RGBA', ((x1-x0)*SUPERSAMPLE, (y1-y0)*SUPERSAMPLE), (0, 0, 0, 0)), (x0, y0, x1, y1)


def _composite(canvas, layer, bounds, alpha):
    from PIL import Image
    x0, y0, x1, y1 = bounds
    layer = layer.resize((x1-x0, y1-y0), Image.LANCZOS)
    if alpha < .999:
        faded = layer.getchannel('A').point(lambda v: int(v*alpha))
        layer.putalpha(faded)
    canvas.alpha_composite(layer, dest=(x0, y0))


def tail_edge(rect, tip, inset):
    """Which bubble edge the tail leaves from, and where.

    Returns ``{'edge', 'point', 'normal'}``: the edge name, the point on it
    nearest the head (kept ``inset`` px from the corners) and the outward
    normal. A head far to the side of the bubble gets a side tail instead of a
    thin sliver skimming the top or bottom edge.
    """
    x, y, w, h = rect
    tip_x, tip_y = tip
    out_x = max(x - tip_x, tip_x - (x + w), 0.)
    out_y = max(y - tip_y, tip_y - (y + h), 0.)
    if out_x > out_y*1.2 and out_x > 0:
        edge = 'left' if tip_x < x else 'right'
        base_y = min(max(tip_y, y + inset), y + h - inset)
        return {'edge': edge, 'point': (x if edge == 'left' else x + w, base_y),
                'normal': (-1. if edge == 'left' else 1., 0.)}
    edge = 'top' if tip_y < y else 'bottom'
    base_x = min(max(tip_x, x + inset), x + w - inset)
    return {'edge': edge, 'point': (base_x, y if edge == 'top' else y + h),
            'normal': (0., -1. if edge == 'top' else 1.)}


def _draw_bubble(canvas, place, spec, body, small, body_px, head_px, pad, part):
    """Draw one bubble in three passes (tail, body, head dot).

    Drawing every tail before any body keeps a long tail of one bubble behind
    another bubble's text instead of cutting across it; dots go last so every
    head stays marked.
    """
    from PIL import ImageDraw
    _, bubble, lines, tag_w, tag, header, line_h, head_h = spec
    colors = robot_colors(bubble.message.sender)
    x, y, w, h = place.rect
    tip_x, tip_y = place.tip
    s = SUPERSAMPLE
    edge_w = max(2., body_px*.13)
    radius = body_px*.75
    layer, bounds = _layer_for(canvas, (min(x, tip_x) - 8, min(y, tip_y) - 8,
                                        max(x + w, tip_x) + 10, max(y + h, tip_y) + 10))
    ox, oy = bounds[0], bounds[1]
    draw = ImageDraw.Draw(layer)

    def P(px, py):
        return ((px - ox)*s, (py - oy)*s)

    def rect(x0, y0, x1, y1):
        return [*P(x0, y0), *P(x1, y1)]

    edge = tail_edge(place.rect, place.tip, radius + body_px*.5)
    half = body_px*.55
    ex, ey = edge['point']
    nx, ny = edge['normal']
    tx, ty = -ny, nx                      # along the bubble edge
    jx, jy = ex - nx*(edge_w + 1.), ey - ny*(edge_w + 1.)    # a little inside the body
    reach = max(math.hypot(tip_x - ex, tip_y - ey), 1.)
    pull = min(1., edge_w*1.6/reach)
    inner_tip = (tip_x + (ex - tip_x)*pull, tip_y + (ey - tip_y)*pull)
    inner_half = half - edge_w*.9

    def paper_tail(fraction):
        """The tail's paper-coloured inside, from its base to ``fraction`` of the way to the tip."""
        left = (jx - tx*inner_half, jy - ty*inner_half)
        right = (jx + tx*inner_half, jy + ty*inner_half)
        if fraction >= 1.:
            return [P(*left), P(*right), P(*inner_tip)]
        mix = lambda point: (point[0] + (inner_tip[0] - point[0])*fraction,
                             point[1] + (inner_tip[1] - point[1])*fraction)
        return [P(*left), P(*right), P(*mix(right)), P(*mix(left))]

    if part == 'tail':
        draw.polygon([P(ex - tx*half, ey - ty*half), P(ex + tx*half, ey + ty*half), P(tip_x, tip_y)],
                     fill=(*colors['edge'], 255))
        draw.polygon(paper_tail(1.), fill=(*PAPER, 255))
    elif part == 'body':
        # soft drop shadow (offset copy, no blur)
        draw.rounded_rectangle(rect(x + 2, y + 3, x + w + 2, y + h + 3), radius=radius*s, fill=(0, 0, 0, 70))
        draw.rounded_rectangle(rect(x, y, x + w, y + h), radius=radius*s, fill=(*colors['edge'], 255))
        draw.rounded_rectangle(rect(x + edge_w, y + edge_w, x + w - edge_w, y + h - edge_w),
                               radius=max(1., radius - edge_w)*s, fill=(*PAPER, 255))
        # paper patch over the border where the tail joins, so there is no seam
        draw.polygon(paper_tail(min(1., (edge_w*3. + 2.)/max(math.hypot(inner_tip[0] - jx,
                                                                        inner_tip[1] - jy), 1.))),
                     fill=(*PAPER, 255))
        top = y + pad*.8
        draw.rounded_rectangle(rect(x + pad, top, x + pad + tag_w, top + head_h), radius=head_h*s/2.,
                               fill=(*colors['fill'], 255), outline=(*colors['edge'], 255), width=s)
        draw.text(P(x + pad + head_px*.5, top + head_h*.5), tag, font=small, fill=(*INK, 255), anchor='lm',
                  stroke_width=1, stroke_fill=(*INK, 255))
        if header:
            draw.text(P(x + pad + tag_w + head_px*.5, top + head_h*.5), header, font=small,
                      fill=(*MUTED_INK, 255), anchor='lm')
        line_y = top + head_h + 3
        for line in lines:
            draw.text(P(x + pad, line_y), line, font=body, fill=(*INK, 255))
            line_y += line_h
    else:   # 'dot': marks the head the tail points at
        dot = max(3., body_px*.22)
        cx, cy = P(tip_x, tip_y)
        ring = (dot + 1.5)*s
        draw.ellipse([cx - ring, cy - ring, cx + ring, cy + ring], fill=(*PAPER, 255))
        draw.ellipse([cx - dot*s, cy - dot*s, cx + dot*s, cy + dot*s], fill=(*colors['edge'], 255))
    _composite(canvas, layer, bounds, bubble.alpha)


def _draw_chip(canvas, place, spec, small, head_px):
    from PIL import ImageDraw
    _, chip, label = spec
    colors = robot_colors(chip.sender)
    x, y, w, h = place.rect
    s = SUPERSAMPLE
    tip_x, tip_y = place.tip
    layer, bounds = _layer_for(canvas, (min(x, tip_x) - 6, min(y, tip_y) - 6,
                                        max(x + w, tip_x) + 8, max(y + h, tip_y) + 8))
    ox, oy = bounds[0], bounds[1]
    draw = ImageDraw.Draw(layer)
    rect = [(x - ox)*s, (y - oy)*s, (x + w - ox)*s, (y + h - oy)*s]
    draw.rounded_rectangle(rect, radius=h*s/2., fill=(*PAPER, 240), outline=(*colors['edge'], 255),
                           width=max(2, int(head_px*.2*s)))
    draw.text(((x + w/2. - ox)*s, (y + h/2. - oy)*s), label, font=small, fill=(*INK, 255), anchor='mm')
    # small dot on the receiver's head, in the sender's colour
    cx, cy = (place.tip[0] - ox)*s, (place.tip[1] - oy)*s
    dot = max(2., head_px*.28)*s
    draw.ellipse([cx - dot - s, cy - dot - s, cx + dot + s, cy + dot + s], fill=(*PAPER, 255))
    draw.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=(*colors['edge'], 255))
    _composite(canvas, layer, bounds, chip.alpha)
