"""render_on_demand_v1: render a robot's camera only on ticks where something reads the picture (execution-layer SPEED switch, DEFAULT off).

Run with --render-on-demand (scripts/run_team_carry.py; needs --overhead and --robot-tags, not --multi-carry / --llm-moves). Two parts, both decided
BEFORE the render of a tick from the state the tick starts with, without any side effect:

1. Robot camera (the own picture, 640x480). On a tick where no consumer reads it, the render is skipped and the robot's LAST picture is handed to the
   code that runs unconditionally each tick (the own-history buffer, the picture file, the student-input record). pixels_idle() names the tick kinds:

   survey_init / survey_settle / survey_restore   SurveyApproach.needs_frame() is False: the look-around holds the far posture and only keeps the
                                                  pictures taken after the pan settle ticks (survey.observe) and, later, every approach / alignment tick;
   decide_wait                                    holding the box, the destination not decided yet: the robot stands still (branch carry_decide_wait);
   door_wait                                      the gate holds the robot (branch carry_gate_wait), only while the gate answers False without asking
                                                  (carry_gate.idle(): waiting for the planner, nobody is asked, no poll due);
   release_replay                                 the carry is over; the release replay table owns the tick (release_code / release_hold: no picture).

   The frozen world's render also forwards the whole world (robot._sync_real_camera_mount: mj_forward) before it draws; a skipped tick does the same
   (run_steps), because without it the physics changes at the 1e-7 m level from the first skipped tick (measured: evaluation rows differ).
   Every other tick renders as before. Kept on purpose (they read the picture and change the motion): the approach servo and the alignment (every tick), the
   ACT grasp (its history frames), the look windows of the carry navigation and the "box still held" watcher (every tick of a carry once the held check
   saw the box), the held check, the return navigation / moves (not supported).
   The own number-tag reader (robot_tags_v1.TagReader) only feeds the planner message 'robots_seen', its statistics and signs-seen / tags-seen files
   when the ceiling cameras are on; it does not run on a reused picture (the reading would repeat the last one). robots_near, the only motion input of
   the tags, comes from the ceiling cameras with --overhead.

2. Ceiling cameras (8 pictures of 1280x960 per reading on a nine-robot map). overhead_cameras_needed(): a camera whose picture cannot contain a robot's top
   card (the card centre farther than 0.35 m outside the picture edge at the card height) is not rendered. The OverheadReader skips cameras it gets no
   picture of, and a card outside the picture is never detected, so the poses it returns are the same as with all pictures (measured: commands and
   student inputs byte-identical on a three-robot map, a work record, 'tile skip'). The robot positions that choose the cameras
   come from the simulator world; they do not reach the policy, only the set of cameras rendered, whose output is unchanged.

What can change a command (reported by the run: report['render_on_demand'], render-on-demand.json): a tick whose prediction was wrong (a state that
changes inside the tick, before the branch ladder: the planner answers the destination or the door question this very tick) then runs its first step on
a picture that is one tick (0.1 s) old. The first rows of a carry are moves (the pictures are read only in the look windows that start 5 rows into a
pause), so no reading is expected to differ; the comparison with the unchanged run says where a command differs, if any does.

Standard library only; no numpy / mujoco. Loaded BY FILE PATH by scripts/run_grasp_act_student.py, only when the switch is on.
"""
from __future__ import annotations

OVERHEAD_MARGIN_M = 0.35    # a ceiling camera is rendered when a card centre is within its picture half span plus this


def pixels_idle(*, approach, skill, carry_nav, carry_state, carry_to_state, gate_idle, release_on):
    """The kind of tick that reads no picture (a short string), or None when the tick must render. Pure: reads the arguments only.
    approach: the SurveyApproach; skill: the sequence skill; carry_nav: the CarryNav or None; carry_state / carry_to_state: the run's dicts;
    gate_idle: carry_gate.idle or None; release_on: the release replay table is on."""
    if approach is None:
        return None
    if not approach.arrived:
        needs = getattr(approach, 'needs_frame', None)
        if needs is None or needs():
            return None
        return 'survey_' + approach.stage
    if skill != 'release':
        return None                              # the ACT grasp reads its history frames
    if carry_nav is None:
        if carry_to_state is not None and carry_to_state.get('rule') is None and 'note' not in carry_to_state:
            return 'decide_wait'
        return None
    if carry_nav.finished:
        # the carry is over: the held watcher and the navigation do not run; the replay table owns the tick (a held check that has just answered
        # reads one picture, and so does a robot that has not yet been through the held check)
        if release_on and ('held' in carry_state or carry_nav.held_result is None):
            return 'release_replay'
        return None
    if ('held' not in carry_state and carry_state.get('started_at_s') is None and carry_to_state is not None and carry_to_state.get('rule')
            and 'note' not in carry_to_state and gate_idle is not None and gate_idle()):
        return 'door_wait'
    return None


def overhead_cameras_needed(cameras, robot_xys, half_x, half_y, margin=OVERHEAD_MARGIN_M):
    """Names of the ceiling cameras whose picture may contain a robot's top card. cameras: [(name, (x, y))] (the camera centres, looking straight
    down); robot_xys: [(x, y)] of the robots; half_x / half_y: the half span of the picture at the card height."""
    return {name for name, (cx, cy) in cameras
            if any(abs(x - cx) <= half_x + margin and abs(y - cy) <= half_y + margin for x, y in robot_xys)}


class Stats:
    """Counters of one robot's run: ticks, reused pictures by tick kind, ceiling cameras rendered / skipped (the shared reading counts once)."""

    def __init__(self):
        self.ticks = 0
        self.reused = 0
        self.by_kind = {}

    def tick(self, kind):
        self.ticks += 1
        if kind is not None:
            self.reused += 1
            self.by_kind[kind] = self.by_kind.get(kind, 0) + 1

    def record(self):
        return {'ticks': self.ticks, 'pictures_reused': self.reused, 'by_kind': dict(self.by_kind),
                'share_reused': round(self.reused / self.ticks, 4) if self.ticks else None}
