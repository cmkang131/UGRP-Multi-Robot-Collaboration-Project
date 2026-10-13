"""Safety receipts travel as visible English text on the actual NL channel.

No extra envelope fields. Lossless sentence encoding is for the executor's
route/handshake validation, not semantic voting on arbitrary partner prose.
"""
import copy,re,json
from harness.zone_study_contract import digest


def rgb(ref):
    return f"{ref['robot_id']} frame {ref['frame_id']} at {ref['t_sim']} image {ref['sha256']}"


def parse_rgb(text):
    match=re.fullmatch(r'(r[123]) frame (\d+) at ([\d.eE+-]+) image ([a-f0-9]{64})',text)
    if not match:raise ValueError('SAFETY_RGB_SENTENCE_REQUIRED')
    r,f,t,h=match.groups();return dict(robot_id=r,frame_id=int(f),t_sim=json.loads(t),sha256=h)


def route_text(contract):
    r=contract['route']
    points='; '.join(f'{x},{y}' for x,y in r['waypoints'])
    refs='; '.join(rgb(v) for v in r['B_rgb_sources'])
    text=f"My route {r['route_hash']} uses map {r['map_version']} frame {r['frame_id']}. Waypoints are {points}. I saw B in {refs}."
    if 'carrier_basis' in r:
        b=r['carrier_basis'];text+=f" Beam basis is {b['yaw_rad']} at {b['center_m'][0]},{b['center_m'][1]}, from {rgb(b['rgb'])}."
    return text


def read_route(text):
    match=re.search(r'My route ([a-f0-9]{64}) uses map (\d+) frame (\d+)\. Waypoints are (.*?)\. I saw B in (.*?)\.(?: Beam basis is (.*?) at (.*?),(.*?), from (.*?)\.)?$',text)
    if not match:return None
    h,m,f,points,refs,y,x,z,ref=match.groups()
    r=dict(schema='ugrp.e2e_route_message.v1',robot_id='r1',frame_id=int(f),map_version=int(m),
        B_rgb_sources=[parse_rgb(t) for t in refs.split('; ')],waypoints=[[json.loads(v) for v in t.split(',')] for t in points.split('; ')],route_hash=h)
    if y is not None:
        r['schema']='ugrp.e2e_route_message.v2';r['carrier_basis']=dict(yaw_rad=json.loads(y),center_m=[json.loads(x),json.loads(z)],rgb=parse_rgb(ref),rule='toward_B_projection_v1')
    from harness.e2e_dialogue import route_contract
    return route_contract(dict(kind='OwnRoute',route=r,source_message_id=None))


def vote_text(action,call_id):
    if action.get('kind')!='route_vote':return ''
    return f" Safety {action['choice']} for {action['order_id']} route {action['route_hash']} epoch {action['grip_epoch']} leg {action['seg']}, request {call_id}."


def read_vote(text):
    m=re.search(r' Safety (GO|ACK) for ([\w-]+) route ([a-f0-9]{64}) epoch (\d+) leg (\d+), request ([\w:-]+)\.',text)
    if not m:return None
    choice,order,route,epoch,seg,cid=m.groups()
    return dict(choice=choice,key=(order,route,int(epoch),int(seg)),call_id=cid)


def delivered(dialogue,actor,cid):
    return (actor,cid) in getattr(dialogue,'task_received_votes',{})


def allowed(dialogue,key):
    if not getattr(dialogue.trial,'task_planner',None):return True
    for rid,partner in (('r1','r2'),('r2','r1')):
        for choice in ('GO','ACK'):
            peer=dialogue.votes.get(partner,{}).get(choice)
            received=getattr(dialogue,'task_received_votes',{}).get((rid,peer['call_id'])) if peer else None
            if not received or received['key']!=tuple(key) or received['choice']!=choice:return False
    return True


def status_text(action):
    if action.get('kind')=='approve_route':return f" I approved route {action['route_hash']} after receiving its proposal."
    if action.get('kind')=='claim':return f" I reserved {action['role']} for {action['order_id']} in {action['destination_zone']}."
    return ''


def read_status(text):
    m=re.search(r' I approved route ([a-f0-9]{64}) after receiving its proposal\.',text)
    if m:return dict(kind='approval',route_hash=m[1])
    m=re.search(r' I reserved (end_neg|end_pos) for ([\w-]+) in ([\w-]+)\.',text)
    return dict(kind='claim',role=m[1],order=m[2],zone=m[3]) if m else None


def approval_visible(dialogue,actor):
    if not getattr(dialogue.trial,'task_planner',None) or actor=='r2':return True
    route=dialogue.proposal['route']['route_hash'] if dialogue.proposal else None
    return any(row['sender']=='r2' and row['status']==dict(kind='approval',route_hash=route)
               for row in getattr(dialogue,'task_received_status',{}).get(actor,[]))


def compile_messages(messages):
    """Count every actual text utterance before scheduler admission/billing."""
    result=[]
    for message in messages:
        contract=message.get('contract')
        if contract is None:
            result.append(message);continue
        base={k:copy.deepcopy(v) for k,v in message.items() if k not in ('contract','text')}
        result.append(dict(base,text=message['text']))
        text=route_text(contract);parts=[text[i:i+440] for i in range(0,len(text),440)]
        for i,part in enumerate(parts,1):
            row=dict(base,text=f"Route fragment {contract['route']['route_hash']} part {i}/{len(parts)}: {part}")
            # Sender-local proof only. relay removes this before the channel.
            if i==len(parts):row['contract']=copy.deepcopy(contract)
            result.append(row)
    return result


def receive_route(dialogue,actor,envelope):
    text=envelope['body'].get('text','')
    m=re.fullmatch(r'Route fragment ([a-f0-9]{64}) part (\d+)/(\d+): ([\s\S]*)',text)
    if not m:return read_route(text)
    h,i,n,part=m.groups();i,n=int(i),int(n)
    if not 1<=i<=n<=16:raise ValueError('INVALID_ROUTE_FRAGMENT_COUNT')
    if not hasattr(dialogue,'task_route_fragments'):dialogue.task_route_fragments={}
    key=(actor,envelope['sender'],h)
    rows=dialogue.task_route_fragments.setdefault(key,{})
    rows[i]=(n,part)
    if len(rows)!=n:return None
    if any(rows[j][0]!=n for j in range(1,n+1)):raise ValueError('INCONSISTENT_ROUTE_FRAGMENTS')
    # Channel delivers each sender's sequential batch in send order.
    if i!=n:raise ValueError('OUT_OF_ORDER_ROUTE_FRAGMENT_BATCH')
    value=read_route(''.join(rows[j][1] for j in range(1,n+1)))
    if value is None or value['route']['route_hash']!=h:raise ValueError('ROUTE_FRAGMENT_HASH_MISMATCH')
    return value
