"""LLM -> local ACT skill boundary. No simulator or privileged dependencies.

Navigation has already reached a camera-estimated handoff. It remains the
existing map controller's job. ACT output is interruptible between chunks;
expiry/stop is enforced between primitive actions too. A done score alone
never becomes a claim of physical success.
"""
from collections.abc import Mapping
from harness.grasp_act_contract import SKILLS, ROLES, CHUNK, PERIOD_S, finite


def task(value):
    if not isinstance(value, Mapping) or set(value) != {'skill', 'end'}:
        raise ValueError('discrete skill/end instruction required')
    if value['skill'] not in (*SKILLS, 'stop') or value['end'] not in ROLES:
        raise ValueError('unknown skill/end instruction')
    return dict(value)


class SkillSession:
    def __init__(self):
        self.instruction = None
        self.until = 0.
        self.chunk = []
        self.revision = 0
        self.verified_count = 0
        self.done_requested = False
        self.result = 'unknown'

    def start(self, instruction, now, *, handoff, timeout_s=90.):
        """handoff is an owned-RGB estimate, not an evaluator result.

        Initial off-screen cases stay with the map/search controller until it
        has a fresh target estimate within 0.8 m. A new request cancels old
        chunks, including when it changes only the assigned color.
        """
        instruction = task(instruction)
        if set(handoff) != {'source', 'age_s', 'distance_m', 'map_arrived'}:
            raise ValueError('owned handoff whitelist required')
        if handoff['source'] != 'own_rgb_and_issued_commands':
            raise ValueError('privileged navigation handoff forbidden')
        now, timeout_s = finite(now), finite(timeout_s)
        if not 0 < timeout_s <= 120:
            raise ValueError('bounded skill duration required')
        if instruction['skill'] in ('grasp_end', 'regrasp') and not (
            handoff['map_arrived'] is True and 0 <= finite(handoff['age_s']) <= 1.
            and 0 <= finite(handoff['distance_m']) <= .8
        ):
            raise ValueError('fresh local RGB handoff required')
        self.instruction = instruction
        self.until = now + timeout_s
        self.revision += 1
        self.chunk = []
        self.verified_count = 0
        self.done_requested = False
        self.result = 'unknown'
        return self.revision

    def cancel(self, reason='wait'):
        self.chunk = []
        self.revision += 1
        self.done_requested = False
        self.result = 'unknown'
        return {'kind': 'stop', 'reason': reason}

    def accept_chunk(self, actions, *, revision, now):
        if revision != self.revision or now >= self.until or self.done_requested:
            return False
        if not self.instruction or self.instruction['skill'] in ('wait', 'stop'):
            return False
        if not 1 <= len(actions) <= CHUNK:
            raise ValueError('at most 0.8 SIM second action chunk')
        self.chunk = list(actions)
        return True

    def next(self, now, *, interruption=None):
        if interruption is not None:
            return self.cancel(interruption)
        if not self.instruction or self.instruction['skill'] in ('wait', 'stop'):
            return {'kind': 'stop', 'reason': 'wait'}
        if now >= self.until:
            self.cancel('timeout')
            self.result = 'failure'
            return {'kind': 'stop', 'reason': 'timeout'}
        if self.done_requested or not self.chunk:
            return {'kind': 'stop', 'reason': 'verify' if self.done_requested else 'need_chunk'}
        action = self.chunk.pop(0)
        if action['done']:
            self.done_requested = True
            self.chunk = []
            return {'kind': 'stop', 'reason': 'verify'}
        return {'kind': 'act', 'action': action, 'period_s': PERIOD_S}

    def verify(self, *, own_camera_result):
        """Result from an independently evaluated own-RGB verifier only.

        Its confidence threshold and calibration are fixed before holdout.
        An uncalibrated/missing/occluded verifier must supply 'unknown'.
        This API deliberately cannot consume held/contact/pose dictionaries.
        """
        if own_camera_result not in ('complete', 'failure', 'unknown'):
            raise ValueError('owned visual verification result required')
        if not self.done_requested:
            return 'unknown'
        self.verified_count = self.verified_count + 1 if own_camera_result == 'complete' else 0
        self.result = ('complete' if self.verified_count >= 3 else
                       'failure' if own_camera_result == 'failure' else 'unknown')
        return self.result
