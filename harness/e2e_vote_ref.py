"""Short GO/ACK vote reference (vote_ref_v1, default off).

Why: in the e2e18 live calls the route_vote action repeats order_id, the 64-char
route_hash, grip_epoch, seg and peer_go_ref; its output is ~138 tokens (median
latency 5.7 s, max 14 s) and Gemma latency tracks output tokens (Spearman 0.65).
Same pattern as route_handle typed_ref_v1: the model chooses `choice` and echoes the
short current vote-window id `dialogue.vote_ref`; the host expands it to the full
closed route_vote from the view captured at call time (no new information, no truth).
`check_action` then validates the expanded action exactly as before, so a wrong ref,
a closed window or a stale epoch is rejected (the response becomes `continue`).
Natural-language messages are untouched (research variable).
"""
import copy
import hashlib
import json
from harness import e2e_own_inputs as own

OPTIONS = ('v1',)
VERSIONS = {'e2e18-v313': 314, 'e2e18-v312': 315}
PROMPT_OLD = ('GO/ACK use the exact current dialogue.key [order_id,route_hash,grip_epoch,seg]. '
              'GO requires own RGB supporting the grip; ACK requires your GO and the current peer_go_ref.')
PROMPT_NEW = ('GO/ACK are typed votes: action={"kind":"route_vote","choice":"GO"|"ACK","vote_ref":dialogue.vote_ref} '
              'with exactly these three fields; copy dialogue.vote_ref and only while dialogue.key is not null. '
              'The host fills order, route, epoch, segment and the peer GO from the current window. '
              'GO requires own RGB supporting the grip; ACK requires your GO and a visible dialogue.peer_go_ref.')


def ref_for(key):
    """Short id of one vote window (order, route, grip epoch, segment)."""
    return 'v' + hashlib.sha256(json.dumps(list(key), separators=(',', ':')).encode()).hexdigest()[:6]


def enabled(dialogue):
    return getattr(dialogue, 'vote_ref', 'off') != 'off'


def expand(dialogue, action, context):
    """Full route_vote from `{kind,choice,vote_ref}`; other actions pass through."""
    if not enabled(dialogue) or not isinstance(action, dict) or action.get('kind') != 'route_vote':
        return action
    if dialogue.vote_ref not in OPTIONS:
        raise own.ContractViolation('UNKNOWN_VOTE_REF')
    own.closed(action, ('kind', 'choice', 'vote_ref'), 'VOTE_REF')
    view = context['view']
    if view.get('key') is None or dialogue.key is None or list(dialogue.key) != view['key']:
        raise own.ContractViolation('VOTE_WINDOW_CLOSED')
    if action['vote_ref'] != view.get('vote_ref') or action['vote_ref'] != ref_for(view['key']):
        raise own.ContractViolation('VOTE_REF_MISMATCH')
    choice = action['choice']
    if choice not in ('GO', 'ACK'):
        raise own.ContractViolation('MATCHING_CURRENT_GO_ACK_REQUIRED')
    order_id, route_hash, grip_epoch, seg = view['key']
    return dict(kind='route_vote', choice=choice, order_id=order_id, route_hash=route_hash,
                grip_epoch=grip_epoch, seg=seg, peer_go_ref=view['peer_go_ref'] if choice == 'ACK' else None)


def view_field(dialogue, key):
    return dict(vote_ref=ref_for(key)) if enabled(dialogue) and key else {}


def prompt(body, system):
    if PROMPT_OLD not in system:
        raise ValueError('VOTE_REF_PROMPT_ANCHOR_MISSING')
    for item in body['action_message_contract']['actions']:
        if item.get('kind') == 'route_vote':
            item.clear()
            item.update(kind='route_vote', choice=['GO', 'ACK'], vote_ref='<dialogue.vote_ref>')
    return system.replace(PROMPT_OLD, PROMPT_NEW)


def compose(bundle, option):
    if option == 'off':
        return ()
    parent = bundle['execution_bundle_id']
    if option not in OPTIONS or parent not in VERSIONS:
        raise ValueError('VOTE_REF_REQUIRES_V313_OR_V312')
    version = VERSIONS[parent]
    bundle['vote_ref_parent'] = parent
    bundle['e2e_options']['vote_ref'] = option
    bundle.update(schema=f'ugrp.e2e_ownmap_live.v{version}', execution_bundle_id=f'e2e18-v{version}',
                  workflow_version=f'7.{version-107}.0')
    return (f'configs/simulation_workflows.d/e2e18_v{version}.json',)


def parent_for_validation(bundle):
    parent = bundle.get('vote_ref_parent')
    if (parent not in VERSIONS or bundle['execution_bundle_id'] != f'e2e18-v{VERSIONS[parent]}'
            or bundle['e2e_options'].get('vote_ref') not in OPTIONS):
        raise ValueError('REGISTERED_VOTE_REF_REQUIRED')
    old = copy.deepcopy(bundle)
    old['execution_bundle_id'] = parent
    old['e2e_options'].pop('vote_ref')
    old.pop('vote_ref_parent')
    return old
