"""Frozen coordinator public-cost fallback, copied without evaluator/generator.
Source: tasklevel/benchmark.py (2026-10-13), public algebra and report parser.
Synthetic closed-world policy; not a learned model or physical cost estimate.
"""
import re

SPECS={
'next':dict(worlds=['cyan_claimed','red_claimed'],task='Choose the next solo order; an order already claimed by the partner wastes duplicate effort.',actions={'cyan':'Take the cyan order','red':'Take the red order','beam':'Request a partner for the beam next'},formula='cyan cost=c_cyan + duplicate if partner claims cyan; red cost=c_red + duplicate if partner claims red; beam cost=c_beam.'),
'pair':dict(worlds=['available','unavailable'],task='Choose whether to pair for the two-robot beam or keep the robot on solo work. Never lift a beam alone.',actions={'pair_now':'Request and reserve partner r2 for beam_1','solo_first':'Do solo order first, then revisit beam','recruit_r3':'Request replacement partner r3'},formula='pair_now cost=c_pair if r2 available, otherwise c_pair+delay; solo_first cost=c_solo; recruit_r3 cost=c_recruit.'),
'help':dict(worlds=['needs_help','withdrawn'],task='Decide whether to accept the standing beam help request, reject it for own solo work, or verify it.',actions={'accept':'Accept the beam help request','decline':'Decline and continue own solo order','verify':'Ask partner to reconfirm before committing'},formula='accept cost=c_accept if request is active (needs_help), otherwise c_accept+wasted; decline cost=c_decline+unserved if needs_help, otherwise c_decline; verify cost=c_verify.'),
'wait':dict(worlds=['near','late'],task='The expected beam partner has not arrived. Choose waiting, replacement, or doing a short solo order first.',actions={'wait':'Wait for assigned partner','reassign':'Ask r3 to replace the assigned partner','solo':'Suspend rendezvous and do a solo order'},formula='wait cost=c_wait if partner near, otherwise c_wait+delay; reassign cost=c_reassign; solo cost=c_solo.'),
'yield':dict(worlds=['committed','yielding'],task='Negotiate access to the single-lane corridor_1. Choices are guarded intentions; code still enforces collision safety.',actions={'yield':'Yield into bay_1','proceed':'Request passage and proceed only after local safety clearance','negotiate':'Pause and negotiate an explicit turn'},formula='yield cost=c_yield plus mutual_yield if partner is already yielding; proceed cost=c_proceed plus conflict if partner committed to crossing; negotiate cost=c_negotiate.'),
'route':dict(worlds=['blocked','clear'],task='Select route to the destination. Static map has both doors; current blockage may differ.',actions={'narrow':'Use door_narrow subject to local safety check','wide':'Use door_wide detour','inspect':'Inspect door_narrow before route commitment'},formula='narrow cost=c_narrow + failed_trip if door_narrow blocked; wide cost=c_wide; inspect cost=c_inspect.'),
'correct':dict(worlds=['initial','new','dropped'],task='Choose where to search next for the target. Initial order-sheet location is not a current observation. Never mark delivered based only on a message.',actions={'initial':'Search initial order-sheet slot','new':'Search reported alternative slot P1-3','recover':'Inspect pickup floor for the dropped target'},formula='Each action costs its corresponding c_initial/c_new/c_recover plus miss if it does not match the current state: initial->initial, new->new, recover->dropped.'),
'relation':dict(worlds=['beam_blocks','robot_blocks','clear'],task='Choose first task to expose can_1 west approach. A beam and a robot can cause different obstructions; moving a beam needs two robots.',actions={'rotate':'Request two-robot beam rotation before retrieving can_1','retreat':'Ask obstructing partner to back away before retrieving can_1','retrieve':'Retrieve can_1 via its west approach'},formula='Each action costs its corresponding c_rotate/c_retreat/c_retrieve plus miss if it does not match obstruction: rotate->beam_blocks, retreat->robot_blocks, retrieve->clear.')}

def costs(domain,p,w):
 if domain=='next':return {'cyan':p['c_cyan']+p['duplicate']*(w=='cyan_claimed'),'red':p['c_red']+p['duplicate']*(w=='red_claimed'),'beam':p['c_beam']}
 if domain=='pair':return {'pair_now':p['c_pair']+p['delay']*(w=='unavailable'),'solo_first':p['c_solo'],'recruit_r3':p['c_recruit']}
 if domain=='help':return {'accept':p['c_accept']+p['wasted']*(w=='withdrawn'),'decline':p['c_decline']+p['unserved']*(w=='needs_help'),'verify':p['c_verify']}
 if domain=='wait':return {'wait':p['c_wait']+p['delay']*(w=='late'),'reassign':p['c_reassign'],'solo':p['c_solo']}
 if domain=='yield':return {'yield':p['c_yield']+p['mutual_yield']*(w=='yielding'),'proceed':p['c_proceed']+p['conflict']*(w=='committed'),'negotiate':p['c_negotiate']}
 if domain=='route':return {'narrow':p['c_narrow']+p['failed_trip']*(w=='blocked'),'wide':p['c_wide'],'inspect':p['c_inspect']}
 mapping={'correct':{'initial':'initial','new':'new','recover':'dropped'},'relation':{'rotate':'beam_blocks','retreat':'robot_blocks','retrieve':'clear'}}[domain]
 return {a:p['c_'+a]+p['miss']*(w!=target) for a,target in mapping.items()}

def domain_of(view):return next(d for d,s in SPECS.items() if s['task']==view['task'])

def extract_fixed(d,b):
 if d=='next':return ['cyan_claimed' if b.get('item')=='cyan' else 'red_claimed']
 if d=='pair':return ['available' if b['act']=='accept' else 'unavailable']
 if d=='help':return ['needs_help' if b['act']=='request' else 'withdrawn']
 if d=='wait':return ['near' if b['state']=='present' else 'late']
 if d=='yield':return ['yielding' if b['act']=='yield' else 'committed']
 if d=='route':return [b['state']]
 if d=='correct':return ['dropped' if b['state']=='absent' else 'new' if b.get('location_ref')=='P1-3' else 'initial']
 return ['clear'] if b['state']=='clear' else ['beam_blocks','robot_blocks']

def extract_english(d,text):
 t=text.lower()
 if d=='next':
  m=re.search(r'(?:claimed the|handling) (cyan|red)|the (cyan|red) job is mine',t)
  return [(next(g for g in m.groups() if g))+'_claimed'] if m else []
 if d=='pair':
  if re.search(r'unavailable|cannot join|cannot be your',t):return ['unavailable']
  if re.search(r'available|can join|can be your',t):return ['available']
 if d=='help':
  if re.search(r'withdraw|no longer need|cancel my',t):return ['withdrawn']
  if re.search(r'still active|still need|nobody at the other',t):return ['needs_help']
 if d=='wait':
  if re.search(r'delayed|stuck|not arrive shortly|still far away',t):return ['late']
  if re.search(r'near the beam|around the corner|almost at the beam',t):return ['near']
 if d=='yield':
  if re.search(r'not yielding|already inside|have entered',t):return ['committed']
  if re.search(r'yielding in|pulled into|not entering|giving you the turn',t):return ['yielding']
 if d=='route':
  if re.search(r'not blocked|nothing is obstructing|door_narrow clear',t):return ['clear']
  if re.search(r'blocked|no way through|not clear',t):return ['blocked']
 if d=='correct':
  if re.search(r'fell|dropped|down on.*floor',t):return ['dropped']
  if 'p1-3' in t:return ['new']
  if re.search(r'initial|original order sheet',t):return ['initial']
 if d=='relation':
  if re.search(r'neither|no obstruction|approach is open',t):return ['clear']
  if re.search(r'my robot.*blocks|robot is in|it is my robot',t):return ['robot_blocks']
  if re.search(r'beam.*across|beam.*spans|beam needs turning',t):return ['beam_blocks']
 return []

def rule(view):
 d=domain_of(view);ws=SPECS[d]['worlds'];posterior={w:1/len(ws) for w in ws};parsed=[]
 messages=sorted(view.get('messages',[]),key=lambda m:m['observation_time_s'])
 if messages:
  m=messages[-1]; matches=extract_fixed(d,m['body']) if isinstance(m['body'],dict) else extract_english(d,m['body']);parsed=matches
  if matches:
   # Explicit bounded-age trust plus confidence. Wrong reports carry no telltale label.
   trust=0.95
   if view['now_s']-m['observation_time_s']>30:trust=0.0
   elif m['confidence']=='low':trust=0.35
   posterior={w:(1-trust)/len(ws)+trust*(w in matches)/len(matches) for w in ws}
 expected={a:sum(posterior[w]*costs(d,view['self_state']['travel_estimates'],w)[a] for w in ws) for a in view['candidates']}
 # Full candidate enumeration is exact for this small stage, stronger than greedy local choice.
 action=min(expected,key=lambda a:(expected[a],a))
 return action,{'posterior':posterior,'estimated_costs':expected,'parsed_worlds':parsed}
