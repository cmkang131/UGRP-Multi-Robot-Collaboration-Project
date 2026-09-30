"""PR #335 counterexample promoted from strict xfail to a live regression.

Source: codex/review-e2e-batch-i, e24cb9ce3c10236efe03a1b66c9ec7671ece71b9,
tests/test_review_e2e_batch_i.py (I-335-1). The geometry and safety assertion
are unchanged. Run against the current tree, including uncommitted fixes;
no pinned old candidate, git history, extraction directory or physics needed.
PR #330 is outside this change and its counterexample is not copied here.
"""


def test_t04_issued_arm_increment_passes_the_same_static_sweep():
    import copy
    import numpy as np
    from tests.test_zone_own_executor_can import MAP, FakeOwnPose, observation, pose, decide
    from harness.zone_can_skill import CanSkill, VIEWS
    from harness.zone_own_guards import OwnPose
    initial = {1:2000, 3:1164, 4:2321, 5:2080, 6:1174}
    static = copy.deepcopy(MAP)
    # Authored static geometry, not a simulator state or a physical collision claim.
    static['obstacles'].append(dict(id='review_static_post',
        center_m=[.27446602791450786, -.11115416383666454],
        half_extents_m=[.0001, .0001], height_m=.025))
    skill = CanSkill('r1', static, destination_zone='C', pose_source=FakeOwnPose())
    skill.on_command(dict(robot_id='r1', t=0., kind='initial_servo_command', pulses=initial))
    own = OwnPose(0., 0., 0., .002, .002)
    out = decide(skill, 1., observation(np.full((480,640,3),80,np.uint8)), pose(1.,xy=(0.,0.)))
    issued = dict(initial)
    for cmd in out['commands']:
        if cmd['kind'] == 'arm':
            issued[cmd['servo_id']] = cmd['pulse']
    def clearance(target):
        return min(skill.guard.arm_clearance(p, own, loaded=False)[0]
                   for p in skill.guard.transition_samples(initial, target))
    result = dict(phase=out['phase'], issued=issued,
        start_clearance_m=skill.guard.arm_clearance(initial,own,loaded=False)[0],
        chassis_clearance_m=skill.guard.chassis_clearance(own)[0],
        checked_clearance_m=clearance(VIEWS[0]), issued_clearance_m=clearance(issued))
    # Fixture validity is separate from the expected failing safety assertion.
    if min(result["start_clearance_m"], result["chassis_clearance_m"]) <= 0:
        raise RuntimeError(f"counterexample no longer starts clear: {result}")
    assert result["issued_clearance_m"] >= 0, result
