"""Same validated route retransmissions retain the actual delivered agreement."""
OPTION='same_route_v1'


def origin(dialogue,contract,new_origin):
    p=dialogue.proposal
    if (getattr(dialogue,'protocol_idempotency','off')==OPTION and p is not None and
        contract['source_message_id'] is None and p['route']==contract['route']):
        return p['origin']
    return new_origin


def resets(dialogue,new_origin):
    return not (getattr(dialogue,'protocol_idempotency','off')==OPTION and new_origin==dialogue.latest_origin)
