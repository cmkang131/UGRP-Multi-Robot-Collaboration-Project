import json,pathlib,hashlib,csv,collections,subprocess
ops=pathlib.Path('/home/ugrp/ugrp-sim/ops-reviews/beampair4-gcp2');base=ops/'baseline-analysis';out=ops/'baseline-summary';out.mkdir(exist_ok=False)
table=json.loads((base/'rejection-table.json').read_text())
summary={k:v for k,v in table.items() if k!='runs'}
summary['runs']=[{k:v for k,v in r.items() if k not in ('events','candidates')} for r in table['runs']]
summary['raw_table']=str(base/'rejection-table.json');summary['raw_table_sha256']=hashlib.sha256((base/'rejection-table.json').read_bytes()).hexdigest()
summary['separate_host_cohort']=True
for seed in (8318620,8318626):
 rows=json.loads((base/f'{seed}-timeline.json').read_text())
 selected=[r for r in rows if abs(r['elapsed_sim_s']-round(r['elapsed_sim_s']))<1e-6 or r is rows[-1]]
 keys=['seed','robot','elapsed_sim_s','phase','assigned_end','observed_band','observed_distance_m','wheels','command_world_dx_m','command_world_dy_m','actual_world_dx_m','actual_world_dy_m','command_actual_cosine','evaluator_pose','eval_saved_qpos_contacts','evaluator_peer_distance_m','evaluator_beam_xy']
 with (out/f'{seed}-one-second-timeline.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in selected)
 candidates=json.loads((base/f'{seed}-candidates.json').read_text());counts=collections.Counter(c['reason'] for c in candidates)
 blocker_counts=collections.Counter();gaps=collections.defaultdict(list)
 for c in candidates:
  for b in c['blockers']:
   k=(c['reason'],b.get('id',b.get('object')),b.get('category'));blocker_counts[k]+=1;gaps[k].append(b.get('gap_m'))
 summary.setdefault('failure_candidates',{})[seed]=dict(candidate_N=len(candidates),first_rejection_distribution=dict(counts),blocker_occurrences=[dict(reason=k[0],object=k[1],category=k[2],N=n,min_gap_m=min([v for v in gaps[k] if v is not None],default=None),max_gap_m=max([v for v in gaps[k] if v is not None],default=None)) for k,n in blocker_counts.most_common()],scope='blocker occurrences overlap; first rejection counts do not')
(out/'rejection-table.json').write_text(json.dumps(summary,indent=2)+'\n')
for seed in (8318620,8318626,8318604):
 root=pathlib.Path('/home/ugrp/ugrp-sim/runs')/f'beampair3-gcp2-repro-{seed}-e645b34b'
 (out/f'{seed}-host-portability.json').write_bytes((root/'host-portability.json').read_bytes())
manifest={p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in out.iterdir()}
(out/'retrieval-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
