from analyze import *
from concurrent.futures import ProcessPoolExecutor

def one(task):
 a,s=task;r=B/f'ops-reviews/beamact3/{a}/heldout20-v1/seed-{s}';ev=rows(r/'eval-only.jsonl');prot=js(r/'start-protocol.json');plan=js(r/'plan.json');origin=ev[0]['t'];go=next((x['t'] for x in prot['events'] if x['event']=='GO'),None)
 out=dict(arm=a,seed=s,GO_sim_s=go-origin if go is not None else None,robots={},both_aligned_at_GO=False)
 if go is not None:
  e=min(ev,key=lambda x:abs(x['t']-go));align=[]
  for rid,role in plan['roles'].items():
   g=geom(e['truth'],rid);j=0 if role=='teal' else 3;aligned=g[j+1]<=.03 and g[j+2]<=.06;align.append(aligned)
   out['robots'][rid]=dict(assigned_end=role,station_error_m=g[j+1],yaw_error_rad=g[j+2],aligned=aligned)
  out['both_aligned_at_GO']=all(align)
 return out
with ProcessPoolExecutor(max_workers=8) as p:runs=list(p.map(one,[(a,s) for a in ('A','B') for s in CFG['heldout_seeds']]))
out=dict(runs=runs,arms={a:dict(GO_N=sum(x['GO_sim_s'] is not None for x in runs if x['arm']==a),GO_before_joint_alignment_N=sum(not x['both_aligned_at_GO'] for x in runs if x['arm']==a)) for a in ('A','B')})
write(O/'protocol-audit.json',out);print(json.dumps(out,indent=2))
