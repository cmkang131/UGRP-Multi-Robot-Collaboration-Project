"""LLM call memory (llm_memory v1/v1_commands, default off).

Why: every E2E18 call is stateless (system+user only). A robot does not see its own earlier
GO/ACK decisions, whether the host accepted them, or in which dialogue window a peer message was
sent. In e2e18-v321-s61006-r65 the seg-0 peer message "GO"/"ACK" (id w1-r2-2) was shown unchanged in
the seg-1 window, r1 answered with a malformed ACK and then repeated invalid ACKs.

What is added (host-known facts about the robot's OWN decisions and message timing only; never
simulator truth, poses, contacts or joint readings):
  a) `own_decision_log`: last N {sim_s, kind, choice, seg, epoch, result, why}.
  b) `decision_feedback`: one line when the latest decision was rejected (code + fixed contract rule).
  c) `peer_reports[].window`: the received GO/ACK window (seg, grip_epoch, current),
     `sent_window` and receipt time; the message body is untouched (research variable).
  d) v1_commands only: `own_command_history` filled with the robot's own issued commands (the live
     dialogue path never filled it, because motion is issued by the transport, not by LLM actions).
  e) Current protocol state filters candidates; an already accepted claim is not offered again.

Same pattern as vote_ref_v1: a pure function of (post-projection body, memory records) so a stored real
request can be rebuilt offline with the same code (`apply`). Combines with vote_ref (v331).
"""
import copy
from collections import deque
from harness.e2e_dialogue_call_policy import reports as call_reports

OPTIONS = ('v1', 'v1_commands')
LOG_N = 8
COMMAND_N = 8
# Same motion parent for both comparisons; only vote_ref differs in v331.
VERSIONS = {('v1', 'off'): 330, ('v1', 'v1'): 331, ('v1_commands', 'off'): 332}
PARENT = 'e2e18-v324'

PROMPT_ADD = (' own_decision_log lists your own recent decisions and whether the host accepted them (rejected: why); '
              'decision_feedback explains your last rejection. peer_reports[].window is the GO/ACK window in which the '
              'peer message was received; sent_window marks its creation window. Unknown timing is not current evidence. '
              'A message from an earlier window is not a vote in the current window. '
              'peer_go_ref only from dialogue.peer_go_ref. '
              'dialogue is the authoritative current protocol state, even if a recent log entry describes a rejection. '
              'own_claim=true means your role claim is ALREADY accepted: never claim again. '
              'A new segment resets GO/ACK, not your role claim. '
              'Choose only an action in the filtered action_message_contract.actions. '
              'When a current window has own_go_sent=false, select GO if your current RGB supports the grip, otherwise continue. '
              'After your GO, ACK only when the current peer_go_ref is present and own_ack_sent=false. '
              'GO/ACK are protocol votes, not body motions; the motion rules below do not forbid negotiating permission. '
              'Accepted means protocol accepted, not physical success.')

# Priority section reused from coordinator cmp/run_complex.py FIXED (2026-10-13).
# Do not copy its illustrative 15-degree/10-cm primitives or fixed camera heading:
# this interface selects protocol actions; numerical motion remains with its controller.
PRIORITY_RULES = (
    ' Rules, in priority order: '
    '(1) Safety: never move toward a robot or obstacle in the path within about 0.6 m, or forward when the front range is under 0.15 m; slide away from it or hold. Safety overrides partner requests and the route. '
    '(2) Own grip: if your own camera shows your grip slipping or the beam dropping, hold. '
    '(3) Partner messages reporting slipping, danger, asking to stop or to wait: hold. '
    '(4) Stalled (commands did not change the image): back_up. '
    '(5) Lifting needs both robots grasped AND GO/ACK agreed for lifting; if not, grasp_only or hold. '
    '(6) While holding: move only along the agreed route segment after GO/ACK; if inside zone B with no route remaining, set_down; if route remains, keep following it; without agreement, hold. '
    '(7) Loop (last commands alternate left/right): break it with back_up or hold. '
    '(8) Fresh camera beats stale map. Banded end cut by an image edge: turn toward that edge or back_up; touching or below the bottom edge: back_up. '
    '(9) At the grasp station (station distance under 0.05 m) with the end fully visible: if the station heading error is over 15 deg, turn toward it; otherwise hold (ready). '
    '(10) Banded end fully visible and not at the station: turn toward it if off-center by more than about 20 deg, else forward. '
    '(11) Searching: turn toward the last-seen bearing if known; if a full rotation found nothing, forward to a new viewpoint. '
    'These are motion priorities, not additional JSON action kinds. This dialogue interface exposes no body-motion candidates. '
    'Use continue when unsafe or uncertain; never infer grip, clearance, or progress from an issued command alone.')

# Fixed contract rules (already stated in the task prompt), keyed by host rejection code.
HINTS = {
    'CAPTURED_PEER_GO_REQUIRED': 'ACK needs your own GO in this window and a non-null dialogue.peer_go_ref.',
    'MATCHING_CURRENT_GO_ACK_REQUIRED': 'GO/ACK must match the current dialogue.key and be sent once per window.',
    'GO_HAS_NO_ACK_REFERENCE': 'GO must use peer_go_ref null.',
    'STALE_OWN_RGB_RESPONSE': 'The answer arrived after the own RGB window closed; decide on a fresh view.',
    'ROUTE_VOTE: CLOSED_SCHEMA_REQUIRED': 'route_vote must be a flat object with exactly the contract fields.',
    'CURRENT_APPROVED_OWN_ROLE_CLAIM_REQUIRED': 'Check dialogue.own_claim: true means already claimed; do not claim again. A new segment needs fresh GO/ACK, not a new claim.',
    'RECEIVED_B_ROUTE_REQUIRED': 'No received route yet.',
    'VOTE_REF_MISMATCH': 'vote_ref must equal the current dialogue.vote_ref.',
    'VOTE_WINDOW_CLOSED': 'No open GO/ACK window (dialogue.key is null).',
}


def code_of(error):
    """Stable reason code of a ContractViolation/ProtocolError text."""
    text = str(error).strip()
    for code in HINTS:
        if text.startswith(code):
            return code
    head = text.split(':')[0].split(' ')[0]
    return head if head.isupper() and len(head) < 60 else 'INVALID_REPLY'


def attempt_of(value):
    """(did, seg, epoch) of a model action dict, tolerant of malformed input."""
    if not isinstance(value, dict):
        return 'invalid', None, None
    kind = value.get('kind')
    if kind == 'route_vote':
        did = value.get('choice') if value.get('choice') in ('GO', 'ACK') else 'route_vote'
        seg, epoch = value.get('seg'), value.get('grip_epoch')
        nested = value.get('dialogue')
        if isinstance(nested, dict):
            seg, epoch = nested.get('seg', seg), nested.get('grip_epoch', epoch)
        return did, seg if type(seg) is int else None, epoch if type(epoch) is int else None
    return (kind if isinstance(kind, str) else 'invalid'), None, None


def decision_log(records, now, n=LOG_N, current_key=None):
    """Last n decisions already answered by the host at call time `now`.

    records: dicts t(answer sim_s), did, seg, epoch, accepted(bool), reason(code|None).
    """
    seen = sorted((r for r in records if r['t'] <= now + 1e-9), key=lambda r: (r['t'], r.get('call_id', '')))[-n:]
    out = []
    for r in seen:
        vote = r['did'] in ('GO', 'ACK')
        row = dict(sim_s=round(r['t'], 2), kind='route_vote' if vote else r['did'],
                   choice=r['did'] if vote else None, result='accepted' if r['accepted'] else 'rejected')
        if r.get('seg') is not None:
            row['seg'] = r['seg']
        if r.get('epoch') is not None:
            row['epoch'] = r['epoch']
        if r['did'] in ('GO', 'ACK') and current_key is not None and r.get('seg') is not None:
            same = (list(r['key']) == list(current_key) if r.get('key') is not None
                    else (r['seg'], r.get('epoch')) == (current_key[3], current_key[2]))
            row['window'] = 'current' if same else 'earlier'
        if not r['accepted']:
            row['why'] = r['reason']
        out.append(row)
    return out


def feedback(log):
    """One line for a last rejected decision, else None."""
    if not log or log[-1]['result'] != 'rejected':
        return None
    last = log[-1]
    seg = '' if 'seg' not in last else f' (seg {last["seg"]})'
    return f'Your last decision {last["choice"] or last["kind"]}{seg} at t={last["sim_s"]} was rejected: {last["why"]}. ' + HINTS.get(last['why'], '')


def window_of(windows, created_at):
    """Window (key list) open when a message was created, else None. windows: [(at, key)] ascending."""
    found = None
    for at, key in windows:
        if at <= created_at + 1e-9:
            found = key
    return found


def window_mark(key, current_key):
    return dict(seg=None if key is None else key[3], grip_epoch=None if key is None else key[2],
                current=bool(key is not None and current_key is not None and list(key) == list(current_key)))


def peer_marks(peer_reports, windows, current_key):
    marks = {}
    for report in peer_reports or ():
        key = window_of(windows, report['created_at_sim_s'])
        marks[report['message_id']] = window_mark(key, current_key)
    return marks


def filter_actions(body):
    """Expose only protocol-feasible candidates; no RGB judgement or automatic vote.

    The model still decides whether its own RGB supports GO. Host validation still
    checks schema, image age, references and the current live window on release.
    """
    view = body['dialogue']
    kept = []
    for source in body.get('action_message_contract', {}).get('actions', ()):
        item = copy.deepcopy(source)
        kind = item['kind']
        if kind == 'continue':
            kept.append(item)
        elif kind == 'claim' and view['approved'] and not view['own_claim']:
            kept.append(item)
        elif (kind == 'approve_route' and body['robot_id'] == 'r2' and not view['approved']
              and view.get('proposal_message_id') is not None
              and any(r['message_id'] == view['proposal_message_id'] for r in call_reports(body))):
            kept.append(item)
        elif kind == 'route_vote' and view['key'] is not None:
            choices = (['GO'] if not view['own_go_sent'] else
                       ['ACK'] if not view['own_ack_sent'] and view['peer_go_ref'] is not None else [])
            if choices:
                item['choice'] = choices
                kept.append(item)
    if 'action_message_contract' in body:
        body['action_message_contract']['actions'] = kept


def apply(body, system, memory, *, commands=False):
    """Add memory fields to a post-projection body (in place) and return the extended system prompt.

    memory: dict(decisions=[records], windows=[(at, key)], commands=[entries] (optional)); now = body['sim_time_s'].
    """
    now = body['sim_time_s']
    current = (body.get('dialogue') or {}).get('key')
    log = decision_log(memory['decisions'], now, current_key=current)
    body['own_decision_log'] = log
    note = feedback(log)
    if note is not None:
        body['decision_feedback'] = note
    else:
        body.pop('decision_feedback', None)
    marks = peer_marks(body.get('peer_reports'), memory['windows'], current)
    for report in body.get('peer_reports') or ():
        report['sent_window'] = (window_mark(memory['sent_keys'].get(report['message_id']), current)
                                 if 'sent_keys' in memory else marks[report['message_id']])
        receipt = memory.get('receipts', {}).get(report['message_id'])
        report['window'] = window_mark(receipt['key'] if receipt else None, current)
        report['received_at_sim_s'] = receipt['at'] if receipt else None
        report['previous_segment'] = bool(
            current is not None and report['sent_window']['seg'] is not None and not report['sent_window']['current'])
    if commands:
        body['own_command_history'] = copy.deepcopy(memory['commands'])
    filter_actions(body)
    return system + PROMPT_ADD + PRIORITY_RULES


# ---- live collection (host side; no truth, only what the host decided/validated) -------------------------

class Memory:
    """Own outcomes, issued commands and committed message timing; no evaluator input."""

    def __init__(self):
        self.rejections = {}     # call_id -> dict(actor, did, seg, epoch, reason)
        self.commands = {rid: deque(maxlen=64) for rid in ('r1', 'r2', 'r3')}
        self.receipts = {rid: {} for rid in ('r1', 'r2', 'r3')}
        self.sent_keys = {}
        self.command_counts = {rid: 0 for rid in ('r1', 'r2', 'r3')}

    def reject(self, call_id, actor, value, error, context=None):
        did, seg, epoch = attempt_of((value or {}).get('action') if isinstance(value, dict) else None)
        key = (context or {}).get('view', {}).get('key')
        if did in ('GO', 'ACK') and seg is None and key is not None:
            seg, epoch = key[3], key[2]  # short vote_ref has no segment fields
        self.rejections[call_id] = dict(actor=actor, did=did, seg=seg, epoch=epoch,
                                       key=copy.deepcopy(key), reason=code_of(error))

    def receive(self, actor, envelope, now, key):
        self.receipts[actor][envelope['message_id']] = dict(at=float(now), key=copy.deepcopy(key))

    def command(self, rid, t, action):
        if rid in self.commands:
            from harness.zone_study_inputs import command_entry
            kind = action['kind']
            # Issued arguments only. Preserve direction and commanded servo values;
            # no backend acknowledgement, measured joint, or simulated outcome.
            allowed = ('forward', 'left', 'turn', 'duration_s', 'servo_id', 'pulse', 'pan_pulse', 'vx', 'vy')
            args = {k: copy.deepcopy(action[k]) for k in allowed if k in action}
            runs = self.commands[rid]
            if runs and runs[-1]['entry']['kind'] == kind and runs[-1]['entry']['arguments'] == args:
                runs[-1]['last_issued_at_sim_s'] = float(t)
                runs[-1]['count'] += 1
            else:
                self.command_counts[rid] += 1
                entry = command_entry(f'cmd_{rid}_{self.command_counts[rid]}', t, kind, args)
                runs.append(dict(entry=entry, last_issued_at_sim_s=float(t), count=1))

    def decisions(self, trial, actor):
        """Accepted/rejected decisions of this actor with their answer times."""
        rows = []
        for row in trial.dispatch_log:
            if row['actor'] != actor:
                continue
            did, seg, epoch = attempt_of(row['action'])
            key = trial.dialogue.captures.get(row['call_id'], {}).get('view', {}).get('key')
            rows.append(dict(call_id=row['call_id'], t=row['sim_s'], did=did, seg=seg, epoch=epoch, key=key,
                             accepted=bool(row['accepted']), reason=row['rejected_reason'] and code_of(row['rejected_reason'])))
        for call_id, r in self.rejections.items():
            entry = trial.scheduler.ledger.get(call_id)
            if r['actor'] == actor and entry and entry.get('finished_sim_s') is not None:
                rows.append(dict(call_id=call_id, t=entry['finished_sim_s'], did=r['did'], seg=r['seg'], epoch=r['epoch'], key=r['key'],
                                 accepted=False, reason=r['reason']))
        return rows

    def command_entries(self, actor, now, n=COMMAND_N):
        """Latest distinct own issued commands; repeated identical writes coalesced.

        duration_s is the requested duration, never an estimate of executed motion.
        """
        return [copy.deepcopy(r['entry']) for r in self.commands[actor]
                if r['entry']['issued_at_sim_s'] <= now + 1e-9][-n:]


def windows_of(dialogue):
    return [(e['at'], list(e['key'])) for e in dialogue.events if e['kind'] == 'epoch_open']


def collect(trial, memory, call, *, commands=False):
    """Memory dict for one live call, from host records only."""
    out = dict(decisions=memory.decisions(trial, call.actor), windows=windows_of(trial.dialogue))
    out['receipts'] = {mid: copy.deepcopy(r) for mid, r in memory.receipts[call.actor].items()
                       if r['at'] <= call.started_sim_s}
    out['sent_keys'] = copy.deepcopy(memory.sent_keys)
    if commands:
        out['commands'] = memory.command_entries(call.actor, call.started_sim_s)
    return out


# ---- bundle registration --------------------------------------------------------------------------------

def compose(bundle, option, vote_ref='off'):
    if option == 'off':
        return ()
    parent = bundle['execution_bundle_id']
    version = VERSIONS.get((option, vote_ref))
    if version is None or parent != PARENT:
        raise ValueError('LLM_MEMORY_REQUIRES_V324')
    bundle['llm_memory_parent'] = parent
    bundle['e2e_options']['llm_memory'] = option
    bundle['e2e_options']['vote_ref'] = vote_ref
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0', llm_memory_parameters=dict(log_n=LOG_N, command_n=COMMAND_N))
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json', 'harness/e2e_llm_memory.py')


def parent_for_validation(bundle):
    parent = bundle.get('llm_memory_parent')
    option = bundle['e2e_options'].get('llm_memory')
    version = VERSIONS.get((option, bundle['e2e_options'].get('vote_ref')))
    if (parent != PARENT or version is None or bundle['execution_bundle_id'] != f'e2e18-v{version}'
            or bundle.get('llm_memory_parameters') != dict(log_n=LOG_N, command_n=COMMAND_N)):
        raise ValueError('REGISTERED_LLM_MEMORY_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = parent
    old['e2e_options'].pop('llm_memory')
    old['e2e_options']['vote_ref'] = 'off'
    old.pop('llm_memory_parent')
    old.pop('llm_memory_parameters')
    return old
