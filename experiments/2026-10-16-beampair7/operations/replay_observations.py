"""Offline GCP raw replay: allowed observations/commands only build model; truth audits separately."""
import json, math, subprocess, sys
from pathlib import Path
from collections import Counter
base=Path('/home/ugrp/ugrp-sim')
sys.path.insert(0,str(base/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'))
from harness.grasp_act_visible_world import VisibleWorld
from sim.grasp_act_visible_route import constraints, free

def read(p, lines=False):
    data=p.read_bytes() if p.exists() else subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])
    return [json.loads(x) for x in data.splitlines()] if lines else json.loads(data)
raw=base/'runs/gv5-beampair-gate-baseline-8318711-0b5faa4c/raw'
plan=read(raw/'plan.json');rows=read(raw/'eval-only.jsonl',True)
cmds={r:read(raw/f'teacher-{r}.jsonl',True) for r in plan['roles']}
models={r:VisibleWorld(r,end,pose_source='issued',odometry='search17_fixed_v1',search22='search22_v1',search23='search23_v1') for r,end in plan['roles'].items()}
log=[]
for i,row in enumerate(rows):
    for rid,model in models.items():
        w=model.observe(row['visible_measurements'][rid],row['t']);peer='r2' if rid=='r1' else 'r1'
        item=dict(sim_s=round(i/10,2),robot=rid,phase=cmds[rid][i]['teacher_phase'],fresh_peers=w['visibility'][rid]['peers'],visible_band_n=w['visibility'][rid]['visible_probes'],peer_in_model=peer in w['robots'],pose=w['robots'][rid]['pose'],own_issued_wheels=cmds[rid][i]['applied_command']['wheels'])
        if peer in w['robots']:
            item.update(peer_age_s=row['t']-model.memory[peer]['seen_t'],model_distance_m=math.dist(w['robots'][rid]['pose'][:2],w['robots'][peer]['pose'][:2]))
        if w['beam']:
            g=w['beam']['ends'][model.end];a=w['beam']['pose'][2]+(math.pi if model.end=='blue' else 0.)
            goal=(g[0]-.203*math.cos(a),g[1]-.203*math.sin(a))
            radius,discs,rects=constraints(w,rid,True)
            item['goal_free']=free(goal,discs,rects,radius)
        item['evaluation_only_distance_m']=math.dist(row['robots'][rid]['pose'][:2],row['robots'][peer]['pose'][:2])
        log.append(item);model.issue(cmds[rid][i]['applied_command'])
summary={}
for rid in models:
    ls=[x for x in log if x['robot']==rid]
    fresh=[x['sim_s'] for x in ls if ('r2' if rid=='r1' else 'r1') in x['fresh_peers']]
    summary[rid]=dict(last_fresh_peer_sim_s=fresh[-1],fresh_peer_N=len(fresh),last_model_peer_sim_s=max(x['sim_s'] for x in ls if x['peer_in_model']),snapshots=[x for x in ls if x['sim_s'] in (6,10,11,12,13,14,15,16,17,18,20,30,40,50,59)])
out=base/'ops-reviews/beampair7';out.mkdir(exist_ok=True)
(out/'allowed-world-replay.json').write_text(json.dumps(dict(summary=summary,rows=log),indent=2))
print(json.dumps(summary,indent=2))
