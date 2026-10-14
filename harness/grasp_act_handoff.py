"""Local demonstration admission from bounded visual memory and issued pose."""
import math
from harness.grasp_act_contract import MEMORY_S

MODE = 'visible_handoff_v1'


def visible_local_sample(world, rid, end, *, handed_off, coordinated_wait=False):
    """No evaluator/truth argument, including when the target is not visible.

    The teacher latches handoff only in a visible tick. Subsequently the same
    bounded visual memory as the student may label the final blind sequence.
    This never drops an episode from the physical gate denominator.
    """
    if world['beam'] is None:
        return False, None
    if world['visibility'][rid]['visible_probes'] < 5:
        seen=world['beam'].get('seen_t')
        if seen is None or not 0 <= world['t']-seen <= MEMORY_S:
            return False, None
    distance = math.dist(world['robots'][rid]['pose'][:2], world['beam']['ends'][end][:2])
    return bool(handed_off and distance <= .8 and not coordinated_wait), distance
