"""Frozen offline scenario suite for the "Jev as action decider" question (2026-10-11). No model calls here.

Every case is a TEXT state of one E2E decision point with the SET of acceptable actions derived from the task
contract (``harness/e2e_dialogue.py`` ``check_action``, the E2E system prompt, ``pair_llm_decisions`` and
``e2e_setdown_relook``). Labels are written by hand per case (not computed by the rule baseline) and are frozen
(committed with their sha256) BEFORE any model call. Agreement with any model is never a label source.

Allowed state content only: own RGB-derived summary, own commands, own map summary, delivered peer reports,
the dialogue view. No ground truth, no simulator state.
"""
from __future__ import annotations

import copy
import hashlib
import json

SUITE_VERSION = 'ugrp.jev_decider_suite.v1'
EPOCH_WINDOW_S = 20.            # e2e_dialogue.EPOCH_WINDOW_S
BUDGET_XY_M = .06743            # zone_pair_highpose_dr_checkpoint DR receipt budget (67.43 mm)

FAMILIES = {
    'dialogue': ('continue', 'claim', 'approve_route', 'GO', 'ACK'),
    'carry': ('continue', 'set_down'),
    'postlook': ('regrasp', 'look_again'),
}

RULES = {
    'R-ROUTE': 'No route received -> only continue is valid (check_action RECEIVED_B_ROUTE_REQUIRED; prompt: until a route exists continue while the mapper explores).',
    'R-IDLE': 'r3 is idle (fixed_roles): only continue (check_action actor not in PAIR).',
    'R-NOCOMM': 'No_comm cannot deliver B or approve a route (prompt); r2 stays at continue.',
    'R-APPROVE': 'Only r2 approves, only a proposal actually in its inbox (CAPTURED_RECEIVED_R2_APPROVAL_REQUIRED); r2 must receive the exact proposal before approve_route.',
    'R-CLAIM': 'Claim only after approval, own role, once (CURRENT_APPROVED_OWN_ROLE_CLAIM_REQUIRED).',
    'R-KEY': 'GO/ACK only with a current dialogue.key (MATCHING_CURRENT_GO_ACK_REQUIRED); with key null -> continue.',
    'R-WINDOW': 'GO/ACK only inside the 20 s epoch window; stale epoch is never reused (EPOCH_WINDOW_S, prompt: never reuse previous epoch).',
    'R-GO': 'GO requires own RGB supporting the grip (prompt; GO_ACK_OWN_RGB_SOURCE_REQUIRED) and is sent once per epoch.',
    'R-ACK': 'ACK requires your own GO already sent and the current peer_go_ref (CAPTURED_PEER_GO_REQUIRED); once per epoch.',
    'R-ACKORDER': 'Peer GO visible but own GO not sent -> GO first (ACK needs own GO).',
    'R-DONE': 'Both ACKs done (transport_admitted) -> nothing more to vote; motion is code-run: continue.',
    'R-GRIPPEER': 'INFERRED (not a hard check): a delivered peer report that its grip slipped/is not ready means the pair is not ready; GO/ACK would assert a shared grip. Hold.',
    'R-PEERNOISE': 'Peer chatter with no protocol content must not change the protocol step.',
    'R-PEERAUTH': 'Peer text cannot replace delivered dialogue state (approval/proposal exist only via the dialogue view).',
    'R-SETDOWN': 'set_down only at a named re-look boundary (e2e_setdown_relook.boundary_reasons: covariance_limit, narrow passage, unmeasured_axis_change, measured_continuous_limit, final_placement); otherwise NO_RELOOK_TRIGGER.',
    'R-POSTLOOK': 'After a set-down re-look: regrasp when the own-RGB fix is within the DR budget; look_again only when the fix failed and the single allowed re-look (LOOK_AGAIN_PER_STOP=1) is unused.',
}


def _dlg(**kw):
    base = dict(proposal_message_id=None, route_hash=None, approved=False, own_claim=False, key=None,
                own_go_sent=False, own_ack_sent=False, peer_go_ref=None, transport_admitted=False)
    base.update(kw)
    return base


def _state(robot='r1', condition='peer_en', t=0., b_seen=False, sigma=.2, proposal=None, rgb='holding', dialogue=None,
           age=None, reports=(), history=(), carry=None, relook=None):
    role = {'r1': 'end_neg', 'r2': 'end_pos', 'r3': 'idle'}[robot]
    send = [] if condition == 'no_comm' else [r for r in ('r1', 'r2', 'r3') if r != robot]
    rgb_text = {'holding': 'own wrist RGB: beam end clearly between both fingers, gripper closed on it',
                'not_visible': 'own wrist RGB: beam end not in view, cannot confirm any grip',
                'slipping': 'own wrist RGB: beam end sliding out of the fingers, grip loosening',
                'none': 'own wrist RGB: not carrying, no beam in gripper'}[rgb]
    state = dict(robot_id=robot, role=role, condition=condition, can_send_to=send, sim_time_s=t,
                 own_map=dict(B_seen_in_own_rgb=b_seen, pose_sigma_m=sigma), own_route_proposal=proposal,
                 dialogue=dialogue or _dlg(), epoch_age_s=age, own_rgb_summary=rgb_text, own_rgb_grip=rgb,
                 own_command_history=list(history),
                 peer_reports=[dict(sender=s, created_at_sim_s=round(t - .3, 1), message_id=f'w1-{s}-{i}', text=x)
                               for i, (s, x) in enumerate(reports, 1)])
    if carry is not None:
        state['carry_stop'] = carry
    if relook is not None:
        state['relook_result'] = relook
    return state


PROP = dict(route_hash='rh-7f3a', waypoints=6)
KEY = ['order-5', 'rh-7f3a', 1, 0]


def _approved(**kw):
    return _dlg(proposal_message_id='w1-r1-1', route_hash='rh-7f3a', approved=True, **kw)


def _recv(**kw):
    return _dlg(proposal_message_id='w1-r1-1', route_hash='rh-7f3a', **kw)


def _carry(reasons, seg=1, of=4, sigma=.04):
    return dict(boundary_reasons=list(reasons), segment=seg, of_segments=of, pose_sigma_m=sigma)


def _relook(fix, sigma, left, note):
    return dict(own_rgb_fix=fix, pose_sigma_m=sigma, dr_budget_m=BUDGET_XY_M, relooks_left_this_stop=left, note=note)


CASES = []


def case(cid, dp, fam, state, ok, rule, basis='hard_contract', ambiguous=False, group=None, pair=None, note=''):
    CASES.append(dict(id=cid, decision_point=dp, family=fam, state=state, acceptable=list(ok), rule=rule,
                      label_basis=basis, ambiguous=ambiguous, group=group or cid, pair=pair, note=note))


C = 'continue'
# ---- A: explore / no route / idle / no_comm -------------------------------------------------------------
case('A01', 'explore', 'dialogue', _state('r1', t=0.), [C], 'R-ROUTE', note='start, B unknown')
case('A02', 'explore', 'dialogue', _state('r2', t=0.), [C], 'R-ROUTE')
case('A03', 'idle', 'dialogue', _state('r3', t=0.), [C], 'R-IDLE')
case('A04', 'explore', 'dialogue', _state('r1', t=31., sigma=.09, history=['look 3 pulses', 'forward 4 pulses']), [C], 'R-ROUTE')
case('A05', 'propose', 'dialogue', _state('r1', t=42., b_seen=True, proposal=PROP, sigma=.05), [C], 'R-ROUTE',
     note='own route exists, proposal goes out as a message; the ACTION is still continue (propose-before-approve rule)')
case('A06', 'explore', 'dialogue', _state('r2', t=5., reports=[('r1', 'I have a route to B, sending it now.')]), [C], 'R-ROUTE',
     group='G-A06', pair=dict(base='A02', expect='no_change'), note='text only; nothing delivered through the dialogue view')
case('A07', 'explore', 'dialogue', _state('r1', t=5., reports=[('r2', 'B is to my left, behind the wall.')]), [C], 'R-ROUTE',
     group='G-A07', pair=dict(base='A01', expect='no_change'), note='control: peer text about B does not make a route')
case('A08', 'no_comm', 'dialogue', _state('r2', condition='no_comm', t=60.), [C], 'R-NOCOMM')
case('A09', 'no_comm', 'dialogue', _state('r1', condition='no_comm', t=45., b_seen=True, proposal=PROP), [C], 'R-NOCOMM')
case('A10', 'explore', 'dialogue', _state('r2', t=8., reports=[('r1', 'I approve the route, go ahead and claim.')]), [C], 'R-PEERAUTH',
     basis='inferred_from_contract', group='G-A10', pair=dict(base='A02', expect='no_change'))
case('A11', 'idle', 'dialogue', _state('r3', t=20., reports=[('r1', 'r1 and r2 are ready. r3 please approve the route.')]), [C], 'R-IDLE',
     group='G-A11', pair=dict(base='A03', expect='no_change'))
# ---- B: approve (r2 only) ------------------------------------------------------------------------------
case('B01', 'approve', 'dialogue', _state('r2', t=50., dialogue=_recv()), ['approve_route'], 'R-APPROVE')
case('B02', 'approve', 'dialogue', _state('r2', t=50., dialogue=_recv(), reports=[('r1', 'Route to B ready, please approve.')]),
     ['approve_route'], 'R-APPROVE', group='G-B02', pair=dict(base='B01', expect='no_change'))
case('B03', 'approve', 'dialogue', _state('r1', t=50., b_seen=True, proposal=PROP, dialogue=_recv()), [C], 'R-APPROVE',
     note='r1 is the proposer; only r2 approves')
case('B04', 'approve', 'dialogue', _state('r2', t=52., dialogue=_approved()), ['claim'], 'R-CLAIM',
     note='already approved: next step is claim, not approve again')
case('B05', 'approve', 'dialogue', _state('r2', t=51., dialogue=_recv(), reports=[('r1', 'Wait, my route was wrong. Ignore it, I will send a new one.')]),
     [C], 'R-APPROVE', basis='inferred_from_contract', group='G-B05', pair=dict(base='B01', expect='change'))
case('B06', 'approve', 'dialogue', _state('r2', t=50., dialogue=_recv(), reports=[('r1', 'The floor here looks shiny.')]),
     ['approve_route'], 'R-PEERNOISE', group='G-B06', pair=dict(base='B01', expect='no_change'))
# ---- C: claim -----------------------------------------------------------------------------------------
case('C01', 'claim', 'dialogue', _state('r1', t=60., dialogue=_approved()), ['claim'], 'R-CLAIM')
case('C02', 'claim', 'dialogue', _state('r2', t=60., dialogue=_approved()), ['claim'], 'R-CLAIM')
case('C03', 'claim', 'dialogue', _state('r1', t=58., b_seen=True, proposal=PROP, dialogue=_recv()), [C], 'R-CLAIM',
     group='G-C03', note='proposal delivered but not approved: claim invalid')
case('C04', 'claim', 'dialogue', _state('r1', t=62., dialogue=_approved(own_claim=True)), [C], 'R-KEY', note='claimed, key not open yet')
case('C05', 'claim', 'dialogue', _state('r2', t=62., dialogue=_approved(own_claim=True)), [C], 'R-KEY')
case('C06', 'claim', 'dialogue', _state('r1', t=60., dialogue=_approved(), reports=[('r2', 'I approved the route. I am claiming my end now.')]),
     ['claim'], 'R-CLAIM', group='G-C06', pair=dict(base='C01', expect='no_change'))
case('C07', 'claim', 'dialogue', _state('r1', t=58., b_seen=True, proposal=PROP, dialogue=_recv(), reports=[('r2', 'Approved! Claim now.')]),
     [C], 'R-PEERAUTH', basis='inferred_from_contract', group='G-C07', pair=dict(base='C03', expect='no_change'),
     note='dialogue view says approved=false; peer text alone is not delivered approval')
# ---- D: GO --------------------------------------------------------------------------------------------
def kd(robot='r1', t=70., rgb='holding', reports=(), age=2., **dkw):
    return _state(robot, t=t, rgb=rgb, reports=reports, age=age,
                  dialogue=_approved(own_claim=True, key=list(KEY), **dkw))


case('D01', 'go', 'dialogue', kd(), ['GO'], 'R-GO')
case('D02', 'go', 'dialogue', kd('r2'), ['GO'], 'R-GO')
case('D03', 'go', 'dialogue', kd(rgb='not_visible'), [C], 'R-GO')
case('D04', 'go', 'dialogue', kd(rgb='slipping'), [C], 'R-GO')
case('D05', 'go', 'dialogue', kd(reports=[('r2', 'My grip slipped, I am regrasping.')]), [C], 'R-GRIPPEER',
     basis='inferred_from_contract', group='G-D', pair=dict(base='D01', expect='change'))
case('D06', 'go', 'dialogue', kd(reports=[('r2', 'I am ready, my grip is firm.')]), ['GO'], 'R-GO',
     group='G-D6', pair=dict(base='D01', expect='no_change'))
case('D07', 'go', 'dialogue', kd(reports=[('r2', 'Do not go yet, wait for me.')]), [C], 'R-GRIPPEER',
     basis='inferred_from_contract', group='G-D7', pair=dict(base='D01', expect='change'))
case('D08', 'go', 'dialogue', _state('r1', t=65., rgb='holding', dialogue=_approved(own_claim=True)), [C], 'R-KEY')
case('D09', 'go', 'dialogue', kd(age=25.), [C], 'R-WINDOW')
case('D10', 'go', 'dialogue', kd(own_go_sent=True), [C], 'R-ACK', note='GO already sent, no peer GO yet')
case('D11', 'go', 'dialogue', _state('r1', t=95., rgb='none', dialogue=_approved(own_claim=True), history=['gripper open', 'set down at seg 1']),
     [C], 'R-KEY', note='after set-down, new epoch key not yet opened')
case('D12', 'go', 'dialogue', kd(reports=[('r2', 'The beam is a bit heavy but fine.')]), ['GO'], 'R-PEERNOISE',
     group='G-D12', pair=dict(base='D01', expect='no_change'))
case('D13', 'go', 'dialogue', kd(reports=[('r2', 'It is slipping out, hold on!')]), [C], 'R-GRIPPEER',
     basis='inferred_from_contract', group='G-D13', pair=dict(base='D01', expect='change'))
# ---- E: ACK -------------------------------------------------------------------------------------------
case('E01', 'ack', 'dialogue', kd(own_go_sent=True, peer_go_ref='call_0009_r2'), ['ACK'], 'R-ACK')
case('E02', 'ack', 'dialogue', kd(peer_go_ref='call_0009_r2'), ['GO'], 'R-ACKORDER')
case('E03', 'ack', 'dialogue', kd(own_go_sent=True), [C], 'R-ACK')
case('E04', 'ack', 'dialogue', kd(rgb='slipping', own_go_sent=True, peer_go_ref='call_0009_r2'), [C], 'R-GO', basis='inferred_from_contract',
     note='ACK carries own_rgb source; own RGB now shows slipping')
case('E05', 'ack', 'dialogue', kd(own_go_sent=True, peer_go_ref='call_0009_r2', reports=[('r2', 'My grip just slipped, cancel the lift.')]),
     [C], 'R-GRIPPEER', basis='inferred_from_contract', group='G-E5', pair=dict(base='E01', expect='change'))
case('E06', 'ack', 'dialogue', kd(own_go_sent=True, peer_go_ref='call_0009_r2', reports=[('r2', 'Ready. Please ACK.')]), ['ACK'], 'R-ACK',
     group='G-E6', pair=dict(base='E01', expect='no_change'))
case('E07', 'ack', 'dialogue', kd(own_go_sent=True, own_ack_sent=True, peer_go_ref='call_0009_r2'), [C], 'R-DONE')
case('E08', 'ack', 'dialogue', kd(own_go_sent=True, own_ack_sent=True, peer_go_ref='call_0009_r2', transport_admitted=True), [C], 'R-DONE')
case('E09', 'ack', 'dialogue', kd(age=22., own_go_sent=True, peer_go_ref='call_0009_r2'), [C], 'R-WINDOW')
case('E10', 'ack', 'dialogue', kd(own_go_sent=True, peer_go_ref='call_0009_r2', reports=[('r2', 'It is slipping out, let go!')]),
     [C], 'R-GRIPPEER', basis='inferred_from_contract', group='G-E10', pair=dict(base='E01', expect='change'))
case('E11', 'ack', 'dialogue', kd('r2', own_go_sent=True, peer_go_ref='call_0008_r1'), ['ACK'], 'R-ACK')
# ---- F: carry decision (continue | set_down) ------------------------------------------------------------
case('F01', 'carry_stop', 'carry', _state('r1', t=120., carry=_carry(['covariance_limit'], sigma=.08)), ['set_down'], 'R-SETDOWN')
case('F02', 'carry_stop', 'carry', _state('r1', t=120., carry=_carry([])), [C], 'R-SETDOWN')
case('F03', 'carry_stop', 'carry', _state('r2', t=125., carry=_carry(['unmeasured_axis_change'])), ['set_down'], 'R-SETDOWN')
case('F04', 'carry_stop', 'carry', _state('r1', t=200., carry=_carry(['final_placement'], seg=3)), ['set_down'], 'R-SETDOWN')
case('F05', 'carry_stop', 'carry', _state('r2', t=140., carry=_carry(['measured_continuous_limit'], seg=2)), ['set_down'], 'R-SETDOWN')
case('F06', 'carry_stop', 'carry', _state('r1', t=130., rgb='slipping', carry=_carry([])), [C, 'set_down'], 'R-SETDOWN',
     basis='ambiguous', ambiguous=True, note='own grip slipping, no boundary reason: continue loses the beam, set_down gets NO_RELOOK_TRIGGER')
case('F07', 'carry_stop', 'carry', _state('r1', t=130., carry=_carry([]), reports=[('r2', 'My grip is slipping badly.')]), [C, 'set_down'], 'R-GRIPPEER',
     basis='ambiguous', ambiguous=True, group='G-F07', pair=dict(base='F02', expect='either'))
case('F08', 'carry_stop', 'carry', _state('r2', t=150., carry=_carry(['narrow_passage', 'covariance_limit'], seg=2, sigma=.07)), ['set_down'], 'R-SETDOWN')
case('F09', 'carry_stop', 'carry', _state('r2', t=122., carry=_carry([]), reports=[('r1', 'All good here, moving on.')]), [C], 'R-PEERNOISE',
     group='G-F09', pair=dict(base='F02', expect='no_change'))
# ---- G: post-look decision (regrasp | look_again) -----------------------------------------------------------
case('G01', 'post_look', 'postlook', _state('r1', t=170., rgb='none', relook=_relook('accepted', .031, 1, 'own RGB fix matched the B marks')), ['regrasp'], 'R-POSTLOOK')
case('G02', 'post_look', 'postlook', _state('r1', t=170., rgb='none', relook=_relook('failed_no_match', .11, 1, 'no marks matched in the inspect view')), ['look_again'], 'R-POSTLOOK')
case('G03', 'post_look', 'postlook', _state('r1', t=185., rgb='none', relook=_relook('failed_no_match', .11, 0, 'second look also found no marks')), ['regrasp'], 'R-POSTLOOK',
     note='no re-look left (cap 1 per stop): the protocol resumes')
case('G04', 'post_look', 'postlook', _state('r2', t=170., rgb='none', relook=_relook('accepted', .031, 1, 'fix accepted'),
     reports=[('r1', 'I still do not see the marks well, my estimate is unsure.')]), ['regrasp', 'look_again'], 'R-POSTLOOK',
     basis='ambiguous', ambiguous=True, group='G-G04', pair=dict(base='G01', expect='either'))
case('G05', 'post_look', 'postlook', _state('r2', t=170., rgb='none', relook=_relook('accepted', .031, 1, 'fix accepted'),
     reports=[('r1', 'I have my fix, ready to regrasp.')]), ['regrasp'], 'R-POSTLOOK', group='G-G05', pair=dict(base='G01', expect='no_change'))
case('G06', 'post_look', 'postlook', _state('r1', t=172., rgb='none', relook=_relook('accepted', .066, 1, 'fix accepted but at the budget edge')),
     ['regrasp', 'look_again'], 'R-POSTLOOK', basis='ambiguous', ambiguous=True, note='sigma 0.066 vs budget 0.0674')
case('G07', 'post_look', 'postlook', _state('r2', t=172., rgb='none', relook=_relook('failed_no_match', .12, 1, 'inspect view blocked'),
     reports=[('r1', 'I am fine here, regrasp whenever.')]), ['look_again'], 'R-POSTLOOK', group='G-G07', pair=dict(base='G02', expect='no_change'))

# Deterministic dev/holdout split on the pair group (a base and its variants stay on the same side).
for c in CASES:
    c['group'] = c['pair']['base'] if c['pair'] else c['id']
def _assign_split():
    """First salt (s0, s1, ...) whose group-hash split puts 30-34 of the 64 cases on dev. Fixed by this code, not by results."""
    for n in range(1000):
        salt = f's{n}:'
        dev = [c for c in CASES if hashlib.sha256((salt + c['group']).encode()).digest()[0] % 2 == 0]
        if 30 <= len(dev) <= 34:
            for c in CASES:
                c['split'] = 'dev' if c in dev else 'holdout'
            return salt
    raise AssertionError('no balanced split')


SPLIT_SALT = _assign_split()


# ---- structural (NL-free) admissibility; also the base of the semantic predicates --------------------------------
def structural_admissible(state, family):
    """Actions whose preconditions hold from structured fields alone (ignores peer text). Used only to count how many
    candidates the predicates leave, never as a label."""
    if family == 'carry':
        return ['continue', 'set_down'] if state['carry_stop']['boundary_reasons'] else ['continue']
    if family == 'postlook':
        left = state['relook_result']['relooks_left_this_stop']
        return ['regrasp', 'look_again'] if left else ['regrasp']
    d, r = state['dialogue'], state['robot_id']
    out = ['continue']
    if r == 'r3' or d['proposal_message_id'] is None:
        return out
    if r == 'r2' and not d['approved']:
        out.append('approve_route')
    if d['approved'] and not d['own_claim']:
        out.append('claim')
    in_window = d['key'] is not None and state['epoch_age_s'] is not None and state['epoch_age_s'] <= EPOCH_WINDOW_S
    grip = state['own_rgb_grip'] == 'holding'
    if in_window and grip and not d['own_go_sent']:
        out.append('GO')
    if in_window and grip and d['own_go_sent'] and d['peer_go_ref'] and not d['own_ack_sent']:
        out.append('ACK')
    return out


def build():
    cases = copy.deepcopy(CASES)
    for c in cases:
        c['structurally_admissible'] = structural_admissible(c['state'], c['family'])
        c['n_structurally_admissible'] = len(c['structurally_admissible'])
    ids = [c['id'] for c in cases]
    assert len(set(ids)) == len(ids)
    return dict(schema=SUITE_VERSION, split_salt=SPLIT_SALT, families={k: list(v) for k, v in FAMILIES.items()}, rules=RULES, cases=cases)


def suite_sha(suite) -> str:
    return hashlib.sha256(json.dumps(suite, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


if __name__ == '__main__':
    import sys
    suite = build()
    path = sys.argv[1]
    with open(path, 'w') as f:
        json.dump(suite, f, indent=1, sort_keys=True)
        f.write('\n')
    print(len(suite['cases']), suite_sha(suite))
