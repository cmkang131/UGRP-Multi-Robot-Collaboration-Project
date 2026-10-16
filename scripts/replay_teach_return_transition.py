"""egomap54: replay the retained own-input handoff, without physics or GT.

Cached observation packets reproduce the completed suffix exactly. The crashed
last frame has only its retained JPEG, so that one observation is recomputed.
The actual controller factory, AMCL, CSM and command adapter run unmocked;
only sensor reads of already-recorded packets are supplied from their ledger.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import argparse,copy,hashlib,json
import cv2
import numpy as np
from harness import self_map_closed_loop as control
from harness.own_teach_capture import TeachGraph
from harness.active_camera import SEARCH
from harness.active_wall_vision import observe
from scripts.run_teach_capture import make_controller


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def encode(v):return json.dumps(v,sort_keys=True)


def restore_graph(saved):
    g=TeachGraph(saved['robot_id'])
    for name in ('nodes','edges','breaks','goal','goal_node','frames','capture_events'):
        setattr(g,name,copy.deepcopy(saved[name]))
    g.anchor=saved['last_node'];g.sealed=saved['sealed']
    g.pinned_candidates={(r['candidate_id'],r['first_t']):r['node'] for r in saved['pinned_B_candidates']}
    assert g.sealed and all(q['t']<=n['t'] for n in g.nodes for q in n['patch_sources'])
    return g


def replay(ep,out):
    assert not out.exists(),'PRESERVE_EXISTING_REPLAY'
    manifest=json.loads((ep/'artifacts.sha256.json').read_text());used={}
    def read(name,lines=False):
        p=ep/name;assert sha(p)==manifest[name],name
        used[name]=manifest[name]
        return [json.loads(l) for l in p.read_text().splitlines()] if lines else json.loads(p.read_text())
    graph=read('teach-graph.json');snapshot=read('snapshot.json')
    trace=read('own-controller.jsonl',True);frames=read('robots/r3/frames.jsonl',True)
    inputs={r['frame_id']:r for r in read('own-inputs.json')}
    contacts={r['frame_id']:r for r in read('own-contacts.jsonl',True)}
    recorded={r['frame_id']:r for r in trace}
    c=make_controller(SimpleNamespace(robot_id='r3',started=frames[0]['sim_time']),seed=49002)
    c.traversal_graph=restore_graph(graph)
    c.last_snapshot=copy.deepcopy(snapshot)
    c.measurements=read('prefix-measurements.json');c.poses=read('prefix-poses.json')
    c.goal=read('remembered-goal.json')
    planned=c.traversal_graph.route(c.traversal_graph.anchor)
    assert planned is not None,'B_ROUTE_REQUIRED'
    loss=snapshot['loss_t'];assert all(n['t']<loss for n in graph['nodes'])
    outputs=[];equal=0;recomputed=[]
    for f in frames:
        if f['sim_time']<loss:continue
        p=ep/f['path'];assert sha(p)==f['sha256'];used[f['path']]=f['sha256']
        rgb=cv2.cvtColor(cv2.imread(str(p)),cv2.COLOR_BGR2RGB)
        i=f['frame_id'];t=f['sim_time'];packet=inputs.get(i)
        observation=contacts.get(i)
        if observation is None:observation=observe(rgb,SEARCH,body_settling=.7)
        kw=dict(robot_id='r3',t=t,frame_id=i,rgb=rgb,servo=SEARCH,
            observation=observation,frame_sha256=f['sha256'])
        if packet:
            with patch.object(control,'own_measurement',return_value=dict(points=packet['points'],columns=[],uv=[])), \
                 patch.object(c.sensor,'measure',return_value=packet['features']):
                cmd,row=c.receive(**kw)
        else:
            cmd,row=c.receive(**kw)
            if t>loss:recomputed.append(i)
        if i in recorded:
            old=recorded[i]
            assert encode(cmd)==encode(old['command']),('COMMAND_DIVERGENCE',i)
            if 'belief' in old:
                assert encode(row['belief'])==encode(old['belief']),('BELIEF_DIVERGENCE',i)
            equal+=1
        c.command(cmd)
        outputs.append(row)
        print('handoff',i,round(t,1),row['stage'],row['status'],flush=True)
    entered=[r for r in outputs if r['stage']=='return' or r['stage']=='declared']
    assert entered and c.traversal.match_events,'REPEAT_MATCHER_NOT_ENTERED'
    assert c.snapshot['t']<loss
    dump(out/'trace.json',outputs)
    result=dict(passed=True,errors=0,source_recording=str(ep),seed=49002,loss_t=loss,
        replayed_frames=len(outputs),exact_recorded_commands_and_beliefs=equal,
        recomputed_jpeg_frames=recomputed,planned_route_nodes=len(planned['nodes']),
        graph_B_connected=True,repeat_entered=True,first_match=entered[0]['teach']['match'],
        selected_route_nodes=None if c.traversal.route is None else len(c.traversal.route['nodes']),
        final_command=outputs[-1]['command'],input_hashes=used,gt_inputs=0,physics=0,
        qualification='Integration gate only; matching rejection is not an exception; no arrival claim.')
    dump(out/'result.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=replay(a.input,a.output)
    print(json.dumps({k:r[k] for k in ('passed','errors','replayed_frames','repeat_entered','selected_route_nodes')}))
