"""Partial saved-state lifecycle replay, NOT saved-costmap/physical replay."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from harness.e2e_exploration import Navigator
from harness.e2e_explore_deadlock import install
from harness.public_navigation_unknown import UnknownCostmap


FIXTURE = Path(__file__).resolve().parents[1]/'tests/fixtures/e2e_idle/terminal_states.json'


def restored(fixture, option):
    row = fixture['controller_row']
    pose = np.array(row['pose_continuity']['odom_pose'])
    n = Navigator(SimpleNamespace(pose=pose.copy()))
    state = row['exploration']
    assert state['target'] is None and not state['locked'] and state['phase'] is None
    n.sweep_pending = None
    n.finished = n.initial_scan_used = True  # code implication of saved finish event
    n.sweep_rotation = state['sweep_rotation_rad']
    # No historical costmap was saved. Use a labelled neutral known-free
    # costmap with no frontier, exercising recovery even without a new goal.
    c = UnknownCostmap(np.zeros((100, 100), np.uint8), pose[:2]-2.5, .05)
    g = SimpleNamespace(robot_id=fixture['robot'], done=False, stage=row['stage'],
        explorer=SimpleNamespace(navigator=n, plan=None, last_plan_t=-float('inf')))
    g.command = lambda action: None
    def receive(**kw):
        plan = n.update(c, pose, kw['t'])
        return n.command(c, pose, plan, kw['t']), dict(status=plan['status'])
    g.receive = receive
    install(g, option)
    return g, n, c, pose


def replay(fixtures):
    records = []
    for f in fixtures:
        results = {}
        for option in ('off', 'replan_v1'):
            g, n, c, pose = restored(f, option)
            start = f['controller_row']['t']
            for i in range(152):
                t = start+i*.2
                action, trace = g.receive(robot_id=f['robot'], t=t)
                g.command(action)
                if action.get('turn', 0) or action.get('forward', 0):
                    break
            results[option] = dict(action=action, elapsed_s=round(t-start, 3),
                finished=n.finished, phase=n.phase, trace=trace)
        records.append(dict(run=f['run'], robot=f['robot'], outcomes=results))
    resumed = sum(bool(r['outcomes']['replan_v1']['action'].get('turn', 0)) for r in records)
    return dict(scope='partial saved terminal flags + synthetic free/no-frontier costmap; no RGB/map/physics replay',
                n=resumed, N=len(records), records=records)


if __name__ == '__main__':
    print(json.dumps(replay(json.loads(FIXTURE.read_text())), indent=1))
