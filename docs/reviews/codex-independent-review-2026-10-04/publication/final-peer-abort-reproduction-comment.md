# E1 추가 재현: 같은 tick abort 이후 실제 command-only port까지의 dispatch

소스 고정: `f2577bb5121748644df31eb0fc5a1c1b94b80d80`. PR #363 게시 전 `73429982ea3088f2569c26cf7a4b5b74a1e6c1a6`에서도 shared Runtime.step/skill/backend와 runner의 최종 veto 부재를 diff/상속 경계로 확인했다. 새 Execution.step의 전용 frame gate는 명령 수집 뒤 최종 dispatch를 취소하는 변경이 아니다. 새 head에서 재현이나 물리를 실행했다는 뜻은 아니다.

의존성은 Python 3.11+ 표준 라이브러리와 해당 소스 checkout뿐이다. checkout root에서 `PYTHONDONTWRITEBYTECODE=1 python -`로 아래 블록을 실행한다. repository 파일·사용자 입력을 쓰지 않고, MuJoCo/OpenCV/model을 import하지 않는다. simulator 대신 raw setpoint만 기록하는 fake robot을 쓴다. 코드를 AST로 읽어 원래 메서드 몸체를 유지하며 frame validity/bootstrap/controller 출력/충돌 guard만 명시적 boundary 대체다.

이미 독립 검증한 두 fixture를 한 블록으로 연결하고 checkout 경로를 cwd로 바꿨다. 편집 후에는 AST syntax만 점검했으며 같은 검사를 세 번째 실행하지 않았다.

<details>
<summary>완전한 offline lifecycle / command-only port 재현</summary>

```python
"""Offline scheduler seam counterexample. Exact AST method bodies, no edited repo.

Actual methods: Runtime.step; ZoneOwnExecutor.step/_step_pair_carry/expire_if_due/
_fail/_record/_end_job; PairExecution.step/check/abort/_clear; PairTeam.poll.
Actual PairStatusChannel/Endpoint module. The motion controller, geometry guard,
frame validity and bootstrap are explicit boundary fakes; no RGB/physics/model.
"""
import ast
import copy
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from harness.zone_pair_status import PairStatusChannel, PairStatusEndpoint

ns = {'math': math, 'copy': copy, 'EPS': 1e-8, 'CONTROL_S': .1,
      'ROBOTS': ('r1', 'r2'), 'PROFILE': 'test-boundary',
      'UNCERTAIN_REASONS': ('POSE_UNCERTAIN', 'NOT_INITIALIZED'),
      'UNCERTAIN_SUFFIXES': ('lost', 'not_initialized', 'pose_uncertain', 'arrival_unconfirmed')}

def exact_class(path, name, methods):
    tree = ast.parse((ROOT / path).read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    assert {n.name for n in nodes} == set(methods)
    out = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
                          ast.ClassDef(name=name, bases=[], keywords=[], body=nodes, decorator_list=[])], type_ignores=[])
    exec(compile(ast.fix_missing_locations(out), str(ROOT / path), 'exec'), ns)
    return ns[name]

Runtime = exact_class('harness/zone_final_pair_runtime.py', 'Runtime', ['step'])
Own = exact_class('harness/zone_own_executor.py', 'ZoneOwnExecutor',
                  ['step', '_step_pair_carry', 'expire_if_due', '_fail', '_record', '_end_job'])
Execution = exact_class('harness/zone_pair_executor.py', 'PairExecution', ['step', 'check', 'abort', '_clear'])
Team = exact_class('harness/zone_pair_executor.py', 'PairTeam', ['poll'])

vision = ModuleType('harness.zone_pair_vision')
vision.frame_gate = lambda policy: lambda obs, rid, now: True
sys.modules['harness.zone_pair_vision'] = vision
channel = PairStatusChannel('synthetic-offline-abort')
actors, endpoints = {}, {}
command = {'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': .15}
for rid in ('r1', 'r2'):
    own, ep = Own(), Execution()
    own.robot_id, own.now, own.stopped = rid, 0., None
    own._pending_hold, own._pair, own._summaries, own.jobs_done, own.events = False, ep, [], [], []
    own.job = SimpleNamespace(job_id=rid+'-job', deadline=10., started_at=0., kind='pair_carry',
                              args={}, ctl=None, driver=None, sweep=None)
    own.last_obs = {'sim_time': 0.}
    own._stationary_bootstrap = lambda now, job: None
    own._emit = lambda now, event, own=own, **detail: own.events.append({'t':now, 'event':event, **detail})
    ep.own, ep.job_id, ep.partner_id = own, own.job.job_id, 'r2' if rid=='r1' else 'r1'
    ep.terminal = ep.cleared = False
    ep.started = ep.control_started = True
    ep.status = PairStatusEndpoint(channel, rid)
    ep.status.tick('start_ready', 0.)
    ep.events, ep.inputs, ep.plan, ep.calibration_sha256 = [], [], {}, 'synthetic'
    ep.next_control, ep.rendezvous_deadline, ep.last_phase, ep.policy = 0., 5., 'carry', None
    ep.port = SimpleNamespace(commands=[])
    ep.command_guard = SimpleNamespace(before_control=lambda now: True, check=lambda now, cmds: cmds)
    ep.controller = SimpleNamespace(state='carry', failure=None, arm=SimpleNamespace(events=[], until=0.), schedule=[])
    if rid == 'r1':
        ep.controller.tick = lambda now, ep=ep: ep.port.commands.append(dict(command))
    else:
        def fail(now, ep=ep):
            ep.controller.state, ep.controller.failure = 'failed', 'SYNTHETIC_LOCAL_GUARD_FAILURE'
        ep.controller.tick = fail
    actors[rid], endpoints[rid] = own, ep
team = Team()
team.sessions = [{'endpoints': endpoints, 'closed': False}]
team.cancel_scheduled = lambda *a: None  # exact current final-v3 adapter policy
runtime = Runtime()
runtime.actors, runtime.team, runtime.started, runtime.submitted = actors, team, True, set(actors)
issued = runtime.step(0.)
result = {'issued_same_tick': issued,
          'terminal_after_poll': {r:e.terminal for r,e in endpoints.items()},
          'pending_hold_after_poll': {r:o._pending_hold for r,o in actors.items()},
          'abort_reasons': {r:o.events for r,o in actors.items()},
          'next_tick': runtime.step(.05)}
assert result['terminal_after_poll'] == {'r1': True, 'r2': True}
assert issued == [('r1', command), ('r2', {'kind':'hold'})]
assert result['next_tick'] == [('r1', {'kind':'hold'}), ('r2', {'kind':'hold'})]


"""Extend scheduler seam through exact issue/receipt and real command-only port.

No MuJoCo, rendering, model, or measured joint is used. The fake robot merely
records raw motor/servo setpoints. This proves dispatch, not physical travel.
"""
import json
import runpy
from types import SimpleNamespace

s = globals()
exact = s['exact_class']
Backend = exact('sim/final_environment_checks.py', 'PhysicsBackend', ['issue'])
OwnReceipt = exact('harness/zone_own_executor.py', 'ZoneOwnExecutor', ['on_command'])
RuntimeReceipt = exact('harness/zone_final_pair_runtime.py', 'Runtime', ['on_command'])
from sim.camera_robot_port import CameraRobotPort

class Robot:
    servo_command_pulses = {1: 1500, 3: 1500, 4: 1500, 5: 1500, 6: 1500}
    def __init__(self): self.motor_calls, self.servo_calls = [], []
    def set_motor_commands(self, values): self.motor_calls.append(list(values))
    def set_servo_pulses(self, values): self.servo_calls.append(dict(values))

robots = {r: Robot() for r in ('r1', 'r2')}
world = SimpleNamespace(data=SimpleNamespace(time=0.), robot=lambda rid: robots[rid])
backend = Backend()
backend.now = 0.
backend.ports = {rid: CameraRobotPort(world, rid, allow_reverse=True, allow_mecanum=True)
                 for rid in robots}
backend.commands = {rid: dict(Robot.servo_command_pulses) for rid in robots}
backend._append = lambda *args: None
receipts = []
runtime = s['runtime']
for rid, own in runtime.actors.items():
    own.servo = dict(Robot.servo_command_pulses)
    own.pose = SimpleNamespace(on_command=lambda row, rid=rid: receipts.append((rid, row)))
    own.on_command = OwnReceipt.on_command.__get__(own)
runtime.on_command = RuntimeReceipt.on_command.__get__(runtime)
# This is run_final_pair_v3:93-98 / run_pair_highpose:205-211 dispatch order.
# V3's issue forwards non-hold to the original BaseBackend.issue and handles
# hold exactly with the port.hold branch used here.
for rid, action in s['issued']:
    if action['kind'] == 'hold': backend.ports[rid].hold(0.)
    else: backend.issue(rid, action)
    runtime.on_command(rid, 0., action)
before = dict(terminal=s['result']['terminal_after_poll'],
              r1_motor_commands=robots['r1'].motor_calls[-1], own_command_receipts=receipts)
assert before['terminal'] == {'r1': True, 'r2': True}
assert before['r1_motor_commands'] == [.1, .1, .1, .1]
backend.ports['r1'].tick(.049)
assert robots['r1'].motor_calls[-1] == [.1, .1, .1, .1]
backend.ports['r1'].hold(.05)
assert robots['r1'].motor_calls[-1] == [0., 0., 0., 0.]
print(json.dumps({'dispatch_after_abort': before,
                  'r1_after_next_50ms_hold': robots['r1'].motor_calls[-1]}, indent=2))

```

</details>

관측 핵심은 `terminal={r1:true,r2:true}`인 상태에서 r1 모터 setpoint `[.1,.1,.1,.1]` 및 own-command receipt가 전달된다는 것이다. 코드의 `tick(.049)` assertion은 명령이 유지됨을, 다음 `.05` hold는 `[0,0,0,0]`이 됨을 확인한다. 정상 루프의 관측 잔존은 50ms이며 command의 .15s는 lease다. 실제 이동거리·접촉·현재 실험 실패의 원인은 측정하지 않았다.

원문 연결: [Runtime.step](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/harness/zone_final_pair_runtime.py#L56-L74), [runner dispatch](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/73429982ea3088f2569c26cf7a4b5b74a1e6c1a6/scripts/run_pair_highpose.py#L210-L217), [command-only port](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/f2577bb5121748644df31eb0fc5a1c1b94b80d80/sim/camera_robot_port.py#L157-L208).
