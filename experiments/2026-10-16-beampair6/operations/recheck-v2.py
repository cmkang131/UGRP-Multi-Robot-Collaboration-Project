"""Run with the existing gcp2 venv; setup-only repeat, no physics."""
import pathlib,json,sys
r=pathlib.Path('/home/ugrp/ugrp-sim');ops=r/'ops-reviews/beampair6';src=r/'src'/sys.argv[1]
sys.path.insert(0,str(src))
from scripts.run_beampair1 import dependency_modules
from scripts.prepare_beampair6 import validity_checker
with dependency_modules(r/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'):
 from sim.grasp_act_search24 import reachability_map
 from sim.grasp_act_search18 import body_clearance
 from sim.grasp_act_search21 import FRESH_MARGIN_M
 from harness.zone_final_environment import resolve
 family=reachability_map(.024);static,_,_=resolve('zone_wide_two_doors_final_v3')
 check=validity_checker(family,body_clearance,FRESH_MARGIN_M,91)
plan=json.loads((src/'experiments/2026-10-16-beampair6/gate-plan.json').read_bytes())
rows=[]
for e in plan['episodes']:
 result=check(e['beam_pose'],static)
 rows.append(dict(seed=e['seed'],result=result,equal_to_frozen=result==e['placement_validity']))
assert all(v['equal_to_frozen'] and v['result']['accepted'] for v in rows)
(ops/'v2-validity-recheck.json').write_text(json.dumps(dict(scope='repeat setup-only exact function; no physics/controller',source=src.name,N=40,accepted_N=40,k=91,family_N=len(family),rows=rows),indent=2)+'\n')
print('v2 exact-source setup recheck40/40')
