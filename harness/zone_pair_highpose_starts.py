"""Dev/confirmation separation (REVIEW_363 P2-1); host/evaluation side only.

* P03 seed 911 from the dock is a FUNCTIONAL_DEV_REPLAY: three checkpoint
  replays of ONE start, never three independent samples.
* Confirmation starts are frozen in a separate registry. A start is rejected
  by its NUMERIC pose (xy distance), regardless of robot id, map name, seed or
  file bytes: renaming cannot hide a reused start.
* After a confirmation collection, each carrier trajectory is compared on its
  motion content (t, base_position_m, base_rotation) with
  harness.kinematic_overlap (byte-identical copy of the criterion-B v94 policy,
  codex/critb-heldout-new-starts 12c1e58c). Issue #219 comments 5966536405 /
  5966843527: file-byte identity missed a duplicate whose only difference was
  an unrelated per-map field.

Never read a prior raw path from a manifest; the prior kinematic corpus is a
coordinator-supplied list. Without it, confirmation qualification is refused.
"""
import json
import math

from harness import kinematic_overlap as ko
from harness.zone_final_pair_contract import ROOT, base

REGISTRATION = 'configs/zone_pair_highpose_confirmation_v96.json'
DEV_SEED = 911
MIN_START_SEPARATION_M = .05       # >> 1e-9 overlap tolerance; any robot id/map/seed


def _xy(pose):
    if len(pose) != 4 or not all(math.isfinite(float(x)) for x in pose):
        raise ValueError('invalid start pose')
    return float(pose[0]), float(pose[1])


def _near(pose, others):
    xy = _xy(pose)
    return [o for o in others if math.dist(xy, _xy(o)) < MIN_START_SEPARATION_M]


def registration():
    value = base.read(ROOT/REGISTRATION)
    prior = [row['pose'] for row in value['prior_start_sources']]
    if value['dev']['seed'] != DEV_SEED or value['dev']['cohort_role'] != 'FUNCTIONAL_DEV_REPLAY':
        raise ValueError('dev replay registration changed')
    seen, seeds = [], set()
    for row in value['confirmation_starts']:
        if row['seed'] == DEV_SEED or row['seed'] in seeds:
            raise ValueError('duplicate/development confirmation seed')
        seeds.add(row['seed'])
        for pose in row['spawns'].values():
            if _near(pose, prior):
                raise ValueError('confirmation start pose duplicates prior data')
            if _near(pose, seen):
                raise ValueError('confirmation starts must differ from each other')
            seen.append(pose)
    return value


def require_dev_seed(seed):
    if seed != DEV_SEED:
        raise ValueError('FUNCTIONAL_DEV_REPLAY_REQUIRES_SEED_911; confirmation uses a separate frozen start list')


def require_novel_start(candidate, reg=None):
    reg = registration() if reg is None else reg
    prior = [row['pose'] for row in reg['prior_start_sources']]
    if any(_near(pose, prior) for pose in candidate['spawns'].values()):
        raise ValueError('START_POSE_DUPLICATES_PRIOR_DATA')
    expected = next((row for row in reg['confirmation_starts'] if row['id'] == candidate['id']), None)
    if candidate != expected:
        raise ValueError('UNREGISTERED_CONFIRMATION_START')
    return True


def read_trace(path):
    """Only t/position/rotation enter identity (kinematic_overlap.trace)."""
    if 'final-pair-v91-heldout-' in str(path):
        raise ValueError('prior heldout raw access forbidden in this PR')
    return ko.read_trace(path)


def qualify_confirmation(candidate, traces, prior, reg=None):
    """traces: {'r1': Trace, 'r2': Trace} of the NEW run; prior: list[Trace]."""
    reg = registration() if reg is None else reg
    require_novel_start(candidate, reg)
    if set(traces) != {'r1', 'r2'}:
        raise ValueError('both carrier trajectory identities required')
    if not reg['prior_trajectory_inventory_complete'] or not prior:
        raise ValueError('PRIOR_KINEMATIC_INVENTORY_REQUIRED')
    report = ko.audit(list(traces.values()), list(prior))
    if report['status'] != 'DISJOINT':
        raise ValueError('TRAJECTORY_DUPLICATES_PRIOR_DATA: '+json.dumps(report['witnesses'][0]))
    return {'confirmation_eligible': True, 'overlap_policy': report['policy'],
            'scope': 'novel start + kinematically disjoint trajectories only, not task success'}
