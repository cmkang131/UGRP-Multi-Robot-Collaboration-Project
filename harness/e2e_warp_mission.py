"""E2E composition of owner navigation, GPU ACT, and release relocalization.

This object has no world/model/evaluation reference. Owner factories are
hash-bound by e2e_warp_components. Their readiness is still pending; the real
first30 smoke does not exercise this mission state machine or an ACT student.
"""
from collections import deque
import copy
import hashlib

from harness import grasp_act_contract as contract


class Nearfield:
    """Build the frozen ACT own-input ABI and execute its existing0.8s chunks."""
    def __init__(self, robot, predict):
        from harness.grasp_act_policy import ChunkExecutor
        self.robot, self.images = robot, deque()
        self.executor, self.clock = ChunkExecutor(predict), contract.IssuedClock()
        self.instruction = None

    def observe(self, frame):
        if frame.robot_id != self.robot:
            raise ValueError('cross-robot ACT input rejected')
        ref = dict(path=f'rgb/{self.robot}-{frame.tick:08d}.jpg',
                   sha256=hashlib.sha256(frame.jpeg).hexdigest(), t=frame.sim_s, robot_id=self.robot)
        self.images.append((ref, frame.jpeg))
        # Existing ABI memory5.2s + existing frame freshness tolerance0.15s.
        while self.images and frame.sim_s-self.images[0][0]['t'] > contract.MEMORY_S+.15:
            self.images.popleft()

    def start(self, instruction, skill):
        self.instruction = {**instruction, 'skill': skill}
        self.executor.reset()  # also reset for two consecutive same-kind tasks
        self.clock = contract.IssuedClock()

    def step(self, frame):
        if self.instruction is None or not self.images or not frame.issued:
            raise ValueError('ACT requires explicit instruction and own history')
        refs = contract.image_history([r for r, _ in self.images], frame.sim_s)
        images = {r['sha256']: raw for r, raw in self.images}
        issued = list(frame.issued[-contract.HISTORY:])
        issued = [issued[0]]*(contract.HISTORY-len(issued)) + issued
        tokens = {k: self.instruction[k] for k in ('skill', 'object_kind', 'role', 'destination_zone')}
        clocks = self.clock.observe(tuple(tokens.values()), frame.sim_s, issued[-1]['pwm'])
        observation = dict(schema=contract.SCHEMA, robot_id=self.robot,
            sample_id=f'{self.robot}:{frame.tick}', t=frame.sim_s, **tokens,
            rgb=refs, issued=issued, **clocks)
        return self.executor.step(observation, [images[r['sha256']] for r in refs])


class IntegratedController:
    """The E2E worker owns orchestration; owners supply only the two adapters.

    navigation: observe(OwnFrame), task_candidates(completed), start(instruction,
      phase), command(sim_s), confirm_act(frame,skill), on_messages(rows),
      accept_release_fix(report). Reports use handoff_ready, destination_arrived,
      holding_status, evidence_revision, map_correction_active; all must derive
      from allowed inputs. map_correction_active means own/static-map correction
      is enabled, not that every frame is accepted as a position fix.
    release: start(instruction,own_report), observe(OwnFrame), command(sim_s).
      A report must say relocalized=true AND static_map_registered=true before
      navigation.accept_release_fix can permit the next task.
    """
    DECISIONS = ('TASK', 'GRASP_AUTH', 'CARRY_AUTH', 'RELEASE_AUTH', 'UNCERTAIN')

    def __init__(self, robot, static, predict_act, navigation, release):
        self.robot, self.static = robot, static
        self.navigation, self.release = navigation, release
        self.act = Nearfield(robot, predict_act)
        self.phase, self.frame, self.report = 'TASK', None, {}
        self.instruction, self.completed = None, []
        self.wait_revision, self.wait_phase, self.peer_event = None, None, False
        self.available, self.events = {}, []

    @property
    def complete(self):
        return self.phase == 'COMPLETE'

    @property
    def needs_decision(self):
        if self.phase in self.DECISIONS:
            return True
        if self.phase == 'WAIT':
            return self.peer_event or self.report.get('evidence_revision') != self.wait_revision
        return False

    def receive(self, rows):
        # Only the runtime's per-world/per-condition channel may call this.
        if rows:
            self.peer_event = True
            self.navigation.on_messages(rows)

    def set_phase(self, phase, reason):
        self.events.append(dict(sim_s=self.frame.sim_s, before=self.phase, after=phase, reason=reason))
        self.phase = phase

    def observe(self, frame):
        self.frame = frame
        self.act.observe(frame)
        self.report = self.navigation.observe(frame)
        if self.report.get('map_correction_active') is not True:
            raise ValueError('HOST_ERROR:owner own/static-map correction must be enabled')
        if self.phase == 'APPROACH' and self.report.get('handoff_ready') is True:
            self.set_phase('GRASP_AUTH', 'owner own-RGB/map nearfield handoff')
        elif self.phase == 'CARRY':
            if self.report.get('holding_status') == 'lost':
                self.set_phase('UNCERTAIN', 'own RGB/issued-command loss report; LLM decides retry')
            elif self.report.get('destination_arrived') is True:
                self.set_phase('RELEASE_AUTH', 'owner own-map destination arrival')
        elif self.phase == 'RELOCALIZE':
            released = self.release.observe(frame)
            if (released.get('relocalized') is True and released.get('static_map_registered') is True
                    and self.navigation.accept_release_fix(released) is True):
                self.completed.append(self.instruction.copy())
                self.set_phase('TASK', 'actual own-RGB lookaround and owner map correction accepted')
            self.report = {**self.report, 'release_relocalization': released}
        return dict(phase=self.phase, own_navigation=self.report, estimated_completed=len(self.completed),
                    complete_claim=self.complete, physical_success_available=False)

    def candidates(self):
        phase = self.wait_phase if self.phase == 'WAIT' else self.phase
        if phase == 'TASK':
            rows = self.navigation.task_candidates(completed=list(self.completed))
        elif phase == 'GRASP_AUTH':
            rows = [dict(id='grasp', skill='grasp', expected_cost='GPU ACT approach/alignment/grasp chunk')]
        elif phase == 'CARRY_AUTH':
            rows = [dict(id='carry', skill='carry', expected_cost='owner map route and code GO/ACK safety'),
                    dict(id='regrasp', skill='regrasp', expected_cost='new ACT attempt, no teacher correction')]
        elif phase == 'RELEASE_AUTH':
            rows = [dict(id='release', skill='release', expected_cost='GPU ACT release then required RGB lookaround')]
        elif phase == 'UNCERTAIN':
            rows = [dict(id='regrasp', skill='regrasp', expected_cost='new ACT attempt after own uncertainty')]
        else:
            rows = []
        rows = [*rows, dict(id='wait', skill='wait', expected_cost='hold until new own evidence or permitted message')]
        if len({r['id'] for r in rows}) != len(rows):
            raise ValueError('duplicate executable candidate')
        self.available = {r['id']: r for r in rows}
        return rows

    def select(self, candidate, now):
        if self.frame is None or now != self.frame.sim_s or candidate not in self.available:
            raise ValueError('fresh executable candidate required')
        row = self.available[candidate]
        if self.phase == 'WAIT':
            self.phase = self.wait_phase
        self.peer_event = False
        if row['skill'] == 'wait':
            self.wait_phase, self.wait_revision = self.phase, self.report.get('evidence_revision')
            self.set_phase('WAIT', 'LLM wait; no periodic micro-decision loop')
        elif row['skill'] == 'transport':
            if self.phase != 'TASK':
                raise ValueError('transport is a task decision')
            for key in ('object_kind', 'role', 'destination_zone', 'order_id'):
                if key not in row['instruction']:
                    raise ValueError('missing task token:' + key)
            self.instruction = copy.deepcopy(row['instruction'])
            self.navigation.start(row['instruction'], phase='approach')
            self.set_phase('APPROACH', 'LLM selected task/destination/route/end')
        elif row['skill'] in ('grasp', 'regrasp', 'release'):
            skill = row['skill']
            self.act.start(self.instruction, skill)
            self.set_phase('ACT_RELEASE' if skill == 'release' else 'ACT_GRASP', 'LLM authorized ACT skill')
        elif row['skill'] == 'carry':
            self.navigation.start(self.instruction, phase='carry')
            self.set_phase('CARRY', 'LLM authorized owner map transport; protocol remains code')
        elif row['skill'] == 'finish' and self.phase == 'TASK':
            self.set_phase('COMPLETE', 'LLM completion claim; physical evaluator remains separate')
        else:
            raise ValueError('unsupported high-level skill')

    def hold(self, now):
        # Safety interruption only; preserves issued PWM. No nearfield policy.
        return dict(t=now, wheels=[0.]*4, duration_s=[0.]*4, pwm=dict(self.frame.issued[-1]['pwm']))

    def command(self, now):
        if self.phase in ('APPROACH', 'CARRY'):
            return contract.command(self.navigation.command(now))
        if self.phase == 'RELOCALIZE':
            return contract.command(self.release.command(now))
        if self.phase in ('ACT_GRASP', 'ACT_RELEASE'):
            skill = 'release' if self.phase == 'ACT_RELEASE' else self.act.instruction['skill']
            command, done = self.act.step(self.frame)
            if done:
                confirmed = self.navigation.confirm_act(self.frame, skill)
                if confirmed is not True:
                    self.set_phase('UNCERTAIN', 'ACT done lacks own RGB confirmation; return unknown to LLM')
                elif self.phase == 'ACT_RELEASE':
                    self.release.start(self.instruction, self.report)
                    self.set_phase('RELOCALIZE', 'ACT release confirmed from own input; real lookaround required')
                else:
                    self.set_phase('CARRY_AUTH', 'ACT grasp confirmed from own input; LLM lift/wait decision')
            return contract.command(command)
        return self.hold(now)
