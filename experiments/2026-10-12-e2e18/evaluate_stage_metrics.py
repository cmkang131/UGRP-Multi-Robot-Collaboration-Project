from pathlib import Path
import json,subprocess,hashlib,sys
root=Path.home()/'ugrp-sim/runs'
def data(p):return p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-dc',str(p)+'.zst'])
def lines(p):return [json.loads(l) for l in data(p).splitlines() if l]
for run in sorted(root.glob(sys.argv[1])):
 if not (run/'EXIT').exists():continue
 raw=run/'raw'
 if not (raw/'result.json').exists():continue
 result=json.loads((raw/'result.json').read_text());robots={}
 for rid in ('r1','r2'):
  p=raw/f'eval_only/{rid}/trajectory.jsonl';b=data(p);a=[json.loads(l) for l in b.splitlines()]
  robots[rid]=dict(max_tilt_deg=max(x['tilt_deg'] for x in a),sim_s=a[-1]['t'],sha256_uncompressed=hashlib.sha256(b).hexdigest(),raw=str(p))
 supports=lines(raw/'eval_only/setdown.jsonl');held=[x['t'] for x in supports if x['cargo_z_m']>.06 and all(len(x['fingers'].get(r,[]))==2 and all(x['fingers'][r]) for r in ['r1','r2'])]
 events=json.loads(data(raw/'transport-trace.json'))
 fine=[e for e in events if e.get('event')=='s3_coarse_fine'];ready=[e for e in fine if e.get('phase')=='ready']
 phases=[e for e in events if e.get('event')=='phase']
 first={}
 for e in phases:first.setdefault(e.get('state'),e['t'])
 synced=[e for e in events if e.get('event')=='s3_synchronized_segment']
 alignment=first.get('align');held_t=held[0] if held else None
 metrics=dict(first_phase_sim_s=first,first_paired_held_sim_s=held_t,
     align_to_grasp_lift_sim_s=first['grasp_lift']-alignment if alignment is not None and 'grasp_lift' in first else None,
     align_to_actual_paired_held_sim_s=held_t-alignment if alignment is not None and held_t is not None else None,
     post_grasp_carry_go_ack_pass=bool(held_t is not None and any(e['t']>=held_t for e in synced)),
     first_sync_segment=next((e for e in synced if held_t is not None and e['t']>=held_t),None),
     trace_sha256_uncompressed=hashlib.sha256(data(raw/'transport-trace.json')).hexdigest())
 print(json.dumps(dict(metrics=metrics,name=run.name,status=result.get('status'),failure=result.get('failure'),robots=robots,paired_held_samples=len(held),first_held_t=held[0] if held else None,maximum_cargo_z_m=max(x['cargo_z_m'] for x in supports),ready=ready,first_fine=fine[0] if fine else None)),flush=True)
