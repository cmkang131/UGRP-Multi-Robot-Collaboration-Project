"""Same v7 certified setup distribution in five40-seed blocks; no simulation."""
import json
from pathlib import Path
from scripts.prepare_beampair6 import generate, MODE
from harness.beampair_recording import SCENE
from harness.grasp_act_data import write_json

ROOT=Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/beampair8'
DEPENDENCY=ROOT/'src/26f84d0f0ada1c33473c83cca2d3415ce51bd247'


def main():
    seeds=set(range(8328000,8328200))|set(range(8329000,8329020))
    # All current managed run names and existing beam gate allocations.
    for p in (ROOT/'runs').iterdir():
        assert not any(str(s) in p.name for s in seeds), 'fresh seed already has a managed run'
    old=json.loads((ROOT/'ops-reviews/beampair7/gate-plan.json').read_text())
    assert not {e['seed'] for e in old['episodes']}&seeds
    train=[];tables=[]
    for block in range(5):
        out=OPS/f'setup-block-{block}';generate(8328000+40*block,out,DEPENDENCY,MODE)
        plan=json.loads((out/'gate-plan.json').read_text());tables.append(str(out/'setup-funnel.json'))
        for e in plan['episodes']:
            e.update(episode_id=f"beampair8-train-{e['seed']}",batch='beampair8-train200',split='train',scene_profile=SCENE)
            train.append(e)
    out=OPS/'setup-heldout';generate(8329000,out,DEPENDENCY,MODE)
    held=json.loads((out/'gate-plan.json').read_text())['episodes'][:20]
    for e in held:e.update(episode_id=f"beampair8-heldout-{e['seed']}",batch='beampair8-heldout20',split='evaluation_reserved_only',scene_profile=SCENE)
    write_json(OPS/'train-plan.json',dict(episodes=train,distribution='unchanged prepare_beampair6 v7 certified; 5 blocks40, original strata reset per block',source_tables=tables))
    write_json(OPS/'heldout-plan.json',dict(episodes=held,recorded=False,evaluation_only=True,source_table=str(out/'setup-funnel.json')))
    write_json(OPS/'seed-reservation.json',dict(task='beampair8',train=[8328000,8328199],heldout=[8329000,8329019],gate_overlap=0,live_run_name_overlap=0))
    print(json.dumps(dict(train_N=len(train),heldout_N=len(held),heldout_recorded_N=0)))


if __name__=='__main__':main()
