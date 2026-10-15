"""Reloc9 reacquisition, adapted from act10 567dc120:harness/grasp_act_search.py.

Own command pose + remembered issued-setdown/visible site aim the camera only.
RGB edge colour is a search cue, never a pose/identity or grasp measurement.
No translation, simulator, evaluator, measured joints or top camera is used.
"""
import math
import cv2
import numpy as np
from sim.active_lookaround import wrap
from sim.solo_carry7 import body_point, TURN_RATE_FLOOR

OPTION = 'reloc9_reacquisition_v1'
PANS = (1500, 1000, 500, 1000, 1500, 2000, 2500, 2000, 1500)
RANGE_FACTORS = (1., .6, 1.6)


def edge_cue(rgb, kind):
    """A same-kind colour component touching the outer 15% suggests a direction.

    Colour alone cannot identify cargo (especially yellow chassis/paint). It is
    bounded to two orient attempts and cannot terminate reacquisition.
    """
    from harness.zone_own_perception import hue_mask
    mask = hue_mask(cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV), kind)
    n, _, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
    candidates = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area >= 12 and h >= 3 and (x < .15*rgb.shape[1] or x+w > .85*rgb.shape[1]):
            candidates.append((int(area), float(centers[i, 0])/rgb.shape[1]))
    return max(candidates)[1] if candidates else None


class CargoSearch:
    def __init__(self, pose, point, now, pwm, ops, *, source):
        self.point, self.source, self.ops = list(point), source, ops
        self.started = self.stage_t = now
        self.stage, self.i = 'orient', 0
        self.failure = None
        self.events = []
        self.scan_yaw = 0.
        self.last_yaw = pose[2]
        self.edge_attempts = 0
        self.edge_heading = None
        angle = abs(wrap(math.atan2(point[1]-pose[1], point[0]-pose[0])-pose[2]))
        self.budget_s = (angle+2*math.pi+math.pi/2)/TURN_RATE_FLOOR+len(PANS)*len(RANGE_FACTORS)*1.5+10.
        self.deadline = now+self.budget_s
        self.edge_return = None

    def tick(self, now, pose, pwm, *, edge_u=None):
        moved = abs(wrap(pose[2]-self.last_yaw))
        self.last_yaw = pose[2]
        if self.stage == 'body_scan':
            self.scan_yaw += moved
        if self.failure or now > self.deadline:
            self.failure = 'carry_reacquire_unconfirmed'
            return 0., dict(pwm)
        local = body_point(pose, self.point)
        distance = max(.12, math.hypot(*local[:2]))
        bearing = math.atan2(local[1], local[0])
        # Raw image left is positive body bearing; commanded pan is positive
        # optical heading. Convert both to a BODY target before centering pan.
        if edge_u is not None and self.edge_attempts < 2 and self.stage in ('pan_scan', 'body_scan'):
            self.edge_heading = pose[2]+math.radians((pwm[6]-1500)*.09)+(1 if edge_u < .5 else -1)*math.radians(20.)
            self.edge_return = self.stage
            self.stage = 'edge_orient'; self.stage_t = now
            self.edge_attempts += 1
            self.events.append(dict(t=now, stage=self.stage, edge_u=edge_u,
                                    source='own_rgb_kind_color_only', attempt=self.edge_attempts))
        factor = RANGE_FACTORS[(self.i//len(PANS)) % len(RANGE_FACTORS)]
        target = self.ops.gaze([distance*factor, 0., local[2]], pwm, visible=False)
        if target is None:
            target = dict(pwm)
        target = dict(target)
        target[6] = 1500 if self.stage in ('orient', 'edge_orient') else PANS[self.i % len(PANS)]
        updated = {**pwm, **self.ops.slew(pwm, target)}
        settled = all(updated[k] == target[k] for k in target)
        error = wrap(self.edge_heading-pose[2]) if self.stage == 'edge_orient' else bearing
        if self.stage in ('orient', 'edge_orient'):
            if abs(error) > math.radians(3.):
                return max(-.1, min(.1, .6*error)), updated
            self.events.append(dict(t=now, stage=self.stage+'_complete', bearing_rad=error))
            self.stage = 'pan_scan' if self.stage == 'orient' else self.edge_return
            self.stage_t = now
        if self.stage == 'pan_scan':
            if not settled:
                self.stage_t = now
            if settled and now-self.stage_t >= .9:
                self.events.append(dict(t=now, stage=self.stage, pan=target[6], range_factor=factor,
                                        commanded_range_m=distance*factor))
                self.i += 1; self.stage_t = now
                if self.i == len(PANS)*len(RANGE_FACTORS):
                    self.stage = 'body_scan'; self.scan_yaw = 0.; self.i = 0
        if self.stage == 'body_scan':
            if self.scan_yaw >= 2*math.pi:
                self.failure = 'carry_reacquire_unconfirmed'
                return 0., updated
            self.i = int((now-self.stage_t)/1.5) % (len(PANS)*len(RANGE_FACTORS))
            return .1, updated
        return 0., updated

    def record(self):
        return dict(option=OPTION, source=self.source, memory_world_m=self.point,
            started=self.started, budget_s=self.budget_s, deadline=self.deadline, stage=self.stage,
            commanded_scan_yaw_rad=self.scan_yaw, edge_attempts=self.edge_attempts,
            failure=self.failure, events=self.events, memory_controls='gaze_and_in_place_rotation_only',
            provenance='act10 PR504 567dc120 command return + range gaze + pan + body scan; fresh visible measurement required')
