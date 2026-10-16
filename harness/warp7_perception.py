"""Default-off MJWarp paint calibration: own RGB only, no world/label reader.

Bounds are saved p01/p99 HSV interior distributions, outward-rounded to the
existing OpenCV integer bins. They are a DEV fit, not a new success tolerance.
All floor-ray, component area, support, range, extent and place gates remain.
"""
import ast,hashlib,inspect,json,os,textwrap
from functools import lru_cache
from pathlib import Path
import cv2
import numpy as np

ENV='UGRP_WARP7_PERCEPTION'


def enabled():
    value=os.environ.get(ENV,'off')
    if value not in ('off','rendered_hsv_v1'):raise ValueError('UNKNOWN_WARP7_PERCEPTION')
    return value!='off'


@lru_cache(maxsize=4)
def load(path,sha):
    data=Path(path).read_bytes()
    if not sha or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('WARP7_CALIBRATION_HASH_MISMATCH')
    c=json.loads(data)
    if c['profile']!='warp7_rendered_hsv_v1':raise ValueError('WARP7_CALIBRATION_PROFILE_REQUIRED')
    return c


def paint_mask(bgr,zone,*,candidate=None):
    if not enabled():raise ValueError('WARP7_EXPLICIT_OPT_IN_REQUIRED')
    c=load(os.environ['UGRP_WARP7_CALIBRATION'],os.environ['UGRP_WARP7_CALIBRATION_SHA256'])
    # Calibration contains RGB class bounds only. No frame mask, pose, cargo
    # identity or evaluator decision is loaded by this runtime capability.
    bounds=c['paint'][zone];hsv=cv2.cvtColor(bgr,cv2.COLOR_BGR2HSV)
    if candidate is None:
        from harness.zone_own_perception import PAINT_HUE
        lo,hi=PAINT_HUE[zone]
        # Exact existing destination candidate mask. The calibration classifies
        # its connected regions, retaining their original boundary/support.
        candidate=((hsv[...,0]>=lo-5)&(hsv[...,0]<=hi+5)&(hsv[...,1]>=30)&(hsv[...,2]>=30))
    n,labels=cv2.connectedComponents(np.asarray(candidate,np.uint8),8)
    result=np.zeros(candidate.shape,bool)
    for i in range(1,n):
        region=labels==i;median=np.median(hsv[region],axis=0)
        if np.all(median>=bounds['low']) and np.all(median<=bounds['high']):result|=region
    return result


def clone(function,transform,namespace):
    tree=ast.parse(textwrap.dedent(inspect.getsource(function)));edits=transform(tree)
    if not edits:raise ValueError('WARP7_FROZEN_DETECTOR_SHAPE_CHANGED')
    scope=dict(function.__globals__,**namespace)
    exec(compile(ast.fix_missing_locations(tree),'<warp7-rgb-only-paint>','exec'),scope)
    result=scope[function.__name__];result._warp7_original=function
    return result


def install():
    if not enabled():return
    from harness import floor_goal
    from sim import destination_visual_acquire as destination,solo_carry_to_zone as carry
    def replace_assignment(tree,name,source):
        edits=0
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
                node.value=ast.parse(source,mode='eval').body;edits+=1;break
        if edits!=1:raise ValueError('WARP7_UNEXPECTED_ASSIGNMENT_COUNT:'+name)
        return edits
    def floor(tree):
        replace_assignment(tree,'mask',"__paint__(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),'B',candidate=(hue & (s>=opt.saturation_min) & (v>=opt.value_min))).astype(np.uint8)")
        fn=tree.body[0]
        # Static paint_B r1: 23905 labelled, HSV23905, valid rays23905,
        # fixed lower35% crop0. Remove only that image rectangle; retain the
        # existing downward/range floor-ray validity (standard ray-plane test).
        removed=[n for n in fn.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Subscript) and isinstance(t.value,ast.Name) and t.value.id=='mask' and isinstance(t.slice,ast.Slice) for t in n.targets)]
        if len(removed)!=1:raise ValueError('WARP7_FIXED_ROI_SHAPE_CHANGED')
        fn.body.remove(removed[0]);return 2
    previous=floor_goal.detect_floor
    original=getattr(previous,'_warp7_original',previous)
    floor_goal.detect_floor=clone(original,floor,{'__paint__':paint_mask})
    for obj in vars(floor_goal).values():
        if isinstance(obj,type) and getattr(obj,'detector',None) in (original,previous):
            obj.detector=staticmethod(floor_goal.detect_floor)
    original=getattr(destination.floor_patch,'_warp7_original',destination.floor_patch)
    destination.floor_patch=clone(original,lambda t:replace_assignment(t,'mask','__paint__(bgr,zone) & _usable_region(w,h)'),{'__paint__':paint_mask})
    original=getattr(carry.CarryToZone.place_visible,'_warp7_original',carry.CarryToZone.place_visible)
    carry.CarryToZone.place_visible=clone(original,lambda t:replace_assignment(t,'painted','__paint__(bgr,self.zone)[roi]'),{'__paint__':paint_mask})
