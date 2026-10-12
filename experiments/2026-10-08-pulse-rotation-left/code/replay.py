"""One full recorded-command/RGB replay per mode. GT parsed only by score.py."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from harness.active_wall_recovery import make_mapper
from harness.active_camera import SEARCH
from harness.self_pulse_rotation import OPTION
from scripts.run_active_wall_nav2 import install_profile,dump

EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/active-frontier-audit-v1/new-seed')
OUT=Path('/Users/changmin/projects/ugrp/outputs/pulse-rotation-left-v1')
def load(p):return json.loads(p.read_text())
def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def predict(mode):
    import cv2
    assert all(sha(RAW/p)==h for p,h in load(RAW/'artifacts.sha256.json').items())
    frozen=load(EXP/'freeze.json')
    assert all(sha(ROOT/p)==h for p,h in frozen['files'].items())
    out=OUT/mode
    out.mkdir(parents=True,exist_ok=False)
    bundle=load(RAW/'bundle.json')
    start=load(RAW/'result.json')['start_sim_s']
    actor=make_mapper('r3',start,SEARCH,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',
        seed=bundle['task']['seed'],active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',
        motion_model='off' if mode=='off' else OPTION)
    install_profile(actor.memory.self_map,profile='egomap27_wide')
    frames={r['frame_id']:r for r in rows(RAW/'robots/r3/frames.jsonl')}
    original,contacts=rows(RAW/'own-controller.jsonl'),rows(RAW/'own-contacts.jsonl')
    poses=[]
    assert len(original)==len(contacts)==891
    with (out/'traces.jsonl').open('x') as stream:
        for i,(old,contact) in enumerate(zip(original,contacts)):
            frame=frames[old['frame_id']]
            rgb=cv2.cvtColor(cv2.imread(str(RAW/frame['path'])),cv2.COLOR_BGR2RGB)
            obs={k:v for k,v in contact.items() if k not in ('t','frame_id')}
            _,trace=actor.receive(robot_id='r3',t=old['t'],frame_id=old['frame_id'],rgb=rgb,servo=SEARCH,observation=obs)
            stream.write(json.dumps(trace,allow_nan=False)+'\n')
            g=actor.memory.self_map
            poses.append(dict(robot_id='r3',t=old['t'],frame_id=old['frame_id'],pose=list(g.odom.pose),
                              covariance=g.odom.covariance.tolist()))
            if mode=='off':assert json.dumps(trace)==json.dumps(old),('DEFAULT_TRACE_CHANGED',i)
            if i<len(original)-1:actor.command(old['command'])
            if i%150==0:print(mode,i+1,'frames',len(g.ledger),'insertions',flush=True)
    dump(out/'prediction.json',dict(grid=g.export(),poses=poses,decisions=g.decisions,ledger=g.ledger))
    graph=actor.memory.pose_graph_result
    assert graph['poses'][-1]['t']==poses[-1]['t'],'UNFINISHED_GRAPH'
    dump(out/'graph.json',dict(grid=actor.memory._graph_view.export(),**graph))
    dump(out/'navigation.json',actor.navigator.events)
    if mode=='off':
        assert (out/'traces.jsonl').read_bytes()==(RAW/'own-controller.jsonl').read_bytes()
        assert json.dumps(g.export())==json.dumps(load(RAW/'frontend-grid.json'))
        assert json.dumps(actor.memory._graph_view.export())==json.dumps(load(RAW/'grid.json'))
        dump(out/'golden.json',dict(frames=891,trace_bytes_equal=True,frontend_grid_equal=True,graph_grid_equal=True,
            sha256=sha(out/'traces.jsonl'),original_sha256=sha(RAW/'own-controller.jsonl')))
    dump(out/'seal.json',dict(source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        mode=mode,gt_parsed=False,physical_runs=0,files={p.name:sha(p) for p in out.iterdir() if p.is_file()},
        recorded_commands_only=True,inputs={p:sha(RAW/p) for p in ['own-controller.jsonl','own-contacts.jsonl','robots/r3/frames.jsonl']}))
    assert 'mujoco' not in sys.modules
    print(mode,'SEALED',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['off','on'])
    predict(p.parse_args().mode)
