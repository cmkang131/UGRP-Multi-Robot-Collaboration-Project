"""One-factor offline SIS ablation: same initial cloud/observations, no resampling.
Only applicable to this zero-base-command scan; no synthetic observation, GT or rejuvenation.
"""
import json,pathlib,numpy as np
from harness.zone_s3_no_prior_contract import hp,old
from harness.zone_solo_cyan_landmarks import MapFeatures,landmark_likelihood
from harness.zone_solo_cyan_amcl_sensor import likelihood
from harness.zone_solo_cyan_likelihood_field import Field
from harness.zone_solo_cyan_best_cluster import extract,connected_labels
B=pathlib.Path(__file__).parent;static=hp.resolve(old.solo.MAP_ID)[0];mapped=MapFeatures(static);field=Field(static);summary={}
for r,folder in [('r1','baseline-r1-v3'),('r2','baseline-r2'),('r3','baseline-r3')]:
 cloud=np.load(B/folder/'clouds.npz');px=cloud['px_0'];w=cloud['w_0'];packets=json.load(open(B/folder/'packets.json'));rows=[];labels=connected_labels(px)
 for q in packets:
  if not (q['wall_points'] or q['features']):continue
  score=likelihood(field,px,q['wall_points'])*landmark_likelihood(mapped,px,q['features']);w*=score;w/=w.sum();est=extract(px,w,labels,{})
  rows.append(dict(t=q['t'],**est,ess=float(1/(w@w))))
 # Every baseline final particle is an exact ancestor of the first cloud.
 # Thus zero own base-command prediction did not move this frozen scan's support.
 original=set(map(tuple,px));ancestry=all(tuple(p) in original for p in cloud['final_px'])
 summary[r]=dict(rows=rows,initial_particles=len(px),baseline_final_exact_ancestry=ancestry,simulation_runs=0,gt_input=False,scope='SIS likelihood replay, resampling removed only; not production candidate or physical result')
 print(r,rows[-1]['x'],rows[-1]['y'],rows[-1]['std_xy_m'],rows[-1]['ess'],ancestry,flush=True)
(B/'importance-replay.json').write_text(json.dumps(summary,indent=2)+'\n')
