"""Saved own RGB input-contract smoke test; neither physics nor quality evidence."""
import json,hashlib,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from harness.active_wall_mapping import ActiveMapper
from harness.active_wall_vision import observe
from scripts.run_active_wall_map import dump
raw=Path('/Users/changmin/projects/ugrp/outputs/servo-stiffness-v1/stiff-explore')
frame=json.loads((raw/'robots/r3/frames.jsonl').read_text().splitlines()[50])
rgb=np.asarray(Image.open(raw/frame['path']).convert('RGB'))
servo={int(k):v for k,v in frame['commanded_servo'].items()}
actor=ActiveMapper('r3',0,servo,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1')
rows=[]
for k,t in enumerate((2.,4.,12.,22.)):
    detection=observe(rgb,servo)
    cmd,trace=actor.receive(robot_id='r3',frame_id=k,t=t,rgb=rgb,servo=servo,observation=detection)
    json.dumps(trace,allow_nan=False)
    rows.append(dict(t=t,status=trace['status'],segments=trace['wall_segments'],map_cells=trace['map_cells'],command=cmd))
    print(rows[-1],flush=True)
assert 'mujoco' not in sys.modules
report=dict(qualification='same saved SEARCH image repeated for API smoke only, no navigation/quality claim',
    frame_sha=hashlib.sha256((raw/frame['path']).read_bytes()).hexdigest(),rows=rows,
    graph_calls=len(actor.graphs),information_calls=len(actor.events))
dump(ROOT/'experiments/2026-10-07-active-wall-map/offline-acceptance.json',report)
