"""Shared offline file/geometry helpers; no simulator dependencies."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,importlib.util,json,math,subprocess,sys
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/bottom-connected-contact-v1')
EPISODES={'31001':Path('/Users/changmin/projects/ugrp/outputs/active-frontier-audit-v1/new-seed'),
          '32002':Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')}
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
from harness.self_odom_grid import transform
from harness.active_wall_vision import modules
from harness.active_camera import transform as camera_transform
from harness.self_wall_segment_points import contact_points
import odom_grid_replay as metric

def load(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):
    p.parent.mkdir(exist_ok=True,parents=True)
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def head():return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
def rgb(ep,frame):
    p=ep/frame['path'];assert sha(p)==frame['sha256']
    return cv2.cvtColor(cv2.imread(str(p)),cv2.COLOR_BGR2RGB)
def uv_of(points,servo):
    origin,rotation=camera_transform(servo)
    optical=(np.c_[np.asarray(points).reshape(-1,2),np.zeros(len(points))]-origin)@rotation
    project=optical@modules()[0].K.T
    return project[:,:2]/project[:,2,None]
def first_box(origin,rays,lower,upper):
    with np.errstate(divide='ignore',invalid='ignore'):
        a=(np.asarray(lower)-origin)/rays;b=(np.asarray(upper)-origin)/rays
    entry=np.maximum(np.minimum(a,b).max(-1),0.)
    exit=np.maximum(a,b).min(-1)
    return np.where((exit>=entry)&(exit>0),entry,np.inf)

OLD_RAW=Path('/Users/changmin/projects/ugrp/outputs/wall-contact-types-v1')
