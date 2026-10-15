"""Opt-in retained-error deadzone compensation; visible errors + issued pulses.

Release's common PulseSettler is unchanged. Comparisons span issued corrections,
not the temporary post-pulse camera displacement which can rebound before READY.
"""
import math
from collections import deque
from sim.settle_pulse import PulseSettler
from sim.crate_settle_v18 import DELTA, INNER, pulse

MODE = 'crate19_v1'
WINDOW = 6


class RetainedErrorSettler(PulseSettler):
    def __init__(self, tolerance, delta):
        super().__init__(tolerance)
        self.delta = delta
        self.errors = deque(maxlen=WINDOW)
        self.boost = 0
        self.stagnant = False

    def issued(self, error):
        old = self.previous
        super().issued(error)
        if old is not None and error*old <= 0:
            self.errors.clear()
            self.boost = 0
        self.errors.append(error)
        self.stagnant = (len(self.errors) == WINDOW and
                         abs(self.errors[0])-min(abs(e) for e in self.errors) < .1*self.delta)
        if self.stagnant:
            tolerance = max(self.tolerance, .6*self.delta)
            if abs(error) <= 2*tolerance:
                self.band = max(tolerance, abs(error))
                self.reason = 'same_sign_retained_error'
            else:
                self.boost = min(3, self.boost+1)
            self.errors.clear()

    def observe(self, error, delta):
        state = super().observe(error, delta)
        state.update(retained_error_stagnant=self.stagnant, pulse_boost=self.boost,
                     retained_error_samples=len(self.errors))
        return state


def settlers():
    return [RetainedErrorSettler(b, d) for b, d in zip(INNER, DELTA)]


def compensated_pulse(hold, axis, error, settler):
    value = pulse(hold, axis, error)
    if any(value['wheels']) and settler.boost:
        value['duration_s'] = [min(.1, math.ceil((d*(1+.5*settler.boost)-1e-12)*1000)/1000)
                               for d in value['duration_s']]
    return value


def blocker_context(nav, world, rid, value):
    """Diagnostic-only nearest geometric constraint, sampled on the issued model.

    The reported gap is geometric padding clearance, not localization certainty.
    Static wall geometry is its stable identifier because admitted walls lack IDs.
    """
    from harness.grasp_act_visible_world import command_delta
    labels=[]
    peers=[k for k in world['robots'] if k!=rid]
    walls=list(world.get('walls',()))
    for kind,r in nav.rectangles:
        if kind=='peer':
            name=next((k for k in peers if tuple(world['robots'][k]['pose'][:2])==tuple(r[:2])), 'visible_peer')
        elif kind=='crate':name='crate_1'
        else:name='static_wall:'+','.join(f'{x:.6g}' for x in r)
        labels.append(name)
    for kind,d in nav.circles:
        labels.append(next((k for k,o in world['objects'].items() if tuple(o['xy'])==tuple(d[:2])),kind))
    labels.append('arena_bounds')
    worst=None
    for i in range(21):
        dt=.1*i/20;dx,dy,da=command_delta(value,dt);x,y,a=nav.pose;c,s=math.cos(a),math.sin(a)
        gaps=nav.clearances((x+c*dx-s*dy,y+s*dx+c*dy),a+da)
        for j,(kind,gap) in enumerate(gaps):
            if worst is None or gap<worst['minimum_gap_m']:
                worst=dict(blocking_object=labels[j],obstacle_category=kind,minimum_gap_m=gap)
    return worst
