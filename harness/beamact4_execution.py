"""Default-off pair student execution candidates; no simulator or teacher API."""
import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_policy import ChunkExecutor
from harness.beamact_pair_student import STAGE_MODE, RECOVERY_MODE, LEARNED_STAGES


def decode_stages(logits):
    values = np.asarray(logits, dtype=float)
    if values.shape != (c.CHUNK, len(LEARNED_STAGES)) or not np.isfinite(values).all():
        raise ValueError('finite, horizon-aligned learned stage logits required')
    # Standard categorical argmax. An exact tie has no unique learned class;
    # fail closed rather than giving READY to a class-order tie break.
    if np.any((values == values.max(axis=-1, keepdims=True)).sum(axis=-1) != 1):
        raise ValueError('ambiguous learned stage; no readiness fallback')
    return [LEARNED_STAGES[i] for i in values.argmax(axis=-1)]


class PairChunkExecutor:
    """Preserve the existing action contract and cadence, optionally revoke done.

    Completion remains an own-model request, never physical success. With the
    recovery toggle, the next control tick after done forces a fresh prediction
    (discarding the old chunk), so the model can retract done and issue recovery.
    """
    def __init__(self, predict, *, stage_mode='off', done_recovery='off'):
        if stage_mode not in ('off', STAGE_MODE) or done_recovery not in ('off', RECOVERY_MODE):
            raise ValueError('unknown pair student candidate')
        self.stage_mode, self.done_recovery = stage_mode, done_recovery
        self.stage, self.stage_plan = None, []

        def wrapped(observation, jpegs):
            result = predict(observation, jpegs)
            if stage_mode == 'off':
                return result
            if not isinstance(result, dict) or set(result) != {'chunk', 'stage_logits'}:
                raise ValueError('stage checkpoint output required; no legacy fallback')
            self.stage_plan = decode_stages(result['stage_logits'])
            return result['chunk']
        self.core = ChunkExecutor(wrapped)

    def discard_pending(self):
        """Re-predict after protocol hold/rejection using actually issued history."""
        self.core.pending.clear()
        self.core.chunks.clear()
        self.stage_plan.clear()

    def step(self, observation, jpegs, *, interrupt=False):
        if self.done_recovery == RECOVERY_MODE and self.core.done_requested:
            self.core.done_requested = False
            self.discard_pending()
        identity = tuple(observation[k] for k in ('robot_id', 'skill', 'object_kind', 'role', 'destination_zone'))
        absorbing = (self.core.done_requested and self.core.identity == identity
            and self.core.last_t is not None
            and abs(observation['t'] - self.core.last_t - c.PERIOD_S) <= 1e-5)
        value, done = self.core.step(observation, jpegs, interrupt=interrupt)
        if interrupt:
            self.stage, self.stage_plan = None, []
        elif self.stage_mode == STAGE_MODE and not absorbing:
            if not self.stage_plan:
                raise ValueError('stage/action horizon mismatch')
            self.stage = self.stage_plan.pop(0)
            if done:
                self.stage_plan.clear()
        return value, done
